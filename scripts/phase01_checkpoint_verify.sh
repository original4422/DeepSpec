#!/usr/bin/env bash
# Long, read-only source checkpoint verification for Phase 01.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec"
SOURCE="/mnt/hdfs/pengzegang/HEDGE/models/deepseek-ai__DeepSeek-V4-Flash-DSpark"
REPOSITORY="deepseek-ai/DeepSeek-V4-Flash-DSpark"
HF_REFERENCE_REVISION="62af8fffb2f7030cac4de2f0169f5b8d1101b646"
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
  "read-only ModelScope checkpoint hash start worker=$WORKER_ID" \
  | tee -a "$LOG"
python3 "$REPO_ROOT/scripts/phase01_checkpoint_manifest.py" \
  --source "$SOURCE" \
  --artifact-dir "$ARTIFACT_DIR" \
  --repository "$REPOSITORY" \
  --modelscope-revision master \
  --hf-reference-revision "$HF_REFERENCE_REVISION" \
  --worker-id "$WORKER_ID" \
  --hash-workers 4 \
  2>&1 | tee -a "$LOG"
printf '%s %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "read-only ModelScope checkpoint hash completed" \
  | tee -a "$LOG"
