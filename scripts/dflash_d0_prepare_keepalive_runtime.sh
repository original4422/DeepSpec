#!/usr/bin/env bash
# Create a lane-local uv runtime for operational keepalive without downloads.

set -euo pipefail

EXPECTED_WORKER_ID=4099543
EXPECTED_GPUS=8
STATE_DIR="/tmp/deepspec-hedge-dflash/keepalive"
VENV="$STATE_DIR/venv"
PYTHON="$VENV/bin/python"
UV="/home/tiger/.local/bin/uv"
IDENTITY="$STATE_DIR/runtime_identity.json"

identity="$(
  nvidia-smi \
    --query-gpu=index,name \
    --format=csv,noheader,nounits
)"
if ! awk -F, -v expected="$EXPECTED_GPUS" '
  {
    count += 1
    name = $2
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
    if (($1 + 0) != count - 1 || name != "NVIDIA H20") bad = 1
  }
  END { exit !(count == expected && !bad) }
' <<<"$identity"; then
  echo "refusing runtime preparation outside the exact 8xH20 lane" >&2
  exit 2
fi

compute_rows="$(
  nvidia-smi \
    --query-compute-apps=gpu_uuid,pid,process_name \
    --format=csv,noheader,nounits
)"
if grep -q '[^[:space:]]' <<<"$compute_rows"; then
  echo "refusing runtime preparation while legacy GPU tasks exist" >&2
  printf '%s\n' "$compute_rows" >&2
  exit 3
fi

test -x "$UV"
test -x /usr/bin/python3
mkdir -p "$STATE_DIR"
if [ ! -x "$PYTHON" ]; then
  "$UV" venv \
    --python /usr/bin/python3 \
    --system-site-packages \
    "$VENV"
fi

timeout --signal=TERM --kill-after=5s 120s "$PYTHON" - "$IDENTITY" <<'PY'
import json
import pathlib
import socket
import sys
from datetime import datetime, timezone

import torch

if not torch.cuda.is_available() or torch.cuda.device_count() != 8:
    raise SystemExit(
        "keepalive runtime requires exactly 8 CUDA devices: "
        f"available={torch.cuda.is_available()} count={torch.cuda.device_count()}"
    )

document = {
    "schema_version": 1,
    "purpose": "DFlash operational keepalive only",
    "worker_id": "4099543",
    "hostname": socket.gethostname(),
    "created_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "venv": sys.prefix,
    "python": sys.executable,
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "cuda_device_count": torch.cuda.device_count(),
    "uses_system_site_packages": True,
}
pathlib.Path(sys.argv[1]).write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(document, sort_keys=True))
PY
