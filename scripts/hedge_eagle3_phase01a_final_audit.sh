#!/usr/bin/env bash
# Read-only final process and keepalive audit for Phase 01A.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_ID="${1:-4099544}"
STATE_ROOT="/tmp/deepspec-hedge-v4-eagle3/phase-01a-acquisition"
STATE_PATH="$STATE_ROOT/acquisition_state.json"
WATCHDOG_PID_PATH="$STATE_ROOT/launcher_watchdog.pid"

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned Eagle3 worker: $WORKER_ID" >&2
  exit 2
fi
if [ ! -f "$STATE_PATH" ] || [ ! -f "$WATCHDOG_PID_PATH" ]; then
  echo "Phase 01A state or watchdog PID evidence is absent" >&2
  exit 2
fi

readarray -t acquisition_pids < <(
  python3 - "$STATE_PATH" "$WATCHDOG_PID_PATH" <<'PY'
import json
import pathlib
import sys

state = json.loads(pathlib.Path(sys.argv[1]).read_text())
watchdog_pid = int(pathlib.Path(sys.argv[2]).read_text().strip())
if state.get("phase") != "complete" or state.get("status") != "complete":
    raise SystemExit("Phase 01A state is not complete")
print(f"launcher:{int(state['pgid'])}")
print(f"python:{int(state['pid'])}")
print(f"watchdog:{watchdog_pid}")
PY
)

audit_status="PASS"
for record in "${acquisition_pids[@]}"; do
  label="${record%%:*}"
  pid="${record##*:}"
  if [ -d "/proc/$pid" ]; then
    command_line="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    printf 'LIVE label=%s pid=%s command=%s\n' \
      "$label" "$pid" "$command_line"
    audit_status="FAIL"
  else
    printf 'EXITED label=%s pid=%s\n' "$label" "$pid"
  fi
done

bash "$REPO_ROOT/scripts/hedge_eagle3_keepalive.sh" \
  status "$WORKER_ID"

if [ "$audit_status" != "PASS" ]; then
  echo "one or more Phase 01A owned processes remain live" >&2
  exit 1
fi
printf 'PHASE01A_FINAL_PROCESS_AUDIT=PASS worker=%s\n' "$WORKER_ID"
