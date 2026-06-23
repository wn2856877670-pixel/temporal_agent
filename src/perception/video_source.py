"""Video source abstraction for surveillance videos."""

from pathlib import Path
from typing import Generator, Protocol

import cv2
import numpy as np


class VideoSource(Protocol):
    """Protocol for video sources."""

    @property
    def fps(self) -> float:
        """Frames per second of the video."""
        ...

    @property
    def total_frames(self) -> int:
        """Total number of frames in the video."""
        ...

    def frames(self) -> Generator[tuple[int, np.ndarray], None, None]:
        """Yield (frame_number, frame) tuples."""
        ...


class CV2VideoSource:
    """Video source backed by OpenCV VideoCapture."""

    def __init__(self, video_path: str | Path):
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        self._cap = cv2.VideoCapture(str(self.video_path))
        if not self._cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    def frames(self) -> Generator[tuple[int, np.ndarray], None, None]:
        frame_num = 0
        while True:
            ret, frame = self._cap.read()
            if not ret:
                break
            yield frame_num, frame
            frame_num += 1

    def __del__(self):
        if hasattr(self, "_cap") and self._cap.isOpened():
            self._cap.release()
