#!/usr/bin/env bash
# Read-only status snapshot for one running P00 environment attempt.

set -euo pipefail

readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly ARTIFACT_DIR="${1:?artifact directory is required}"
readonly ATTEMPT_ID="${2:?attempt ID is required}"
readonly OUTPUT="${3:?output filename is required}"
readonly SCRATCH="/tmp/deepspec-hedge-dspark-${ATTEMPT_ID}"

case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
case "$OUTPUT" in
  *[!A-Za-z0-9._-]*|"")
    echo "invalid output filename" >&2
    exit 2
    ;;
esac
[[ -d "$SCRATCH" ]]
[[ ! -e "$ARTIFACT_DIR/$OUTPUT" ]]

{
  printf 'observed_at_utc=%s\nscratch=%s\n\nprocesses:\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SCRATCH"
  process_rows="$(
    ps -eo pid=,ppid=,pgid=,sid=,stat=,etimes=,args= --sort=pid
  )"
  printf '%s\n' "$process_rows" \
    | grep -F "$ATTEMPT_ID" \
    | grep -v 'grep -F' || true
  launcher_pgid="$(
    printf '%s\n' "$process_rows" \
      | grep -F "hedge_dspark_p00_environment.sh" \
      | grep -F "$ATTEMPT_ID" \
      | awk 'NR == 1 {print $3}'
  )"
  if [[ -n "$launcher_pgid" ]]; then
    printf '\nregistered_process_group=%s:\n' "$launcher_pgid"
    printf '%s\n' "$process_rows" \
      | awk -v pgid="$launcher_pgid" '$3 == pgid'
  fi
  printf '\nuv_sync_tail:\n'
  tail -100 "$SCRATCH/uv-sync.log" 2>/dev/null || true
  printf '\nuv_pip_check_tail:\n'
  tail -100 "$SCRATCH/uv-pip-check.log" 2>/dev/null || true
} >"$ARTIFACT_DIR/$OUTPUT"
cat "$ARTIFACT_DIR/$OUTPUT"
