#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
set -a; source .env; set +a
mkdir -p logs
if [[ -f logs/business_backend.pid ]] && kill -0 "$(cat logs/business_backend.pid)" 2>/dev/null && grep -aq 'deer-backend-1.0.0.jar' "/proc/$(cat logs/business_backend.pid)/cmdline"; then
  echo 'Business backend already running'; exit 0
fi
nohup java -Xms64m -Xmx256m -XX:ActiveProcessorCount=2 -jar backend/target/deer-backend-1.0.0.jar > logs/business_backend.log 2>&1 &
echo $! > logs/business_backend.pid
echo 'Business API starting on 127.0.0.1:6020; see logs/business_backend.log'
