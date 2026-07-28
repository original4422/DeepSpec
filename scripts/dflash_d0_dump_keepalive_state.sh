#!/usr/bin/env bash
# Read-only dump of the registered DFlash D0 keepalive state.

set -euo pipefail

STATE_DIR="/tmp/deepspec-hedge-dflash/keepalive"
PID_FILE="$STATE_DIR/supervisor.pid"
PID="$(cat "$PID_FILE")"

[[ "$PID" =~ ^[1-9][0-9]*$ ]]
kill -0 "$PID"

printf '%s\n' '=== runtime_identity.json ==='
cat "$STATE_DIR/runtime_identity.json"
printf '%s\n' '=== process_identity.json ==='
cat "$STATE_DIR/process_identity.json"
printf '%s\n' '=== gpu_identity.csv ==='
cat "$STATE_DIR/gpu_identity.csv"
printf '%s\n' '=== keepalive_gate.json ==='
cat "$STATE_DIR/keepalive_gate.json"
printf '%s\n' '=== keepalive_gpu_samples.csv ==='
cat "$STATE_DIR/keepalive_gpu_samples.csv"
printf '%s\n' '=== supervisor_ps ==='
ps -o pid=,ppid=,pgid=,sid=,lstart=,etime=,stat=,args= -p "$PID"
printf '%s\n' '=== process_group_ps ==='
ps -eo pid=,ppid=,pgid=,sid=,lstart=,etime=,stat=,args= \
  | awk -v pgid="$PID" '$3 == pgid'
printf '%s\n' '=== compute_apps ==='
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory \
  --format=csv,noheader,nounits
printf '%s\n' '=== log_tail ==='
tail -40 "$STATE_DIR/keepalive.log"
