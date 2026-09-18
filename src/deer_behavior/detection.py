from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import Settings
from .geometry import Box, clamp_box
from .interaction import Detection


@dataclass
class MaleTrackState:
    probabilities: deque[float] = field(default_factory=deque)
    last_seen_frame: int = 0


class MaleIdentifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.classifier = None
        self.male_class_index: int | None = None
        self.tracks: dict[int, MaleTrackState] = {}
        self.target_track_id: int | None = None
        self.target_last_seen_frame = 0

        if settings.male_classifier_model.exists():
            from ultralytics import YOLO

            self.classifier = YOLO(str(settings.male_classifier_model))
            names = getattr(self.classifier, "names", {}) or {}
            for index, name in names.items():
                if str(name) == settings.male_class_name:
                    self.male_class_index = int(index)
                    break
            if self.male_class_index is None:
                raise ValueError(f"Male class not found in classifier names: {settings.male_class_name}")

    def update(
        self,
        *,
        frame: np.ndarray,
        frame_number: int,
        fps: float,
        detections: list[Detection],
    ) -> Detection | None:
        if not detections:
            return None
        lost_frames = max(1, round(self.settings.target_lost_seconds * fps))
        if (
            self.target_track_id is not None
            and frame_number - self.target_last_seen_frame > lost_frames
        ):
            self.target_track_id = None

        if self.classifier is not None and frame_number % self.settings.classify_stride == 0:
            self._classify_frame(frame, frame_number, detections)

        for detection in detections:
            state = self.tracks.get(detection.track_id)
            if state and state.probabilities:
                detection.male_probability = sum(state.probabilities) / len(state.probabilities)

        visible_ids = {item.track_id for item in detections}
        if self.target_track_id in visible_ids:
            self.target_last_seen_frame = frame_number
            return self._by_id(detections, self.target_track_id)

        candidate = self._best_candidate(detections)
        if candidate is not None:
            self.target_track_id = candidate.track_id
            self.target_last_seen_frame = frame_number
            return candidate
        return None

    def _classify_frame(self, frame: np.ndarray, frame_number: int, detections: list[Detection]) -> None:
        if self.classifier is None or self.male_class_index is None:
            return
        height, width = frame.shape[:2]
        crops: list[np.ndarray] = []
        crop_detections: list[Detection] = []
        for detection in detections:
            x1, y1, x2, y2 = clamp_box(detection.box, width, height)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crops.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            crop_detections.append(detection)
        if not crops:
            return

        results = self.classifier.predict(
            source=crops,
            imgsz=self.settings.classify_imgsz,
            device=self.settings.device,
            verbose=False,
        )
        for detection, result in zip(crop_detections, results):
            probs = getattr(result, "probs", None)
            if probs is None:
                continue
            data = probs.data.detach().cpu().numpy()
            if self.male_class_index >= len(data):
                continue
            probability = float(data[self.male_class_index])
            state = self.tracks.setdefault(
                detection.track_id,
                MaleTrackState(deque(maxlen=self.settings.male_lock_window)),
            )
            state.probabilities.append(probability)
            state.last_seen_frame = frame_number
            detection.male_probability = probability

    def _best_candidate(self, detections: list[Detection]) -> Detection | None:
        best: Detection | None = None
        best_score = -1.0
        for detection in detections:
            state = self.tracks.get(detection.track_id)
            if state is None or len(state.probabilities) < self.settings.male_lock_min_hits:
                continue
            score = sum(state.probabilities) / len(state.probabilities)
            if score >= self.settings.male_lock_threshold and score > best_score:
                best = detection
                best_score = score
        return best

    @staticmethod
    def _by_id(detections: list[Detection], track_id: int | None) -> Detection | None:
        for detection in detections:
            if detection.track_id == track_id:
                return detection
        return None


def load_detector(settings: Settings):
    if not Path(settings.detector_model).exists():
        raise FileNotFoundError(f"Detector model not found: {settings.detector_model}")
    from ultralytics import YOLO

    return YOLO(str(settings.detector_model))


def parse_yolo_detections(result) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or boxes.xyxy is None:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confs = boxes.conf.detach().cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))
    ids = boxes.id.detach().cpu().numpy().astype(int) if boxes.id is not None else np.arange(len(xyxy))

    detections: list[Detection] = []
    for box, confidence, track_id in zip(xyxy, confs, ids):
        x1, y1, x2, y2 = [int(round(value)) for value in box[:4]]
        detections.append(Detection(int(track_id), (x1, y1, x2, y2), float(confidence)))
    return detections
