#!/usr/bin/env bash
# Sourced by init_business_native.sh; no automatic shutdown or data migration.

redis_persistence_exists() {
  local directory="$1" name
  for name in dump.rdb appendonly.aof appendonlydir; do
    if [[ -e "$directory/$name" || -L "$directory/$name" ]]; then
      return 0
    fi
  done
  return 1
}

ensure_business_redis() {
  local media_dir data_dir reply running_dir
  export REDIS_PORT="${REDIS_PORT:-6380}"
  export REDIS_DATA_DIR="${REDIS_DATA_DIR:-/var/lib/deer-business-redis}"
  : "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
  : "${DEER_MEDIA_ROOT:?DEER_MEDIA_ROOT is required}"
  if [[ ! "$REDIS_PORT" =~ ^[0-9]+$ ]] || ((10#$REDIS_PORT < 1 || 10#$REDIS_PORT > 65535)); then
    echo 'Invalid REDIS_PORT.' >&2
    return 1
  fi
  media_dir="$(realpath -m -- "$DEER_MEDIA_ROOT")" || return 1
  data_dir="$(realpath -m -- "$REDIS_DATA_DIR")" || return 1
  if [[ "$media_dir" == / || "$data_dir" == / || "$data_dir" == "$media_dir" || "$data_dir" == "$media_dir/"* || "$media_dir" == "$data_dir/"* ]]; then
    echo 'Redis and media directories must be separate, non-nested paths (including symlinks).' >&2
    return 1
  fi

  # redis-cli can exit successfully for an error response; require an actual PONG.
  reply="$(REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h 127.0.0.1 -p "$REDIS_PORT" --raw PING 2>&1)" || true
  reply="${reply//$'\r'/}"
  if [[ "$reply" == PONG ]]; then
    running_dir="$(REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h 127.0.0.1 -p "$REDIS_PORT" --raw CONFIG GET dir)" || return 1
    running_dir="${running_dir//$'\r'/}"
    if [[ "$running_dir" != $'dir\n'* ]]; then
      echo 'Cannot verify the running Redis data directory; leaving the instance unchanged.' >&2
      return 1
    fi
    running_dir="$(realpath -m -- "${running_dir#*$'\n'}")" || return 1
    if [[ "$running_dir" != "$data_dir" ]]; then
      echo "Redis is already running in $running_dir, not $data_dir. No changes made to Redis." >&2
      echo 'Follow the Redis isolation section in docs/BUSINESS_ARCHITECTURE.md before retrying.' >&2
      return 1
    fi
    echo "Redis already running on 127.0.0.1:$REDIS_PORT with separate persistence."
    return 0
  fi

  if (exec 3<>"/dev/tcp/127.0.0.1/$REDIS_PORT") 2>/dev/null; then
    echo 'Redis port is occupied but authentication/PING failed; refusing to start another instance.' >&2
    return 1
  fi
  if redis_persistence_exists "$media_dir"; then
    echo 'Legacy Redis persistence still exists in the media directory; refusing an automatic restart or migration.' >&2
    echo 'Follow the Redis isolation section in docs/BUSINESS_ARCHITECTURE.md, keeping all originals.' >&2
    return 1
  fi
  install -d -m 700 -- "$data_dir" || return 1
  redis-server --port "$REDIS_PORT" --bind 127.0.0.1 --requirepass "$REDIS_PASSWORD" \
    --appendonly yes --dir "$data_dir" --daemonize yes --pidfile "$PWD/logs/redis_business.pid" || return 1
  reply="$(REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h 127.0.0.1 -p "$REDIS_PORT" --raw PING)" || return 1
  if [[ "${reply//$'\r'/}" != PONG ]]; then
    echo 'Redis did not become ready; inspect its startup output before retrying.' >&2
    return 1
  fi
}
