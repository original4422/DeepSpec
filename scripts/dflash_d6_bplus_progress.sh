#!/usr/bin/env bash
# Read-only progress entrypoint for one active D6 B+ formal attempt.
set -Eeuo pipefail

readonly ATTEMPT_ID="${1:?attempt id required}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly HELPER="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_d6_bplus_progress.py"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/runs/${ATTEMPT_ID}"

[[ "${ATTEMPT_ID}" =~ ^dflash-d6-bplus-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ -x "${PYTHON}" && -f "${HELPER}" && -d "${SCRATCH}" ]]

export PYTHONNOUSERSITE=1
exec "${PYTHON}" "${HELPER}" --scratch "${SCRATCH}"
