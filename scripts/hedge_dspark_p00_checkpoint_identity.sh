#!/usr/bin/env bash
# Run the P00 checkpoint metadata check on the authorized worker.

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

exec python3 "$REPO_ROOT/scripts/hedge_dspark_p00_checkpoint_identity.py" \
  --worker-id "$WORKER_ID" \
  --artifact-dir "$ARTIFACT_DIR"
