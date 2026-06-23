"""Pydantic models for the temporal agent benchmark system."""

from enum import Enum
from pydantic import BaseModel, Field,ConfigDict
from typing import Any, List

class Detection(BaseModel):
    """A single object detection from YOLO."""
    
    class_id: int = Field(description="COCO class ID")
    class_name: str = Field(description="Human-readable class name")
    confidence: float = Field(description="Detection confidence 0-1")
    bbox: tuple[float, float, float, float] = Field(
        description="Bounding box (x1, y1, x2, y2) normalized 0-1"
    )
    
    def __hash__(self) -> int:
        return hash((self.class_id, self.bbox))


class FrameState(BaseModel):
    """State of a single video frame."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    frame_number: int = Field(description="Frame index in video")
    timestamp_seconds: float = Field(description="Timestamp in seconds")
    detections: list[Detection] = Field(default_factory=list)
    objects: List[Any]

    image: Any = None


class EventType(str, Enum):
    """Types of events that can trigger agent invocation."""
    
    OBJECT_ENTER = "object_enter"  # New object appeared
    OBJECT_EXIT = "object_exit"    # Object disappeared
    OBJECT_INTERACT = "object_interact"  # Objects overlap/interact
    NEW_CLASS = "new_class"        # First time seeing this class


class Event(BaseModel):
    """A temporal event detected in the video stream."""
    
    event_type: EventType
    frame_number: int
    timestamp_seconds: float
    object_class: str
    details: str = Field(default="", description="Additional event context")
    
    def __str__(self) -> str:
        return f"[{self.timestamp_seconds:.2f}s] {self.event_type.value}: {self.object_class}"


class TemporalContext(BaseModel):
    """Context passed to the agent for reasoning."""
    
    current_frame: int
    current_timestamp: float
    recent_events: list[Event] = Field(default_factory=list)
    active_objects: list[str] = Field(
        default_factory=list,
        description="Object classes currently visible"
    )
    frames: list = None
    event_history_summary: str = Field(
        default="",
        description="Summary of earlier events"
    )


class AgentOutput(BaseModel):
    """Structured output from the temporal agent."""
    
    summary: str = Field(description="Natural language summary of what happened")
    key_events: list[str] = Field(
        default_factory=list,
        description="List of important events with timestamps"
    )
    objects_mentioned: list[str] = Field(
        default_factory=list,
        description="Object classes discussed in summary"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agent's confidence in the summary"
    )


class BenchmarkResult(BaseModel):
    """Results from a single benchmark run."""
    
    trigger_type: str = Field(description="'fixed' or 'event_driven'")
    total_frames: int
    total_invocations: int
    agent_outputs: list[AgentOutput] = Field(default_factory=list)
    invocation_frames: list[int] = Field(
        default_factory=list,
        description="Frame numbers where agent was invoked"
    )
    events_detected: list[Event] = Field(default_factory=list)
    
    @property
    def invocation_rate(self) -> float:
        """Percentage of frames that triggered invocation."""
        if self.total_frames == 0:
            return 0.0
        return (self.total_invocations / self.total_frames) * 100
