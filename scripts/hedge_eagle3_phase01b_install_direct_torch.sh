#!/usr/bin/env bash
# Install the hash-verified local torch wheel with uv and probe import only.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_install_direct_torch.sh WORKER_ID ATTEMPT_DIR}"
ATTEMPT_DIR="${2:?usage: hedge_eagle3_phase01b_install_direct_torch.sh WORKER_ID ATTEMPT_DIR}"
DOWNLOAD="$ATTEMPT_DIR/direct_download.json"
ENV_DIR="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
UV_BIN="/home/tiger/.local/bin/uv"
LANE_UV_CACHE="/tmp/deepspec-hedge-v4-eagle3/uv-cache"
EXPECTED_SHA256="225b22e0a4e36ea573d3a68796e6816a160616f67e8b8c55683a88bf7777f4cd"

if [ "$WORKER_ID" != "$EXPECTED_WORKER" ]; then
  echo "refusing unassigned worker: $WORKER_ID" >&2
  exit 2
fi
case "$ATTEMPT_DIR" in
  /mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/*)
    ;;
  *)
    echo "refusing attempt outside Eagle3 run root" >&2
    exit 2
    ;;
esac
test -x "$UV_BIN"
test -x "$ENV_DIR/bin/python"
test -f "$DOWNLOAD"
export UV_CACHE_DIR="$LANE_UV_CACHE"
if [ "$UV_CACHE_DIR" != "/tmp/deepspec-hedge-v4-eagle3/uv-cache" ]; then
  echo "refusing non-lane uv cache" >&2
  exit 2
fi
if [ -e "$ATTEMPT_DIR/direct_install.json" ]; then
  echo "refusing to overwrite direct install evidence" >&2
  exit 2
fi

wheel="$(
  python3 - "$DOWNLOAD" "$EXPECTED_SHA256" <<'PY'
import json
from pathlib import Path
import sys

download = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if download.get("status") != "DIRECT_DOWNLOAD_PASS":
    raise SystemExit("direct download gate did not pass")
if download.get("wheel_sha256") != sys.argv[2]:
    raise SystemExit("download evidence has the wrong SHA-256")
print(download["wheel_path"])
PY
)"
test -f "$wheel"
actual_sha256="$(sha256sum "$wheel" | awk '{print $1}')"
if [ "$actual_sha256" != "$EXPECTED_SHA256" ]; then
  echo "local wheel hash changed before install" >&2
  exit 2
fi

set +e
"$UV_BIN" pip install \
  --python "$ENV_DIR/bin/python" \
  --no-deps \
  "$wheel" \
  >"$ATTEMPT_DIR/direct_uv_install.stdout.txt" \
  2>"$ATTEMPT_DIR/direct_uv_install.stderr.txt"
install_rc=$?
set -e
if [ "$install_rc" -ne 0 ]; then
  python3 - \
    "$ATTEMPT_DIR/direct_install.json" \
    "$wheel" \
    "$install_rc" <<'PY'
import json
from pathlib import Path
import sys

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "LOCAL_UV_INSTALL_FAILED",
            "wheel_path": sys.argv[2],
            "uv_returncode": int(sys.argv[3]),
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

set +e
LD_LIBRARY_PATH="/usr/local/cuda/compat:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}" \
  "$ENV_DIR/bin/python" - <<'PY' \
  >"$ATTEMPT_DIR/direct_import.stdout.txt" \
  2>"$ATTEMPT_DIR/direct_import.stderr.txt"
import json
import torch

print(
    json.dumps(
        {
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "cuda_initialized": torch.cuda.is_initialized(),
        },
        sort_keys=True,
    )
)
PY
import_rc=$?
set -e

python3 - \
  "$ATTEMPT_DIR/direct_install.json" \
  "$wheel" \
  "$EXPECTED_SHA256" \
  "$install_rc" \
  "$import_rc" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
import_stderr = output.parent / "direct_import.stderr.txt"
import_stdout = output.parent / "direct_import.stdout.txt"
import_rc = int(sys.argv[5])
payload = {
    "schema_version": 1,
    "status": "IMPORT_PASS" if import_rc == 0 else "IMPORT_FAILED",
    "worker_id": "4099544",
    "wheel_path": sys.argv[2],
    "wheel_sha256": sys.argv[3],
    "uv_local_no_deps": True,
    "uv_returncode": int(sys.argv[4]),
    "import_returncode": import_rc,
    "import_stdout": import_stdout.read_text(encoding="utf-8"),
    "import_stderr": import_stderr.read_text(encoding="utf-8"),
    "cuda_operation_performed": False,
}
output.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

if [ "$import_rc" -ne 0 ]; then
  echo "DIRECT_TORCH_IMPORT_FAILED evidence=$ATTEMPT_DIR/direct_install.json" >&2
  exit "$import_rc"
fi
printf 'DIRECT_TORCH_IMPORT_PASS evidence=%s\n' \
  "$ATTEMPT_DIR/direct_install.json"
