#!/usr/bin/env bash
# Seal one failed P00 environment attempt without changing its state.

set -euo pipefail

readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly ARTIFACT_DIR="${1:?artifact directory is required}"
readonly ATTEMPT_ID="${2:?attempt ID is required}"
readonly SCRATCH="/tmp/deepspec-hedge-dspark-${ATTEMPT_ID}"
readonly DESTINATION="$ARTIFACT_DIR/environment-attempts/$ATTEMPT_ID"

case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
[[ -d "$SCRATCH" ]] || {
  echo "missing environment attempt scratch: $SCRATCH" >&2
  exit 1
}
[[ ! -e "$DESTINATION" ]] || {
  echo "refusing existing destination: $DESTINATION" >&2
  exit 1
}

mkdir -p -- "$DESTINATION"
for name in environment_setup.identity source_clone.log uv-sync.log uv-pip-check.log; do
  if [[ -f "$SCRATCH/$name" ]]; then
    cp -- "$SCRATCH/$name" "$DESTINATION/$name"
  fi
done
printf 'sealed_at_utc=%s\nsource_scratch=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SCRATCH" \
  >"$DESTINATION/seal.txt"
find "$DESTINATION" -maxdepth 1 -type f -printf '%f %s\n' | sort
