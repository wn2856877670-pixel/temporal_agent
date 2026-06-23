"""CLI entry point for the temporal agent benchmark system."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.config import settings
from src.perception.video_source import CV2VideoSource, SyntheticVideoSource
from src.perception.detector import CachedDetector
from src.benchmark.runner_new import run_comparison, BenchmarkRunner
from src.benchmark.metrics import ComparisonMetrics, calculate_temporal_precision
from src.triggers.fixed import FixedIntervalTrigger
from src.triggers.event_driven_new import EventDrivenTrigger


async def _run_and_wait_background_tasks(coro):
    """运行主任务，并在结束后等待所有后台的大模型任务完成"""
    result = await coro
    
    # 查找所有正在运行的后台任务
    pending_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending_tasks:
        console.print(f"\n[bold yellow]⏳ 视频流虽已结束，但还有 {len(pending_tasks)} 个 Qwen-VL 分析任务正在后台运行！[/bold yellow]")
        console.print("[bold yellow]🧠 大模型正在疯狂思考中，请勿关闭程序...[/bold yellow]")
        # 强制阻塞，等待大模型输出报告
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        console.print("[bold green]✅ 所有后台分析任务已全部完成！[/bold green]")
        
    return result
app = typer.Typer(
    name="temporal-agent",
    help="Benchmark event-driven vs fixed-interval LLM invocation for video understanding",
)
console = Console()


@app.command()
def benchmark(
    video: str = typer.Option(
        "synthetic",
        help="Video source: 'synthetic' or path to video file",
    ),
    frames: int = typer.Option(
        300,
        help="Number of frames for synthetic video",
    ),
    fixed_interval: int = typer.Option(
        100,
        help="Frames between fixed trigger invocations",
    ),
    event_cooldown: float = typer.Option(
        2.0,
        help="Seconds before same object can re-trigger",
    ),
    dry_run: bool = typer.Option(
        True,
        help="Skip actual LLM calls (measure invocation counts only)",
    ),
):
    """Run benchmark comparing fixed vs event-driven triggers."""
    console.print("[bold cyan]Temporal Agent Benchmark[/bold cyan]")
    console.print("=" * 50)
    
    # Create video source
    if video == "synthetic":
        console.print(f"\n[yellow]Using synthetic video ({frames} frames)[/yellow]")
        video_source = SyntheticVideoSource(num_frames=frames)
        video_id = f"synthetic_{frames}"
        ground_truth = video_source.get_ground_truth_events()
    else:
        video_path = Path(video)
        if not video_path.exists():
            console.print(f"[red]Video not found: {video}[/red]")
            raise typer.Exit(1)
        console.print(f"\n[yellow]Using video: {video}[/yellow]")
        video_source = CV2VideoSource(video_path)
        video_id = video_path.stem
        ground_truth = []
    
    # Update settings
    settings.fixed_trigger_interval = fixed_interval
    settings.event_trigger_cooldown = event_cooldown
    
    # Determine if we should use synthetic detector
    use_synthetic = video == "synthetic"
    
    # Run comparison
    fixed_result, event_result = asyncio.run(
        run_comparison(
            video_source=video_source,
            video_id=video_id,
            fixed_interval=fixed_interval,
            event_cooldown=event_cooldown,
            dry_run=dry_run,
            use_synthetic_detector=use_synthetic,
        )
    )
    
    # Display results
    metrics = ComparisonMetrics(fixed_result, event_result)
    console.print("\n" + metrics.summary())
    
    # Show temporal precision if ground truth available
    if ground_truth:
        console.print("\n[bold]Temporal Precision (Event-Driven):[/bold]")
        precision = calculate_temporal_precision(
            event_result.events_detected,
            ground_truth,
        )
        
        table = Table()
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Precision", f"{precision['precision']:.2%}")
        table.add_row("Recall", f"{precision['recall']:.2%}")
        table.add_row("F1 Score", f"{precision['f1']:.2%}")
        table.add_row("Matched Events", f"{precision['matched']}/{precision['total_gt']}")
        console.print(table)
    
    # Show invocation frames
    console.print("\n[bold]Invocation Frames:[/bold]")
    console.print(f"Fixed: {fixed_result.invocation_frames[:10]}{'...' if len(fixed_result.invocation_frames) > 10 else ''}")
    console.print(f"Event: {event_result.invocation_frames[:10]}{'...' if len(event_result.invocation_frames) > 10 else ''}")


@app.command()
def run(
    video: str = typer.Argument(..., help="Path to video file"),
    trigger: str = typer.Option(
        "event",
        help="Trigger type: 'fixed' or 'event'",
    ),
    interval: int = typer.Option(100, help="Fixed trigger interval"),
    cooldown: float = typer.Option(2.0, help="Event trigger cooldown"),
    model: str = typer.Option("gpt-4o-mini", help="LLM model to use"),
):
    """Run agent on a video file with specified trigger."""
    video_path = Path(video)
    if not video_path.exists():
        console.print(f"[red]Video not found: {video}[/red]")
        raise typer.Exit(1)
    
    video_source = CV2VideoSource(video_path)
    
    if trigger == "fixed":
        trigger_impl = FixedIntervalTrigger(interval=interval)
    else:
        trigger_impl = EventDrivenTrigger(cooldown_seconds=cooldown)
    
    runner = BenchmarkRunner(
        trigger=trigger_impl,
        model_name=model,
        dry_run=False,
    )
    
    console.print(f"[bold]Processing {video} with {trigger_impl.name}...[/bold]")
    
    # 修改后：给它套上一层保护锁
    result = asyncio.run(_run_and_wait_background_tasks(runner.run(video_source, video_path.stem)))
    
    console.print(f"\n[green]Complete![/green]")
    console.print(f"Frames: {result.total_frames}")
    console.print(f"Invocations: {result.total_invocations}")
    
    if result.agent_outputs:
        console.print("\n[bold]Agent Summaries:[/bold]")
        for i, output in enumerate(result.agent_outputs[:5]):
            console.print(f"\n[cyan]Invocation {i+1}:[/cyan]")
            console.print(output.summary)


@app.command()
def generate_synthetic(
    frames: int = typer.Option(300, help="Number of frames"),
    output: str = typer.Option("synthetic_test.mp4", help="Output video path"),
    fps: int = typer.Option(30, help="Frames per second"),
):
    """Generate a synthetic test video file."""
    import cv2
    
    console.print(f"[bold]Generating synthetic video: {output}[/bold]")
    
    source = SyntheticVideoSource(num_frames=frames, fps=float(fps))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output, fourcc, fps, (640, 480))
    
    for frame_num, frame in source.frames():
        writer.write(frame)
    
    writer.release()
    
    console.print(f"[green]Created {output} ({frames} frames at {fps} fps)[/green]")
    
    # Show ground truth events
    console.print("\n[bold]Ground Truth Events:[/bold]")
    for event in source.get_ground_truth_events():
        console.print(f"  {event['type']}: {event['object']} at {event['timestamp']:.2f}s")


if __name__ == "__main__":
    app()
