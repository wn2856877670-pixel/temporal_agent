# Data Directory

Place your video files here for testing.

## Supported Formats
- `.mp4`
- `.avi`
- `.mov`
- Any format supported by OpenCV

## Usage

```bash
# Run with your video
uv run python main.py run data/your_video.mp4

# Benchmark with your video
uv run python main.py benchmark --video data/your_video.mp4
```

## Cache

Detection results are cached in `.cache/` to ensure reproducibility.
Delete the cache if you want to re-run YOLO detection.
