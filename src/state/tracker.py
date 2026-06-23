"""Object tracking and event detection across frames."""

from collections import defaultdict

from src.models import Detection, FrameState, Event, EventType


def iou(box1: tuple, box2: tuple) -> float:
    """Calculate Intersection over Union between two boxes.
    
    Boxes are in format (x1, y1, x2, y2) normalized 0-1.
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0


class ObjectTracker:
    """Track objects across frames and emit events.
    
    Uses simple IoU-based matching to track object identity across frames.
    Emits events when objects enter, exit, or interact.
    """
    
    def __init__(self, iou_threshold: float = 0.3):
        self.iou_threshold = iou_threshold
        
        # Track active objects by class: {class_name: [Detection, ...]}
        self._active_objects: dict[str, list[Detection]] = defaultdict(list)
        
        # Track which classes we've seen at all
        self._seen_classes: set[str] = set()
        
        # Previous frame state for comparison
        self._prev_frame: FrameState | None = None
    
    def update(self, frame_state: FrameState) -> list[Event]:
        """Process a new frame and return detected events.
        
        Args:
            frame_state: Current frame with detections
            
        Returns:
            List of events detected in this frame
        """
        events = []
        current_classes: dict[str, list[Detection]] = defaultdict(list)
        
        # Group detections by class
        for det in frame_state.detections:
            current_classes[det.class_name].append(det)
        
        # Check for new classes (never seen before)
        for class_name in current_classes:
            if class_name not in self._seen_classes:
                self._seen_classes.add(class_name)
                events.append(Event(
                    event_type=EventType.NEW_CLASS,
                    frame_number=frame_state.frame_number,
                    timestamp_seconds=frame_state.timestamp_seconds,
                    object_class=class_name,
                    details=f"First detection of {class_name}",
                ))
        
        # Check for object entries (class wasn't in previous frame)
        for class_name, detections in current_classes.items():
            if class_name not in self._active_objects or not self._active_objects[class_name]:
                events.append(Event(
                    event_type=EventType.OBJECT_ENTER,
                    frame_number=frame_state.frame_number,
                    timestamp_seconds=frame_state.timestamp_seconds,
                    object_class=class_name,
                    details=f"{len(detections)} {class_name}(s) entered frame",
                ))
        
        # Check for object exits (class was in previous frame but not now)
        for class_name in list(self._active_objects.keys()):
            if class_name not in current_classes or not current_classes[class_name]:
                if self._active_objects[class_name]:  # Was present before
                    events.append(Event(
                        event_type=EventType.OBJECT_EXIT,
                        frame_number=frame_state.frame_number,
                        timestamp_seconds=frame_state.timestamp_seconds,
                        object_class=class_name,
                        details=f"{class_name} exited frame",
                    ))
        
        # Check for interactions (overlapping bounding boxes of different classes)
        all_detections = frame_state.detections
        for i, det1 in enumerate(all_detections):
            for det2 in all_detections[i + 1:]:
                if det1.class_name != det2.class_name:
                    if iou(det1.bbox, det2.bbox) > 0.1:  # Slight overlap
                        events.append(Event(
                            event_type=EventType.OBJECT_INTERACT,
                            frame_number=frame_state.frame_number,
                            timestamp_seconds=frame_state.timestamp_seconds,
                            object_class=f"{det1.class_name}+{det2.class_name}",
                            details=f"{det1.class_name} and {det2.class_name} interacting",
                        ))
        
        # Update state
        self._active_objects = current_classes
        self._prev_frame = frame_state
        
        return events
    
    def reset(self) -> None:
        """Reset tracker state."""
        self._active_objects.clear()
        self._seen_classes.clear()
        self._prev_frame = None
    
    @property
    def active_object_classes(self) -> list[str]:
        """Return list of currently active object classes."""
        return [c for c, dets in self._active_objects.items() if dets]
