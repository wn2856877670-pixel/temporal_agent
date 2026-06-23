"""Event-driven trigger with deduplication cooldown."""

from src.models import FrameState, Event, EventType
from src.config import settings


class EventDrivenTrigger:
    """Trigger that invokes agent only on meaningful state changes.
    
    Includes deduplication: same object class won't re-trigger within
    the cooldown window, preventing redundant invocations from repeated
    detections of the same object.
    """
    
    def __init__(
        self,
        event_types: list[EventType] = None,
        cooldown_seconds: float = None,
    ):
        """Initialize event-driven trigger.
        
        Args:
            event_types: Which event types should trigger invocation.
                         Defaults to all types.
            cooldown_seconds: Minimum seconds before same object class
                              can re-trigger. Defaults to config value.
        """
        self.event_types = event_types or list(EventType)
        self.cooldown_seconds = cooldown_seconds or settings.event_trigger_cooldown
        
        # Track last trigger time per object class: {class_name: timestamp}
        self._last_trigger: dict[str, float] = {}
    
    def should_invoke(
        self,
        frame_state: FrameState,
        events: list[Event],
    ) -> bool:
        """Check if any qualifying events occurred that aren't in cooldown.
        
        Args:
            frame_state: Current frame state
            events: Events detected in this frame
            
        Returns:
            True if agent should be invoked
        """
        if not events:
            return False
        
        current_time = frame_state.timestamp_seconds
        should_trigger = False
        
        for event in events:
            # Check if this event type qualifies
            if event.event_type not in self.event_types:
                continue
            
            # Check cooldown for this object class
            last_time = self._last_trigger.get(event.object_class, -float('inf'))
            time_since_last = current_time - last_time
            
            if time_since_last >= self.cooldown_seconds:
                # This event should trigger
                should_trigger = True
                self._last_trigger[event.object_class] = current_time
        
        return should_trigger
    
    def reset(self) -> None:
        """Reset for new video."""
        self._last_trigger.clear()
    
    @property
    def name(self) -> str:
        return f"event_driven_{self.cooldown_seconds}s"


class HybridTrigger:
    """Combines event-driven with a maximum interval fallback.
    
    Ensures agent is invoked at least every max_interval frames,
    even if no events occur. This prevents long silences in
    low-activity portions of video.
    """
    
    def __init__(
        self,
        event_types: list[EventType] = None,
        cooldown_seconds: float = None,
        max_interval: int = 500,
    ):
        self._event_trigger = EventDrivenTrigger(event_types, cooldown_seconds)
        self.max_interval = max_interval
        self._last_invoked: int = 0
    
    def should_invoke(
        self,
        frame_state: FrameState,
        events: list[Event],
    ) -> bool:
        """Invoke on event or if max interval exceeded."""
        # Check event trigger first
        if self._event_trigger.should_invoke(frame_state, events):
            self._last_invoked = frame_state.frame_number
            return True
        
        # Fallback: max interval exceeded
        if frame_state.frame_number - self._last_invoked >= self.max_interval:
            self._last_invoked = frame_state.frame_number
            return True
        
        return False
    
    def reset(self) -> None:
        self._event_trigger.reset()
        self._last_invoked = 0
    
    @property
    def name(self) -> str:
        return f"hybrid_{self._event_trigger.cooldown_seconds}s_max{self.max_interval}"
