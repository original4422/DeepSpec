#!/usr/bin/env bash
# Phase 00 read-only worker inventory. The only writes are new evidence files
# below the caller-provided, previously absent artifact directory.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:?usage: hedge_eagle3_phase00_inventory.sh ABSOLUTE_NEW_OUTPUT_DIR}"
WORKER_ID="${2:-4099544}"

case "$OUTPUT_DIR" in
  /mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/*)
    ;;
  *)
    echo "refusing output outside the Eagle3 run root: $OUTPUT_DIR" >&2
    exit 2
    ;;
esac

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned worker: $WORKER_ID" >&2
  exit 2
fi
if [ -e "$OUTPUT_DIR" ]; then
  echo "refusing to reuse or overwrite artifact directory: $OUTPUT_DIR" >&2
  exit 2
fi

umask 027
mkdir -p "$OUTPUT_DIR"
exec python3 "$REPO_ROOT/scripts/hedge_eagle3_phase00_inventory.py" \
  --worker-id "$WORKER_ID" \
  --output-dir "$OUTPUT_DIR"
