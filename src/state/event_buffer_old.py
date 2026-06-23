"""Temporal event buffer for building agent context."""

from collections import deque
from src.models import Event, TemporalContext


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

        self._frame_buffer: deque = deque(maxlen=fps * pre_trigger_seconds)
    
    def add(self, event: Event) -> None:
        """Add an event to the buffer."""
        self._recent.append(event)
        self._history.append(event)
    
    def add_many(self, events: list[Event]) -> None:
        """Add multiple events to the buffer."""
        for event in events:
            self.add(event)
    
    def get_context(
        self,
        current_frame: int,
        current_timestamp: float,
        active_objects: list[str],
    ) -> TemporalContext:
        """Build temporal context for agent invocation.
        
        Args:
            current_frame: Current frame number
            current_timestamp: Current timestamp in seconds
            active_objects: List of currently visible object classes
            
        Returns:
            TemporalContext ready for agent prompt
        """
        recent_events = list(self._recent)
        
        # Build history summary from older events
        history_summary = self._build_history_summary()
        
        return TemporalContext(
            current_frame=current_frame,
            current_timestamp=current_timestamp,
            recent_events=recent_events,
            active_objects=active_objects,
            event_history_summary=history_summary,
        )
    
    def _build_history_summary(self) -> str:
        """Generate a text summary of event history."""
        if not self._history:
            return "No previous events recorded."
        
        # Group events by type
        enters = []
        exits = []
        interactions = []
        
        for event in self._history:
            if event.event_type.value == "object_enter":
                enters.append(f"{event.object_class} at {event.timestamp_seconds:.1f}s")
            elif event.event_type.value == "object_exit":
                exits.append(f"{event.object_class} at {event.timestamp_seconds:.1f}s")
            elif event.event_type.value == "object_interact":
                interactions.append(f"{event.object_class} at {event.timestamp_seconds:.1f}s")
        
        parts = []
        if enters:
            parts.append(f"Objects entered: {', '.join(enters[:5])}")
        if exits:
            parts.append(f"Objects exited: {', '.join(exits[:5])}")
        if interactions:
            parts.append(f"Interactions: {', '.join(interactions[:5])}")
        
        return " | ".join(parts) if parts else "No significant events."
    
    @property
    def event_count(self) -> int:
        """Total events in history."""
        return len(self._history)
    
    def clear(self) -> None:
        """Clear all buffered events."""
        self._recent.clear()
        self._history.clear()
