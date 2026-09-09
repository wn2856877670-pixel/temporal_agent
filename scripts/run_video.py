from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deer_behavior.config import load_settings
from deer_behavior.pipeline import run_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deer abnormal behavior detection on one video.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", default=Path("configs/config.json"), type=Path)
    args = parser.parse_args()

    settings = load_settings(args.config)
    summary = run_video(args.input, args.output, settings)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
