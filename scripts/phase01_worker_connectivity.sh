#!/usr/bin/env bash
# Read-only network connectivity evidence from the selected Phase 01 worker.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec"
PYTHON="/home/tiger/venvs/hedge-deepspec/bin/python"
WORKER_ID="${1:?worker ID is required}"
ARTIFACT_DIR="${2:?artifact directory is required}"

case "$WORKER_ID" in
  *[!0-9]*|"")
    echo "invalid worker ID" >&2
    exit 2
    ;;
esac
case "$ARTIFACT_DIR" in
  "$HDFS_ROOT"/runs/*) ;;
  *)
    echo "artifact directory is outside the registered run root" >&2
    exit 2
    ;;
esac

"$PYTHON" "$REPO_ROOT/scripts/phase01_worker_probe.py" connectivity \
  --artifact-dir "$ARTIFACT_DIR" \
  --worker-id "$WORKER_ID"
