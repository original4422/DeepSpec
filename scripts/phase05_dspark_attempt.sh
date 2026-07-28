#!/usr/bin/env bash
# Atomic Phase 05 lifecycle. Must be invoked on the selected worker.
set -euo pipefail

readonly WORKER_ID="${1:?worker ID is required}"
readonly ATTEMPT_ID="${2:?attempt ID is required}"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}"
readonly SCRATCH="/tmp/deepspec-${ATTEMPT_ID}"
readonly BASELINE="${REPO_ROOT}/config/dspark/deepseek_v4_flash_dspark_4xh20_mvp.json"
readonly PYTHON="/home/tiger/venvs/deepspec-dspark/bin/python"
readonly PID_FILE="${SCRATCH}/server.pid"
readonly SAMPLER_PID_FILE="${SCRATCH}/sampler.pid"
readonly WATCHDOG_PID_FILE="${SCRATCH}/watchdog.pid"

server_pid=""
sampler_pid=""
watchdog_pid=""
keepalive_paused=0

copy_artifacts() {
  mkdir -p "${HDFS_RUN}"
  find "${SCRATCH}" -maxdepth 1 -type f -exec cp -f {} "${HDFS_RUN}/" \;
}

wait_no_cuda_contexts() {
  local output="$1" attempt rows
  : >"${output}"
  for attempt in $(seq 1 30); do
    if ! rows="$(
      nvidia-smi \
        --query-compute-apps=pid,gpu_uuid,process_name,used_memory \
        --format=csv,noheader,nounits 2>&1
    )"; then
      printf '%s attempt=%s query_failed=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${attempt}" "${rows}" \
        >>"${output}"
      return 1
    fi
    printf '%s attempt=%s contexts=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${attempt}" \
      "${rows:-none}" >>"${output}"
    if ! grep -q '[^[:space:]]' <<<"${rows}"; then
      return 0
    fi
    [[ "${attempt}" -eq 30 ]] || sleep 1
  done
  return 1
}

stop_group_if_owned() {
  local pid="$1" expected="$2" cmdline pgid sid
  [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 0
  kill -0 "${pid}" 2>/dev/null || return 0
  cmdline="$(tr '\0' ' ' <"/proc/${pid}/cmdline")"
  [[ "${cmdline}" == *"${expected}"* ]] || {
    echo "refusing to stop unverified pid=${pid}: ${cmdline}" >&2
    return 1
  }
  pgid="$(ps -o pgid= -p "${pid}" | tr -d ' ')"
  sid="$(ps -o sid= -p "${pid}" | tr -d ' ')"
  [[ "${pgid}" = "${pid}" && "${sid}" = "${pid}" ]] || return 1
  kill -TERM -- "-${pid}" 2>/dev/null || true
  for _ in $(seq 1 30); do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 1
  done
  kill -KILL -- "-${pid}" 2>/dev/null || true
}

cleanup() {
  local original_rc=$?
  local cleanup_rc=0
  trap - EXIT INT TERM
  set +e
  stop_group_if_owned "${watchdog_pid}" phase05_watchdog.py || cleanup_rc=1
  stop_group_if_owned "${sampler_pid}" phase05_gpu_sampler.py || cleanup_rc=1
  stop_group_if_owned "${server_pid}" sglang.launch_server || cleanup_rc=1
  wait_no_cuda_contexts \
    "${SCRATCH}/cuda_contexts_after_server.txt" || cleanup_rc=1
  if [[ "${keepalive_paused}" -eq 1 ]]; then
    if [[ "${cleanup_rc}" -eq 0 ]]; then
      bash "${REPO_ROOT}/scripts/keepalive.sh" resume "${WORKER_ID}" \
        >"${SCRATCH}/keepalive_after.txt" 2>&1 || cleanup_rc=1
    else
      printf 'keepalive not resumed because CUDA context cleanup was not proven\n' \
        >"${SCRATCH}/keepalive_after.txt"
    fi
  fi
  copy_artifacts || cleanup_rc=1
  if [[ "${original_rc}" -ne 0 || "${cleanup_rc}" -ne 0 ]]; then
    exit 1
  fi
  exit 0
}

[[ "${WORKER_ID}" =~ ^[0-9]+$ ]]
[[ "${ATTEMPT_ID}" =~ ^[0-9]{8}T[0-9]{6}Z-phase05- ]]
[[ ! -e "${SCRATCH}" && ! -e "${HDFS_RUN}" ]]
mkdir -p "${SCRATCH}" "${HDFS_RUN}"
exec > >(tee "${SCRATCH}/lifecycle.log") 2>&1
trap cleanup EXIT INT TERM

bash "${REPO_ROOT}/scripts/keepalive.sh" status "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_before.txt"
"${PYTHON}" "${REPO_ROOT}/scripts/phase05_resolve.py" \
  --config "${BASELINE}" \
  --output-config "${SCRATCH}/resolved_config.json" \
  --output-command "${SCRATCH}/resolved_command.txt"

bash "${REPO_ROOT}/scripts/keepalive.sh" pause "${WORKER_ID}"
keepalive_paused=1
wait_no_cuda_contexts "${SCRATCH}/cuda_contexts_after_pause.txt"
mapfile -d '' -t command < <(
  "${PYTHON}" "${REPO_ROOT}/scripts/phase05_resolve.py" \
    --config "${BASELINE}" --print-command-null
)
while IFS='=' read -r key value; do export "${key}=${value}"; done < <(
  "${PYTHON}" -c \
    'import json,sys; d=json.load(open(sys.argv[1])); [print(f"{k}={v}") for k,v in d["environment"].items()]' \
    "${BASELINE}"
)
unset SGLANG_DSV4_FP4_DEQUANT
setsid "${command[@]}" >"${SCRATCH}/server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" >"${PID_FILE}"
server_start_ticks="$(
  "${PYTHON}" -c \
    'from pathlib import Path; import sys; s=Path(f"/proc/{sys.argv[1]}/stat").read_text(); print(s[s.rfind(")")+2:].split()[19])' \
    "${server_pid}"
)"

