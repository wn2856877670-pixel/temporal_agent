#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec python worker/consumer.py "$@"
