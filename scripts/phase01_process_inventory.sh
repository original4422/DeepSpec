#!/usr/bin/env bash
# Read-only post-incident process and keepalive evidence for Phase 01.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec"
PYTHON="/home/tiger/venvs/hedge-deepspec/bin/python"
WORKER_ID="${1:?worker ID is required}"
ARTIFACT_DIR="${2:?artifact directory is required}"
LOG="$ARTIFACT_DIR/preflight.log"

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

printf '%s %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "read-only post-incident process inventory start" \
  | tee -a "$LOG"
"$PYTHON" "$REPO_ROOT/scripts/phase01_worker_probe.py" processes \
  --artifact-dir "$ARTIFACT_DIR" \
  --worker-id "$WORKER_ID" \
  2>&1 | tee -a "$LOG"
bash "$REPO_ROOT/scripts/keepalive.sh" status "$WORKER_ID" \
  2>&1 \
  | tee "$ARTIFACT_DIR/keepalive_post_incident.txt" \
  | tee -a "$LOG"
printf '%s %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "read-only post-incident process inventory completed" \
  | tee -a "$LOG"
