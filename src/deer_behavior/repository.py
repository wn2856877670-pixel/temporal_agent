from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from .config import Settings
from .database import create_session, init_database, resolve_database_path
from .models import BehaviorEvent, VideoTask
from .storage import now_text

logger = logging.getLogger(__name__)


class DeerRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        init_database(settings)

    @property
    def database_path(self) -> Path:
        return resolve_database_path(self.settings)

    def create_task(
        self,
        *,
        task_id: str,
        filename: str | None = None,
        input_path: str | Path | None = None,
        output_path: str | Path | None = None,
        status: str = "queued",
        created_at: str | None = None,
        total_frames: int | None = None,
    ) -> dict | None:
        session = create_session(self.settings)
        if session is None:
            return None
        try:
            task = session.scalar(select(VideoTask).where(VideoTask.task_id == task_id))
            if task is None:
                task = VideoTask(task_id=task_id, created_at=created_at or now_text())
                session.add(task)
            task.filename = filename or task.filename
            task.input_path = _path_text(input_path) or task.input_path
            task.output_path = _path_text(output_path) or task.output_path
            task.status = status
            task.total_frames = total_frames if total_frames is not None else task.total_frames
            session.commit()
            return serialize_task(task)
        except Exception:
            _rollback(session)
            logger.exception("Failed to create video task in SQLite: %s", task_id)
            return None
        finally:
            session.close()

    def update_task(self, task_id: str, **fields: Any) -> dict | None:
        allowed = {
            "filename",
            "input_path",
            "output_path",
            "status",
            "started_at",
            "finished_at",
            "total_frames",
            "processed_frames",
            "event_count",
            "error_message",
        }
        session = create_session(self.settings)
        if session is None:
            return None
        try:
            task = session.scalar(select(VideoTask).where(VideoTask.task_id == task_id))
            if task is None:
                task = VideoTask(task_id=task_id, created_at=now_text())
                session.add(task)
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key in {"input_path", "output_path"}:
                    value = _path_text(value)
                setattr(task, key, value)
            session.commit()
            return serialize_task(task)
        except Exception:
            _rollback(session)
            logger.exception("Failed to update video task in SQLite: %s", task_id)
            return None
        finally:
            session.close()

    def create_event(
        self,
        *,
        task_id: str,
        event_index: int,
        event_type: str | None,
        start_time: float | None,
        end_time: float | None,
        duration: float | None,
        male_track_id: int | None,
        target_track_id: int | None,
        confidence: float | None,
        clip_path: str | Path | None,
        created_at: str | None = None,
    ) -> dict | None:
        session = create_session(self.settings)
        if session is None:
            return None
        try:
            event = session.scalar(
                select(BehaviorEvent).where(
                    BehaviorEvent.task_id == task_id,
                    BehaviorEvent.event_index == event_index,
                )
            )
            if event is None:
                event = BehaviorEvent(task_id=task_id, event_index=event_index, created_at=created_at or now_text())
                session.add(event)
            event.event_type = event_type
            event.start_time = start_time
            event.end_time = end_time
            event.duration = duration
            event.male_track_id = male_track_id
            event.target_track_id = target_track_id
            event.confidence = confidence
            event.clip_path = _path_text(clip_path)
            session.commit()
            return serialize_event(event)
        except Exception:
            _rollback(session)
            logger.exception("Failed to create behavior event in SQLite: %s #%s", task_id, event_index)
            return None
        finally:
            session.close()

    def update_event_qwen(
        self,
        *,
        task_id: str,
        event_index: int,
        qwen_result: str | None,
        qwen_confidence: float | None,
    ) -> dict | None:
        session = create_session(self.settings)
        if session is None:
            return None
        try:
            event = session.scalar(
                select(BehaviorEvent).where(
                    BehaviorEvent.task_id == task_id,
                    BehaviorEvent.event_index == event_index,
                )
            )
            if event is None:
                return None
            event.qwen_result = qwen_result
            event.qwen_confidence = qwen_confidence
            session.commit()
            return serialize_event(event)
        except Exception:
            _rollback(session)
            logger.exception("Failed to update Qwen result in SQLite: %s #%s", task_id, event_index)
            return None
        finally:
            session.close()

    def query_tasks(self, limit: int = 100) -> list[dict]:
        session = create_session(self.settings)
        if session is None:
            return []
        try:
            rows = session.scalars(
                select(VideoTask).order_by(VideoTask.created_at.desc()).limit(_limit(limit))
            ).all()
            return [serialize_task(row) for row in rows]
        except Exception:
            _rollback(session)
            logger.exception("Failed to query video task history from SQLite")
            return []
        finally:
            session.close()

    def query_events(
        self,
        *,
        task_id: str | None = None,
        event_type: str | None = None,
        qwen_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        session = create_session(self.settings)
        if session is None:
            return []
        try:
            stmt = self._event_query(
                task_id=task_id,
                event_type=event_type,
                qwen_result=qwen_result,
                start_date=start_date,
                end_date=end_date,
            )
            rows = session.scalars(
                stmt.order_by(BehaviorEvent.created_at.desc())
                .offset(_offset(offset))
                .limit(_limit(limit))
            ).all()
            return [serialize_event(row) for row in rows]
        except Exception:
            _rollback(session)
            logger.exception("Failed to query behavior event history from SQLite")
            return []
        finally:
            session.close()

    def count_events(
        self,
        *,
        task_id: str | None = None,
        event_type: str | None = None,
        qwen_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        session = create_session(self.settings)
        if session is None:
            return 0
        try:
            stmt = self._event_query(
                task_id=task_id,
                event_type=event_type,
                qwen_result=qwen_result,
                start_date=start_date,
                end_date=end_date,
            ).subquery()
            return int(session.scalar(select(func.count()).select_from(stmt)) or 0)
        except Exception:
            _rollback(session)
            logger.exception("Failed to count behavior events from SQLite")
            return 0
        finally:
            session.close()

    def _event_query(
        self,
        *,
        task_id: str | None = None,
        event_type: str | None = None,
        qwen_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ):
        stmt = select(BehaviorEvent)
        if task_id:
            stmt = stmt.where(BehaviorEvent.task_id == task_id)
        if event_type:
            stmt = stmt.where(BehaviorEvent.event_type == event_type)
        if qwen_result:
            stmt = stmt.where(BehaviorEvent.qwen_result == qwen_result)
        if start_date:
            stmt = stmt.where(BehaviorEvent.created_at >= f"{start_date} 00:00:00")
        if end_date:
            stmt = stmt.where(BehaviorEvent.created_at <= f"{end_date} 23:59:59")
        return stmt

    def get_event(self, event_id: int) -> dict | None:
        session = create_session(self.settings)
        if session is None:
            return None
        try:
            event = session.get(BehaviorEvent, event_id)
            return serialize_event(event) if event else None
        except Exception:
            _rollback(session)
            logger.exception("Failed to query behavior event from SQLite: %s", event_id)
            return None
        finally:
            session.close()

    def statistics_overview(self) -> dict:
        session = create_session(self.settings)
        if session is None:
            return {"total_tasks": 0, "total_events": 0, "total_abnormal": 0, "today_tasks": 0, "today_events": 0, "today_abnormal": 0}
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            total_tasks = session.scalar(select(func.count()).select_from(VideoTask)) or 0
            total_events = session.scalar(select(func.count()).select_from(BehaviorEvent)) or 0
            total_abnormal = (
                session.scalar(
                    select(func.count()).select_from(BehaviorEvent).where(BehaviorEvent.qwen_result == "异常")
                )
                or 0
            )
            today_tasks = (
                session.scalar(select(func.count()).select_from(VideoTask).where(VideoTask.created_at >= f"{today} 00:00:00"))
                or 0
            )
            today_events = (
                session.scalar(
                    select(func.count()).select_from(BehaviorEvent).where(BehaviorEvent.created_at >= f"{today} 00:00:00")
                )
                or 0
            )
            today_abnormal = (
                session.scalar(
                    select(func.count())
                    .select_from(BehaviorEvent)
                    .where(BehaviorEvent.created_at >= f"{today} 00:00:00", BehaviorEvent.qwen_result == "异常")
                )
                or 0
            )
            return {
                "total_tasks": int(total_tasks),
                "total_events": int(total_events),
                "total_abnormal": int(total_abnormal),
                "today_tasks": int(today_tasks),
                "today_events": int(today_events),
                "today_abnormal": int(today_abnormal),
            }
        except Exception:
            _rollback(session)
            logger.exception("Failed to query overview statistics from SQLite")
            return {"total_tasks": 0, "total_events": 0, "total_abnormal": 0, "today_tasks": 0, "today_events": 0, "today_abnormal": 0}
        finally:
            session.close()

    def statistics_daily(self, days: int = 7) -> list[dict]:
        days = max(1, min(int(days or 7), 90))
        start = datetime.now().date() - timedelta(days=days - 1)
        labels = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]
        counts = {label: 0 for label in labels}
        session = create_session(self.settings)
        if session is None:
            return [{"date": label, "count": 0} for label in labels]
        try:
            rows = session.execute(
                select(func.substr(BehaviorEvent.created_at, 1, 10), func.count())
                .where(BehaviorEvent.created_at >= f"{labels[0]} 00:00:00")
                .group_by(func.substr(BehaviorEvent.created_at, 1, 10))
            ).all()
            for day, count in rows:
                if day in counts:
                    counts[day] = int(count)
            return [{"date": label, "count": counts[label]} for label in labels]
        except Exception:
            _rollback(session)
            logger.exception("Failed to query daily statistics from SQLite")
            return [{"date": label, "count": 0} for label in labels]
        finally:
            session.close()

    def statistics_event_types(self) -> list[dict]:
        session = create_session(self.settings)
        if session is None:
            return []
        try:
            rows = session.execute(
                select(BehaviorEvent.event_type, func.count()).group_by(BehaviorEvent.event_type).order_by(func.count().desc())
            ).all()
            return [{"event_type": event_type or "unknown", "count": int(count)} for event_type, count in rows]
        except Exception:
            _rollback(session)
            logger.exception("Failed to query event type statistics from SQLite")
            return []
        finally:
            session.close()

    def delete_task(self, task_id: str) -> None:
        session = create_session(self.settings)
        if session is None:
            return
        try:
            session.execute(BehaviorEvent.__table__.delete().where(BehaviorEvent.task_id == task_id))
            session.execute(VideoTask.__table__.delete().where(VideoTask.task_id == task_id))
            session.commit()
        except Exception:
            _rollback(session)
            logger.exception("Failed to delete SQLite test task: %s", task_id)
        finally:
            session.close()


def serialize_task(task: VideoTask) -> dict:
    return {
        "id": task.id,
        "task_id": task.task_id,
        "filename": task.filename,
        "input_path": task.input_path,
        "output_path": task.output_path,
        "status": task.status,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "total_frames": task.total_frames,
        "processed_frames": task.processed_frames,
        "event_count": task.event_count,
        "error_message": task.error_message,
    }


def serialize_event(event: BehaviorEvent) -> dict:
    return {
        "id": event.id,
        "task_id": event.task_id,
        "event_index": event.event_index,
        "event_type": event.event_type,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "duration": event.duration,
        "male_track_id": event.male_track_id,
        "target_track_id": event.target_track_id,
        "confidence": event.confidence,
        "qwen_result": event.qwen_result,
        "qwen_confidence": event.qwen_confidence,
        "clip_path": event.clip_path,
        "created_at": event.created_at,
    }


def _path_text(path: str | Path | None) -> str | None:
    return str(path) if path is not None else None


def _limit(value: int) -> int:
    try:
        return max(1, min(int(value), 1000))
    except (TypeError, ValueError):
        return 100


def _offset(value: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _rollback(session) -> None:
    try:
        session.rollback()
    except Exception:
        logger.exception("Failed to rollback SQLite session")
