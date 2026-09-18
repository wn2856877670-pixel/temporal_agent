#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export RABBITMQ_CTL_ERL_ARGS='+S 1:1'
mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS deer_business_test CHARACTER SET utf8mb4;
GRANT ALL ON deer_business_test.* TO 'deer'@'localhost';
SQL
if ! rabbitmqctl list_vhosts -q | grep -qx deer_test; then rabbitmqctl add_vhost deer_test >/dev/null; fi
rabbitmqctl set_permissions -p deer_test "$RABBITMQ_USER" '.*' '.*' '.*' >/dev/null
export MYSQL_URL='jdbc:mysql://127.0.0.1:3306/deer_business_test?connectionTimeZone=Asia/Shanghai'
export SERVER_PORT=6021 INTERNAL_API_URL=http://127.0.0.1:6021 RABBITMQ_VHOST=deer_test
export DEER_MEDIA_ROOT=/var/lib/deer-business-test RETRY_DELAY_MS=2000
install -d -m 755 "$DEER_MEDIA_ROOT"
java -Xms64m -Xmx256m -XX:ActiveProcessorCount=2 -jar backend/target/deer-backend-1.0.0.jar > logs/business_test_api.log 2>&1 &
test_pid=$!
trap 'kill "$test_pid" 2>/dev/null || true; wait "$test_pid" 2>/dev/null || true' EXIT
for i in $(seq 1 90); do
  curl -sf "$INTERNAL_API_URL/api/statistics/overview" >/dev/null && break
  kill -0 "$test_pid" || { tail -40 logs/business_test_api.log; exit 1; }
  sleep 2
done
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=160x90:rate=10 -t 2 -c:v libx264 -pix_fmt yuv420p -movflags +faststart -y "$DEER_MEDIA_ROOT/fixture.mp4"
python scripts/verify_business.py "$DEER_MEDIA_ROOT/fixture.mp4"
MYSQL_PWD="$MYSQL_PASSWORD" mysql -udeer deer_business_test -e 'SHOW TABLES; SELECT status,attempts,event_count FROM analysis_task ORDER BY id DESC LIMIT 3;'
REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -p "${REDIS_PORT:-6379}" --scan --pattern 'deer:task:*' | head -5
