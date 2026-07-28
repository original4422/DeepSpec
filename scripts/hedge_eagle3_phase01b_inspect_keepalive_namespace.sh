#!/usr/bin/env bash
# Read-only PID-namespace diagnostics for the registered Eagle3 keepalive.

set -euo pipefail

STATE_DIR="/home/tiger/.deepspec-hedge-v4-eagle3/keepalive"
mapfile -t PID_FILES < <(find "$STATE_DIR" -maxdepth 1 -type f -name '*.pid' -print)
if [ "${#PID_FILES[@]}" -ne 1 ]; then
  echo "expected exactly one PID file" >&2
  exit 2
fi
PID="$(<"${PID_FILES[0]}")"
printf 'pid_file=%s\nnamespace_pid=%s\n' "${PID_FILES[0]}" "$PID"
ps -o pid=,ppid=,pgid=,sid=,lstart=,args= -p "$PID"
grep -E '^(Name|Pid|PPid|Tgid|NSpid):' "/proc/$PID/status"
printf 'pid_namespace='
readlink "/proc/$PID/ns/pid"
printf 'cgroup\n'
sed -n '1,80p' "/proc/$PID/cgroup"
printf 'nvidia_smi_contexts\n'
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory \
  --format=csv,noheader,nounits
printf 'device_users\n'
fuser -v /dev/nvidia0 /dev/nvidia1 /dev/nvidia2 /dev/nvidia3 \
  /dev/nvidia4 /dev/nvidia5 /dev/nvidia6 /dev/nvidia7 \
  /dev/nvidiactl /dev/nvidia-uvm 2>&1 || true
