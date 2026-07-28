#!/usr/bin/env bash
# Metadata-only formal-environment probe; keepalive must remain healthy throughout.

set -euo pipefail

readonly EXPECTED_WORKER_ID="4099543"
readonly WORKER_ID="${1:-}"
readonly WORKTREE="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly VENV="/home/tiger/venvs/deepspec-hedge-dflash"
readonly CUDA_ROOT="${VENV}/lib/python3.11/site-packages/nvidia/cu13"
readonly COMPAT_ROOT="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
readonly ARTIFACT_DIR="${WORKTREE}/docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1b"
readonly PROBE="${WORKTREE}/scripts/dflash_d1b_environment_probe.py"

if [[ "${WORKER_ID}" != "${EXPECTED_WORKER_ID}" ]]; then
  echo "expected worker ${EXPECTED_WORKER_ID}, got ${WORKER_ID:-<unset>}" >&2
  exit 2
fi

for required in \
  "${VENV}/bin/python" \
  "${CUDA_ROOT}/bin/nvcc" \
  "${COMPAT_ROOT}/libcuda.so.1" \
  "${PROBE}"; do
  if [[ ! -e "${required}" ]]; then
    echo "required path is missing: ${required}" >&2
    exit 3
  fi
done

export CUDA_VISIBLE_DEVICES=""
export CUDA_HOME="${CUDA_ROOT}"
export LD_LIBRARY_PATH="${COMPAT_ROOT}:${CUDA_ROOT}/lib:${VENV}/lib/python3.11/site-packages/nvidia/nccl/lib"
export PATH="${VENV}/bin:${CUDA_ROOT}/bin:/home/tiger/.local/bin:/usr/local/bin:/usr/bin:/bin"
export FLASHINFER_DISABLE_VERSION_CHECK="1"
export PYTHONNOUSERSITE="1"

exec timeout --signal=TERM --kill-after=10s 240s \
  "${VENV}/bin/python" "${PROBE}" \
    --worker-id "${WORKER_ID}" \
    --artifact-dir "${ARTIFACT_DIR}"
