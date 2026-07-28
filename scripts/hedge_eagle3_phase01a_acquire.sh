#!/usr/bin/env bash
# Long-running Phase 01A launcher for the assigned Eagle3 worker only.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_ID="${1:-4099544}"
KEEPALIVE_MARKER="${2:-}"
RUN_ID="20260728T211500Z-phase-01a-acquisition-01"
RUN_DIR="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/$RUN_ID"
SCRATCH_ROOT="/tmp/deepspec-hedge-v4-eagle3"
ACQUISITION_ROOT="$SCRATCH_ROOT/phase-01a-acquisition"
LOG="$ACQUISITION_ROOT/acquisition.log"
KEEPALIVE_STATUS="$ACQUISITION_ROOT/keepalive_status_before.txt"
UV_BIN="/home/tiger/.local/bin/uv"
TOOL_ENV="$ACQUISITION_ROOT/tool-venv"
UV_CACHE="$ACQUISITION_ROOT/uv-cache"
PYTHON="${DEEPSPEC_EAGLE3_PHASE01A_PYTHON:-$TOOL_ENV/bin/python}"
WATCHDOG_PID=""

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned Eagle3 worker: $WORKER_ID" >&2
  exit 2
fi
if [ -z "$KEEPALIVE_MARKER" ] || [ ! -f "$KEEPALIVE_MARKER" ]; then
  echo "healthy Phase 01B keepalive marker is required" >&2
  exit 2
fi
mkdir -p "$ACQUISITION_ROOT"

seal_runtime_evidence() {
  local observed_command=""
  if [ -n "$WATCHDOG_PID" ] && kill -0 "$WATCHDOG_PID" 2>/dev/null; then
    if [ -r "/proc/$WATCHDOG_PID/cmdline" ]; then
      observed_command="$(tr '\0' ' ' <"/proc/$WATCHDOG_PID/cmdline")"
    fi
    case "$observed_command" in
      *hedge_eagle3_phase01a_watchdog.sh*4099544*)
        kill -TERM "$WATCHDOG_PID" 2>/dev/null || true
        for _ in $(seq 1 60); do
          kill -0 "$WATCHDOG_PID" 2>/dev/null || break
          sleep 0.25
        done
        if kill -0 "$WATCHDOG_PID" 2>/dev/null; then
          printf '%s verified watchdog required bounded KILL pid=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            "$WATCHDOG_PID" >>"$LOG"
          kill -KILL "$WATCHDOG_PID" 2>/dev/null || true
        fi
        ;;
      *)
        printf '%s refusing to signal unverified watchdog pid=%s cmd=%s\n' \
          "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
          "$WATCHDOG_PID" \
          "$observed_command" >>"$LOG"
        ;;
    esac
  fi
  set +e
  bash "$REPO_ROOT/scripts/hedge_eagle3_keepalive.sh" \
    status "$WORKER_ID" \
    >"$ACQUISITION_ROOT/keepalive_status_after.txt" 2>&1
  set -e
  if [ -d "$RUN_DIR" ]; then
    for source in \
      "$LOG" \
      "$ACQUISITION_ROOT/watchdog.log" \
      "$ACQUISITION_ROOT/watchdog_status.json" \
      "$ACQUISITION_ROOT/keepalive_status_after.txt" \
      "$ACQUISITION_ROOT/acquisition_uv_freeze.txt"; do
      if [ -f "$source" ]; then
        cp "$source" "$RUN_DIR/$(basename "$source")"
      fi
    done
  fi
}
trap seal_runtime_evidence EXIT

bash "$REPO_ROOT/scripts/hedge_eagle3_keepalive.sh" status "$WORKER_ID" \
  >"$KEEPALIVE_STATUS" 2>&1
if ! grep -q '^HEALTHY .*worker=4099544 ' "$KEEPALIVE_STATUS"; then
  echo "independent exact-eight-GPU keepalive status gate failed" >&2
  sed -n '1,240p' "$KEEPALIVE_STATUS" >&2
  exit 1
fi

test -x "$UV_BIN"
export UV_CACHE_DIR="$UV_CACHE"
export UV_PYTHON_DOWNLOADS=never
mkdir -p "$UV_CACHE"
if [ -e "$TOOL_ENV" ]; then
  test -x "$TOOL_ENV/bin/python"
  test -f "$TOOL_ENV/pyvenv.cfg"
else
  "$UV_BIN" venv --python 3.11 "$TOOL_ENV"
fi
"$UV_BIN" pip install \
  --python "$TOOL_ENV/bin/python" \
  "huggingface-hub[hf-xet]==0.36.2" \
  "hf-xet==1.5.0"
"$UV_BIN" pip freeze --python "$TOOL_ENV/bin/python" \
  >"$ACQUISITION_ROOT/acquisition_uv_freeze.txt"
test -x "$PYTHON"
export HF_HOME="$ACQUISITION_ROOT/hf-home"
export HF_HUB_CACHE="$ACQUISITION_ROOT/hf-home/hub"
export HF_XET_CACHE="$ACQUISITION_ROOT/hf-home/xet"
export HF_HUB_DOWNLOAD_TIMEOUT=600
export HF_HUB_ETAG_TIMEOUT=60
export HF_XET_HIGH_PERFORMANCE=1
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TMPDIR="$ACQUISITION_ROOT/tmp"
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$HF_XET_CACHE" "$TMPDIR"

{
  printf '%s launcher_pid=%s pgid=%s sid=%s worker=%s host=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$$" \
    "$(ps -o pgid= -p $$ | tr -d ' ')" \
    "$(ps -o sid= -p $$ | tr -d ' ')" \
    "$WORKER_ID" \
    "$(hostname)"
  printf '%s command=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PYTHON"
} >>"$LOG"

DEEPSPEC_EAGLE3_PHASE01A_WATCHDOG_INTERVAL=600 \
  bash "$REPO_ROOT/scripts/hedge_eagle3_phase01a_watchdog.sh" \
    "$$" "$WORKER_ID" "$ACQUISITION_ROOT" \
    >>"$LOG" 2>&1 &
WATCHDOG_PID=$!
printf '%s\n' "$WATCHDOG_PID" >"$ACQUISITION_ROOT/launcher_watchdog.pid"

"$PYTHON" "$REPO_ROOT/scripts/hedge_eagle3_phase01a_acquire.py" \
  --worker-id "$WORKER_ID" \
  --run-dir "$RUN_DIR" \
  --keepalive-marker "$KEEPALIVE_MARKER" \
  --keepalive-status-evidence "$KEEPALIVE_STATUS" \
  --download-workers 8 \
  --copy-workers 4 \
  2>&1 | tee -a "$LOG"
