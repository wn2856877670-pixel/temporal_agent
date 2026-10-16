"""Temporary fixtures only. Real Nginx HTTP checks run when nginx is installed."""
import http.client
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('BASH_BINARY') or shutil.which('bash')
NGINX = os.environ.get('NGINX_BINARY') or shutil.which('nginx')


def shell_path(path):
    text = Path(path).absolute().as_posix()
    if os.name == 'nt':
        return '/' + text[0].lower() + text[2:]
    return text


@unittest.skipUnless(BASH, 'Bash is not installed')
class RedisDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='deer-redis-isolation-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / 'media'
        self.data = self.root / 'redis'
        self.bin = self.root / 'bin'
        self.media.mkdir()
        self.bin.mkdir()
        self.env = {**os.environ, 'DEER_MEDIA_ROOT': shell_path(self.media),
                    'REDIS_DATA_DIR': shell_path(self.data), 'REDIS_PASSWORD': 'test-only',
                    'MOCK_ROOT': shell_path(self.root), 'MOCK_RUNNING_DIR': shell_path(self.data)}
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.env['REDIS_PORT'] = str(self.listener.getsockname()[1])
        self.addCleanup(self.listener.close)
        scripts = {
            'redis-cli': '''#!/usr/bin/env bash
if [[ "$*" == *"CONFIG GET dir" ]]; then
  printf 'dir\\n%s\\n' "$MOCK_RUNNING_DIR"
elif [[ "${MOCK_REPLY:-}" == PONG || -f "$MOCK_ROOT/started" ]]; then
  printf 'PONG\\n'
elif [[ -n "${MOCK_REPLY:-}" ]]; then
  printf '%s\\n' "$MOCK_REPLY"
else
  exit 1
fi
''',
            'redis-server': '''#!/usr/bin/env bash
printf '%s\\n' "$@" > "$MOCK_ROOT/start-args"
touch "$MOCK_ROOT/started"
''',
        }
        if os.name == 'nt':
            # Git Bash cannot apply POSIX mode 700 to Windows temporary folders.
            scripts['install'] = '''#!/usr/bin/env bash
printf '%s\\n' "$@" > "$MOCK_ROOT/install-args"
mkdir -p -- "${@: -1}"
'''
        for name, contents in scripts.items():
            path = self.bin / name
            path.write_text(contents, encoding='utf-8', newline='\n')
            path.chmod(0o755)

    def run_initializer(self, **extra):
        env = {**self.env, **extra}
        script = 'export PATH="$MOCK_BIN:$PATH"; source "$HELPER"; ensure_business_redis'
        env.update(MOCK_BIN=shell_path(self.bin), HELPER=shell_path(ROOT / 'scripts/business_redis.sh'))
        return subprocess.run([BASH, '--noprofile', '--norc', '-c', script], env=env,
                              cwd=self.root, text=True, encoding='utf-8', errors='replace',
                              capture_output=True, timeout=15)

    def assert_refused(self, **extra):
        result = self.run_initializer(**extra)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / 'start-args').exists())
        return result

    def test_fresh_start_uses_separate_directory(self):
        result = self.run_initializer()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = (self.root / 'start-args').read_text().splitlines()
        self.assertEqual(args[args.index('--dir') + 1], shell_path(self.data))
        self.assertEqual(args[args.index('--port') + 1], self.env['REDIS_PORT'])
        self.assertTrue(self.data.is_dir())
        self.assertEqual(list(self.media.iterdir()), [])
        if os.name == 'nt':
            self.assertIn('700', (self.root / 'install-args').read_text().splitlines())
        else:
            self.assertEqual(self.data.stat().st_mode & 0o777, 0o700)

    def test_nested_equal_and_root_directories_are_refused(self):
        for target in (self.media, self.media / 'redis', self.root):
            with self.subTest(target=target):
                self.assert_refused(REDIS_DATA_DIR=shell_path(target))
        self.assert_refused(REDIS_DATA_DIR='/')

    def test_symlink_into_media_is_refused(self):
        link = self.root / 'linked-redis'
        try:
            link.symlink_to(self.media, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is not permitted on this host')
        self.assert_refused(REDIS_DATA_DIR=shell_path(link))

    def test_legacy_data_is_not_moved_or_replaced(self):
        for name in ('dump.rdb', 'appendonly.aof', 'appendonlydir'):
            with self.subTest(name=name):
                legacy_dir = self.media / ('case-' + name)
                legacy_dir.mkdir()
                path = legacy_dir / name
                if name == 'appendonlydir':
                    path.mkdir()
                    path = path / 'appendonly.aof.manifest'
                path.write_bytes(b'original Redis data')
                self.assert_refused(DEER_MEDIA_ROOT=shell_path(legacy_dir))
                self.assertEqual(path.read_bytes(), b'original Redis data')
                self.assertFalse(self.data.exists())

    def test_existing_matching_instance_is_reused(self):
        result = self.run_initializer(MOCK_REPLY='PONG')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'start-args').exists())

    def test_existing_legacy_or_unknown_instance_is_not_reconfigured(self):
        self.assert_refused(MOCK_REPLY='PONG', MOCK_RUNNING_DIR=shell_path(self.media))

    def test_occupied_port_with_bad_auth_never_starts_another_instance(self):
        self.listener.listen()
        self.assert_refused(MOCK_REPLY='WRONGPASS invalid username-password pair')

    def test_existing_separate_data_is_preserved(self):
        self.data.mkdir()
        snapshot = self.data / 'dump.rdb'
        snapshot.write_bytes(b'existing snapshot')
        result = self.run_initializer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot.read_bytes(), b'existing snapshot')


