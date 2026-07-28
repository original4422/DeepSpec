#!/usr/bin/env bash
# Entry point for all CPU-only Phase 01B runner/process fixtures.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
VENV="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
export PYTHONPATH="$REPO_ROOT"
export CUDA_VISIBLE_DEVICES=""
exec "$VENV/bin/python" \
  "$REPO_ROOT/scripts/hedge_eagle3_phase01b_run_fixtures.py" \
  "$@"
