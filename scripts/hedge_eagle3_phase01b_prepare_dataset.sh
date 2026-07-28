#!/usr/bin/env bash
# Entry point for the pinned GSM8K 32+500 split manifest.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
VENV="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
export HF_HOME="/tmp/deepspec-hedge-v4-eagle3/huggingface"
export HF_DATASETS_CACHE="/tmp/deepspec-hedge-v4-eagle3/datasets"
export CUDA_VISIBLE_DEVICES=""
exec "$VENV/bin/python" \
  "$REPO_ROOT/scripts/hedge_eagle3_phase01b_prepare_dataset.py" \
  "$@"
