from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import cv2

from .config import PROJECT_ROOT


def make_writer(path: Path, fps: float, size: tuple[int, int], codec: str = "mp4v") -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*codec)
    writer = cv2.VideoWriter(str(path), fourcc, max(1.0, fps), size)
    if not writer.isOpened():
        raise RuntimeError(f"VideoWriter failed to open: {path}")
    return writer


def find_ffmpeg(configured_path: str = "") -> str | None:
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return str(path)
    return shutil.which("ffmpeg")


def make_browser_mp4(input_path: Path, ffmpeg_path: str = "") -> Path | None:
    input_path = Path(input_path)
    existing = existing_browser_video(input_path)
    if existing is not None:
        return existing
    if input_path.stem.endswith("_browser") and input_path.exists() and input_path.stat().st_size > 1024:
        return input_path

    ffmpeg = find_ffmpeg(ffmpeg_path)
    if not input_path.exists():
        return None
    if ffmpeg:
        output_path = input_path.with_name(f"{input_path.stem}_browser.mp4")
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True)
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            if output_path.exists() and output_path.stat().st_size > 1024:
                return output_path
    return make_browser_webm(input_path)


def existing_browser_video(input_path: Path) -> Path | None:
    input_path = Path(input_path)
    if input_path.stem.endswith("_browser"):
        mp4 = input_path.with_suffix(".mp4")
        if mp4.exists() and mp4.stat().st_size > 1024:
            return mp4
        return input_path if input_path.exists() and input_path.stat().st_size > 1024 else None
    for suffix in (".mp4", ".webm"):
        candidate = input_path.with_name(f"{input_path.stem}_browser{suffix}")
        if candidate.exists() and candidate.stat().st_size > 1024:
            return candidate
    return None


def make_browser_webm(input_path: Path) -> Path | None:
    input_path = Path(input_path)
    output_path = input_path.with_name(f"{input_path.stem}_browser.webm")
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        return None
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            return None
        for codec in ("VP80", "VP90"):
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*codec),
                max(1.0, fps),
                (width, height),
            )
            if not writer.isOpened():
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frames = 0
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    writer.write(frame)
                    frames += 1
            finally:
                writer.release()
            if frames > 0 and output_path.exists() and output_path.stat().st_size > 1024:
                return output_path
            output_path.unlink(missing_ok=True)
    finally:
        capture.release()
    return None


def publish_media_file(path: Path, media_root: str | Path | None = None) -> Path | None:
    media_root = media_root or os.getenv("DEER_NGINX_MEDIA_ROOT")
    if not media_root:
        return None
    source = Path(path)
    if not source.exists() or not source.is_file():
        return None
    try:
        relative = source.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    target = Path(media_root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime and target.stat().st_size == source.stat().st_size:
        return target
    shutil.copy2(source, target)
    return target
