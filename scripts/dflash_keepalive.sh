#!/usr/bin/env bash
# Sustain and verify DFlash lane utilization on exactly 8 GPUs.
#
# This is operational load, never experiment evidence. It may start only after
# a fresh read-only inventory proves the assigned worker has no compute apps.

set -euo pipefail

REPO="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
STATE_DIR="/tmp/deepspec-hedge-dflash/keepalive"
PYTHON="${DEEPSPEC_DFLASH_KEEPALIVE_PYTHON:-$STATE_DIR/venv/bin/python}"
LOAD_SCRIPT="$REPO/scripts/keepalive_load.py"
EXPECTED_GPUS=8
MINIMUM_UTILIZATION=40
PLATFORM_THRESHOLD=30
MATRIX_SIZE=8192
STATUS_SAMPLES=10
STATUS_INTERVAL=1
EXPECTED_WORKER_ID=4099543
WORKER_ID="${2:-}"
ACTION="${1:-status}"
HOST="$(hostname)"
GPU_IDENTITY_FILE="$STATE_DIR/gpu_identity.csv"
SAMPLE_FILE="$STATE_DIR/keepalive_gpu_samples.csv"
SUMMARY_FILE="$STATE_DIR/keepalive_gate.json"
LOG_FILE="$STATE_DIR/keepalive.log"
PID_FILE="$STATE_DIR/supervisor.pid"
IDENTITY_FILE="$STATE_DIR/process_identity.json"
PAUSE_FILE="$STATE_DIR/paused"
LOCK_FILE="$STATE_DIR/control.lock"

if [ "$WORKER_ID" != "$EXPECTED_WORKER_ID" ]; then
  echo "expected worker id $EXPECTED_WORKER_ID, got ${WORKER_ID:-<empty>}" >&2
  exit 2
fi

mkdir -p "$STATE_DIR"
exec 9<>"$LOCK_FILE"
flock --exclusive 9

utc_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

query_gpu_identity() {
  nvidia-smi \
    --query-gpu=index,uuid,name \
    --format=csv,noheader,nounits
}

require_exact_identity() {
  local identity
  identity="$(query_gpu_identity)"
  if ! awk -F, -v expected="$EXPECTED_GPUS" '
    {
      count += 1
      gpu_index = $1 + 0
      name = $3
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
      if (gpu_index != count - 1 || name != "NVIDIA H20") bad = 1
    }
    END { exit !(count == expected && !bad) }
  ' <<<"$identity"; then
    echo "worker GPU identity is not exactly 8 indexed NVIDIA H20 GPUs" >&2
    printf '%s\n' "$identity" >&2
    exit 2
  fi
  printf '%s\n' "$identity" >"$GPU_IDENTITY_FILE"
}

compute_rows() {
  nvidia-smi \
    --query-compute-apps=gpu_uuid,pid,process_name \
    --format=csv,noheader,nounits
}

load_process_matches() {
  local pid="${1:-}"
  local actual_exe expected_exe actual_script expected_script pgid sid
  local -a argv=()

  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  mapfile -d '' -t argv <"/proc/$pid/cmdline" 2>/dev/null || return 1
  [ "${#argv[@]}" -eq 7 ] || return 1
  [ "${argv[1]}" = "$LOAD_SCRIPT" ] || return 1
  [ "${argv[2]}" = "load" ] || return 1
  [ "${argv[3]}" = "--expected-gpus" ] || return 1
  [ "${argv[4]}" = "$EXPECTED_GPUS" ] || return 1
  [ "${argv[5]}" = "--matrix-size" ] || return 1
  [ "${argv[6]}" = "$MATRIX_SIZE" ] || return 1
  actual_exe="$(readlink -f "/proc/$pid/exe" 2>/dev/null)" || return 1
  expected_exe="$(readlink -f "$PYTHON" 2>/dev/null)" || return 1
  [ "$actual_exe" = "$expected_exe" ] || return 1
  actual_script="$(readlink -f "${argv[1]}" 2>/dev/null)" || return 1
  expected_script="$(readlink -f "$LOAD_SCRIPT" 2>/dev/null)" || return 1
  [ "$actual_script" = "$expected_script" ] || return 1
  pgid="$(ps -o pgid= -p "$pid" | tr -d ' ')"
  sid="$(ps -o sid= -p "$pid" | tr -d ' ')"
  [ "$pgid" = "$pid" ] && [ "$sid" = "$pid" ]
}

current_pid() {
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  load_process_matches "$pid" || return 1
  printf '%s\n' "$pid"
}

