from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    detector_model: Path
    male_classifier_model: Path
    qwen_model: Path | None
    tracker_config: str
    device: str
    detect_imgsz: int
    detect_confidence: float
    detect_iou: float
    classify_imgsz: int
    male_class_name: str
    male_lock_threshold: float
    male_lock_min_hits: int
    male_lock_window: int
    classify_stride: int
    target_lost_seconds: float
    near_distance_ratio: float
    overlap_iou_threshold: float
    any_pair_iou_threshold: float
    trigger_min_seconds: float
    cooldown_seconds: float
    event_pre_seconds: float
    event_post_seconds: float
    max_events: int
    enable_qwen: bool
    force_qwen_abnormal: bool
    ffmpeg_path: str
    output_codec: str
    database_enabled: bool
    database_type: str
    database_path: Path


DEFAULTS: dict[str, Any] = {
    "detector_model": "models/deer_detector.pt",
    "male_classifier_model": "models/male_classifier.pt",
    "qwen_model": "",
    "tracker_config": "botsort.yaml",
    "device": "0",
    "detect_imgsz": 640,
    "detect_confidence": 0.45,
    "detect_iou": 0.55,
    "classify_imgsz": 320,
    "male_class_name": "clothed_visible",
    "male_lock_threshold": 0.7,
    "male_lock_min_hits": 5,
    "male_lock_window": 12,
    "classify_stride": 3,
    "target_lost_seconds": 5.0,
    "near_distance_ratio": 0.9,
    "overlap_iou_threshold": 0.02,
    "any_pair_iou_threshold": 0.1,
    "trigger_min_seconds": 0.10,
    "cooldown_seconds": 10.0,
    "event_pre_seconds": 5.0,
    "event_post_seconds": 10.0,
    "max_events": 20,
    "enable_qwen": True,
    "force_qwen_abnormal": False,
    "ffmpeg_path": "",
    "output_codec": "mp4v",
    "database": {
        "enabled": True,
        "type": "sqlite",
        "path": "data/deer_behavior.db",
    },
}


def project_path(value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value)
    if text.startswith("/"):
        return Path(text)
    path = Path(text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_settings(config_path: str | Path | None = None) -> Settings:
    data = DEFAULTS.copy()
    if config_path:
        path = Path(config_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            data.update(json.loads(path.read_text(encoding="utf-8")))
    database = DEFAULTS["database"].copy()
    database.update(data.get("database") or {})

    return Settings(
        detector_model=project_path(data["detector_model"]) or Path(),
        male_classifier_model=project_path(data["male_classifier_model"]) or Path(),
        qwen_model=project_path(data.get("qwen_model")),
        tracker_config=str(data["tracker_config"]),
        device=str(data["device"]),
        detect_imgsz=int(data["detect_imgsz"]),
        detect_confidence=float(data["detect_confidence"]),
        detect_iou=float(data["detect_iou"]),
        classify_imgsz=int(data["classify_imgsz"]),
        male_class_name=str(data["male_class_name"]),
        male_lock_threshold=float(data["male_lock_threshold"]),
        male_lock_min_hits=int(data["male_lock_min_hits"]),
        male_lock_window=int(data["male_lock_window"]),
        classify_stride=max(1, int(data["classify_stride"])),
        target_lost_seconds=float(data["target_lost_seconds"]),
        near_distance_ratio=float(data["near_distance_ratio"]),
        overlap_iou_threshold=float(data["overlap_iou_threshold"]),
        any_pair_iou_threshold=float(data["any_pair_iou_threshold"]),
        trigger_min_seconds=float(data["trigger_min_seconds"]),
        cooldown_seconds=float(data["cooldown_seconds"]),
        event_pre_seconds=float(data["event_pre_seconds"]),
        event_post_seconds=float(data["event_post_seconds"]),
        max_events=int(data["max_events"]),
        enable_qwen=bool(data["enable_qwen"]),
        force_qwen_abnormal=bool(data["force_qwen_abnormal"]),
        ffmpeg_path=str(data.get("ffmpeg_path", "")),
        output_codec=str(data["output_codec"]),
        database_enabled=bool(database.get("enabled", True)),
        database_type=str(database.get("type", "sqlite")),
        database_path=project_path(database.get("path")) or (PROJECT_ROOT / "data" / "deer_behavior.db"),
    )
