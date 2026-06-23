"""Pipeline runner for deer surveillance video processing."""

import asyncio
import os
from collections import deque
from datetime import datetime
from typing import Generator

import cv2
from rich.console import Console
from rich.progress import Progress

from src.agent.qwen_agent import QwenTemporalAgent
from src.models import AgentOutput, BenchmarkResult, Event, FrameState
from src.perception.detector import CachedDetector
from src.perception.video_source import VideoSource
from src.state.tracker import ObjectTracker


console = Console()


class BenchmarkRunner:
    """Run YOLO filtering, event triggering, video clipping, and Qwen-VL analysis."""

    def __init__(
        self,
        trigger,
        detector: CachedDetector | None = None,
        dry_run: bool = False,
        pre_seconds: int = 5,
        post_seconds: int = 5,
    ):
        self.trigger = trigger
        self.detector = detector or CachedDetector()
        self.dry_run = dry_run
        self.pre_seconds = pre_seconds
        self.post_seconds = post_seconds

        self.tracker = ObjectTracker()
        self.agent = None

        if not dry_run:
            console.print("[cyan]Loading Qwen-VL model...[/cyan]")
            self.agent = QwenTemporalAgent()

    async def run(
        self,
        video_source: VideoSource,
        video_id: str,
        show_progress: bool = True,
    ) -> BenchmarkResult:
        """Process one video and return basic pipeline metrics."""
        self.tracker.reset()
        self.trigger.reset()

        invocations = 0
        invocation_frames: list[int] = []
        agent_outputs: list[AgentOutput] = []
        all_events: list[Event] = []
        total_frames = 0

        frame_generator = self.detector.process_video(
            video_source,
            video_id,
            use_cache=False,
        )
        fps = int(round(video_source.fps)) if video_source.fps > 0 else 30

        if show_progress:
            with Progress() as progress:
                task = progress.add_task(
                    f"[cyan]Processing with {self.trigger.name}...",
                    total=video_source.total_frames,
                )
                async for output in self._process_frames(frame_generator, fps):
                    if output["type"] == "frame":
                        progress.update(task, advance=1)
                        total_frames = output["frame_number"] + 1
                        all_events.extend(output["events"])
                    elif output["type"] == "invocation":
                        invocations += 1
                        invocation_frames.append(output["frame_number"])
                        agent_outputs.append(output["agent_output"])
        else:
            async for output in self._process_frames(frame_generator, fps):
                if output["type"] == "frame":
                    total_frames = output["frame_number"] + 1
                    all_events.extend(output["events"])
                elif output["type"] == "invocation":
                    invocations += 1
                    invocation_frames.append(output["frame_number"])
                    agent_outputs.append(output["agent_output"])

        return BenchmarkResult(
            trigger_type=self.trigger.name,
            total_frames=total_frames,
            total_invocations=invocations,
            agent_outputs=agent_outputs,
            invocation_frames=invocation_frames,
            events_detected=all_events,
        )

    async def _process_frames(
        self,
        frame_states: Generator[FrameState, None, None],
        fps: int,
    ):
        pre_frame_count = max(1, fps * self.pre_seconds)
        post_frame_count = max(1, fps * self.post_seconds)
        frame_buffer = deque(maxlen=pre_frame_count)

        is_recording_after = False
        post_trigger_frames = []

        for frame_state in frame_states:
            events = self.tracker.update(frame_state)

            current_image = getattr(frame_state, "image", None)
            if current_image is not None and not is_recording_after:
                frame_buffer.append(current_image)

            yield {
                "type": "frame",
                "frame_number": frame_state.frame_number,
                "events": events,
            }

            if not is_recording_after and self.trigger.should_invoke(frame_state, events):
                console.print(
                    f"\n[bold yellow]Suspicious event triggered at frame "
                    f"{frame_state.frame_number}; collecting post-event frames...[/bold yellow]"
                )
                is_recording_after = True
                post_trigger_frames = []

            if is_recording_after:
                if current_image is not None:
                    post_trigger_frames.append(current_image)

                if len(post_trigger_frames) >= post_frame_count:
                    all_frames = list(frame_buffer) + post_trigger_frames
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

                    video_path = ""
                    if not self.dry_run and self.agent:
                        video_path = await asyncio.to_thread(
                            self.sync_save_video_util,
                            all_frames,
                            fps,
                            timestamp_str,
                        )
                        console.print(f"[dim]Saved event clip: {video_path}[/dim]")
                        asyncio.create_task(
                            self._background_analyze_only(video_path, timestamp_str)
                        )

                    del all_frames
                    post_trigger_frames.clear()
                    frame_buffer.clear()
                    is_recording_after = False

                    yield {
                        "type": "invocation",
                        "frame_number": frame_state.frame_number,
                        "agent_output": AgentOutput(
                            summary=f"Analysis task launched for {video_path}"
                        ),
                    }

            frame_state.image = None

    async def _background_analyze_only(self, video_path: str, timestamp_str: str):
        """Run Qwen-VL on a saved event clip and write a markdown report."""
        if not video_path:
            return

        prompt = """
你是一套用于梅花鹿监控视频的 AI 预警系统。

请判断该视频片段中是否存在疑似发情行为或异常行为。可疑行为包括：追逐、爬跨、身体近距离重叠、持续嗅闻、惊慌奔跑、倒地，或其他异常运动。正常行为包括：缓慢行走、采食、站立、休息，以及平静的群体聚集。

请按照以下格式返回结果：
[Conclusion]: “发现疑似异常行为” 或 “未发现异常行为”
[Evidence]: 说明可见的运动情况、检测框/空间关系、速度变化，以及是否存在接触迹象。
"""

        try:
            analysis_result = await asyncio.to_thread(
                self.agent.analyze_video,
                video_path,
                prompt,
            )

            console.print(f"\n[bold magenta]Qwen-VL report ({timestamp_str})[/bold magenta]")
            console.print(analysis_result)
            console.print("[bold magenta]================================================[/bold magenta]\n")

            report_path = video_path.replace(".mp4", ".md")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"### Trigger time: {timestamp_str}\n\n")
                f.write(analysis_result)
        except Exception as exc:
            console.print(f"[bold red]Background analysis failed: {exc}[/bold red]")

    def sync_save_video_util(self, frames: list, fps: int, timestamp_str: str) -> str:
        """Save event frames to MP4, preferring H.264 and falling back if unavailable."""
        if not frames:
            return ""

        height, width = frames[0].shape[:2]
        save_dir = os.path.abspath("data/event_records")
        os.makedirs(save_dir, exist_ok=True)

        last_error = None
        for codec in ("avc1", "mp4v"):
            video_path = os.path.join(save_dir, f"event_{timestamp_str}_{codec}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(
                video_path,
                cv2.CAP_FFMPEG,
                fourcc,
                fps,
                (width, height),
            )
            if not writer.isOpened():
                writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
            if not writer.isOpened():
                last_error = f"Could not open VideoWriter with codec {codec}"
                continue

            for frame in frames:
                writer.write(frame)
            writer.release()

            if os.path.exists(video_path) and os.path.getsize(video_path) > 1024:
                if codec != "avc1":
                    console.print(
                        "[yellow]H.264 writer unavailable; saved event clip with mp4v.[/yellow]"
                    )
                return video_path

            last_error = f"VideoWriter with codec {codec} produced an empty file"
            if os.path.exists(video_path):
                os.remove(video_path)

        raise RuntimeError(last_error or "Could not save event video")
