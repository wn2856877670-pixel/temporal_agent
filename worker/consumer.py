"""Manual-ack worker with fenced leases, supervised inference and broker heartbeats."""
import json
import logging
import multiprocessing as mp
import os
import queue
import signal
import time
import uuid
from pathlib import Path

import pika
import requests
from pipeline_adapter import execute, test_execute

LOG = logging.getLogger('deer.worker')


class Worker:
    def __init__(self, test_mode=False):
        self.base = os.environ.get('INTERNAL_API_URL', 'http://127.0.0.1:6020').rstrip('/')
        self.session = requests.Session()
        self.session.headers['X-Internal-Token'] = os.environ['INTERNAL_API_TOKEN']
        self.owner = str(uuid.uuid4())
        self.root = Path(os.environ.get('DEER_MEDIA_ROOT', '/var/lib/deer-business')).resolve()
        self.test_mode = test_mode
        self.connection = None

    def request(self, method, task, endpoint, body, token=None):
        headers = {'X-Lease-Token': token} if token else {}
        response = self.session.request(method, f'{self.base}/api/internal/tasks/{task}/{endpoint}',
                                        json=body, headers=headers, timeout=(5, 15))
        response.raise_for_status()
        return response.json() if response.content else None

    def process(self, channel, method, properties, body):
        task = token = None
        child = None
        updates = result = None
        try:
            message = json.loads(body)
            task = str(uuid.UUID(message['taskId']))
            claim = self.request('POST', task, 'claim', {'owner': self.owner})
            if claim.get('alreadyCompleted'):
                channel.basic_ack(method.delivery_tag)
                LOG.info('ACK already completed %s', task)
                return
            if not claim.get('claimed'):
                # Busy duplicate goes through delayed retry; failed tasks go to DLQ.
                channel.basic_nack(method.delivery_tag, requeue=False)
                return
            token = claim['leaseToken']
            video = Path(claim['videoPath']).resolve()
            if not video.is_relative_to(self.root / 'uploads') or not video.is_file():
                raise ValueError('Claimed input missing or outside upload root')
            # Trust the server's canonical path, not an arbitrary path in the MQ payload.
            output = self.root / 'results' / task / token / 'videos' / 'result.mp4'
            output.parent.mkdir(parents=True, exist_ok=True)
            ctx = mp.get_context('spawn')
            updates, result = ctx.Queue(), ctx.Queue()
            child = ctx.Process(target=test_execute if self.test_mode else execute,
                                args=(str(video), str(output), task, updates, result))
            child.start()
            progress = dict(progress=0, stage='STARTING', processedFrames=0, totalFrames=0)
            reviewed = claim.get('status') == 'REVIEWING'
            last_heartbeat = 0
            payload = None
            while payload is None:
                self.connection.process_data_events(time_limit=0.2)
                while True:
                    try:
                        update = updates.get_nowait()
                    except queue.Empty:
                        break
                    if update.get('stage') == 'REVIEWING':
                        if not reviewed:
                            self.request('PATCH', task, 'status', {'status': 'REVIEWING'}, token)
                            reviewed = True
                        progress['stage'] = 'QWEN_REVIEW'
                    progress['progress'] = min(99, int(update.get('progress', progress['progress'])))
                    if not reviewed:
                        progress['progress'] = min(89, progress['progress'])
                        progress['stage'] = 'DETECTING'
                    progress['processedFrames'] = int(update.get('frame', progress['processedFrames']))
                    progress['totalFrames'] = int(update.get('total_frames', progress['totalFrames']))
                if time.monotonic() - last_heartbeat >= 2:
                    self.request('PATCH', task, 'progress', progress, token)
                    last_heartbeat = time.monotonic()
                try:
                    payload = result.get(timeout=0.2)
                except queue.Empty:
                    if not child.is_alive():
                        # The queue feeder can finish just after process exit.
                        try:
                            payload = result.get(timeout=2)
                        except queue.Empty:
                            raise RuntimeError(f'AI subprocess exited without result: {child.exitcode}')
            if payload.get('error'):
                raise RuntimeError(payload['error'])
            if not reviewed:
                self.request('PATCH', task, 'status', {'status': 'REVIEWING'}, token)
            self.request('POST', task, 'events', payload['events'], token)
            self.request('PATCH', task, 'status', {'status': 'COMPLETED',
                         'resultVideoPath': payload['resultVideoPath'], 'result': payload['result']}, token)
            # Archive and terminal state must both be committed before acknowledging delivery.
            channel.basic_ack(method.delivery_tag)
            LOG.info('ACK archived %s attempt=%s', task, claim['attempt'])
        except Exception as exc:
            LOG.exception('NACK task=%s', task)
            if child is not None and child.is_alive():
                child.terminate()
                child.join(timeout=5)
            if task and token:
                try:
                    self.request('POST', task, 'release', {'error': str(exc)[-3900:]}, token)
                except Exception:
                    LOG.warning('Could not release lease; it will expire', exc_info=True)
            if channel.is_open:
                channel.basic_nack(method.delivery_tag, requeue=False)
        finally:
            if child is not None:
                child.join(timeout=5)
                if child.is_alive():
                    child.kill()
                    child.join(timeout=5)
            for q in (updates, result):
                if q is not None:
                    q.close()

    def run(self):
        while True:
            try:
                credentials = pika.PlainCredentials(os.environ.get('RABBITMQ_USER', 'deer'), os.environ['RABBITMQ_PASSWORD'])
                self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                    host=os.environ.get('RABBITMQ_HOST', '127.0.0.1'), port=int(os.environ.get('RABBITMQ_PORT', '5672')),
                    virtual_host=os.environ.get('RABBITMQ_VHOST', '/'), credentials=credentials,
                    heartbeat=60, blocked_connection_timeout=30))
                channel = self.connection.channel()
                channel.queue_declare(queue='deer.task.queue', passive=True)
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(queue='deer.task.queue', on_message_callback=self.process, auto_ack=False)
                LOG.info('Consuming deer.task.queue test_mode=%s', self.test_mode)
                channel.start_consuming()
            except KeyboardInterrupt:
                break
            except Exception:
                LOG.exception('Connection unavailable, reconnecting')
                time.sleep(5)
            finally:
                if self.connection and self.connection.is_open:
                    self.connection.close()


if __name__ == '__main__':
    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--integration-test-double', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    Worker(test_mode=args.integration_test_double).run()
