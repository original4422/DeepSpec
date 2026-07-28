#!/usr/bin/env bash
# Generic controller defaulting to DSpark's 4-GPU lane; a dedicated wrapper
# may pin exact lane-specific overrides, such as Eagle3's 8-GPU inventory.
# This operational load must never overlap with a model experiment.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${DEEPSPEC_KEEPALIVE_STATE_DIR:-/home/tiger/.deepspec-dspark-keepalive}"
PYTHON="${DEEPSPEC_KEEPALIVE_PYTHON:-${DEEPSPEC_DSPARK_KEEPALIVE_PYTHON:-/home/tiger/venvs/hedge-deepspec/bin/python}}"
LOAD_SCRIPT="$REPO/scripts/keepalive_load.py"
EXPECTED_GPUS="${DEEPSPEC_KEEPALIVE_EXPECTED_GPUS:-4}"
CUDA_DEVICES="${DEEPSPEC_KEEPALIVE_CUDA_VISIBLE_DEVICES:-0,1,2,3}"
MINIMUM_UTILIZATION=40
PLATFORM_THRESHOLD=30
MATRIX_SIZE=8192
STATUS_SAMPLES=10
STATUS_INTERVAL=1
HOST="$(hostname)"
PID_NAMESPACE_INODE="$(stat -Lc '%i' /proc/self/ns/pid)"
STATE_KEY="${HOST}.pidns-${PID_NAMESPACE_INODE}"
LOG="$STATE_DIR/$STATE_KEY.log"
PID_FILE="$STATE_DIR/$STATE_KEY.pid"
PAUSE_FILE="$STATE_DIR/$STATE_KEY.pause"
LOCK_FILE="$STATE_DIR/$STATE_KEY.lock"
ACTION="${1:-status}"
WORKER_ID="${2:-unknown}"

case "$WORKER_ID" in
  ""|*[!A-Za-z0-9._-]*)
    echo "worker ID contains invalid characters" >&2
    exit 2
    ;;
esac

mkdir -p "$STATE_DIR"
exec 9<>"$LOCK_FILE"
flock --exclusive 9

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG"
}

load_process_matches() {
  local pid="${1:-}"
  local pgid sid process_executable expected_executable
  local process_script expected_script
  local -a command_line=()

  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  mapfile -d '' -t command_line <"/proc/$pid/cmdline" 2>/dev/null \
    || return 1
  [ "${#command_line[@]}" -eq 7 ] || return 1
  [ "${command_line[2]}" = "load" ] || return 1
  [ "${command_line[3]}" = "--expected-gpus" ] || return 1
  [ "${command_line[4]}" = "$EXPECTED_GPUS" ] || return 1
  [ "${command_line[5]}" = "--matrix-size" ] || return 1
  [ "${command_line[6]}" = "$MATRIX_SIZE" ] || return 1

  process_executable="$(readlink -f -- "/proc/$pid/exe" 2>/dev/null)" \
    || return 1
  expected_executable="$(readlink -f -- "$PYTHON" 2>/dev/null)" \
    || return 1
  [ "$process_executable" = "$expected_executable" ] || return 1
  process_script="$(readlink -f -- "${command_line[1]}" 2>/dev/null)" \
    || return 1
  expected_script="$(readlink -f -- "$LOAD_SCRIPT" 2>/dev/null)" \
    || return 1
  [ "$process_script" = "$expected_script" ] || return 1

  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  sid="$(ps -o sid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [ "$pgid" = "$pid" ] && [ "$sid" = "$pid" ]
}

current_pid() {
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if load_process_matches "$pid"; then
    printf '%s\n' "$pid"
    return 0
  fi
  return 1
}

wait_for_no_compute_contexts() {
  local attempt rows
  for attempt in $(seq 1 30); do
    if ! rows="$(
      nvidia-smi \
        --query-compute-apps=pid \
        --format=csv,noheader,nounits 2>&1
    )"; then
      echo "cannot verify GPU compute contexts" >&2
      printf '%s\n' "$rows" >&2
      return 1
    fi
    if ! grep -q '[^[:space:]]' <<<"$rows"; then
      return 0
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  echo "residual GPU compute contexts remain" >&2
  printf '%s\n' "$rows" >&2
  return 1
}

require_idle_gpu_inventory() {
  local utilization compute_pids
  utilization="$(
    nvidia-smi \
      --query-gpu=index,utilization.gpu \
      --format=csv,noheader,nounits
  )"
  if ! awk -F, -v expected="$EXPECTED_GPUS" '
    {
      count += 1
      value = $2 + 0
      if (value > 2) busy = 1
    }
    END { exit !(count == expected && !busy) }
  ' <<<"$utilization"; then
    echo "refusing keepalive on a busy or non-${EXPECTED_GPUS}-GPU inventory" >&2
    printf '%s\n' "$utilization" >&2
    return 1
  fi

  compute_pids="$(
    nvidia-smi \
      --query-compute-apps=pid \
      --format=csv,noheader,nounits 2>/dev/null \
      | awk '/^[[:space:]]*[0-9]+[[:space:]]*$/ {print}'
  )"
  if [ -n "$compute_pids" ]; then
    echo "refusing keepalive while GPU compute PIDs exist" >&2
    printf '%s\n' "$compute_pids" >&2
    return 1
  fi
}

run_health_check() {
  local samples="${1:-$STATUS_SAMPLES}"
  "$PYTHON" "$LOAD_SCRIPT" check \
    --expected-gpus "$EXPECTED_GPUS" \
    --minimum-utilization "$MINIMUM_UTILIZATION" \
    --platform-reclamation-threshold "$PLATFORM_THRESHOLD" \
    --samples "$samples" \
    --sample-interval "$STATUS_INTERVAL"
}

