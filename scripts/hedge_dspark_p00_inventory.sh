#!/usr/bin/env bash
# Read-only P00 inventory for worker 4106666. This script never starts load.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly WORKER_ID="${1:?worker ID is required}"
readonly ARTIFACT_DIR="${2:?artifact directory is required}"

if [[ "$WORKER_ID" != "4106666" ]]; then
  echo "refusing worker $WORKER_ID; only 4106666 is authorized" >&2
  exit 2
fi
case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac

mkdir -p -- "$ARTIFACT_DIR"
exec python3 "$REPO_ROOT/scripts/hedge_dspark_p00_inventory.py" \
  --worker-id "$WORKER_ID" \
  --artifact-dir "$ARTIFACT_DIR"
