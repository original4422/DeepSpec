#!/usr/bin/env bash
# Remote entrypoint for the read-only Torch ELF closure capture.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
exec python3 \
  "$REPO_ROOT/scripts/hedge_eagle3_phase01b_capture_torch_elf_closure.py" \
  "$@"
