"""CLI entry point for Sika deer video monitoring."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from src.perception.video_source import CV2VideoSource


app = typer.Typer(
    name="deer-monitor",
    help="Process Sika deer surveillance video with YOLO and Qwen-VL.",
)
console = Console()


async def _run_and_wait_background_tasks(coro):
    """Run the video pipeline and wait for Qwen-VL background analysis tasks."""
    result = await coro

    pending_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending_tasks:
        console.print(
            f"\n[bold yellow]Video processing finished; waiting for "
            f"{len(pending_tasks)} Qwen-VL analysis task(s)...[/bold yellow]"
        )
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        console.print("[bold green]All background analysis tasks completed.[/bold green]")

    return result


@app.command()
def run(
    video: str = typer.Argument(..., help="Path to the surveillance video file"),
    cooldown: float = typer.Option(2.0, help="Seconds before another trigger is allowed"),
    iou_threshold: float = typer.Option(
        0.01,
        help="Minimum bbox overlap for suspicious-contact triggering",
    ),
):
    """Run YOLO filtering, suspicious-event trigger, and Qwen-VL analysis."""
    video_path = Path(video)
    if not video_path.exists():
        console.print(f"[red]Video not found: {video}[/red]")
        raise typer.Exit(1)

    from src.benchmark.runner_new import BenchmarkRunner
    from src.triggers.event_driven_new import EventDrivenTrigger

    video_source = CV2VideoSource(video_path)
    trigger = EventDrivenTrigger(
        cooldown_seconds=cooldown,
        iou_threshold=iou_threshold,
    )
    runner = BenchmarkRunner(trigger=trigger, dry_run=False)

    console.print(f"[bold]Processing {video_path} with {trigger.name}...[/bold]")
    result = asyncio.run(
        _run_and_wait_background_tasks(runner.run(video_source, video_path.stem))
    )

    console.print("\n[green]Complete.[/green]")
    console.print(f"Frames processed: {result.total_frames}")
    console.print(f"Suspicious clips generated: {result.total_invocations}")
    console.print("Output directory: data/event_records")


if __name__ == "__main__":
    app()
