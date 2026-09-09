from __future__ import annotations

from dataclasses import dataclass

from .geometry import Box, box_diagonal, box_iou, center_distance


@dataclass
class Detection:
    track_id: int
    box: Box
    confidence: float
    male_probability: float | None = None


@dataclass
class InteractionEvent:
    event_id: str
    frame_number: int
    timestamp_seconds: float
    reason: str
    male_track_id: int | None
    other_track_id: int | None
    male_box: Box | None
    other_box: Box | None
    iou: float
    distance: float


class InteractionTrigger:
    def __init__(
        self,
        *,
        trigger_min_seconds: float,
        cooldown_seconds: float,
        overlap_iou_threshold: float,
        near_distance_ratio: float,
        any_pair_iou_threshold: float,
    ) -> None:
        self.trigger_min_seconds = trigger_min_seconds
        self.cooldown_seconds = cooldown_seconds
        self.overlap_iou_threshold = overlap_iou_threshold
        self.near_distance_ratio = near_distance_ratio
        self.any_pair_iou_threshold = any_pair_iou_threshold
        self._active_since: dict[tuple[int, int, str], float] = {}
        self._cooldown_until: dict[tuple[int, int, str], float] = {}
        self._counter = 0

    def update(
        self,
        *,
        frame_number: int,
        timestamp_seconds: float,
        male: Detection | None,
        detections: list[Detection],
    ) -> list[InteractionEvent]:
        candidates: list[tuple[str, Detection | None, Detection, float, float]] = []
        if male is not None:
            for other in detections:
                if other.track_id == male.track_id:
                    continue
                iou = box_iou(male.box, other.box)
                distance = center_distance(male.box, other.box)
                near_limit = ((box_diagonal(male.box) + box_diagonal(other.box)) / 2.0) * self.near_distance_ratio
                if iou >= self.overlap_iou_threshold:
                    candidates.append(("male_overlap", male, other, iou, distance))
                elif distance <= near_limit:
                    candidates.append(("male_near", male, other, iou, distance))

        for index, left in enumerate(detections):
            for right in detections[index + 1 :]:
                iou = box_iou(left.box, right.box)
                if iou >= self.any_pair_iou_threshold:
                    distance = center_distance(left.box, right.box)
                    candidates.append(("any_pair_iou", left, right, iou, distance))

        events: list[InteractionEvent] = []
        seen_keys: set[tuple[int, int, str]] = set()
        for reason, left, right, iou, distance in candidates:
            left_id = left.track_id if left else -1
            key = (min(left_id, right.track_id), max(left_id, right.track_id), reason)
            seen_keys.add(key)
            if timestamp_seconds < self._cooldown_until.get(key, -1.0):
                continue
            start = self._active_since.setdefault(key, timestamp_seconds)
            if timestamp_seconds - start < self.trigger_min_seconds:
                continue
            self._active_since[key] = timestamp_seconds
            self._cooldown_until[key] = timestamp_seconds + self.cooldown_seconds
            self._counter += 1
            events.append(
                InteractionEvent(
                    event_id=f"event_{frame_number:08d}_{self._counter:04d}",
                    frame_number=frame_number,
                    timestamp_seconds=timestamp_seconds,
                    reason=reason,
                    male_track_id=left.track_id if left else None,
                    other_track_id=right.track_id,
                    male_box=left.box if left else None,
                    other_box=right.box,
                    iou=iou,
                    distance=distance,
                )
            )

        stale = [key for key in self._active_since if key not in seen_keys]
        for key in stale:
            self._active_since.pop(key, None)
        return events