terminate_group() {
  local pid="$1"
  local attempt

  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  for attempt in $(seq 1 30); do
    if ! kill -0 -- "-$pid" 2>/dev/null; then
      break
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  if kill -0 -- "-$pid" 2>/dev/null; then
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  wait_for_no_compute_contexts
}

stop_load() {
  local pid
  pid="$(current_pid 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    terminate_group "$pid"
  elif [ -f "$PID_FILE" ]; then
    echo "stale or unverified PID state; checking contexts before cleanup" >&2
    wait_for_no_compute_contexts
  else
    wait_for_no_compute_contexts
  fi
  rm -f -- "$PID_FILE"
}

start_load() {
  local pid report deadline

  if [ -f "$PAUSE_FILE" ]; then
    echo "keepalive is paused; use resume" >&2
    return 1
  fi
  if pid="$(current_pid 2>/dev/null)"; then
    report="$(run_health_check)"
    load_process_matches "$pid"
    echo "HEALTHY on $HOST worker=$WORKER_ID pid=$pid"
    printf '%s\n' "$report"
    return 0
  fi

  rm -f -- "$PID_FILE"
  require_idle_gpu_inventory
  test -x "$PYTHON"
  test -f "$LOAD_SCRIPT"
  log \
    "keepalive start worker=$WORKER_ID host=$HOST expected_gpus=$EXPECTED_GPUS minimum_utilization=$MINIMUM_UTILIZATION platform_threshold=$PLATFORM_THRESHOLD"
  (
    exec 9>&-
    export CUDA_VISIBLE_DEVICES="$CUDA_DEVICES"
    export LD_LIBRARY_PATH="${DEEPSPEC_KEEPALIVE_LD_LIBRARY_PATH:-/usr/local/cuda/compat:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}}"
    exec setsid nohup "$PYTHON" "$LOAD_SCRIPT" load \
      --expected-gpus "$EXPECTED_GPUS" \
      --matrix-size "$MATRIX_SIZE"
  ) >>"$LOG" 2>&1 &
  pid=$!
  printf '%s\n' "$pid" >"$PID_FILE"

  for _ in $(seq 1 100); do
    load_process_matches "$pid" && break
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  if ! load_process_matches "$pid"; then
    echo "keepalive failed to establish the expected process identity" >&2
    terminate_group "$pid" || true
    rm -f -- "$PID_FILE"
    tail -20 "$LOG" >&2 || true
    return 1
  fi

  deadline=$((SECONDS + 300))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! load_process_matches "$pid"; then
      echo "keepalive exited before reaching the utilization floor" >&2
      terminate_group "$pid" || true
      rm -f -- "$PID_FILE"
      tail -20 "$LOG" >&2 || true
      return 1
    fi
    if report="$(run_health_check 3 2>/dev/null)"; then
      load_process_matches "$pid"
      log "keepalive healthy worker=$WORKER_ID report=$report"
      echo "HEALTHY on $HOST worker=$WORKER_ID pid=$pid"
      printf '%s\n' "$report"
      return 0
    fi
    sleep 5
  done

  echo "keepalive did not reach the utilization floor within 300 seconds" >&2
  stop_load
  return 1
}

show_status() {
  local pid report rc unmanaged_rows

  if ! pid="$(current_pid 2>/dev/null)"; then
    unmanaged_rows="$(
      nvidia-smi \
        --query-compute-apps=gpu_uuid,pid \
        --format=csv,noheader,nounits 2>&1
    )" || {
      echo "UNKNOWN_CONTEXT_STATE on $HOST worker=$WORKER_ID"
      printf '%s\n' "$unmanaged_rows" >&2
      return 1
    }
    if grep -q '[^[:space:]]' <<<"$unmanaged_rows"; then
      echo "UNMANAGED_CONTEXTS on $HOST worker=$WORKER_ID"
      printf '%s\n' "$unmanaged_rows"
      return 1
    fi
    if [ -f "$PAUSE_FILE" ]; then
      echo "PAUSED on $HOST worker=$WORKER_ID"
    else
      echo "STOPPED on $HOST worker=$WORKER_ID"
    fi
    return 1
  fi

  set +e
  report="$(run_health_check)"
  rc=$?
  set -e
  if [ "$rc" -eq 0 ] && ! load_process_matches "$pid"; then
    rc=1
    echo "keepalive identity changed during sampling" >&2
  fi
  if [ "$rc" -eq 0 ]; then
    echo "HEALTHY on $HOST worker=$WORKER_ID pid=$pid"
  else
    echo "UNHEALTHY on $HOST worker=$WORKER_ID pid=$pid"
  fi
  printf '%s\n' "$report"
  nvidia-smi \
    --query-gpu=index,utilization.gpu,memory.used \
    --format=csv,noheader
  return "$rc"
}

case "$ACTION" in
  start)
    start_load
    ;;
  status)
    show_status
    ;;
  pause)
    stop_load
    : >"$PAUSE_FILE"
    log "keepalive paused worker=$WORKER_ID"
    echo "PAUSED on $HOST worker=$WORKER_ID; CUDA contexts are clear"
    ;;
  resume)
    rm -f -- "$PAUSE_FILE"
    log "keepalive resume worker=$WORKER_ID"
    start_load
    ;;
  *)
    echo "usage: $0 {start|status|pause|resume} [worker-id]" >&2
    exit 2
    ;;
esac
