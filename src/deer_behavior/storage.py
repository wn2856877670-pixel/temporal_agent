from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import PROJECT_ROOT


@dataclass
class Paths:
    root: Path = PROJECT_ROOT

    @property
    def uploads(self) -> Path:
        return self.root / "data" / "uploads"

    @property
    def videos(self) -> Path:
        return self.root / "outputs" / "videos"

    @property
    def jobs(self) -> Path:
        return self.root / "outputs" / "jobs"

    @property
    def events(self) -> Path:
        return self.root / "outputs" / "events"

    def ensure(self) -> None:
        for path in (self.uploads, self.videos, self.jobs, self.events):
            path.mkdir(parents=True, exist_ok=True)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JobStore:
    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths()
        self.paths.ensure()

    def create(self, original_name: str, upload_path: Path) -> dict:
        job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        output_path = self.paths.videos / f"{Path(original_name).stem}_{job_id}_result.mp4"
        job = {
            "job_id": job_id,
            "state": "queued",
            "original_name": original_name,
            "upload_path": str(upload_path),
            "output_path": str(output_path),
            "web_output": "",
            "created_at": now_text(),
            "created_at_ts": time.time(),
            "started_at_ts": None,
            "finished_at_ts": None,
            "progress": 0,
            "eta_seconds": None,
            "queue_position": None,
            "events": [],
            "result": {},
        }
        self.save(job)
        return job

    def save(self, job: dict) -> None:
        self.paths.jobs.mkdir(parents=True, exist_ok=True)
        path = self.paths.jobs / f"{job['job_id']}.json"
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, job_id: str) -> dict | None:
        path = self.paths.jobs / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict]:
        jobs = []
        for path in self.paths.jobs.glob("*.json"):
            try:
                jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return sorted(jobs, key=lambda item: item.get("created_at_ts", 0), reverse=True)

    def clear(self) -> None:
        for path in self.paths.jobs.glob("*.json"):
            path.unlink(missing_ok=True)


def safe_upload_name(filename: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(filename).name)
    return safe or "uploaded.mp4"


def media_path(path: str | Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return ""
