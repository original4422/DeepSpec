#!/usr/bin/env bash
# Read-only progress observation for the pinned direct torch wheel.

set -euo pipefail

SCRATCH_DIR="/tmp/deepspec-hedge-v4-eagle3/direct-torch-04"
WHEEL_NAME="torch-2.11.0+cu130-cp311-cp311-manylinux_2_28_x86_64.whl"
PARTIAL="$SCRATCH_DIR/$WHEEL_NAME.partial"
WHEEL="$SCRATCH_DIR/$WHEEL_NAME"

if [ -f "$SCRATCH_DIR/head.headers" ]; then
  awk '
    tolower($1) == "content-length:" {
      gsub("\r", "", $2)
      print "content_length=" $2
    }
  ' "$SCRATCH_DIR/head.headers" | tail -1
fi
if [ -f "$PARTIAL" ]; then
  stat --printf='state=partial bytes=%s mtime=%y path=%n\n' "$PARTIAL"
elif [ -f "$WHEEL" ]; then
  stat --printf='state=complete bytes=%s mtime=%y path=%n\n' "$WHEEL"
else
  printf 'state=not-created scratch=%s\n' "$SCRATCH_DIR"
fi
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory \
  --format=csv,noheader,nounits