require_idle() {
  local rows utilization
  rows="$(compute_rows)"
  if grep -q '[^[:space:]]' <<<"$rows"; then
    echo "refusing to start: existing GPU compute applications must end naturally" >&2
    printf '%s\n' "$rows" >&2
    exit 3
  fi
  utilization="$(
    nvidia-smi \
      --query-gpu=index,utilization.gpu \
      --format=csv,noheader,nounits
  )"
  if ! awk -F, -v expected="$EXPECTED_GPUS" '
    {
      count += 1
      if (($1 + 0) != count - 1 || ($2 + 0) > 2) busy = 1
    }
    END { exit !(count == expected && !busy) }
  ' <<<"$utilization"; then
    echo "refusing to start: GPU utilization is not idle" >&2
    printf '%s\n' "$utilization" >&2
    exit 3
  fi
}

collect_gate() {
  local sample timestamp row index utilization memory_used
  printf 'sample,timestamp_utc,gpu_index,utilization_percent,memory_used_mib\n' \
    >"$SAMPLE_FILE"
  for sample in $(seq 1 "$STATUS_SAMPLES"); do
    timestamp="$(utc_now)"
    while IFS=, read -r index utilization memory_used; do
      index="${index//[[:space:]]/}"
      utilization="${utilization//[[:space:]]/}"
      memory_used="${memory_used//[[:space:]]/}"
      printf '%s,%s,%s,%s,%s\n' \
        "$sample" "$timestamp" "$index" "$utilization" "$memory_used" \
        >>"$SAMPLE_FILE"
    done < <(
      nvidia-smi \
        --query-gpu=index,utilization.gpu,memory.used \
        --format=csv,noheader,nounits
    )
    [ "$sample" -eq "$STATUS_SAMPLES" ] || sleep "$STATUS_INTERVAL"
  done

  "$PYTHON" - "$SAMPLE_FILE" "$SUMMARY_FILE" <<'PY'
import csv
import json
import os
import pathlib
import statistics
import sys

sample_path = pathlib.Path(sys.argv[1])
summary_path = pathlib.Path(sys.argv[2])
by_gpu = {index: [] for index in range(8)}
with sample_path.open(newline="") as handle:
    rows = list(csv.DictReader(handle))
for row in rows:
    index = int(row["gpu_index"])
    if index not in by_gpu:
        raise SystemExit(f"unexpected GPU index: {index}")
    by_gpu[index].append(float(row["utilization_percent"]))
if len(rows) != 80 or any(len(values) != 10 for values in by_gpu.values()):
    raise SystemExit("expected exactly 10 samples for each of 8 GPUs")
means = {str(index): statistics.fmean(values) for index, values in by_gpu.items()}
healthy = all(value >= 40.0 for value in means.values())
summary = {
    "schema_version": 1,
    "expected_gpus": 8,
    "sample_count_per_gpu": 10,
    "minimum_mean_utilization_percent": 40.0,
    "platform_reclamation_threshold_percent": 30.0,
    "per_gpu_mean_utilization_percent": means,
    "healthy": healthy,
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
raise SystemExit(0 if healthy else 1)
PY
}

write_identity() {
  local pid="$1" pgid sid argv_json
  pgid="$(ps -o pgid= -p "$pid" | tr -d ' ')"
  sid="$(ps -o sid= -p "$pid" | tr -d ' ')"
  argv_json="$(
    "$PYTHON" - "$pid" <<'PY'
import json
import pathlib
import sys

raw = (pathlib.Path("/proc") / sys.argv[1] / "cmdline").read_bytes()
print(json.dumps([part.decode(errors="replace") for part in raw.split(b"\0") if part]))
PY
  )"
  "$PYTHON" - \
    "$IDENTITY_FILE" \
    "$GPU_IDENTITY_FILE" \
    "$pid" \
    "$pgid" \
    "$sid" \
    "$argv_json" <<'PY'
import csv
import json
import os
import pathlib
import socket
import sys
from datetime import datetime, timezone

path, gpu_identity_path, pid, pgid, sid, argv_json = sys.argv[1:]
pid = int(pid)
clock_ticks = int(os.sysconf("SC_CLK_TCK"))
proc_stat = (pathlib.Path("/proc") / str(pid) / "stat").read_text().split()
boot_time = next(
    int(line.split()[1])
    for line in pathlib.Path("/proc/stat").read_text().splitlines()
    if line.startswith("btime ")
)
started_at = datetime.fromtimestamp(
    boot_time + int(proc_stat[21]) / clock_ticks,
    tz=timezone.utc,
).isoformat().replace("+00:00", "Z")
gpus = []
with pathlib.Path(gpu_identity_path).open(newline="") as handle:
    for raw_index, raw_uuid, raw_name in csv.reader(handle):
        gpus.append(
            {
                "index": int(raw_index.strip()),
                "uuid": raw_uuid.strip(),
                "name": raw_name.strip(),
            }
        )
document = {
    "schema_version": 1,
    "lane": "dflash",
    "worker_id": "4099543",
    "hostname": socket.gethostname(),
    "pid": pid,
    "pgid": int(pgid),
    "sid": int(sid),
    "argv": json.loads(argv_json),
    "expected_gpu_count": 8,
    "cuda_visible_devices": "0,1,2,3,4,5,6,7",
    "physical_gpus": gpus,
    "started_at_utc": started_at,
    "identity_recorded_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
}
pathlib.Path(path).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

wait_for_no_compute_contexts() {
  local attempt rows
  for attempt in $(seq 1 30); do
    rows="$(compute_rows)"
    if ! grep -q '[^[:space:]]' <<<"$rows"; then
      return
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  echo "GPU compute contexts remain after stopping the verified keepalive" >&2
  printf '%s\n' "$rows" >&2
  return 1
}

terminate_verified_group() {
  local pid="$1" attempt
  if ! load_process_matches "$pid"; then
    echo "refusing to signal an unverified process identity: $pid" >&2
    return 1
  fi
  kill -TERM -- "-$pid"
  for attempt in $(seq 1 30); do
    if ! kill -0 -- "-$pid" 2>/dev/null; then
      break
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  if kill -0 -- "-$pid" 2>/dev/null; then
    if ! load_process_matches "$pid"; then
      echo "process identity changed while stopping; refusing SIGKILL" >&2
      return 1
    fi
    kill -KILL -- "-$pid"
  fi
  wait_for_no_compute_contexts
  rm -f "$PID_FILE"
}

start_load() {
  local pid deadline summary
  require_exact_identity
  if [ -f "$PAUSE_FILE" ]; then
    echo "keepalive is paused; use resume" >&2
    exit 3
  fi
  if pid="$(current_pid 2>/dev/null)"; then
    summary="$(collect_gate)"
    load_process_matches "$pid"
    write_identity "$pid"
    echo "HEALTHY worker=$WORKER_ID host=$HOST pid=$pid"
    printf '%s\n' "$summary"
    return
  fi
  require_idle
  test -x "$PYTHON"
  test -f "$LOAD_SCRIPT"
  rm -f "$PID_FILE"
  (
    exec 9>&-
    export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
    export LD_LIBRARY_PATH="/usr/local/cuda/compat:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
    exec setsid nohup "$PYTHON" "$LOAD_SCRIPT" load \
      --expected-gpus "$EXPECTED_GPUS" \
      --matrix-size "$MATRIX_SIZE"
  ) >>"$LOG_FILE" 2>&1 &
  pid=$!
  printf '%s\n' "$pid" >"$PID_FILE"
  deadline=$((SECONDS + 300))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if load_process_matches "$pid"; then
      if summary="$(collect_gate 2>/dev/null)"; then
        load_process_matches "$pid"
        write_identity "$pid"
        echo "HEALTHY worker=$WORKER_ID host=$HOST pid=$pid"
        printf '%s\n' "$summary"
        return
      fi
    elif ! kill -0 "$pid" 2>/dev/null; then
      echo "keepalive supervisor exited before the gate" >&2
      tail -40 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      exit 4
    fi
    sleep 5
  done
  echo "keepalive did not pass the 8-GPU utilization gate within 300 seconds" >&2
  if load_process_matches "$pid"; then
    terminate_verified_group "$pid" || true
  fi
  exit 4
}

show_status() {
  local pid summary rows
  require_exact_identity
  if ! pid="$(current_pid 2>/dev/null)"; then
    rows="$(compute_rows)"
    if grep -q '[^[:space:]]' <<<"$rows"; then
      echo "UNMANAGED_CONTEXTS worker=$WORKER_ID host=$HOST"
      printf '%s\n' "$rows"
      exit 3
    fi
    if [ -f "$PAUSE_FILE" ]; then
      echo "PAUSED worker=$WORKER_ID host=$HOST"
    else
      echo "STOPPED worker=$WORKER_ID host=$HOST"
    fi
    exit 3
  fi
  summary="$(collect_gate)"
  load_process_matches "$pid"
  write_identity "$pid"
  echo "HEALTHY worker=$WORKER_ID host=$HOST pid=$pid"
  printf '%s\n' "$summary"
}

pause_load() {
  local pid rows
  require_exact_identity
  if pid="$(current_pid 2>/dev/null)"; then
    terminate_verified_group "$pid"
  else
    rows="$(compute_rows)"
    if grep -q '[^[:space:]]' <<<"$rows"; then
      echo "refusing pause cleanup: only unmanaged GPU contexts are visible" >&2
      printf '%s\n' "$rows" >&2
      exit 3
    fi
  fi
  : >"$PAUSE_FILE"
  echo "PAUSED worker=$WORKER_ID host=$HOST; CUDA contexts are clear"
}

resume_load() {
  rm -f "$PAUSE_FILE"
  start_load
}

case "$ACTION" in
  start)
    start_load
    ;;
  status)
    show_status
    ;;
  pause)
    pause_load
    ;;
  resume)
    resume_load
    ;;
  *)
    echo "usage: $0 {start|status|pause|resume} 4099543" >&2
    exit 2
    ;;
esac
