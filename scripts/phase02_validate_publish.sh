#!/usr/bin/env bash
# Publish the already-complete Phase 02 staging after minimal validation.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
ATTEMPT_ID="${1:?attempt ID is required}"
WORKER_ID="${2:?worker ID is required}"
PRIOR_ATTEMPT="20260728T164102Z-phase02-modelscope-copy"
SOURCE="/mnt/hdfs/pengzegang/HEDGE/models/deepseek-ai__DeepSeek-V4-Flash-DSpark"
SOURCE_MANIFEST="/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T151614Z-phase01-preflight/source_checkpoint_manifest.json"
SNAPSHOT_ID="bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
PARENT="/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots"
STAGING="$PARENT/.staging-$PRIOR_ATTEMPT"
FORMAL="$PARENT/modelscope-$SNAPSHOT_ID"
RUN_DIR="/mnt/hdfs/pengzegang/DeepSpec/runs/$ATTEMPT_ID"
PRIOR_RUN="/mnt/hdfs/pengzegang/DeepSpec/runs/$PRIOR_ATTEMPT"
SCRATCH="/tmp/deepspec-$ATTEMPT_ID"
PRIOR_SCRATCH="/tmp/deepspec-$PRIOR_ATTEMPT"

test -d "$STAGING"
test ! -e "$FORMAL"
test ! -e "$RUN_DIR"
test ! -e "$SCRATCH"
test -d "$PRIOR_RUN"
test -d "$PRIOR_SCRATCH"

exec python3 "$REPO_ROOT/scripts/phase02_validate_publish.py" \
  --attempt-id "$ATTEMPT_ID" \
  --prior-attempt-id "$PRIOR_ATTEMPT" \
  --source "$SOURCE" \
  --source-manifest "$SOURCE_MANIFEST" \
  --staging "$STAGING" \
  --formal "$FORMAL" \
  --run-dir "$RUN_DIR" \
  --prior-run-dir "$PRIOR_RUN" \
  --scratch "$SCRATCH" \
  --prior-scratch "$PRIOR_SCRATCH" \
  --worker-id "$WORKER_ID" \
  --keepalive-script "$REPO_ROOT/scripts/keepalive.sh"
