#!/usr/bin/env bash
# Final read-only keepalive gate for the Phase 01 handoff.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
HDFS_ROOT="/mnt/hdfs/pengzegang/DeepSpec"
WORKER_ID="${1:?worker ID is required}"
ARTIFACT_DIR="${2:?artifact directory is required}"

case "$WORKER_ID" in
  *[!0-9]*|"")
    echo "invalid worker ID" >&2
    exit 2
    ;;
esac
case "$ARTIFACT_DIR" in
  "$HDFS_ROOT"/runs/*) ;;
  *)
    echo "artifact directory is outside the registered run root" >&2
    exit 2
    ;;
esac

LOCAL_STATUS="$(mktemp /tmp/deepspec-phase01-keepalive-status.XXXXXX)"
ARTIFACT_STATUS_TEMP="$ARTIFACT_DIR/.keepalive_exit.txt.tmp-$$"
cleanup() {
  rm -f -- "$LOCAL_STATUS" "$ARTIFACT_STATUS_TEMP"
}
trap cleanup EXIT

set +e
bash "$REPO_ROOT/scripts/keepalive.sh" status "$WORKER_ID" \
  >"$LOCAL_STATUS" 2>&1
STATUS_RC=$?
set -e

cat "$LOCAL_STATUS"
cp -- "$LOCAL_STATUS" "$ARTIFACT_STATUS_TEMP"
mv -f -- "$ARTIFACT_STATUS_TEMP" "$ARTIFACT_DIR/keepalive_exit.txt"
rm -f -- "$LOCAL_STATUS"
trap - EXIT
exit "$STATUS_RC"
