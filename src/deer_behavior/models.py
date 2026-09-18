from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(19), index=True, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(19), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(19), nullable=True)
    total_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"
    __table_args__ = (UniqueConstraint("task_id", "event_index", name="uq_behavior_event_task_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    male_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    qwen_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    qwen_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    clip_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(19), index=True, nullable=True)
