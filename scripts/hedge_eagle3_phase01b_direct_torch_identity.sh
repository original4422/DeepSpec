#!/usr/bin/env bash
# Remote entrypoint for locked torch wheel identity attestation.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
PYTHON="/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
exec "$PYTHON" "$REPO_ROOT/scripts/hedge_eagle3_phase01b_direct_torch_identity.py" \
  --repo-root "$REPO_ROOT" \
  "$@"
