"""Fixed interval trigger - invoke every N frames."""

from src.models import FrameState, Event
from src.config import settings


class FixedIntervalTrigger:
    """Trigger that invokes agent every N frames.
    
    This is the baseline approach: regular invocation regardless of content.
    """
    
    def __init__(self, interval: int = None):
        """Initialize fixed interval trigger.
        
        Args:
            interval: Frames between invocations. Defaults to config value.
        """
        self.interval = interval or settings.fixed_trigger_interval
        self._last_invoked: int = -self.interval  # Ensure first frame can trigger
    
    def should_invoke(
        self,
        frame_state: FrameState,
        events: list[Event],
    ) -> bool:
        """Check if N frames have passed since last invocation."""
        frames_since_last = frame_state.frame_number - self._last_invoked
        
        if frames_since_last >= self.interval:
            self._last_invoked = frame_state.frame_number
            return True
        
        return False
    
    def reset(self) -> None:
        """Reset for new video."""
        self._last_invoked = -self.interval
    
    @property
    def name(self) -> str:
        return f"fixed_{self.interval}"
