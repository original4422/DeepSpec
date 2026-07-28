#!/usr/bin/env bash
# Capture the platform inventory without logging into any non-DSpark lane.

set -euo pipefail

readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly OUTPUT="${1:?output path is required}"

case "$OUTPUT" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "output is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
[[ ! -e "$OUTPUT" ]] || {
  echo "refusing existing output: $OUTPUT" >&2
  exit 1
}
mkdir -p -- "$(dirname "$OUTPUT")"
{
  printf 'observed_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mlx worker list
} >"$OUTPUT"
grep -Eq '^4106666[[:space:]]+184[[:space:]]+1896[[:space:]]+8[[:space:]]+NVIDIA-H20' \
  "$OUTPUT"
