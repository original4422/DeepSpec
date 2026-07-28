#!/usr/bin/env bash
# Phase 01 worker inventory and a bounded 4-GPU P2P/NCCL probe.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec"
KEEPALIVE="$REPO_ROOT/scripts/keepalive.sh"
PROBE="$REPO_ROOT/scripts/phase01_worker_probe.py"
PYTHON="/home/tiger/venvs/hedge-deepspec/bin/python"
WORKER_ID="${1:?worker ID is required}"
ARTIFACT_DIR="${2:?artifact directory is required}"
PROBE_LABEL="${3:-probe-01}"
MODE="${4:-run}"
LOG="$ARTIFACT_DIR/preflight.log"

case "$WORKER_ID" in
  *[!0-9]*|"")
    echo "invalid worker ID" >&2
    exit 2
    ;;
esac
case "$ARTIFACT_DIR" in
  "$HDFS_ROOT"/runs/*) ;;
  *)
    echo "artifact directory is outside the registered run root" >&2
    exit 2
    ;;
esac
case "$PROBE_LABEL" in
  ""|*[!A-Za-z0-9._-]*)
    echo "invalid probe label" >&2
    exit 2
    ;;
esac
case "$MODE" in
  run|precheck-only) ;;
  *)
    echo "mode must be run or precheck-only" >&2
    exit 2
    ;;
esac

mkdir -p "$ARTIFACT_DIR"
touch "$LOG"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

resume_required=0
probe_pid=""

wait_for_no_contexts() {
  local attempt rows
  for attempt in $(seq 1 30); do
    rows="$(
      nvidia-smi \
        --query-compute-apps=gpu_uuid,pid,process_name \
        --format=csv,noheader,nounits
    )"
    if ! grep -q '[^[:space:]]' <<<"$rows"; then
      return 0
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  log "ERROR residual CUDA contexts remain"
  printf '%s\n' "$rows" | tee -a "$LOG"
  return 1
}

probe_group_matches() {
  local pid="${1:-}" pgid sid cmdline
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  sid="$(ps -o sid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [ "$pgid" = "$pid" ] && [ "$sid" = "$pid" ] || return 1
  cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)" || return 1
  [[ "$cmdline" == *"$PYTHON -m torch.distributed.run"* ]] || return 1
  [[ "$cmdline" == *"$PROBE nccl"* ]]
}

terminate_probe() {
  local pid="${probe_pid:-}" attempt
  if probe_group_matches "$pid"; then
    log "terminating registered probe process group pgid=$pid"
    kill -TERM -- "-$pid" 2>/dev/null || true
    for attempt in $(seq 1 15); do
      if ! kill -0 -- "-$pid" 2>/dev/null; then
        break
      fi
      [ "$attempt" -eq 15 ] || sleep 1
    done
    if kill -0 -- "-$pid" 2>/dev/null; then
      kill -KILL -- "-$pid" 2>/dev/null || true
    fi
  elif [ -n "$pid" ]; then
    log "probe PID no longer matches registered identity; failing closed"
  fi
  probe_pid=""
  wait_for_no_contexts
}

restore_keepalive() {
  if [ "$resume_required" -eq 1 ]; then
    log "restoring operational keepalive after bounded GPU probe"
    set +e
    bash "$KEEPALIVE" resume "$WORKER_ID" \
      2>&1 \
      | tee "$ARTIFACT_DIR/keepalive_resume_${PROBE_LABEL}.txt" \
      | tee -a "$LOG"
    local resume_rc=${PIPESTATUS[0]}
    bash "$KEEPALIVE" status "$WORKER_ID" \
      2>&1 \
      | tee "$ARTIFACT_DIR/keepalive_after_${PROBE_LABEL}.txt" \
      | tee -a "$LOG"
    local status_rc=${PIPESTATUS[0]}
    set -e
    resume_required=0
    if [ "$resume_rc" -ne 0 ] || [ "$status_rc" -ne 0 ]; then
      log "ERROR keepalive restoration or 10x1s health gate failed"
      return 90
    fi
  fi
  return 0
}

on_error() {
  local rc=$?
  log "ERR trap rc=$rc line=${BASH_LINENO[0]:-unknown}"
  return "$rc"
}

on_exit() {
  local rc=$?
  trap - ERR HUP INT TERM EXIT
  set +e
  if [ -n "${probe_pid:-}" ]; then
    terminate_probe
    [ "$?" -eq 0 ] || rc=91
  fi
  if [ "$resume_required" -eq 1 ]; then
    restore_keepalive
    [ "$?" -eq 0 ] || rc=90
  fi
  exit "$rc"
}

trap on_error ERR
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
trap on_exit EXIT

log \
  "Phase 01 remote preflight start worker=$WORKER_ID host=$(hostname) probe=$PROBE_LABEL"
bash "$KEEPALIVE" status "$WORKER_ID" \
  2>&1 \
  | tee "$ARTIFACT_DIR/keepalive_before_${PROBE_LABEL}.txt" \
  | tee -a "$LOG"

"$PYTHON" "$PROBE" baseline \
  --artifact-dir "$ARTIFACT_DIR" \
  --worker-id "$WORKER_ID" \
  --repo-root "$REPO_ROOT" \
  --hdfs-root "$HDFS_ROOT" \
  2>&1 | tee -a "$LOG"

log "validating probe Python and torchrun identity without touching CUDA"
precheck_contexts_before="$(
  nvidia-smi \
    --query-compute-apps=gpu_uuid,pid,process_name \
    --format=csv,noheader,nounits
)"
"$PYTHON" -c '
import importlib.util
import json
import pathlib
import sys
import torch

spec = importlib.util.find_spec("torch.distributed.run")
print(json.dumps({
    "python_executable": sys.executable,
    "python_realpath": str(pathlib.Path(sys.executable).resolve()),
    "python_version": sys.version,
    "torch_version": torch.__version__,
    "torch_path": torch.__file__,
    "torchrun_module": spec.origin if spec else None,
    "cuda_initialized": torch.cuda.is_initialized(),
}, sort_keys=True))
' 2>&1 | tee "$ARTIFACT_DIR/torchrun_identity_${PROBE_LABEL}.json" | tee -a "$LOG"
"$PYTHON" -m torch.distributed.run --help \
  >"$ARTIFACT_DIR/torchrun_help_${PROBE_LABEL}.txt" 2>&1
precheck_contexts_after="$(
  nvidia-smi \
    --query-compute-apps=gpu_uuid,pid,process_name \
    --format=csv,noheader,nounits
)"
if [ "$precheck_contexts_before" != "$precheck_contexts_after" ]; then
  log "ERROR torchrun precheck changed the CUDA context inventory"
  exit 6
fi
log "torchrun identity/help precheck passed; CUDA context inventory unchanged"
if [ "$MODE" = "precheck-only" ]; then
  log "precheck-only mode completed; keepalive was not paused"
  exit 0
fi

log "pausing keepalive immediately before P2P/NCCL probe"
resume_required=1
bash "$KEEPALIVE" pause "$WORKER_ID" \
  2>&1 \
  | tee "$ARTIFACT_DIR/keepalive_pause_${PROBE_LABEL}.txt" \
  | tee -a "$LOG"

wait_for_no_contexts
log "CUDA context inventory is empty; starting bounded 4-rank NCCL probe"

CUDA_VISIBLE_DEVICES=0,1,2,3 \
NCCL_DEBUG=INFO \
setsid "$PYTHON" -m torch.distributed.run \
  --standalone \
  --nproc-per-node=4 \
  "$PROBE" nccl \
  --artifact-dir "$ARTIFACT_DIR" \
  --expected-gpus 4 \
  >"$ARTIFACT_DIR/nccl_probe_${PROBE_LABEL}.log" 2>&1 &
probe_pid=$!
printf '%s\n' "$probe_pid" >"$ARTIFACT_DIR/nccl_probe_${PROBE_LABEL}.pid"
for _ in $(seq 1 50); do
  probe_group_matches "$probe_pid" && break
  kill -0 "$probe_pid" 2>/dev/null || break
  sleep 0.1
done
if ! probe_group_matches "$probe_pid"; then
  log "ERROR torchrun did not establish the registered process-group identity"
  terminate_probe
  exit 7
fi
log "registered bounded NCCL probe pid/pgid/sid=$probe_pid"

deadline=$((SECONDS + 180))
while kill -0 "$probe_pid" 2>/dev/null; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    log "ERROR NCCL probe exceeded 180-second timeout"
    terminate_probe
    exit 8
  fi
  log "NCCL probe heartbeat pid=$probe_pid"
  sleep 5
done
set +e
wait "$probe_pid"
probe_rc=$?
set -e
probe_pid=""

wait_for_no_contexts
log "P2P/NCCL probe exited rc=$probe_rc and CUDA contexts are empty"

set +e
"$PYTHON" "$PROBE" aggregate \
  --artifact-dir "$ARTIFACT_DIR" \
  --expected-gpus 4 \
  2>&1 | tee -a "$LOG"
aggregate_rc=${PIPESTATUS[0]}
set -e

restore_keepalive
if [ "$probe_rc" -ne 0 ] || [ "$aggregate_rc" -ne 0 ]; then
  log "Phase 01 remote preflight GPU probe failed"
  exit 5
fi
log "Phase 01 remote preflight completed successfully"
