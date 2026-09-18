"""Real infrastructure contract test. Requires isolated deer_test RabbitMQ vhost/DB.

Uses a deliberately marked inference double, not YOLO/Qwen. Does not consume the
production queue. The production worker never enables the double implicitly.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pika
import requests

assert os.environ.get('RABBITMQ_VHOST') == 'deer_test', 'Run only in the isolated test vhost'
BASE = os.environ.get('INTERNAL_API_URL', 'http://127.0.0.1:6021')
ROOT = Path(os.environ['DEER_MEDIA_ROOT'])
HTTP = requests.Session()
HTTP.headers['X-Internal-Token'] = os.environ['INTERNAL_API_TOKEN']


def api(method, path, code=200, **kwargs):
    r = HTTP.request(method, BASE + '/api' + path, timeout=20, **kwargs)
    assert r.status_code == code, (path, r.status_code, r.text[:1000])
    return r.json() if r.content else None


def upload(fail=False):
    content = b'FAIL_TEST' if fail else Path(sys.argv[1]).read_bytes()
    return api('POST', '/tasks', code=202, files={'video': ('INTEGRATION_TEST.mp4', content, 'video/mp4')})


def wait(id, state, timeout=100):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        t = api('GET', '/tasks/' + id)
        if t['status'] == state:
            return t
        time.sleep(1)
    raise AssertionError(f'{id}: expected {state}, last={t}')


credentials = pika.PlainCredentials(os.environ['RABBITMQ_USER'], os.environ['RABBITMQ_PASSWORD'])
conn = pika.BlockingConnection(pika.ConnectionParameters(host='127.0.0.1',virtual_host='deer_test',credentials=credentials))
channel = conn.channel()
channel.confirm_delivery()
for name in ('deer.task.queue', 'deer.task.retry.queue', 'deer.task.failure.queue', 'deer.task.dlq'):
    channel.queue_purge(name)


def publish(t):
    channel.basic_publish(exchange='deer.task.exchange', routing_key='deer.task.analyze',
        body=json.dumps({'taskId':t['taskId'],'videoPath':t['videoPath']}),
        properties=pika.BasicProperties(content_type='application/json',delivery_mode=2), mandatory=True)


# Validate security, conditional claims, event idempotency and terminal fencing.
assert requests.post(BASE+'/api/internal/tasks/nope/claim',json={'owner':'bad'}).status_code == 401
t = upload(); id = t['taskId']
claim = api('POST',f'/internal/tasks/{id}/claim',json={'owner':'integration'})
headers = {'X-Lease-Token':claim['leaseToken']}
redis_env = {**os.environ, 'REDISCLI_AUTH':os.environ.get('REDIS_PASSWORD','')}
redis = ['redis-cli','-p',os.environ.get('REDIS_PORT','6379'),'--raw']
assert subprocess.check_output(redis+['HGET','deer:task:'+id,'status'],env=redis_env,text=True).strip() == 'RUNNING'
assert not api('POST',f'/internal/tasks/{id}/claim',json={'owner':'duplicate'})['claimed']
api('PATCH',f'/internal/tasks/{id}/status',code=409,headers=headers,json={'status':'COMPLETED'})
api('PATCH',f'/internal/tasks/{id}/status',headers=headers,json={'status':'REVIEWING'})
clip = ROOT/'results'/id/'fixture.mp4';clip.parent.mkdir(parents=True,exist_ok=True);clip.write_bytes(Path(sys.argv[1]).read_bytes())
event = {'eventIndex':1,'eventType':'integration_test','startTime':0,'endTime':1,'qwenResult':'测试结果','clipPath':str(clip),'evidence':'No model inference'}
api('POST',f'/internal/tasks/{id}/events',headers=headers,json=[event])
api('POST',f'/internal/tasks/{id}/events',headers=headers,json=[event])
assert len(api('GET',f'/tasks/{id}/events')) == 1
api('PATCH',f'/internal/tasks/{id}/status',headers=headers,json={'status':'COMPLETED','resultVideoPath':str(clip),'result':{'conclusion':'测试结果'}})
api('PATCH',f'/internal/tasks/{id}/status',code=409,headers=headers,json={'status':'RUNNING'})
assert api('POST',f'/internal/tasks/{id}/claim',json={'owner':'duplicate'})['alreadyCompleted']
assert int(api('GET',f'/tasks/{id}/progress')['progress']) == 100
assert 0 < int(subprocess.check_output(redis+['TTL','deer:task:'+id],env=redis_env,text=True)) <= 86400
playback = HTTP.get(BASE + '/media/business/' + str(clip.relative_to(ROOT)), headers={'Range':'bytes=0-1023'})
assert playback.status_code == 206 and len(playback.content) == 1024
print('PASS internal authentication / claim / event idempotency / state fencing', flush=True)

log = open('logs/integration_worker.log','w')
worker = subprocess.Popen([sys.executable,'worker/consumer.py','--integration-test-double'],stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy())
try:
    good = upload(); done = wait(good['taskId'],'COMPLETED')
    assert done['attempts'] == 1 and done['eventCount'] == 1
    publish(good); publish(good)
    time.sleep(5)
    assert api('GET','/tasks/'+good['taskId'])['attempts'] == 1
    assert len(api('GET','/tasks/'+good['taskId']+'/events')) == 1
    bad = upload(fail=True); failed = wait(bad['taskId'],'FAILED')
    assert failed['attempts'] == 4, failed
    time.sleep(3)
    delivery, props, body = channel.basic_get('deer.task.dlq',auto_ack=False)
    assert delivery is not None and json.loads(body)['taskId'] == bad['taskId']
    channel.basic_nack(delivery.delivery_tag,requeue=True)
    time.sleep(6)
    mq = HTTP.get('http://127.0.0.1:15672/api/queues/deer_test/deer.task.queue',auth=(os.environ['RABBITMQ_USER'],os.environ['RABBITMQ_PASSWORD']),timeout=10)
    mq.raise_for_status()
    assert mq.json()['messages_unacknowledged'] == 0 and mq.json()['messages_ready'] == 0
    assert api('GET', '/statistics/overview')['total_tasks'] >= 3
    assert len(api('GET','/statistics/daily?days=7')) == 7
    assert api('GET',f'/events?taskId={good["taskId"]}&eventType=integration_test&page=1&pageSize=10')['total'] == 1
    print('PASS real publish / consume / manual ACK / duplicate delivery / 3 retries / DLQ / queries',flush=True)
    Path('logs/business_verification.json').write_text(json.dumps({'manualTask':id,'workerTask':good['taskId'],'failedTask':bad['taskId'],'workerAttempts':failed['attempts'],'inference':'explicit test double'},indent=2))
finally:
    worker.terminate();worker.wait(timeout=10);log.close();conn.close()
