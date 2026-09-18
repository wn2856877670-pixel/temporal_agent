"""Adapter only: reuses the existing pipeline without writing to SQLite/MySQL."""
import os
import traceback
from pathlib import Path


class ArchiveCollector:
    def __init__(self):
        self.events = {}

    def create_task(self, **fields):
        pass

    def update_task(self, *args, **fields):
        pass

    def create_event(self, **fields):
        self.events[fields['event_index']] = fields

    def update_event_qwen(self, *, event_index, **fields):
        self.events[event_index].update(fields)


def execute(video, output, task_id, updates, result):
    try:
        # Import expensive model dependencies only inside the supervised child.
        from deer_behavior.config import load_settings
        from deer_behavior.pipeline import run_video
        settings = load_settings(os.environ.get('DEER_CONFIG', 'configs/config.json'))
        repository = ArchiveCollector()
        summary = run_video(video, output, settings, task_id=task_id,
                            repository=repository, progress_callback=updates.put)
        rows = []
        for index, event in repository.events.items():
            qwen = summary['events'][index - 1].get('qwen_result') or {}
            rows.append(dict(eventIndex=index, eventType=event['event_type'],
                             startTime=event['start_time'], endTime=event['end_time'],
                             maleTrackId=event['male_track_id'], targetTrackId=event['target_track_id'],
                             confidence=event['confidence'], qwenResult=event.get('qwen_result') or '待复核',
                             qwenConfidence=event.get('qwen_confidence'), clipPath=str(event['clip_path']),
                             evidence=qwen.get('evidence')))
        result.put({'events': rows, 'resultVideoPath': summary['browser_output'], 'result': summary['result']})
    except BaseException:
        result.put({'error': traceback.format_exc()[-3900:]})


def test_execute(video, output, task_id, updates, result):
    """Explicit integration-test double. Never selected by the production entry point."""
    import shutil
    import time
    if Path(video).read_bytes().startswith(b'FAIL_TEST'):
        result.put({'error': 'Intentional integration-test failure'})
        return
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, output)
    updates.put({'progress': 40, 'frame': 4, 'total_frames': 10})
    time.sleep(1)
    updates.put({'stage': 'REVIEWING', 'progress': 90})
    time.sleep(1)
    result.put({'events': [dict(eventIndex=1, eventType='integration_test', startTime=0, endTime=1,
                maleTrackId=None, targetTrackId=None, confidence=None, qwenResult='测试结果',
                qwenConfidence=None, clipPath=output, evidence='TEST DOUBLE - no AI inference')],
                'resultVideoPath': output, 'result': {'conclusion': '测试结果', 'evidence': 'No AI inference'}})
