"""Base trigger interface."""

from abc import ABC, abstractmethod
from typing import Protocol

from src.models import FrameState, Event


class Trigger(Protocol):
    """Protocol for trigger implementations.
    
    Triggers decide when the LLM agent should be invoked.
    """
    
    def should_invoke(
        self,
        frame_state: FrameState,
        events: list[Event],
    ) -> bool:
        """Determine if agent should be invoked for this frame.
        
        Args:
            frame_state: Current frame state with detections
            events: Events detected in this frame
            
        Returns:
            True if agent should be invoked
        """
        ...
    
    def reset(self) -> None:
        """Reset trigger state for new video."""
        ...
    
    @property
    def name(self) -> str:
        """Trigger name for logging/metrics."""
        ...
