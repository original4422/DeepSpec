#!/usr/bin/env bash
# D6 native-formal entrypoint; all mutable lifecycle state is attempt-scoped.
set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 {contract|preflight|live} ATTEMPT_ID HARD_STOP_UTC" >&2
  exit 2
fi

readonly ACTION="${1}"
readonly ATTEMPT_ID="${2}"
readonly HARD_STOP_UTC="${3}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly LIFECYCLE="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_d6_lifecycle.py"

[[ "${ACTION}" =~ ^(contract|preflight|live)$ ]]
[[ "${ATTEMPT_ID}" =~ ^dflash-d6-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ "${HARD_STOP_UTC}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
[[ -x "${PYTHON}" && -f "${LIFECYCLE}" ]]

export PYTHONNOUSERSITE=1
exec "${PYTHON}" "${LIFECYCLE}" \
  "${ACTION}" "${ATTEMPT_ID}" "${HARD_STOP_UTC}"