class MediaAllowlistTests(unittest.TestCase):
    def test_only_result_video_paths_are_allowlisted(self):
        config = (ROOT / 'deploy/nginx_business.conf').read_text(encoding='utf-8')
        pattern = re.search(r'location ~ "([^"]+)"', config).group(1)
        pattern = pattern.replace('(?<result_video>', '(?P<result_video>')
        for path in ('task/attempt/videos/result_browser.mp4',
                     'task/attempt/events/event_00000054_0001_1.80s_browser.webm'):
            self.assertIsNotNone(re.fullmatch(pattern, '/media/business/results/' + path))
        for path in ('/media/business/dump.rdb', '/media/business/appendonly.aof',
                     '/media/business/appendonlydir/appendonly.aof.manifest',
                     '/media/business/uploads/task/input.mp4',
                     '/media/business/results/task/events/event.json',
                     '/media/business/results/task/.private/secret.mp4',
                     '/media/business/results/task/../../dump.mp4',
                     '/media/business/results/task/videos/result_browser.mp4.part',
                     '/media/business/results/'):
            with self.subTest(path=path):
                self.assertIsNone(re.fullmatch(pattern, path))
        self.assertIn('location /media/ { return 404; }', config)
        self.assertIn('disable_symlinks on;', config)


@unittest.skipUnless(NGINX and os.name != 'nt', 'Linux Nginx is not installed')
class NginxHttpTests(unittest.TestCase):
    def test_video_range_and_private_file_denial(self):
        with tempfile.TemporaryDirectory(prefix='deer-nginx-isolation-') as directory:
            root = Path(directory)
            media = root / 'media'
            public = media / 'results/task/attempt/videos'
            public.mkdir(parents=True)
            video = (ROOT / 'frontend/tests/playback.webm').read_bytes()
            (public / 'result_browser.webm').write_bytes(video)
            (public / 'private.json').write_bytes(b'private metadata')
            (media / 'dump.rdb').write_bytes(b'private redis snapshot')
            upload = media / 'uploads/task'
            upload.mkdir(parents=True)
            (upload / 'input.mp4').write_bytes(b'private upload')
            (public / 'linked.mp4').symlink_to(media / 'dump.rdb')
            (root / 'static').mkdir()
            (root / 'static/index.html').write_text('SPA sentinel')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            config = (ROOT / 'deploy/nginx_business.conf').read_text()
            config = config.replace('/root/autodl-tmp/deer_behavior_clean/logs/', root.as_posix() + '/')
            config = config.replace('include /etc/nginx/mime.types;', 'types { video/webm webm; video/mp4 mp4; }')
            config = config.replace('listen 6010;', f'listen 127.0.0.1:{port};')
            config = config.replace('/var/www/deer-business', (root / 'static').as_posix())
            config = config.replace('/var/lib/deer-business/', media.as_posix() + '/')
            config = config.replace('sendfile on;', 'sendfile on; access_log off;')
            if os.geteuid() == 0:
                config = 'user root;\n' + config
            path = root / 'nginx.conf'
            path.write_text(config)
            subprocess.run([NGINX, '-t', '-p', directory + '/', '-c', str(path)], check=True,
                           capture_output=True, timeout=10)
            process = subprocess.Popen([NGINX, '-p', directory + '/', '-c', str(path), '-g', 'daemon off;'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                            break
                    except OSError:
                        if process.poll() is not None:
                            self.fail((root / 'nginx_business_error.log').read_text())
                        time.sleep(0.05)

                def request(url, method='GET', headers=None):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                    try:
                        connection.request(method, url, headers=headers or {})
                        response = connection.getresponse()
                        return response.status, dict(response.getheaders()), response.read()
                    finally:
                        connection.close()

                url = '/media/business/results/task/attempt/videos/result_browser.webm'
                self.assertEqual(request(url + '?v=test')[2], video)
                self.assertEqual(request(url, 'HEAD')[0], 200)
                status, headers, body = request(url, headers={'Range': 'bytes=0-1023'})
                self.assertEqual(status, 206)
                self.assertEqual(body, video[:1024])
                self.assertEqual(headers['Content-Range'], f'bytes 0-1023/{len(video)}')
                for blocked in ('dump.rdb', 'appendonly.aof', 'appendonlydir/appendonly.aof.manifest',
                                'uploads/task/input.mp4', 'results/task/attempt/videos/private.json',
                                'results/task/attempt/videos/missing.mp4', 'results/task/attempt/videos/',
                                'results/task/attempt/videos/%2e%2e/%2e%2e/%2e%2e/%2e%2e/dump.rdb'):
                    with self.subTest(blocked=blocked):
                        self.assertEqual(request('/media/business/' + blocked)[0], 404)
                self.assertIn(request('/media/business/results/task/attempt/videos/linked.mp4')[0], (403, 404))
                self.assertEqual(request(url, 'POST')[0], 403)
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
