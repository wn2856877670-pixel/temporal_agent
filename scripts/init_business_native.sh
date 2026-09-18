#!/usr/bin/env bash
# Native alternative for AutoDL containers without a Docker daemon. Run as root.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [[ ! -f .env ]]; then
  for name in MYSQL_PASSWORD MYSQL_ROOT_PASSWORD REDIS_PASSWORD RABBITMQ_PASSWORD INTERNAL_API_TOKEN; do
    printf '%s=%s\n' "$name" "$(openssl rand -hex 24)" >> .env
  done
  printf 'MYSQL_USER=deer\nRABBITMQ_USER=deer\nDEER_MEDIA_ROOT=/var/lib/deer-business\n' >> .env
fi
set -a
source .env
set +a
umask 022
mkdir -p logs
install -d -m 755 "$DEER_MEDIA_ROOT"
service mysql start
mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS deer_business CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'deer'@'localhost' IDENTIFIED BY '$MYSQL_PASSWORD';
GRANT ALL ON deer_business.* TO 'deer'@'localhost';
SQL
# A dedicated Redis instance avoids modifying an existing Redis configuration.
if ! redis-cli -p 6380 ping >/dev/null 2>&1; then
  redis-server --port 6380 --bind 127.0.0.1 --requirepass "$REDIS_PASSWORD" --appendonly yes --dir "$DEER_MEDIA_ROOT" --daemonize yes --pidfile "$PWD/logs/redis_business.pid"
fi
if ! grep -q '^REDIS_PORT=' .env; then printf 'REDIS_PORT=6380\n' >> .env; fi
export RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS='+S 2:2'
export RABBITMQ_CTL_ERL_ARGS='+S 1:1'
if ! rabbitmq-diagnostics -q ping >/dev/null 2>&1; then rabbitmq-server -detached; fi
for i in $(seq 1 60); do rabbitmq-diagnostics -q check_running >/dev/null 2>&1 && break; sleep 2; done
rabbitmq-diagnostics -q check_running >/dev/null
if ! rabbitmqctl list_users -q | awk '{print $1}' | grep -qx "$RABBITMQ_USER"; then
  rabbitmqctl add_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" >/dev/null
fi
rabbitmqctl set_permissions -p / "$RABBITMQ_USER" '.*' '.*' '.*' >/dev/null
rabbitmqctl set_user_tags "$RABBITMQ_USER" administrator >/dev/null
if [[ -f /etc/rabbitmq/enabled_plugins ]]; then chmod 644 /etc/rabbitmq/enabled_plugins; fi
rabbitmq-plugins enable rabbitmq_management >/dev/null
echo 'Business infrastructure initialized. Secrets are in .env (not committed).'
