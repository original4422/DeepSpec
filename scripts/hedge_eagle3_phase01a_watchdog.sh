#!/usr/bin/env bash
# Read-only Phase 01A watchdog for worker identity, acquisition heartbeat, and
# the exact-eight-GPU operational keepalive.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER_PID="${1:-}"
WORKER_ID="${2:-4099544}"
STATE_DIR="${3:-/tmp/deepspec-hedge-v4-eagle3/phase-01a-acquisition}"
INTERVAL_SECONDS="${DEEPSPEC_EAGLE3_PHASE01A_WATCHDOG_INTERVAL:-600}"
STATUS_PATH="$STATE_DIR/watchdog_status.json"
LOG_PATH="$STATE_DIR/watchdog.log"

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned Eagle3 worker: $WORKER_ID" >&2
  exit 2
fi
if ! [[ "$OWNER_PID" =~ ^[1-9][0-9]*$ ]]; then
  echo "owner PID must be a positive integer" >&2
  exit 2
fi
if ! [[ "$INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "watchdog interval must be a positive integer" >&2
  exit 2
fi
case "$STATE_DIR" in
  /tmp/deepspec-hedge-v4-eagle3/phase-01a-acquisition)
    ;;
  *)
    echo "refusing watchdog state outside Phase 01A scratch" >&2
    exit 2
    ;;
esac

mkdir -p "$STATE_DIR"
printf '%s\n' "$$" >"$STATE_DIR/watchdog.pid"
printf '%s\n' "$(ps -o pgid= -p $$ | tr -d ' ')" \
  >"$STATE_DIR/watchdog.pgid"
printf '%s\n' "$(ps -o sid= -p $$ | tr -d ' ')" \
  >"$STATE_DIR/watchdog.sid"

write_status() {
  local health="$1"
  local detail="$2"
  local temporary="$STATUS_PATH.tmp-$$"
  printf \
    '{"schema_version":1,"session":"hedge-v4-eagle3",'\
'"worker_id":"4099544","owner_pid":%s,"watchdog_pid":%s,'\
'"status":"%s","detail":%s,"updated_at":"%s"}\n' \
    "$OWNER_PID" \
    "$$" \
    "$health" \
    "$(printf '%s' "$detail" | python3 "$REPO_ROOT/scripts/hedge_eagle3_phase01a_json_string.py")" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >"$temporary"
  mv "$temporary" "$STATUS_PATH"
}

while kill -0 "$OWNER_PID" 2>/dev/null; do
  set +e
  keepalive_output="$(
    bash "$REPO_ROOT/scripts/hedge_eagle3_keepalive.sh" \
      status "$WORKER_ID" 2>&1
  )"
  keepalive_rc=$?
  set -e
  if [ "$keepalive_rc" -eq 0 ] \
    && grep -q '^HEALTHY .*worker=4099544 ' <<<"$keepalive_output"; then
    write_status "healthy" "$keepalive_output"
    printf '%s watchdog healthy owner_pid=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OWNER_PID" >>"$LOG_PATH"
  else
    write_status "unhealthy" "$keepalive_output"
    printf '%s watchdog unhealthy owner_pid=%s rc=%s\n%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$OWNER_PID" \
      "$keepalive_rc" \
      "$keepalive_output" >>"$LOG_PATH"
  fi

  for _ in $(seq 1 "$INTERVAL_SECONDS"); do
    kill -0 "$OWNER_PID" 2>/dev/null || exit 0
    sleep 1
  done
done
