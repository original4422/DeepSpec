#!/usr/bin/env bash
# P07 HEDGE-on entrypoint; delegates only lifecycle mechanics to accepted P06.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
export DEEPSPEC_P07_ENTRYPOINT="$REPO_ROOT/scripts/hedge_dspark_p07_attempt.sh"
exec bash "$REPO_ROOT/scripts/hedge_dspark_p06_attempt.sh" \
  --p07-adapter "$@"
