"""Benchmark runner - orchestrates the full pipeline."""

import os
import cv2
import asyncio
from datetime import datetime
from collections import deque
from typing import Generator

from rich.console import Console
from rich.progress import Progress, TaskID

from src.config import settings
from src.models import (
    BenchmarkResult,
    FrameState,
    Event,
    AgentOutput,
)
from src.perception.detector import CachedDetector
from src.perception.video_source import VideoSource
from src.state.tracker import ObjectTracker
from src.state.event_buffer_old import EventBuffer
from src.triggers.base import Trigger

# 【修改】弃用原本的 pydantic_ai agent，引入你的本地 Qwen-VL Agent
# 如果你的文件路径不同，请相应修改 import
from src.agent.qwen_agent import QwenTemporalAgent

console = Console()

class BenchmarkRunner:
    """Orchestrates video processing with a specific trigger.
    
    Handles the full pipeline:
    video -> detection -> tracking -> events -> trigger -> agent
    """
    
    def __init__(
        self,
        trigger: Trigger,
        detector: CachedDetector = None,
        model_name: str = None,
        dry_run: bool = False,
    ):
        self.trigger = trigger
        self.detector = detector or CachedDetector()
        self.model_name = model_name or settings.default_model
        self.dry_run = dry_run
        
        self.tracker = ObjectTracker()
        self.event_buffer = EventBuffer()
        
        # 【修改】初始化 Qwen-VL Agent
        if not dry_run:
            console.print("[cyan]正在加载 Qwen-VL 模型...[/cyan]")
            self.agent = QwenTemporalAgent()
        else:
            self.agent = None

    async def run(
        self,
        video_source: VideoSource,
        video_id: str,
        show_progress: bool = True,
    ) -> BenchmarkResult:
        """Run benchmark on a video."""
        # Reset state
        self.tracker.reset()
        self.event_buffer.clear()
        self.trigger.reset()
        
        # Results collection
        invocations = 0
        invocation_frames: list[int] = []
        agent_outputs: list[AgentOutput] = []
        all_events: list[Event] = []
        total_frames = 0
        
        # Process frames
        frame_generator = self.detector.process_video(
            video_source, video_id, use_cache=False
        )
        
        if show_progress:
            with Progress() as progress:
                task = progress.add_task(
                    f"[cyan]Processing with {self.trigger.name}...",
                    total=video_source.total_frames,
                )
                
                async for output in self._process_frames(
                    frame_generator,
                    video_source.total_frames,
                ):
                    if output["type"] == "frame":
                        progress.update(task, advance=1)
                        total_frames = output["frame_number"] + 1
                        all_events.extend(output["events"])
                    elif output["type"] == "invocation":
                        invocations += 1
                        invocation_frames.append(output["frame_number"])
                        if output["agent_output"]:
                            agent_outputs.append(output["agent_output"])
        else:
            async for output in self._process_frames(
                frame_generator,
                video_source.total_frames,
            ):
                if output["type"] == "frame":
                    total_frames = output["frame_number"] + 1
                    all_events.extend(output["events"])
                elif output["type"] == "invocation":
                    invocations += 1
                    invocation_frames.append(output["frame_number"])
                    if output["agent_output"]:
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
        total_frames: int,
    ):
        """Process frame stream and yield outputs with 60s sliding window."""
        
        # 【新增】状态机与录制参数
        fps = 30  # 建议通过 video_source.fps 获取，这里硬编码为 30
        pre_seconds = 5
        post_seconds = 5
        target_post_frames = fps * post_seconds
        
        # 环形缓存：维持触发前 30 秒的画面
        frame_buffer = deque(maxlen=fps * pre_seconds)
        
        is_recording_after = False
        post_trigger_frames = []

        for frame_state in frame_states:
            # 1. Track objects and detect events
            events = self.tracker.update(frame_state)
            self.event_buffer.add_many(events)
            
            # 【新增】存入原始视频帧到前置缓存（平时悄悄录制）
            # 注意：请确保你的 frame_state 中有存储图像矩阵的属性，例如 .image 或 .frame
            current_image = getattr(frame_state, 'image', None) 
            if current_image is not None and not is_recording_after:
                frame_buffer.append(current_image)
            
            yield {
                "type": "frame",
                "frame_number": frame_state.frame_number,
                "events": events,
            }
            
            # 2. Check if we should trigger
            if not is_recording_after and self.trigger.should_invoke(frame_state, events):
                console.print(f"\n[bold yellow]⚠️ 触发事件 (Frame {frame_state.frame_number})! 开始录制后30秒...[/bold yellow]")
                is_recording_after = True
                post_trigger_frames = []
                
            # 3. 录制触发后的 30 秒画面
            if is_recording_after:
                if current_image is not None:
                    post_trigger_frames.append(current_image)
                
                # 录满指定帧数，完成 60 秒集结！
                # 录满指定帧数，完成 60 秒集结！
                if len(post_trigger_frames) >= target_post_frames:
                    console.print("[bold green]✅ 60秒视频集结完毕，正在写入硬盘释放内存...[/bold green]")
                    
                    # 取出所有的帧
                    all_frames = list(frame_buffer) + post_trigger_frames
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    if not self.dry_run and self.agent:
                        # 【核心保命改动 1】：在这里 AWAIT，强制主程序停下 2 秒钟，把视频存进硬盘！
                        video_path = await asyncio.to_thread(
                            self.sync_save_video_util, all_frames, fps, timestamp_str
                        )
                        console.print(f"[dim]💾 视频已保存至: {video_path}[/dim]")
                        
                        # 【核心保命改动 2】：创建后台分析任务时，**只传文本路径**，绝不传数组！
                        asyncio.create_task(
                            self._background_analyze_only(video_path, timestamp_str)
                        )
                    
                    # 【核心保命改动 3】：立刻物理摧毁这个 3.3GB 的内存核弹！
                    del all_frames
                    post_trigger_frames.clear()
                    frame_buffer.clear()
                    
                    # 记录一次 Agent Invocation
                    yield {
                        "type": "invocation",
                        "frame_number": frame_state.frame_number,
                        "agent_output": AgentOutput(summary="Async task launched"), 
                    }
                    
                    # 状态机复位
                    is_recording_after = False
                    #post_trigger_frames = []
                    #frame_buffer.clear()
            frame_state.image = None  # 及时释放帧数据，防止内存积压
    async def _background_analyze_only(self, video_path: str, timestamp_str: str):
        """只负责调用大模型，绝对轻量级的后台任务"""
        try:
            prompt = """
你是一个用于自动化监测梅花鹿行为的 AI 预警系统。你的核心任务是识别画面中是否出现“疑似发情或异常”的行为。若画面出现可疑迹象（如追逐、爬跨、闻嗅），可判定为“异常”
请严格按照以下格式输出你的分析报告：
【结论】：（必须是以下两种之一）
1. 🚨 发现疑似发情/异常行为！
2. ✅ 未发现异常，鹿群状态正常。
【判定依据】：说明你做出上述结论的原因。
"""
            # 在独立线程运行大模型推理
            analysis_result = await asyncio.to_thread(
                self.agent.analyze_video, video_path, prompt
            )
            
            console.print(f"\n[bold magenta]🦌 === Qwen-VL 分析报告 ({timestamp_str}) ===[/bold magenta]")
            console.print(analysis_result)
            console.print("[bold magenta]================================================[/bold magenta]\n")

            report_path = video_path.replace(".mp4", ".md")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"### 🕒 触发时间: {timestamp_str}\n\n")
                f.write(analysis_result)
            
        except Exception as e:
            console.print(f"[bold red]❌ 后台分析任务出错: {str(e)}[/bold red]")
    def sync_save_video_util(self, frames: list, fps: int, timestamp_str: str) -> str:
        """同步保存视频，纯 CPU 密集型任务"""
        if not frames:
            return ""
        
        height, width = frames[0].shape[:2]
        save_dir = os.path.abspath("data/event_records")
        os.makedirs(save_dir, exist_ok=True)
        
        # 使用最标准的 mp4v 编码，消除 l??? 报错
        video_path = os.path.join(save_dir, f"event_{timestamp_str}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'avc1') 
        out = cv2.VideoWriter(video_path, cv2.CAP_FFMPEG, fps, (width, height))
        
        for f in frames:
            out.write(f)
        out.release()
        
        return video_path
                                                                                                                                                                                                                                                                            
        

async def run_comparison(
    video_source: VideoSource,
    video_id: str,
    fixed_interval: int = None,
    event_cooldown: float = None,
    dry_run: bool = True,
    use_synthetic_detector: bool = False,
) -> tuple[BenchmarkResult, BenchmarkResult]:
    """Run both trigger types on the same video."""
    from src.triggers.fixed import FixedIntervalTrigger
    from temporal_agent.src.triggers.event_driven_new import EventDrivenTrigger
    from src.perception.video_source import SyntheticVideoSource
    from src.perception.synthetic_detector import SyntheticDetector
    
    # Choose detector based on video type
    if use_synthetic_detector and isinstance(video_source, SyntheticVideoSource):
        detector = SyntheticDetector(video_source)
        console.print("[dim]Using synthetic detector (ground truth detections)[/dim]")
    else:
        detector = CachedDetector()
        console.print("[dim]Using YOLO detector with caching[/dim]")
    
    # Run fixed trigger
    fixed_trigger = FixedIntervalTrigger(
        interval=fixed_interval or settings.fixed_trigger_interval
    )
    fixed_runner = BenchmarkRunner(
        trigger=fixed_trigger,
        detector=detector,
        dry_run=dry_run,
    )
    
    console.print("\n[bold]Running Fixed Interval Trigger...[/bold]")
    fixed_result = await fixed_runner.run(video_source, video_id)
    
    # Run event trigger
    event_trigger = EventDrivenTrigger(
        cooldown_seconds=event_cooldown or settings.event_trigger_cooldown
    )
    event_runner = BenchmarkRunner(
        trigger=event_trigger,
        detector=detector,
        dry_run=dry_run,
    )
    
    console.print("\n[bold]Running Event-Driven Trigger...[/bold]")
    event_result = await event_runner.run(video_source, video_id)
    
    return fixed_result, event_result