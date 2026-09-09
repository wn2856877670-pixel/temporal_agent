#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/root/autodl-tmp/deer_behavior_clean}"
APP_PORT="${APP_PORT:-6011}"
PUBLIC_PORT="${PUBLIC_PORT:-6008}"
CONFIG_PATH="${CONFIG_PATH:-configs/config.json}"
MEDIA_ROOT="${MEDIA_ROOT:-/var/www/deer_behavior_media}"
STATIC_ROOT="${STATIC_ROOT:-/var/www/deer_behavior_static}"

cd "$PROJECT_ROOT"
mkdir -p logs

source /root/miniconda3/etc/profile.d/conda.sh
conda activate deer
export PYTHONPATH="$PROJECT_ROOT/src"
export DEER_NGINX_MEDIA_ROOT="$MEDIA_ROOT"

if ! command -v nginx >/dev/null 2>&1; then
    echo "nginx is not installed. Install it first: apt-get update && apt-get install -y nginx"
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "warning: ffmpeg is not installed; browser video conversion will fall back to OpenCV WebM."
fi

mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"
cp -a "$PROJECT_ROOT/src/deer_behavior/static/." "$STATIC_ROOT/"
find outputs -type f \( -name '*_browser.mp4' -o -name '*_browser.webm' \) -exec cp --parents {} "$MEDIA_ROOT" \; 2>/dev/null || true

nohup python -m deer_behavior.app \
    --host 127.0.0.1 \
    --port "$APP_PORT" \
    --config "$CONFIG_PATH" \
    > logs/fastapi.log 2>&1 &

sleep 2

if nginx -t -c "$PROJECT_ROOT/deploy/nginx_deer_behavior.conf"; then
    nginx -s reload -c "$PROJECT_ROOT/deploy/nginx_deer_behavior.conf" 2>/dev/null \
        || nginx -c "$PROJECT_ROOT/deploy/nginx_deer_behavior.conf"
fi

echo "FastAPI is listening on 127.0.0.1:${APP_PORT}"
echo "Nginx is listening on 0.0.0.0:${PUBLIC_PORT}"
