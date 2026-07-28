#!/usr/bin/env bash
# Retry the attempt-2 command with only --index changed to --index-url.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_retry_uv_index_url.sh WORKER_ID OUTPUT_DIR}"
OUTPUT_DIR="${2:?usage: hedge_eagle3_phase01b_retry_uv_index_url.sh WORKER_ID OUTPUT_DIR}"
REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
ENV_DIR="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
SCRATCH_ROOT="/tmp/deepspec-hedge-v4-eagle3"
UV_BIN="/home/tiger/.local/bin/uv"
VARIABLE_CHANGE="uv --index -> --index-url; all attempt-2 settings held constant"

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
if [ -e "$OUTPUT_DIR" ]; then
  echo "refusing to overwrite output directory: $OUTPUT_DIR" >&2
  exit 2
fi
test -x "$UV_BIN"
test -x "$ENV_DIR/bin/python"
test -f "$ENV_DIR/pyvenv.cfg"

umask 027
mkdir -p "$OUTPUT_DIR"
export UV_CACHE_DIR="$SCRATCH_ROOT/uv-cache"
export UV_PYTHON_DOWNLOADS=never

set +e
"$UV_BIN" pip install \
  --python "$ENV_DIR/bin/python" \
  --index-url https://download.pytorch.org/whl/cu130 \
  --system-certs \
  --verbose \
  "torch==2.11.0" \
  >"$OUTPUT_DIR/uv-install.stdout.txt" \
  2>"$OUTPUT_DIR/uv-install.stderr.txt"
install_rc=$?
set -e

if [ "$install_rc" -ne 0 ]; then
  python3 - "$OUTPUT_DIR/attempt_status.json" "$install_rc" "$VARIABLE_CHANGE" <<'PY'
import datetime as dt
import json
from pathlib import Path
import sys

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "FAILED",
            "finished_at": dt.datetime.now(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "returncode": int(sys.argv[2]),
            "single_variable_change": sys.argv[3],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
  exit "$install_rc"
fi

"$ENV_DIR/bin/python" \
  "$REPO_ROOT/scripts/hedge_eagle3_phase01b_record_minimal_env.py" \
  --output-dir "$OUTPUT_DIR" \
  --single-variable-change "$VARIABLE_CHANGE"
