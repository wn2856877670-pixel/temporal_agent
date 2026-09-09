from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable
from uuid import uuid4

import cv2

from .config import Settings
from .detection import MaleIdentifier, load_detector, parse_yolo_detections
from .event_buffer import EventBuffer
from .interaction import Detection, InteractionTrigger
from .qwen_vl import QwenVLAnalyzer
from .repository import DeerRepository
from .storage import now_text
from .video_utils import make_browser_mp4, make_writer, publish_media_file

ProgressCallback = Callable[[dict], None]


def run_video(
    input_path: str | Path,
    output_path: str | Path,
    settings: Settings,
    *,
    progress_callback: ProgressCallback | None = None,
    task_id: str | None = None,
    filename: str | None = None,
) -> dict:
    input_path = Path(input_path)
    output_path = Path(output_path)
    task_id = task_id or f"cli_{uuid4().hex[:12]}"
    filename = filename or input_path.name
    repository = DeerRepository(settings)
    repository.create_task(
        task_id=task_id,
        filename=filename,
        input_path=input_path,
        output_path=output_path,
        status="queued",
    )
    if not input_path.exists():
        repository.update_task(
            task_id,
            status="failed",
            finished_at=now_text(),
            error_message=f"Input video not found: {input_path}",
        )
        raise FileNotFoundError(f"Input video not found: {input_path}")

    try:
        summary = _run_video_core(
            input_path=input_path,
            output_path=output_path,
            settings=settings,
            repository=repository,
            task_id=task_id,
            filename=filename,
            progress_callback=progress_callback,
        )
        return summary
    except Exception as exc:
        repository.update_task(
            task_id,
            status="failed",
            finished_at=now_text(),
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise


def _run_video_core(
    *,
    input_path: Path,
    output_path: Path,
    settings: Settings,
    repository: DeerRepository,
    task_id: str,
    filename: str,
    progress_callback: ProgressCallback | None,
) -> dict:
    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if width <= 0 or height <= 0:
        repository.update_task(
            task_id,
            status="failed",
            finished_at=now_text(),
            total_frames=total_frames,
            error_message=f"Failed to read video metadata: {input_path}",
        )
        raise RuntimeError(f"Failed to read video metadata: {input_path}")

    repository.update_task(
        task_id,
        status="processing",
        started_at=now_text(),
        total_frames=total_frames,
        processed_frames=0,
        event_count=0,
        output_path=output_path,
    )
    frame_number = 0
    detector = load_detector(settings)
    male_identifier = MaleIdentifier(settings)
    trigger = InteractionTrigger(
        trigger_min_seconds=settings.trigger_min_seconds,
        cooldown_seconds=settings.cooldown_seconds,
        overlap_iou_threshold=settings.overlap_iou_threshold,
        near_distance_ratio=settings.near_distance_ratio,
        any_pair_iou_threshold=settings.any_pair_iou_threshold,
    )
    event_buffer = EventBuffer(
        output_dir=output_path.parents[1] / "events",
        fps=fps,
        frame_size=(width, height),
        pre_seconds=settings.event_pre_seconds,
        post_seconds=settings.event_post_seconds,
        codec=settings.output_codec,
        max_events=settings.max_events,
    )
    qwen = QwenVLAnalyzer(settings)
    writer = make_writer(output_path, fps, (width, height), settings.output_codec)

    try:
        results = detector.track(
            source=str(input_path),
            stream=True,
            persist=True,
            tracker=settings.tracker_config,
            conf=settings.detect_confidence,
            iou=settings.detect_iou,
            imgsz=settings.detect_imgsz,
            device=settings.device,
            verbose=False,
        )
        for result in results:
            frame_number += 1
            frame = result.orig_img.copy()
            detections = parse_yolo_detections(result)
            timestamp = frame_number / fps
            male = male_identifier.update(
                frame=frame,
                frame_number=frame_number,
                fps=fps,
                detections=detections,
            )
            annotated = draw_frame(frame, frame_number, fps, detections, male)
            writer.write(annotated)
            event_buffer.add_frame(frame_number, annotated)
            for event in trigger.update(
                frame_number=frame_number,
                timestamp_seconds=timestamp,
                male=male,
                detections=detections,
            ):
                event_buffer.trigger(event, annotated)

            if progress_callback and (frame_number == 1 or frame_number % 10 == 0):
                repository.update_task(
                    task_id,
                    total_frames=total_frames,
                    processed_frames=frame_number,
                    event_count=len(event_buffer.saved_events),
                )
                progress_callback(
                    {
                        "frame": frame_number,
                        "total_frames": total_frames,
                        "progress": _progress(frame_number, total_frames),
                        "events": len(event_buffer.saved_events),
                        "target_track_id": male.track_id if male else None,
                    }
                )
    except Exception as exc:
        repository.update_task(
            task_id,
            status="failed",
            finished_at=now_text(),
            total_frames=total_frames,
            processed_frames=frame_number,
            event_count=len(event_buffer.saved_events),
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        writer.release()
        event_buffer.close()

    qwen_events = []
    for event_index, saved in enumerate(event_buffer.saved_events, start=1):
        original_event_video = Path(saved.video_path)
        event_video = make_browser_mp4(original_event_video, settings.ffmpeg_path)
        if event_video is not None:
            publish_media_file(event_video)
            saved.video_path = str(event_video)
        start_time = max(0.0, saved.timestamp_seconds - settings.event_pre_seconds)
        end_time = saved.timestamp_seconds + settings.event_post_seconds
        repository.create_event(
            task_id=task_id,
            event_index=event_index,
            event_type=saved.reason,
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time,
            male_track_id=saved.male_track_id,
            target_track_id=saved.other_track_id,
            confidence=None,
            clip_path=saved.video_path,
        )
        result = qwen.analyze_video(original_event_video)
        event_buffer.update_qwen_result(saved.event_id, result)
        saved.qwen_result = result
        repository.update_event_qwen(
            task_id=task_id,
            event_index=event_index,
            qwen_result=str(result.get("conclusion")) if result.get("conclusion") is not None else None,
            qwen_confidence=_optional_float(result.get("confidence")),
        )
        qwen_events.append(asdict(saved))

    browser_video = make_browser_mp4(output_path, settings.ffmpeg_path)
    if browser_video is not None:
        publish_media_file(browser_video)
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "browser_output": str(browser_video or output_path),
        "task_id": task_id,
        "frame_count": frame_number,
        "fps": fps,
        "events": qwen_events,
        "event_count": len(qwen_events),
        "result": summarize_events(qwen_events),
    }
    repository.update_task(
        task_id,
        status="completed",
        finished_at=now_text(),
        total_frames=total_frames,
        processed_frames=frame_number,
        event_count=len(qwen_events),
        output_path=browser_video or output_path,
        error_message=None,
    )
    if progress_callback:
        progress_callback({"progress": 100, "events": len(qwen_events)})
    return summary


def summarize_events(events: list[dict]) -> dict:
    if not events:
        return {
            "conclusion": "正常",
            "confidence": 0.8,
            "evidence": "未触发公鹿靠近、重叠或任意两鹿 IoU 重叠候选事件。",
        }
    abnormal_keywords = ("异常", "疑似")
    for event in events:
        qwen = event.get("qwen_result") or {}
        conclusion = str(qwen.get("conclusion", ""))
        if any(keyword in conclusion for keyword in abnormal_keywords):
            return {
                "conclusion": "异常" if "疑似" in conclusion else conclusion,
                "confidence": qwen.get("confidence", 0.0),
                "evidence": qwen.get("evidence", "已触发候选事件。"),
            }
    first = events[0].get("qwen_result") or {}
    return {
        "conclusion": first.get("conclusion", "疑似异常"),
        "confidence": first.get("confidence", 0.5),
        "evidence": first.get("evidence", "已触发候选事件，请人工复核事件片段。"),
    }


def draw_frame(
    frame,
    frame_number: int,
    fps: float,
    detections: list[Detection],
    male: Detection | None,
):
    target_id = male.track_id if male else None
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        is_target = detection.track_id == target_id
        color = (0, 220, 255) if is_target else (0, 220, 0)
        label_prefix = "target_male" if is_target else "deer"
        label = f"{label_prefix}_{detection.track_id} det={detection.confidence:.2f}"
        if detection.male_probability is not None:
            label += f" male={detection.male_probability:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            label,
            (x1, max(18, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    status = "LOCKED" if target_id is not None else "SEARCHING"
    cv2.putText(
        frame,
        f"Male target: {status} id={target_id if target_id is not None else '-'}  FPS={fps:.1f}",
        (16, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"Frame: {frame_number}",
        (16, 64),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def _progress(frame_number: int, total_frames: int) -> int:
    if total_frames <= 0:
        return 0
    return max(1, min(99, round(frame_number / total_frames * 100)))


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
