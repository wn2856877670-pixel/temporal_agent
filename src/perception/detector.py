"""YOLO detector with caching for reproducible benchmarks."""

import json
from pathlib import Path
from typing import Generator

import numpy as np
from ultralytics import YOLO

from src.config import settings
from src.models import Detection, FrameState


class CachedDetector:
    """YOLO detector that caches results for reproducibility.
    
    Both fixed and event-driven triggers consume the same cached detections,
    ensuring fair comparison isolated from YOLO's non-determinism.
    """
    
    def __init__(
        self,
        model_path: str = None,
        confidence_threshold: float = None,
        cache_dir: str = None,
    ):
        self.model_path = model_path or settings.yolo_model
        self.confidence_threshold = confidence_threshold or settings.yolo_confidence_threshold
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._model: YOLO | None = None
    
    @property
    def model(self) -> YOLO:
        """Lazy load YOLO model."""
        if self._model is None:
            self._model = YOLO(self.model_path).to("cuda")
        return self._model
    
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run YOLO detection on a single frame."""
        results = self.model(frame, device="cuda:0", verbose=True)[0]
        detections = []
        
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.confidence_threshold:
                continue
            
            class_id = int(box.cls[0])

            class_name = results.names[class_id]
            
            # Normalize bbox to 0-1
            xyxy = box.xyxy[0].cpu().numpy()
            h, w = frame.shape[:2]
            bbox = (
                float(xyxy[0] / w),
                float(xyxy[1] / h),
                float(xyxy[2] / w),
                float(xyxy[3] / h),
            )
            
            detections.append(Detection(
                class_id=class_id,
                class_name=class_name,
                confidence=conf,
                bbox=bbox,
            ))
        
        return detections
    
    def process_video(self, video_source, video_id: str, use_cache: bool = False) -> Generator[FrameState, None, None]:
        """处理视频流，支持从缓存读取或实时检测。"""
        
        if use_cache and self.cache_exists(video_id):
            print(f"📦 正在从缓存加载检测结果: {video_id}")
            yield from self.load_cache(video_id)
            return

        print(f"🔍 开始实时 YOLO 检测...")
        # 👇 修改 1：不要在这里初始化 all_states = []，长视频会撑爆内存
        fps = video_source.fps

        for frame_num, frame in video_source.frames():
            detections = self.detect(frame)
            timestamp = frame_num / fps if fps > 0 else 0.0
            
            frame_state = FrameState(
                frame_number=frame_num,
                timestamp_seconds=timestamp,
                detections=detections,
                objects=detections,
                image=frame  # 这一帧会被传给触发器，触发器用完就会被回收
            )
            
            # 👇 修改 2：删掉 all_states.append(frame_state)
            # 我们不需要在内存里保留 15 分钟的所有帧数据
            
            yield frame_state

        # 👇 修改 3：由于删了 all_states，我们也暂时不自动保存这种超大缓存
        # 如果确实需要缓存，应该只存坐标，不存 image 数组
            
    def get_cache_path(self, video_id: str) -> Path:
        """Get cache file path for a video."""
        return self.cache_dir / f"{video_id}_detections.json"
    
    def cache_exists(self, video_id: str) -> bool:
        """Check if cached detections exist for a video."""
        return self.get_cache_path(video_id).exists()
    
    def save_cache(self, video_id: str, frame_states: list[FrameState]) -> None:
        """Save detections to cache file."""
        cache_path = self.get_cache_path(video_id)
        data = [fs.model_dump() for fs in frame_states]
        cache_path.write_text(json.dumps(data, indent=2))
    
    def load_cache(self, video_id: str) -> Generator[FrameState, None, None]:
        """Load cached detections."""
        cache_path = self.get_cache_path(video_id)
        data = json.loads(cache_path.read_text())
        for frame_data in data:
            yield FrameState.model_validate(frame_data)
    

