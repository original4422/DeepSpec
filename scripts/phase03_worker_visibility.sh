#!/usr/bin/env bash
set -euo pipefail

readonly WORKER_ID="${1:?worker ID is required}"
readonly ATTEMPT_ID="20260728T171850Z-phase03-minimal-03"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly VENV_PATH="/home/tiger/venvs/deepspec-dspark"
readonly CUDA_ROOT="${VENV_PATH}/lib/python3.11/site-packages/nvidia/cu13"
readonly COMPAT_ROOT="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
readonly SCRATCH_ROOT="/tmp/${ATTEMPT_ID}-worker"
readonly HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}"
readonly LOG_PATH="${SCRATCH_ROOT}/worker_visibility.log"

copy_artifacts() {
  local source_path destination_path temporary_path
  mkdir -p "${HDFS_ROOT}"
  while IFS= read -r -d '' source_path; do
    destination_path="${HDFS_ROOT}/$(basename "${source_path}")"
    temporary_path="${destination_path}.tmp.$$"
    cp "${source_path}" "${temporary_path}"
    mv "${temporary_path}" "${destination_path}"
  done < <(find "${SCRATCH_ROOT}" -maxdepth 1 -type f -print0)
}

cleanup() {
  local original_rc=$?
  trap - EXIT
  set +e
  copy_artifacts
  exit "${original_rc}"
}

[[ ! -e "${SCRATCH_ROOT}" ]] || {
  echo "Refusing to overwrite worker scratch: ${SCRATCH_ROOT}" >&2
  exit 1
}
mkdir -p "${SCRATCH_ROOT}"
exec > >(tee "${LOG_PATH}") 2>&1
trap cleanup EXIT

printf 'attempt_id=%s\nworker_id=%s\nhostname=%s\nstarted_at=%s\n' \
  "${ATTEMPT_ID}" "${WORKER_ID}" "$(hostname)" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

export CUDA_HOME="${CUDA_ROOT}"
export LD_LIBRARY_PATH="${COMPAT_ROOT}:${CUDA_ROOT}/lib"
export PATH="${VENV_PATH}/bin:${CUDA_ROOT}/bin:/usr/bin:/bin"

bash "${REPO_ROOT}/scripts/keepalive.sh" status "${WORKER_ID}" \
  > "${SCRATCH_ROOT}/keepalive_before.txt"
timeout --signal=TERM --kill-after=5s 60s \
  "${VENV_PATH}/bin/python" -u \
  "${REPO_ROOT}/scripts/phase03_minimal_validation.py" \
  worker "${SCRATCH_ROOT}/worker_cuda_visibility.json"
bash "${REPO_ROOT}/scripts/keepalive.sh" status "${WORKER_ID}" \
  > "${SCRATCH_ROOT}/keepalive_after.txt"

printf 'finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
