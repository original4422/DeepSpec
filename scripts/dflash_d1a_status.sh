#!/usr/bin/env bash
# Read-only status for one fixed-format D1A acquisition attempt.

set -euo pipefail

readonly ATTEMPT_ID="${1:-}"
readonly ROOT="/tmp/deepspec-hedge-dflash/d1a/attempts/${ATTEMPT_ID}"
readonly KEEPALIVE_PID_FILE="/tmp/deepspec-hedge-dflash/keepalive/supervisor.pid"

if [[ ! "$ATTEMPT_ID" =~ ^dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "usage: $0 dflash-d1a-primary-YYYYmmddTHHMMSSZ" >&2
  exit 2
fi

test "$(hostname)" = "g340-cd51-4b00-4d69-9088-7ae6-6253"
test -d "$ROOT"

printf '%s\n' '=== heartbeat.json ==='
cat "$ROOT/heartbeat.json"
printf '%s\n' '=== download.log tail ==='
tail -20 "$ROOT/download.log"
printf '%s\n' '=== active partial files ==='
find /tmp/deepspec-hedge-dflash/d1a \
  -type f -name '*.partial' -printf '%p %s bytes\n'
printf '%s\n' '=== keepalive supervisor ==='
readonly KEEPALIVE_PID="$(cat "$KEEPALIVE_PID_FILE")"
[[ "$KEEPALIVE_PID" =~ ^[1-9][0-9]*$ ]]
kill -0 "$KEEPALIVE_PID"
ps -o pid=,pgid=,sid=,etime=,stat=,args= -p "$KEEPALIVE_PID"
