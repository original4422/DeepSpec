#!/usr/bin/env bash
# Read-only status snapshot for a running or completed Phase 01A acquisition.

set -euo pipefail

WORKER_ID="${1:-4099544}"
ACQUISITION_ROOT="/tmp/deepspec-hedge-v4-eagle3/phase-01a-acquisition"
RUN_DIR="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T211500Z-phase-01a-acquisition-01"
TARGET="/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash/snapshots/huggingface-60d8d70770c6776ff598c94bb586a859a38244f1"
DRAFT="/mnt/hdfs/pengzegang/DeepSpec/models/SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/snapshots/huggingface-4c68aa4689d59cb1064f20abec7708174ee4613d"
MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/target-deepseek-v4-flash-60d8d70770c6776ff598c94bb586a859a38244f1.complete.json"

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned Eagle3 worker: $WORKER_ID" >&2
  exit 2
fi

printf 'observed_at=%s worker=%s hostname=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$WORKER_ID" \
  "$(hostname)"
nvidia-smi \
  --query-gpu=index,uuid,name,utilization.gpu,memory.used \
  --format=csv,noheader,nounits

for state in \
  "$ACQUISITION_ROOT/acquisition_state.json" \
  "$ACQUISITION_ROOT/heartbeat.json" \
  "$ACQUISITION_ROOT/watchdog_status.json"; do
  if [ -f "$state" ]; then
    printf 'STATE %s\n' "$state"
    sed -n '1,240p' "$state"
  else
    printf 'MISSING %s\n' "$state"
  fi
done

for root in \
  "$ACQUISITION_ROOT/target/snapshot" \
  "$ACQUISITION_ROOT/draft/snapshot" \
  "$RUN_DIR" \
  "$TARGET" \
  "$DRAFT"; do
  if [ -e "$root" ]; then
    du -sb "$root"
  else
    printf 'MISSING %s\n' "$root"
  fi
done

if [ -f "$MARKER" ]; then
  printf 'TARGET_MARKER %s\n' "$MARKER"
  sed -n '1,240p' "$MARKER"
else
  printf 'MISSING %s\n' "$MARKER"
fi
