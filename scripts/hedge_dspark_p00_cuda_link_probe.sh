#!/usr/bin/env bash
# Run the seconds-long guarded CUDA link probe on worker 4106666.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly WORKER_ID="${1:?worker ID is required}"
readonly ARTIFACT_DIR="${2:?artifact directory is required}"

[[ "$WORKER_ID" = "4106666" ]]
case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac

exec /home/tiger/venvs/hedge-v4-dspark/bin/python \
  "$REPO_ROOT/scripts/hedge_dspark_p00_cuda_link_probe.py" \
  --artifact-dir "$ARTIFACT_DIR"