setsid "${PYTHON}" "${REPO_ROOT}/scripts/phase05_gpu_sampler.py" \
  --output "${SCRATCH}/gpu_samples.csv" --server-pid "${server_pid}" &
sampler_pid=$!
printf '%s\n' "${sampler_pid}" >"${SAMPLER_PID_FILE}"
owner_start_ticks="$(
  "${PYTHON}" -c \
    'from pathlib import Path; import sys; s=Path(f"/proc/{sys.argv[1]}/stat").read_text(); print(s[s.rfind(")")+2:].split()[19])' \
    "$$"
)"
setsid "${PYTHON}" "${REPO_ROOT}/scripts/phase05_watchdog.py" \
  --owner-pid "$$" --owner-start-ticks "${owner_start_ticks}" \
  --server-pid "${server_pid}" --server-start-ticks "${server_start_ticks}" \
  --worker-id "${WORKER_ID}" --repo-root "${REPO_ROOT}" \
  --scratch "${SCRATCH}" --hdfs-run "${HDFS_RUN}" \
  >"${SCRATCH}/watchdog.log" 2>&1 &
watchdog_pid=$!
printf '%s\n' "${watchdog_pid}" >"${WATCHDOG_PID_FILE}"

"${PYTHON}" "${REPO_ROOT}/scripts/phase05_wait_ready.py" \
  --base-url http://127.0.0.1:30000 --server-pid "${server_pid}" \
  --timeout 3600 --output "${SCRATCH}/startup.json"
"${PYTHON}" "${REPO_ROOT}/scripts/phase05_api_smoke.py" \
  --base-url http://127.0.0.1:30000 \
  --model deepseek-v4-flash-dspark \
  --output "${SCRATCH}/api_smoke.json"
"${PYTHON}" "${REPO_ROOT}/scripts/phase05_gsm8k_smoke.py" \
  --dataset "${REPO_ROOT}/eval_datasets/gsm8k_main_test_first10.jsonl" \
  --output "${SCRATCH}/gsm8k_outputs.jsonl" \
  --summary "${SCRATCH}/summary.json"
