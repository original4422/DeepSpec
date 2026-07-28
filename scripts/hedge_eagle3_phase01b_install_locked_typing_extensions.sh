#!/usr/bin/env bash
# Install only the first dependency proven missing by the torch import.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_install_locked_typing_extensions.sh WORKER_ID ATTEMPT_DIR}"
ATTEMPT_DIR="${2:?usage: hedge_eagle3_phase01b_install_locked_typing_extensions.sh WORKER_ID ATTEMPT_DIR}"
REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
ENV_DIR="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
UV_BIN="/home/tiger/.local/bin/uv"
LANE_UV_CACHE="/tmp/deepspec-hedge-v4-eagle3/uv-cache"
DEP_DIR="/tmp/deepspec-hedge-v4-eagle3/direct-torch-04/deps"
WHEEL_NAME="typing_extensions-4.16.0-py3-none-any.whl"
PARTIAL="$DEP_DIR/$WHEEL_NAME.partial"
WHEEL="$DEP_DIR/$WHEEL_NAME"
URL="https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl"
EXPECTED_SHA256="481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8"
PREVIOUS="$ATTEMPT_DIR/direct_install.json"
OUTPUT="$ATTEMPT_DIR/typing_extensions_install.json"

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
test -f "$PREVIOUS"
if [ -e "$OUTPUT" ] || [ -e "$PARTIAL" ] || [ -e "$WHEEL" ]; then
  echo "refusing to overwrite dependency evidence or scratch" >&2
  exit 2
fi
export UV_CACHE_DIR="$LANE_UV_CACHE"
if [ "$UV_CACHE_DIR" != "/tmp/deepspec-hedge-v4-eagle3/uv-cache" ]; then
  echo "refusing non-lane uv cache" >&2
  exit 2
fi
mkdir -p "$DEP_DIR" "$UV_CACHE_DIR"

python3 - "$PREVIOUS" "$REPO_ROOT/uv.lock" "$URL" "$EXPECTED_SHA256" <<'PY'
import json
from pathlib import Path
import sys
import tomllib

previous = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if previous.get("status") != "IMPORT_FAILED":
    raise SystemExit("previous import did not establish a dependency blocker")
if "No module named 'typing_extensions'" not in previous.get("import_stderr", ""):
    raise SystemExit("first actual missing dependency is not typing_extensions")
lock = tomllib.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
matches = [
    package
    for package in lock["package"]
    if package.get("name") == "typing-extensions"
    and package.get("version") == "4.16.0"
]
if len(matches) != 1:
    raise SystemExit("typing-extensions lock identity is not unique")
wheels = [
    wheel for wheel in matches[0]["wheels"] if wheel["url"] == sys.argv[3]
]
if len(wheels) != 1 or wheels[0]["hash"] != f"sha256:{sys.argv[4]}":
    raise SystemExit("typing-extensions wheel differs from uv.lock")
PY

curl \
  --fail \
  --location \
  --max-time 120 \
  --silent \
  --show-error \
  --output "$PARTIAL" \
  "$URL"
actual_sha256="$(sha256sum "$PARTIAL" | awk '{print $1}')"
if [ "$actual_sha256" != "$EXPECTED_SHA256" ]; then
  echo "typing-extensions SHA-256 mismatch" >&2
  exit 2
fi
mv "$PARTIAL" "$WHEEL"

"$UV_BIN" pip install \
  --python "$ENV_DIR/bin/python" \
  --no-deps \
  "$WHEEL" \
  >"$ATTEMPT_DIR/typing_extensions_uv.stdout.txt" \
  2>"$ATTEMPT_DIR/typing_extensions_uv.stderr.txt"

set +e
LD_LIBRARY_PATH="/usr/local/cuda/compat:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}" \
  "$ENV_DIR/bin/python" - <<'PY' \
  >"$ATTEMPT_DIR/typing_extensions_import.stdout.txt" \
  2>"$ATTEMPT_DIR/typing_extensions_import.stderr.txt"
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
  "$OUTPUT" \
  "$WHEEL" \
  "$EXPECTED_SHA256" \
  "$import_rc" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
stderr = output.parent / "typing_extensions_import.stderr.txt"
stdout = output.parent / "typing_extensions_import.stdout.txt"
import_rc = int(sys.argv[4])
output.write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "IMPORT_PASS" if import_rc == 0 else "IMPORT_FAILED",
            "dependency": "typing-extensions==4.16.0",
            "wheel_path": sys.argv[2],
            "wheel_sha256": sys.argv[3],
            "uv_cache_dir": (
                "/tmp/deepspec-hedge-v4-eagle3/uv-cache"
            ),
            "uv_local_no_deps": True,
            "import_returncode": import_rc,
            "import_stdout": stdout.read_text(encoding="utf-8"),
            "import_stderr": stderr.read_text(encoding="utf-8"),
            "cuda_operation_performed": False,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
if [ "$import_rc" -ne 0 ]; then
  echo "TYPING_EXTENSIONS_NEXT_IMPORT_FAILED evidence=$OUTPUT" >&2
  exit "$import_rc"
fi
printf 'TYPING_EXTENSIONS_IMPORT_PASS evidence=%s\n' "$OUTPUT"
