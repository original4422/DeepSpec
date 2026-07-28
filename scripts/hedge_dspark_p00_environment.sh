#!/usr/bin/env bash
# Build the isolated P00 uv environment and exact SGLang base source.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly BASE_SOURCE="/home/tiger/src/deepspec-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
readonly TARGET_SOURCE="/home/tiger/src/hedge-v4-dspark-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
readonly TARGET_VENV="/home/tiger/venvs/hedge-v4-dspark"
readonly EXPECTED_SHA="fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
readonly RUST_PREFIX="/home/tiger/toolchains/deepspec-rust-1.90.0"
readonly PROTOC="/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc"
readonly EXISTING_UV_CACHE="/home/tiger/.cache/deepspec-phase03-20260728T163751Z/uv-cache"
readonly ARTIFACT_DIR="${1:?artifact directory is required}"
readonly ATTEMPT_ID="${2:?attempt ID is required}"
readonly SCRATCH="/tmp/deepspec-hedge-dspark-${ATTEMPT_ID}"

case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
case "$ATTEMPT_ID" in
  *[!A-Za-z0-9._-]*|"")
    echo "invalid attempt ID" >&2
    exit 2
    ;;
esac

[[ -s "$REPO_ROOT/pyproject.toml" && -s "$REPO_ROOT/uv.lock" ]]
[[ -x "$PROTOC" ]]
[[ -d "$EXISTING_UV_CACHE/git-v0/checkouts" ]]
[[ -d "$BASE_SOURCE/.git" ]]
[[ "$(git -C "$BASE_SOURCE" rev-parse HEAD)" = "$EXPECTED_SHA" ]]
[[ -z "$(git -C "$BASE_SOURCE" status --porcelain)" ]]

if [[ -e "$SCRATCH" ]]; then
  echo "refusing existing scratch path: $SCRATCH" >&2
  exit 1
fi
mkdir -p -- "$SCRATCH/uv-cache" "$ARTIFACT_DIR"
: >"$SCRATCH/source_clone.log"
cached_checkout="$(
  find "$EXISTING_UV_CACHE/git-v0/checkouts" \
    -mindepth 2 -maxdepth 2 -type d \
    -name "${EXPECTED_SHA:0:10}" -print -quit
)"
[[ -n "$cached_checkout" && -d "$cached_checkout/.git" ]]
[[ "$(git -C "$cached_checkout" rev-parse HEAD)" = "$EXPECTED_SHA" ]]
printf 'cache_path=%s\ncached_checkout=%s\ncached_commit=%s\n' \
  "$EXISTING_UV_CACHE" "$cached_checkout" "$EXPECTED_SHA" \
  >"$SCRATCH/uv-cache-identity.txt"
printf 'pid=%s\npgid=%s\nsid=%s\nstarted_at_utc=%s\nuv_command=%s\nuv_cache=%s\n' \
  "$$" \
  "$(ps -o pgid= -p "$$" | tr -d ' ')" \
  "$(ps -o sid= -p "$$" | tr -d ' ')" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "uv sync --frozen --python 3.11" \
  "$EXISTING_UV_CACHE" \
  >"$SCRATCH/environment_setup.identity"

if [[ -e "$TARGET_SOURCE" ]]; then
  [[ -d "$TARGET_SOURCE/.git" ]] || {
    echo "refusing unknown target source path: $TARGET_SOURCE" >&2
    exit 1
  }
  [[ "$(git -C "$TARGET_SOURCE" rev-parse HEAD)" = "$EXPECTED_SHA" ]]
  [[ -z "$(git -C "$TARGET_SOURCE" status --porcelain)" ]]
else
  git clone --no-hardlinks --no-checkout "$BASE_SOURCE" "$TARGET_SOURCE" \
    >>"$SCRATCH/source_clone.log" 2>&1
  git -C "$TARGET_SOURCE" checkout --detach "$EXPECTED_SHA" \
    >>"$SCRATCH/source_clone.log" 2>&1
  git -C "$TARGET_SOURCE" remote set-url origin \
    https://github.com/sgl-project/sglang.git
fi
if [[ ! -s "$SCRATCH/source_clone.log" ]]; then
  printf 'reused_existing_clean_source=%s\ncommit=%s\n' \
    "$TARGET_SOURCE" "$EXPECTED_SHA" >"$SCRATCH/source_clone.log"
fi
[[ "$(git -C "$TARGET_SOURCE" rev-parse HEAD)" = "$EXPECTED_SHA" ]]
[[ -z "$(git -C "$TARGET_SOURCE" status --porcelain)" ]]

if [[ -e "$TARGET_VENV" && ! -f "$TARGET_VENV/pyvenv.cfg" ]]; then
  echo "refusing unknown target venv path: $TARGET_VENV" >&2
  exit 1
