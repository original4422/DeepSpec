#!/usr/bin/env bash
# Establish the minimal, lane-owned uv environment needed by the Eagle3
# operational keepalive. This performs no CUDA operation.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_bootstrap_uv.sh WORKER_ID OUTPUT_DIR}"
OUTPUT_DIR="${2:?usage: hedge_eagle3_phase01b_bootstrap_uv.sh WORKER_ID OUTPUT_DIR}"
ENV_DIR="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
STATE_DIR="/home/tiger/.deepspec-hedge-v4-eagle3"
SCRATCH_ROOT="/tmp/deepspec-hedge-v4-eagle3"
UV_BIN="/home/tiger/.local/bin/uv"

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

umask 027
mkdir -p "$OUTPUT_DIR" "$STATE_DIR" "$SCRATCH_ROOT/uv-cache"
export UV_CACHE_DIR="$SCRATCH_ROOT/uv-cache"
export UV_PYTHON_DOWNLOADS=never

if [ -e "$ENV_DIR" ]; then
  test -x "$ENV_DIR/bin/python"
  test -f "$ENV_DIR/pyvenv.cfg"
else
  "$UV_BIN" venv --python 3.11 "$ENV_DIR"
fi

"$UV_BIN" pip install \
  --python "$ENV_DIR/bin/python" \
  --index https://download.pytorch.org/whl/cu130 \
  "torch==2.11.0"

"$ENV_DIR/bin/python" - "$OUTPUT_DIR/minimal_environment.json" <<'PY'
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import torch

output_path = Path(sys.argv[1])
freeze = subprocess.run(
    [
        "/home/tiger/.local/bin/uv",
        "pip",
        "freeze",
        "--python",
        sys.executable,
    ],
    check=True,
    capture_output=True,
    text=True,
).stdout
(output_path.parent / "minimal_uv_freeze.txt").write_text(
    freeze,
    encoding="utf-8",
)
payload = {
    "schema_version": 1,
    "created_at": dt.datetime.now(dt.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "purpose": "minimal Eagle3 operational keepalive prerequisite",
    "worker_id": "4099544",
    "hostname": platform.node(),
    "environment": "/home/tiger/venvs/deepspec-hedge-v4-eagle3",
    "python_executable": sys.executable,
    "python_version": platform.python_version(),
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "cuda_initialized": torch.cuda.is_initialized(),
    "cuda_operation_performed": False,
    "uv_version": subprocess.run(
        ["/home/tiger/.local/bin/uv", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip(),
    "uv_cache_dir": os.environ["UV_CACHE_DIR"],
    "freeze_path": str(output_path.parent / "minimal_uv_freeze.txt"),
    "freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
}
if payload["cuda_initialized"]:
    raise RuntimeError("minimal environment bootstrap unexpectedly initialized CUDA")
output_path.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
