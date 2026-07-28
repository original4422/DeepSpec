#!/usr/bin/env bash
# Retry the exact minimal torch install with uv's system-certificate TLS
# backend. The package, version, index, cache, venv and Python stay fixed.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_retry_uv_system_certs.sh WORKER_ID OUTPUT_DIR}"
OUTPUT_DIR="${2:?usage: hedge_eagle3_phase01b_retry_uv_system_certs.sh WORKER_ID OUTPUT_DIR}"
ENV_DIR="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
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
test -x "$ENV_DIR/bin/python"
test -f "$ENV_DIR/pyvenv.cfg"

umask 027
mkdir -p "$OUTPUT_DIR"
export UV_CACHE_DIR="$SCRATCH_ROOT/uv-cache"
export UV_PYTHON_DOWNLOADS=never

set +e
"$UV_BIN" pip install \
  --python "$ENV_DIR/bin/python" \
  --index https://download.pytorch.org/whl/cu130 \
  --system-certs \
  --verbose \
  "torch==2.11.0" \
  >"$OUTPUT_DIR/uv-install.stdout.txt" \
  2>"$OUTPUT_DIR/uv-install.stderr.txt"
install_rc=$?
set -e

if [ "$install_rc" -ne 0 ]; then
  python3 - "$OUTPUT_DIR/attempt_status.json" "$install_rc" <<'PY'
import datetime as dt
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = {
    "schema_version": 1,
    "status": "FAILED",
    "finished_at": dt.datetime.now(dt.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "returncode": int(sys.argv[2]),
    "single_variable_change": (
        "uv bundled TLS -> uv --system-certs "
        "(current uv equivalent of native TLS)"
    ),
}
path.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
  exit "$install_rc"
fi

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
freeze_path = output_path.parent / "minimal_uv_freeze.txt"
freeze_path.write_text(freeze, encoding="utf-8")
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
    "freeze_path": str(freeze_path),
    "freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
    "single_variable_change": (
        "uv bundled TLS -> uv --system-certs "
        "(current uv equivalent of native TLS)"
    ),
    "install_stdout": str(output_path.parent / "uv-install.stdout.txt"),
    "install_stderr": str(output_path.parent / "uv-install.stderr.txt"),
}
if payload["cuda_initialized"]:
    raise RuntimeError("minimal environment bootstrap unexpectedly initialized CUDA")
output_path.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

python3 - "$OUTPUT_DIR/attempt_status.json" <<'PY'
import datetime as dt
import json
from pathlib import Path
import sys

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "PASS",
            "finished_at": dt.datetime.now(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "single_variable_change": (
                "uv bundled TLS -> uv --system-certs "
                "(current uv equivalent of native TLS)"
            ),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

printf 'MINIMAL_UV_READY artifact=%s\n' \
  "$OUTPUT_DIR/minimal_environment.json"
