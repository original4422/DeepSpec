#!/usr/bin/env bash
# Capture the final read-only worker/keepalive state for Phase 06.
set -euo pipefail

readonly WORKER_ID="${1:?worker ID is required}"
readonly RUN_DIR="${2:?run directory is required}"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs"
readonly SCRATCH="$(mktemp -d /tmp/deepspec-phase06-final-state.XXXXXX)"

cleanup() {
  rm -rf -- "${SCRATCH}"
}
trap cleanup EXIT

[[ "${WORKER_ID}" =~ ^[0-9]+$ ]]
case "${RUN_DIR}" in
  "${HDFS_RUN_ROOT}"/*) ;;
  *)
    echo "run directory is outside the registered HDFS run root" >&2
    exit 2
    ;;
esac
[[ -d "${RUN_DIR}" ]]

bash "${REPO_ROOT}/scripts/keepalive.sh" status "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_status.txt"

readonly STATUS_LINE="$(
  awk '/^HEALTHY / { line = $0 } END { print line }' \
    "${SCRATCH}/keepalive_status.txt"
)"
readonly HEALTH_JSON="$(
  awk '/^\{/ { line = $0 } END { print line }' \
    "${SCRATCH}/keepalive_status.txt"
)"
[[ -n "${STATUS_LINE}" && -n "${HEALTH_JSON}" ]]
readonly KEEPALIVE_PID="$(
  sed -n 's/.* pid=\([0-9][0-9]*\)$/\1/p' <<<"${STATUS_LINE}"
)"
[[ "${KEEPALIVE_PID}" =~ ^[1-9][0-9]*$ ]]

printf '%s\n' "${HEALTH_JSON}" >"${SCRATCH}/keepalive_final.json"
/home/tiger/venvs/hedge-deepspec/bin/python -m json.tool \
  "${SCRATCH}/keepalive_final.json" >/dev/null

nvidia-smi \
  --query-gpu=index,uuid,name,memory.total,utilization.gpu,memory.used \
  --format=csv,noheader,nounits \
  >"${SCRATCH}/gpu_inventory.txt"
nvidia-smi \
  --query-compute-apps=pid,gpu_uuid,process_name,used_memory \
  --format=csv,noheader,nounits \
  >"${SCRATCH}/compute_contexts.txt"
ps -o pid=,ppid=,pgid=,sid=,stat=,etime=,args= -g "${KEEPALIVE_PID}" \
  >"${SCRATCH}/keepalive_processes.txt"
ps -eo pid=,args= \
  | awk '
      /sglang\.launch_server|sglang::|SGLang::/ {
        if ($0 !~ /awk/) {
          print
        }
      }
    ' >"${SCRATCH}/model_processes.txt"

awk -F, '
  {
    count += 1
    name = $3
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
    if (name != "NVIDIA H20") {
      wrong_name = 1
    }
  }
  END {
    exit !(count == 4 && !wrong_name)
  }
' "${SCRATCH}/gpu_inventory.txt"

awk -F, '
  {
    uuid = $2
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", uuid)
    seen[uuid] = 1
    count += 1
  }
  END {
    for (uuid in seen) {
      unique += 1
    }
    exit !(count == 4 && unique == 4)
  }
' "${SCRATCH}/compute_contexts.txt"
[[ ! -s "${SCRATCH}/model_processes.txt" ]]

{
  printf 'captured_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'worker_id=%s\n' "${WORKER_ID}"
  printf 'hostname=%s\n' "$(hostname)"
  printf 'keepalive_status=%s\n' "${STATUS_LINE}"
  printf '\nkeepalive_health_json:\n%s\n' "${HEALTH_JSON}"
  printf '\ngpu_inventory:\n'
  cat "${SCRATCH}/gpu_inventory.txt"
  printf '\ncompute_contexts:\n'
  cat "${SCRATCH}/compute_contexts.txt"
  printf '\ncompute_context_pid_note:\n'
  printf '%s\n' \
    'nvidia-smi reports host PIDs while ps uses the worker PID namespace; direct PID comparison is unavailable.'
  printf '\nregistered_keepalive_process_group:\n'
  cat "${SCRATCH}/keepalive_processes.txt"
  printf '\nunregistered_model_processes:\nnone\n'
} >"${SCRATCH}/phase06_live_state.txt"

for name in keepalive_final.json phase06_live_state.txt; do
  cp "${SCRATCH}/${name}" "${RUN_DIR}/${name}.phase06-staging"
  cmp "${SCRATCH}/${name}" "${RUN_DIR}/${name}.phase06-staging"
  mv "${RUN_DIR}/${name}.phase06-staging" "${RUN_DIR}/${name}"
done

printf 'phase06_final_state=PASS\n'
printf 'worker_id=%s\n' "${WORKER_ID}"
printf 'keepalive_pid=%s\n' "${KEEPALIVE_PID}"
printf 'run_dir=%s\n' "${RUN_DIR}"
