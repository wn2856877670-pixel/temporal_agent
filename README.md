# Temporal Agent Benchmark System

A benchmark framework for comparing **event-driven** vs **fixed-interval** LLM invocation strategies in video understanding tasks.

## The Problem

Current AI video understanding pipelines typically invoke LLMs at fixed intervals (every N frames) regardless of content. This leads to:
- **Wasted inference** on static scenes
- **Missed events** between sampling points
- **Poor temporal grounding** in generated summaries

## Our Approach

We propose a three-layer architecture that separates:

1. **Perception Layer** - Continuous, cheap detection (YOLO)
2. **State Layer** - Temporal event tracking (enter/exit/interact)
3. **Reasoning Layer** - Sparse, event-driven LLM invocation

The key insight: **invoke the LLM only when meaningful state changes occur**, not on a fixed schedule.

## Architecture

```
VIDEO → YOLO Detection → Object Tracking → Event Detection → Trigger → LLM Agent
             ↓                   ↓                ↓              ↓
         (cached)          (IoU-based)      (ENTER/EXIT)    (fixed vs event)
```

## Installation

```bash
# Clone and enter directory
cd temporal_agent

# Install dependencies with uv
uv sync

# Create .env file with your API key (optional, for LLM calls)
echo "OPENAI_API_KEY=your-key-here" > .env
```

## Quick Start

### Run Synthetic Benchmark (No Setup Required)

```bash
# Compare triggers on synthetic video (300 frames, no LLM calls)
uv run python main.py benchmark --video synthetic --frames 300 --dry-run
```

This generates a synthetic video with known events (objects entering/exiting) and compares:
- **Fixed Trigger**: Invokes every 100 frames
- **Event-Driven Trigger**: Invokes only on state changes

### Run with Real Video

```bash
# Place your video in data/ folder, then:
uv run python main.py benchmark --video data/your_video.mp4
```

### Generate Synthetic Test Video

```bash
# Create a .mp4 file with known ground truth events
uv run python main.py generate-synthetic --frames 500 --output data/test.mp4
```

## CLI Commands

### `benchmark`

Compare fixed vs event-driven triggers.

```bash
uv run python main.py benchmark [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--video` | `synthetic` | Video source: `synthetic` or path to file |
| `--frames` | 300 | Frame count for synthetic video |
| `--fixed-interval` | 100 | Frames between fixed invocations |
| `--event-cooldown` | 2.0 | Seconds before re-triggering same object |
| `--dry-run/--no-dry-run` | `True` | Skip actual LLM calls |

### `run`

Process a video with a specific trigger and get agent summaries.

```bash
uv run python main.py run VIDEO [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--trigger` | `event` | Trigger type: `fixed` or `event` |
| `--interval` | 100 | Fixed trigger interval |
| `--cooldown` | 2.0 | Event trigger cooldown |
| `--model` | `gpt-4o-mini` | LLM model to use |

### `generate-synthetic`

Generate a test video with known events.

```bash
uv run python main.py generate-synthetic [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--frames` | 300 | Number of frames |
| `--output` | `synthetic_test.mp4` | Output file path |
| `--fps` | 30 | Frames per second |

## Project Structure

```
temporal_agent/
├── main.py                 # CLI entry point
├── src/
│   ├── config.py           # Settings (API keys, thresholds)
│   ├── models.py           # Pydantic data models
│   ├── perception/
│   │   ├── video_source.py      # CV2 + Synthetic video sources
│   │   ├── detector.py          # YOLO with caching
│   │   └── synthetic_detector.py # Ground truth for testing
│   ├── state/
│   │   ├── tracker.py           # Object tracking + event emission
│   │   └── event_buffer.py      # Sliding window context
│   ├── triggers/
│   │   ├── base.py              # Trigger protocol
│   │   ├── fixed.py             # Every-N-frames baseline
│   │   └── event_driven.py      # Event-based with cooldown
│   ├── agent/
│   │   └── temporal_agent.py    # Pydantic AI agent
│   └── benchmark/
│       ├── runner.py            # Pipeline orchestration
│       └── metrics.py           # Comparison metrics
├── data/                   # Place videos here
│   └── README.md
└── tests/                  # Unit tests
```

## Configuration

Create a `.env` file or set environment variables:

```bash
# Required for LLM calls (not needed for --dry-run)
OPENAI_API_KEY=sk-...

# Optional overrides
DEFAULT_MODEL=gpt-4o-mini
YOLO_MODEL=yolo11n.pt
YOLO_CONFIDENCE_THRESHOLD=0.5
FIXED_TRIGGER_INTERVAL=100
EVENT_TRIGGER_COOLDOWN=2.0
CACHE_DIR=.cache
```

## How It Works

### Detection Caching

YOLO detections are cached to `.cache/` to ensure reproducibility. Both trigger types consume the **same cached detections**, so comparisons are fair.

```bash
# Clear cache to re-run YOLO
rm -rf .cache/
```

### Event Types

The tracker emits these event types:

| Event | Description |
|-------|-------------|
| `NEW_CLASS` | First time seeing this object class |
| `OBJECT_ENTER` | Object appeared in frame |
| `OBJECT_EXIT` | Object left frame |
| `OBJECT_INTERACT` | Two objects' bboxes overlap |

### Deduplication Cooldown

Event-driven triggers include a cooldown to prevent re-triggering on the same object:

```
Frame 10: Person enters → TRIGGER
Frame 11: Person still there → (cooldown, no trigger)
...
Frame 70: Person still there → (cooldown expired, but no new event)
Frame 100: Car enters → TRIGGER
```

## Metrics

| Metric | Description |
|--------|-------------|
| **Invocation Count** | Number of LLM calls |
| **Invocation Rate** | Percentage of frames triggering invocation |
| **Invocation Reduction** | `(1 - event/fixed) * 100%` |
| **Temporal Precision** | Accuracy of event timestamps vs ground truth |
| **Recall** | Percentage of ground truth events detected |

## Example Output

```
============================================================
BENCHMARK COMPARISON RESULTS
============================================================

Total frames processed: 300

Fixed Interval Trigger:
  - Invocations: 3
  - Rate: 1.00%

Event-Driven Trigger:
  - Invocations: 4
  - Rate: 1.33%
  - Events detected: 8

Temporal Precision (Event-Driven):
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric         ┃ Value   ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Precision      │ 62.50%  │
│ Recall         │ 100.00% │
│ F1 Score       │ 76.92%  │
│ Matched Events │ 5/5     │
└────────────────┴─────────┘
```

## Development

```bash
# Run linting
uv run ruff check .

# Run tests (when available)
uv run pytest tests/ -v
```

## License

MIT
