"""Video source abstraction for loading video frames."""

from abc import ABC, abstractmethod
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
    """Video source using OpenCV VideoCapture."""
    
    def __init__(self, video_path: str | Path):
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        #self._cap = cv2.VideoCapture(str(self.video_path))
        self._cap = cv2.VideoCapture(video_path)
        #self._cap = cv2.VideoCapture(video_path, cv2.CAP_MSMF)
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
    
    def frames(self):
        frame_num = 0
        while True:
            try:
                ret, frame = self._cap.read()
                if not ret:
                    break
                yield frame_num, frame
                
            except SystemError as e:
                print(f"⚠️ 警告: 视频帧 {frame_num} 触发底层报错，强行跳过。")
                pass
            except Exception as e:
                print(f"⚠️ 警告: 读取帧 {frame_num} 发生错误: {e}")
                pass
                
            frame_num += 1
    
    def __del__(self):
        if hasattr(self, '_cap') and self._cap.isOpened():
            self._cap.release()


class SyntheticVideoSource:
    """Generate synthetic test video with COCO-like objects.
    
    Creates frames with simple shapes that simulate object enter/exit events.
    Used for controlled testing with known ground truth.
    """
    
    def __init__(
        self,
        num_frames: int = 300,
        fps: float = 30.0,
        width: int = 640,
        height: int = 480,
        seed: int = 42,
    ):
        self._fps = fps
        self._total_frames = num_frames
        self._width = width
        self._height = height
        self._rng = np.random.default_rng(seed)
        
        # Pre-generate object trajectories for reproducibility
        self._trajectories = self._generate_trajectories()
    
    @property
    def fps(self) -> float:
        return self._fps
    
    @property
    def total_frames(self) -> int:
        return self._total_frames
    
    def _generate_trajectories(self) -> list[dict]:
        """Generate object appearance/movement patterns."""
        trajectories = []
        
        # Object 1: appears early, stays
        trajectories.append({
            "start_frame": 10,
            "end_frame": self._total_frames,
            "color": (0, 255, 0),  # Green
            "label": "person",
            "base_x": 100,
            "base_y": 200,
            "size": 80,
        })
        
        # Object 2: appears mid-video, exits before end
        trajectories.append({
            "start_frame": 100,
            "end_frame": 250,
            "color": (255, 0, 0),  # Blue
            "label": "car",
            "base_x": 400,
            "base_y": 300,
            "size": 100,
        })
        
        # Object 3: brief appearance
        trajectories.append({
            "start_frame": 150,
            "end_frame": 180,
            "color": (0, 0, 255),  # Red
            "label": "dog",
            "base_x": 300,
            "base_y": 150,
            "size": 50,
        })
        
        return trajectories
    
    def frames(self) -> Generator[tuple[int, np.ndarray], None, None]:
        """Generate synthetic frames with moving objects."""
        for frame_num in range(self._total_frames):
            # Create blank frame
            frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
            frame[:] = (40, 40, 40)  # Dark gray background
            
            # Draw objects that are visible in this frame
            for traj in self._trajectories:
                if traj["start_frame"] <= frame_num < traj["end_frame"]:
                    # Add some movement
                    offset_x = int(20 * np.sin(frame_num * 0.1))
                    offset_y = int(10 * np.cos(frame_num * 0.05))
                    
                    x = traj["base_x"] + offset_x
                    y = traj["base_y"] + offset_y
                    size = traj["size"]
                    
                    # Draw rectangle (simulating detected object)
                    cv2.rectangle(
                        frame,
                        (x - size // 2, y - size // 2),
                        (x + size // 2, y + size // 2),
                        traj["color"],
                        -1  # Filled
                    )
                    
                    # Add label
                    cv2.putText(
                        frame,
                        traj["label"],
                        (x - size // 2, y - size // 2 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1
                    )
            
            yield frame_num, frame
    
    def get_ground_truth_events(self) -> list[dict]:
        """Return ground truth events for validation."""
        events = []
        for traj in self._trajectories:
            events.append({
                "type": "object_enter",
                "frame": traj["start_frame"],
                "timestamp": traj["start_frame"] / self._fps,
                "object": traj["label"],
            })
            if traj["end_frame"] < self._total_frames:
                events.append({
                    "type": "object_exit",
                    "frame": traj["end_frame"],
                    "timestamp": traj["end_frame"] / self._fps,
                    "object": traj["label"],
                })
        return sorted(events, key=lambda e: e["frame"])
    
    def get_frame_detections(self, frame_num: int) -> list[dict]:
        """Get ground truth detections for a specific frame.
        
        Returns detections in a format compatible with the Detection model.
        This bypasses YOLO for controlled testing.
        """
        from src.models import Detection
        
        detections = []
        for traj in self._trajectories:
            if traj["start_frame"] <= frame_num < traj["end_frame"]:
                # Calculate position with movement
                offset_x = int(20 * np.sin(frame_num * 0.1))
                offset_y = int(10 * np.cos(frame_num * 0.05))
                
                x = traj["base_x"] + offset_x
                y = traj["base_y"] + offset_y
                size = traj["size"]
                
                # Normalize bbox to 0-1
                x1 = (x - size // 2) / self._width
                y1 = (y - size // 2) / self._height
                x2 = (x + size // 2) / self._width
                y2 = (y + size // 2) / self._height
                
                # Map class names to COCO class IDs
                class_ids = {"person": 0, "car": 2, "dog": 16}
                
                detections.append(Detection(
                    class_id=class_ids.get(traj["label"], 0),
                    class_name=traj["label"],
                    confidence=0.95,  # Ground truth has high confidence
                    bbox=(x1, y1, x2, y2),
                ))
        
        return detections
    
    @property
    def trajectories(self) -> list[dict]:
        """Expose trajectories for mock detection."""
        return self._trajectories

