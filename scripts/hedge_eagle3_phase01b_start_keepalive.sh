#!/usr/bin/env bash
# Start and prove the exact-eight-GPU Eagle3 operational keepalive.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_start_keepalive.sh WORKER_ID OUTPUT_DIR MARKER_PATH}"
OUTPUT_DIR="${2:?usage: hedge_eagle3_phase01b_start_keepalive.sh WORKER_ID OUTPUT_DIR MARKER_PATH}"
MARKER_PATH="${3:?usage: hedge_eagle3_phase01b_start_keepalive.sh WORKER_ID OUTPUT_DIR MARKER_PATH}"
REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
PYTHON="/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
EVIDENCE="$REPO_ROOT/scripts/hedge_eagle3_phase01b_keepalive_evidence.py"
CONTROLLER="$REPO_ROOT/scripts/hedge_eagle3_keepalive.sh"

if [ "$WORKER_ID" != "$EXPECTED_WORKER" ]; then
  echo "refusing unassigned worker: $WORKER_ID" >&2
  exit 2
fi
case "$OUTPUT_DIR" in
  /mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/*)
    ;;
  *)
    echo "refusing output outside Eagle3 run root: $OUTPUT_DIR" >&2
    exit 2
    ;;
esac
case "$MARKER_PATH" in
  /mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-*/keepalive-active.json)
    ;;
  *)
    echo "refusing marker outside the Eagle3 coordination directory" >&2
    exit 2
    ;;
esac
if [ -e "$OUTPUT_DIR" ] || [ -e "$MARKER_PATH" ]; then
  echo "refusing to overwrite keepalive evidence or marker" >&2
  exit 2
fi
test -x "$PYTHON"
test -f "$EVIDENCE"
test -x "$CONTROLLER"

umask 027
mkdir -p "$OUTPUT_DIR"
cd "$REPO_ROOT"

"$PYTHON" "$EVIDENCE" preflight \
  --output "$OUTPUT_DIR/preflight.json"

"$CONTROLLER" start "$WORKER_ID" \
  >"$OUTPUT_DIR/keepalive_start.stdout.txt" \
  2>"$OUTPUT_DIR/keepalive_start.stderr.txt"

"$CONTROLLER" status "$WORKER_ID" \
  >"$OUTPUT_DIR/keepalive_status.stdout.txt" \
  2>"$OUTPUT_DIR/keepalive_status.stderr.txt"

"$PYTHON" "$EVIDENCE" finalize \
  --output-dir "$OUTPUT_DIR" \
  --marker "$MARKER_PATH"

printf 'KEEPALIVE_ACTIVE marker=%s evidence=%s\n' \
  "$MARKER_PATH" "$OUTPUT_DIR/keepalive_active.json"
