#!/usr/bin/env bash
# Launch the Phase 02 ModelScope entity-copy coordinator on the devbox.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
ATTEMPT_ID="${1:?attempt ID is required}"
WORKER_ID="${2:?worker ID is required}"
SOURCE="/mnt/hdfs/pengzegang/HEDGE/models/deepseek-ai__DeepSeek-V4-Flash-DSpark"
PHASE01_RUN="/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T151614Z-phase01-preflight"
SOURCE_MANIFEST="$PHASE01_RUN/source_checkpoint_manifest.json"
SNAPSHOT_ID="bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
SNAPSHOT_PARENT="/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots"
STAGING="$SNAPSHOT_PARENT/.staging-$ATTEMPT_ID"
FORMAL="$SNAPSHOT_PARENT/modelscope-$SNAPSHOT_ID"
RUN_DIR="/mnt/hdfs/pengzegang/DeepSpec/runs/$ATTEMPT_ID"
SCRATCH="/tmp/deepspec-$ATTEMPT_ID"
KEEPALIVE_SCRIPT="$REPO_ROOT/scripts/keepalive.sh"

case "$ATTEMPT_ID" in
  ""|*[!A-Za-z0-9._-]*)
    echo "attempt ID contains invalid characters" >&2
    exit 2
    ;;
esac
case "$WORKER_ID" in
  ""|*[!0-9]*)
    echo "worker ID must be numeric" >&2
    exit 2
    ;;
esac

test -f "$SOURCE_MANIFEST"
test -d "$SOURCE"
test -f "$KEEPALIVE_SCRIPT"
test ! -e "$RUN_DIR"
test ! -e "$SCRATCH"
test ! -e "$STAGING"
test ! -e "$FORMAL"

mkdir -p "$SNAPSHOT_PARENT"
mkdir "$SCRATCH"
exec >"$SCRATCH/runner.log" 2>&1

exec setsid python3 "$REPO_ROOT/scripts/phase02_copy.py" \
  --attempt-id "$ATTEMPT_ID" \
  --source "$SOURCE" \
  --source-manifest "$SOURCE_MANIFEST" \
  --staging "$STAGING" \
  --formal "$FORMAL" \
  --run-dir "$RUN_DIR" \
  --scratch "$SCRATCH" \
  --worker-id "$WORKER_ID" \
  --keepalive-script "$KEEPALIVE_SCRIPT"
