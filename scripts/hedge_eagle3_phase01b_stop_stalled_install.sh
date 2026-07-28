#!/usr/bin/env bash
# Remote entrypoint for exact owned install-group termination.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
exec python3 "$REPO_ROOT/scripts/hedge_eagle3_phase01b_stop_stalled_install.py" "$@"
