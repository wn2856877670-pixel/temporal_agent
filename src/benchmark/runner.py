"""Benchmark runner - orchestrates the full pipeline."""

import asyncio
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
from temporal_agent.src.state.event_buffer_old import EventBuffer
from src.triggers.base import Trigger
from src.agent.temporal_agent import (
    create_temporal_agent,
    invoke_agent,
)


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
        """Initialize benchmark runner.
        
        Args:
            trigger: Trigger implementation to use
            detector: Detection cache (shared across runs)
            model_name: LLM model for agent
            dry_run: If True, don't actually call the LLM
        """
        self.trigger = trigger
        self.detector = detector or CachedDetector()
        self.model_name = model_name or settings.default_model
        self.dry_run = dry_run
        
        self.tracker = ObjectTracker()
        self.event_buffer = EventBuffer()
        
        if not dry_run:
            self.agent = create_temporal_agent(self.model_name)
        else:
            self.agent = None
    
    async def run(
        self,
        video_source: VideoSource,
        video_id: str,
        show_progress: bool = True,
    ) -> BenchmarkResult:
        """Run benchmark on a video.
        
        Args:
            video_source: Video source to process
            video_id: Unique ID for caching
            show_progress: Show progress bar
            
        Returns:
            BenchmarkResult with metrics
        """
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
            video_source, video_id, use_cache=True
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
        """Process frame stream and yield outputs.
        
        Yields dicts with either:
        - {"type": "frame", "frame_number": int, "events": list[Event]}
        - {"type": "invocation", "frame_number": int, "agent_output": AgentOutput|None}
        """
        for frame_state in frame_states:
            # Track objects and detect events
            events = self.tracker.update(frame_state)
            self.event_buffer.add_many(events)
            
            yield {
                "type": "frame",
                "frame_number": frame_state.frame_number,
                "events": events,
            }
            
            # Check if we should invoke agent
            if self.trigger.should_invoke(frame_state, events):
                agent_output = None
                
                if not self.dry_run and self.agent:
                    # Build context and invoke
                    context = self.event_buffer.get_context(
                        current_frame=frame_state.frame_number,
                        current_timestamp=frame_state.timestamp_seconds,
                        active_objects=self.tracker.active_object_classes,
                    )
                    
                    try:
                        agent_output = await invoke_agent(self.agent, context)
                    except Exception as e:
                        console.print(f"[red]Agent error: {e}[/red]")
                
                yield {
                    "type": "invocation",
                    "frame_number": frame_state.frame_number,
                    "agent_output": agent_output,
                }


async def run_comparison(
    video_source: VideoSource,
    video_id: str,
    fixed_interval: int = None,
    event_cooldown: float = None,
    dry_run: bool = True,
    use_synthetic_detector: bool = False,
) -> tuple[BenchmarkResult, BenchmarkResult]:
    """Run both trigger types on the same video.
    
    Args:
        video_source: Video to process
        video_id: Unique ID for caching
        fixed_interval: Frames between fixed invocations
        event_cooldown: Seconds between event re-triggers
        dry_run: Skip actual LLM calls
        use_synthetic_detector: Use ground truth detections (for synthetic video)
        
    Returns:
        (fixed_result, event_result) tuple
    """
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

