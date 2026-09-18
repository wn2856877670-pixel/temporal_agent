from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .interaction import InteractionEvent
from .video_utils import make_writer


@dataclass
class SavedEvent:
    event_id: str
    video_path: str
    metadata_path: str
    frame_number: int
    timestamp_seconds: float
    reason: str
    male_track_id: int | None
    other_track_id: int | None
    qwen_result: dict | None = None


class EventBuffer:
    def __init__(
        self,
        *,
        output_dir: Path,
        fps: float,
        frame_size: tuple[int, int],
        pre_seconds: float,
        post_seconds: float,
        codec: str = "mp4v",
        max_events: int = 20,
    ) -> None:
        self.output_dir = output_dir
        self.fps = max(1.0, fps)
        self.frame_size = frame_size
        self.pre_frames = max(1, round(pre_seconds * self.fps))
        self.post_frames = max(1, round(post_seconds * self.fps))
        self.codec = codec
        self.max_events = max_events
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._frames: deque[tuple[int, np.ndarray]] = deque(maxlen=self.pre_frames)
        self._active: list[dict] = []
        self.saved_events: list[SavedEvent] = []

    def add_frame(self, frame_number: int, frame: np.ndarray) -> None:
        self._frames.append((frame_number, frame.copy()))
        for item in list(self._active):
            item["writer"].write(frame)
            if frame_number >= item["end_frame"]:
                self._close_event(item)

    def trigger(self, event: InteractionEvent, frame: np.ndarray) -> SavedEvent | None:
        if len(self.saved_events) + len(self._active) >= self.max_events:
            return None
        event_video = self.output_dir / f"{event.event_id}_{event.timestamp_seconds:.2f}s.mp4"
        metadata_path = event_video.with_suffix(".json")
        writer = make_writer(event_video, self.fps, self.frame_size, self.codec)

        for _, buffered_frame in self._frames:
            writer.write(buffered_frame)
        saved = SavedEvent(
            event_id=event.event_id,
            video_path=str(event_video),
            metadata_path=str(metadata_path),
            frame_number=event.frame_number,
            timestamp_seconds=event.timestamp_seconds,
            reason=event.reason,
            male_track_id=event.male_track_id,
            other_track_id=event.other_track_id,
        )
        self._active.append(
            {
                "writer": writer,
                "end_frame": event.frame_number + self.post_frames,
                "saved": saved,
                "metadata": asdict(event),
            }
        )
        self._write_metadata(saved, asdict(event))
        return saved

    def close(self) -> None:
        for item in list(self._active):
            self._close_event(item)

    def update_qwen_result(self, event_id: str, result: dict) -> None:
        for saved in self.saved_events:
            if saved.event_id == event_id:
                saved.qwen_result = result
                metadata = json.loads(Path(saved.metadata_path).read_text(encoding="utf-8"))
                metadata["qwen_result"] = result
                Path(saved.metadata_path).write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return

    def _close_event(self, item: dict) -> None:
        item["writer"].release()
        saved = item["saved"]
        if saved not in self.saved_events:
            self.saved_events.append(saved)
        self._active.remove(item)

    @staticmethod
    def _write_metadata(saved: SavedEvent, event_data: dict) -> None:
        payload = {"event": event_data, "saved": asdict(saved)}
        Path(saved.metadata_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