fi

export RUSTUP_HOME="$RUST_PREFIX/rustup"
export CARGO_HOME="$RUST_PREFIX/cargo"
export PATH="$CARGO_HOME/bin:/home/tiger/.local/bin:/usr/local/bin:/usr/bin:/bin"
export PROTOC
export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
export UV_CACHE_DIR="$EXISTING_UV_CACHE"
export UV_HTTP_TIMEOUT=600
export UV_LINK_MODE=copy

(
  cd "$REPO_ROOT"
  uv sync --frozen --python 3.11
) >"$SCRATCH/uv-sync.log" 2>&1
uv pip check --python "$TARGET_VENV/bin/python" \
  >"$SCRATCH/uv-pip-check.log" 2>&1

"$TARGET_VENV/bin/python" - "$ARTIFACT_DIR/environment_identity.json" \
  "$REPO_ROOT" "$TARGET_VENV" "$EXPECTED_SHA" \
  "$EXISTING_UV_CACHE" "$cached_checkout" <<'PY'
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

output = Path(sys.argv[1])
repo_root = Path(sys.argv[2])
venv = Path(sys.argv[3])
expected_sglang_sha = sys.argv[4]
uv_cache = Path(sys.argv[5])
cached_checkout = Path(sys.argv[6])

def version(distribution: str):
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None

import sglang
import torch

lock = repo_root / "uv.lock"
payload = {
    "schema_version": 1,
    "authorized_phase": "P00",
    "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    "hostname": platform.node(),
    "venv": str(venv),
    "python": {
        "executable": sys.executable,
        "version": platform.python_version(),
    },
    "uv": subprocess.run(
        ["uv", "--version"], capture_output=True, text=True, check=True
    ).stdout.strip(),
    "uv_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    "uv_sync_command": ["uv", "sync", "--frozen", "--python", "3.11"],
    "uv_cache": {
        "path": str(uv_cache),
        "cached_sglang_checkout": str(cached_checkout),
        "cached_sglang_commit": expected_sglang_sha,
        "link_mode": "copy",
    },
    "packages": {
        name: version(name)
        for name in (
            "torch",
            "sglang",
            "sglang-kernel",
            "flashinfer-python",
            "triton",
            "nvidia-nccl-cu13",
            "nvidia-cuda-runtime",
            "nvidia-cuda-nvrtc",
            "nvidia-cuda-nvcc",
        )
    },
    "torch_cuda_version": torch.version.cuda,
    "sglang_import_path": str(Path(sglang.__file__).resolve()),
    "sglang_expected_source_commit": expected_sglang_sha,
    "cuda_probe_deferred_while_keepalive_active": True,
    "resolved_environment": {
        "VIRTUAL_ENV": str(venv),
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "SGLANG_DSV4_FP4_DEQUANT": "unset",
    },
}
temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
PY

python3 - "$ARTIFACT_DIR/sglang_base_identity.json" \
  "$TARGET_SOURCE" "$BASE_SOURCE" "$EXPECTED_SHA" <<'PY'
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

output = Path(sys.argv[1])
target = Path(sys.argv[2])
base = Path(sys.argv[3])
expected = sys.argv[4]

def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

payload = {
    "schema_version": 1,
    "authorized_phase": "P00",
    "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    "target_source": str(target),
    "source_commit": git(target, "rev-parse", "HEAD"),
    "expected_source_commit": expected,
    "clean": git(target, "status", "--porcelain") == "",
    "origin": git(target, "remote", "get-url", "origin"),
    "clone_source": str(base),
    "clone_source_commit": git(base, "rev-parse", "HEAD"),
    "clone_mode": "git clone --no-hardlinks; detached checkout",
}
payload["status"] = (
    "PASS"
    if payload["source_commit"] == expected
    and payload["clone_source_commit"] == expected
    and payload["clean"]
    else "FAIL"
)
temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
if payload["status"] != "PASS":
    raise SystemExit("SGLang source identity failed")
PY

cp -- "$SCRATCH/environment_setup.identity" \
  "$ARTIFACT_DIR/environment_setup.identity"
cp -- "$SCRATCH/uv-cache-identity.txt" \
  "$ARTIFACT_DIR/uv-cache-identity.txt"
cp -- "$SCRATCH/source_clone.log" "$ARTIFACT_DIR/source_clone.log"
cp -- "$SCRATCH/uv-sync.log" "$ARTIFACT_DIR/uv-sync.log"
cp -- "$SCRATCH/uv-pip-check.log" "$ARTIFACT_DIR/uv-pip-check.log"
printf 'finished_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  >>"$ARTIFACT_DIR/environment_setup.identity"

echo "P00 environment setup PASS"
