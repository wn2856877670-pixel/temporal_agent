"""Temporal event buffer for building agent context."""

from collections import deque
from src.models import Event, TemporalContext
# 【新增】如果你的画面是 numpy array，可能需要 import numpy

class EventBuffer:
    """Buffer for temporal events with sliding window context.
    
    Maintains a rolling window of recent events and can build
    context summaries for agent prompts.
    """
    
    def __init__(
        self,
        max_recent_events: int = 20,
        max_history_events: int = 100,
        fps: int = 30,
        pre_trigger_seconds: int = 10,
    ):
        self.max_recent_events = max_recent_events
        self.max_history_events = max_history_events
        
        # Recent events (shown to agent in detail)
        self._recent: deque[Event] = deque(maxlen=max_recent_events)
        # Full history (for summary generation)
        self._history: deque[Event] = deque(maxlen=max_history_events)
        
        # 【修改点 1】新增：画面环形缓存 (前10秒)
        self._frame_buffer: deque = deque(maxlen=fps * pre_trigger_seconds)
    
    # 【修改点 2】新增：存入视频帧的方法
    def add_frame(self, frame) -> None:
        """Add a raw video frame to the rolling buffer."""
        if frame is not None:
            self._frame_buffer.append(frame)
            
    def get_cached_frames(self) -> list:
        """Get the last N seconds of cached frames."""
        return list(self._frame_buffer)
        
    def clear_frames(self) -> None:
        """Clear the frame buffer (usually after a trigger)."""
        self._frame_buffer.clear()

    # ... 保持原有的 add, add_many, _build_history_summary 等方法不变 ...
    def add(self, event: Event) -> None:
        """Add an event to the buffer."""
        self._recent.append(event)
        self._history.append(event)
    
    def add_many(self, events: list[Event]) -> None:
        """Add multiple events to the buffer."""
        for event in events:
            self.add(event)
    
    
    def _build_history_summary(self) -> str:
        """Generate a text summary of event history."""
        if not self._history:
            return "No previous events recorded."
    def get_context(
        self,
        current_frame: int,
        current_timestamp: float,
        active_objects: list[str],
    ) -> TemporalContext:
        """Build temporal context for agent invocation."""
        recent_events = list(self._recent)
        history_summary = self._build_history_summary()
        
        # 【修改点 3】注意：你需要在 src/models.py 的 TemporalContext 中新增一个 `frames: list = None` 字段
        return TemporalContext(
            current_frame=current_frame,
            current_timestamp=current_timestamp,
            recent_events=recent_events,
            active_objects=active_objects,
            event_history_summary=history_summary,
            frames=self.get_cached_frames() # 将缓存的帧带入上下文
        )