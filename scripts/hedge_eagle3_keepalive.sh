#!/usr/bin/env bash
# Exact eight-GPU operational keepalive controller for the Eagle3 lane.
# Phase 00 only prepares this entrypoint; it must not be started until the
# phase handoff has been accepted and the dedicated uv environment exists.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_ID="${2:-4099544}"

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned Eagle3 worker: $WORKER_ID" >&2
  exit 2
fi

export DEEPSPEC_KEEPALIVE_STATE_DIR="/home/tiger/.deepspec-hedge-v4-eagle3/keepalive"
export DEEPSPEC_KEEPALIVE_PYTHON="${DEEPSPEC_EAGLE3_KEEPALIVE_PYTHON:-/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python}"
export DEEPSPEC_KEEPALIVE_EXPECTED_GPUS=8
export DEEPSPEC_KEEPALIVE_CUDA_VISIBLE_DEVICES="0,1,2,3,4,5,6,7"

exec bash "$REPO_ROOT/scripts/keepalive.sh" "${1:-status}" "$WORKER_ID"
