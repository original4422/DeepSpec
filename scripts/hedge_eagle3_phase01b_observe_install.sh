#!/usr/bin/env bash
# Agent-runnable red/green gate for a lane-owned uv install.

set -euo pipefail

PID="${1:?usage: hedge_eagle3_phase01b_observe_install.sh PID OUTPUT_JSON [initial|system-certs|index-url]}"
OUTPUT_JSON="${2:?usage: hedge_eagle3_phase01b_observe_install.sh PID OUTPUT_JSON [initial|system-certs|index-url]}"
MODE="${3:-initial}"
REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"

case "$OUTPUT_JSON" in
  /mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/*)
    ;;
  *)
    echo "refusing output outside Eagle3 run root: $OUTPUT_JSON" >&2
    exit 2
    ;;
esac

exec python3 "$REPO_ROOT/scripts/hedge_eagle3_phase01b_install_progress.py" \
  --pid "$PID" \
  --output "$OUTPUT_JSON" \
  --mode "$MODE" \
  --sample-seconds 15
