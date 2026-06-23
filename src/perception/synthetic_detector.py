"""Mock detector for synthetic video testing."""

from typing import Generator

from src.models import Detection, FrameState
from src.perception.video_source import SyntheticVideoSource


class SyntheticDetector:
    """Detector that uses ground truth from SyntheticVideoSource.
    
    This bypasses YOLO entirely for controlled testing,
    ensuring detection consistency across benchmark runs.
    """
    
    def __init__(self, video_source: SyntheticVideoSource):
        self.video_source = video_source
    
    def process_video(
        self,
        video_source: SyntheticVideoSource,
        video_id: str,
        use_cache: bool = True,
    ) -> Generator[FrameState, None, None]:
        """Generate FrameStates with ground truth detections.
        
        Args:
            video_source: Must be a SyntheticVideoSource
            video_id: Ignored for synthetic (always deterministic)
            use_cache: Ignored for synthetic
            
        Yields:
            FrameState for each frame with ground truth detections
        """
        fps = video_source.fps
        
        for frame_num, _ in video_source.frames():
            detections = video_source.get_frame_detections(frame_num)
            timestamp = frame_num / fps if fps > 0 else 0.0
            
            yield FrameState(
                frame_number=frame_num,
                timestamp_seconds=timestamp,
                detections=detections,
            )
