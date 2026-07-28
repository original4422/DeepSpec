#!/usr/bin/env bash
# Synchronize the complete Eagle3 uv environment from the frozen lane lock.

set -euo pipefail

REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
SOURCE_ROOT="/home/tiger/src/sglang-hedge-v4-eagle3"
VENV="/home/tiger/venvs/deepspec-hedge-v4-eagle3"
PYTHON="$VENV/bin/python"
UV="/home/tiger/.local/bin/uv"
UV_CACHE="/tmp/deepspec-hedge-v4-eagle3/uv-cache"
COMPAT_ROOT="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
RUST_ROOT="/home/tiger/toolchains/deepspec-rust-1.90.0"
PROTOC="/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc"
ATTEMPT_ID="${1:-20260728T224200Z-phase-01b-full-env-07}"
case "$ATTEMPT_ID" in
  20260728T224200Z-phase-01b-full-env-07|\
  20260728T224500Z-phase-01b-full-env-rust-08|\
  20260728T224800Z-phase-01b-full-env-protoc-09)
    ;;
  *)
    echo "refusing unknown full-environment attempt ID" >&2
    exit 2
    ;;
esac
SCRATCH="/tmp/deepspec-hedge-v4-eagle3/$ATTEMPT_ID"
OUTPUT="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/$ATTEMPT_ID"

if [ -e "$SCRATCH" ] || [ -e "$OUTPUT" ]; then
  echo "refusing to overwrite full-environment attempt" >&2
  exit 2
fi
test -x "$PYTHON"
test -x "$UV"
test -f "$REPO_ROOT/pyproject.toml"
test -f "$REPO_ROOT/uv.lock"
test -e "$SOURCE_ROOT/.git"
test -f "$COMPAT_ROOT/libcuda.so.1"
test -x "$RUST_ROOT/cargo/bin/cargo"
test -x "$RUST_ROOT/cargo/bin/rustc"
test -x "$PROTOC"
if [ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" != \
  "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1" ]; then
  echo "fixed SGLang source identity differs" >&2
  exit 2
fi
if [ -n "$(git -C "$SOURCE_ROOT" status --porcelain=v1)" ]; then
  echo "fixed SGLang source is dirty before environment sync" >&2
  exit 2
fi

mkdir -p "$SCRATCH" "$OUTPUT" "$UV_CACHE"
exec >"$SCRATCH/environment_sync.log" 2>&1

publish() {
  local original_rc=$?
  trap - EXIT
  set +e
  for source_path in "$SCRATCH"/*; do
    if [ -f "$source_path" ]; then
      destination="$OUTPUT/$(basename "$source_path")"
      temporary="$destination.tmp.$$"
      cp "$source_path" "$temporary"
      mv "$temporary" "$destination"
    fi
  done
  exit "$original_rc"
}
trap publish EXIT

printf 'attempt_id=%s\nstarted_at=%s\nrepo=%s\nsource=%s\nvenv=%s\n' \
  "$ATTEMPT_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$REPO_ROOT" "$SOURCE_ROOT" "$VENV"
printf 'pyproject_sha256=%s\nuv_lock_sha256=%s\nsource_head=%s\n' \
  "$(sha256sum "$REPO_ROOT/pyproject.toml" | awk '{print $1}')" \
  "$(sha256sum "$REPO_ROOT/uv.lock" | awk '{print $1}')" \
  "$(git -C "$SOURCE_ROOT" rev-parse HEAD)"

export VIRTUAL_ENV="$VENV"
export UV_PROJECT_ENVIRONMENT="$VENV"
export UV_CACHE_DIR="$UV_CACHE"
export UV_LINK_MODE="copy"
export UV_NO_PROGRESS=1
export PATH="$RUST_ROOT/cargo/bin:$(dirname "$PROTOC"):/usr/local/bin:/usr/bin:/bin"
export RUSTUP_HOME="$RUST_ROOT/rustup"
export CARGO_HOME="$RUST_ROOT/cargo"
export PROTOC
printf 'rustc=%s\ncargo=%s\nprotoc=%s\n' \
  "$(rustc --version)" "$(cargo --version)" "$(protoc --version)"

"$UV" sync \
  --project "$REPO_ROOT" \
  --frozen \
  --no-install-project \
  --python "$PYTHON"

"$UV" pip install \
  --python "$PYTHON" \
  --no-deps \
  --editable "$SOURCE_ROOT/python"

"$UV" pip check --python "$PYTHON" \
  >"$SCRATCH/uv_pip_check.log" 2>&1

SITE_PACKAGES="$VENV/lib/python3.11/site-packages"
NVIDIA_LIB_DIRS=()
for library_dir in "$SITE_PACKAGES"/nvidia/*/lib; do
  if [ -d "$library_dir" ]; then
    NVIDIA_LIB_DIRS+=("$library_dir")
  fi
done
if [ "${#NVIDIA_LIB_DIRS[@]}" -eq 0 ]; then
  echo "no NVIDIA wheel library directories after uv sync" >&2
  exit 2
fi
LANE_LIBRARY_PATH="$(
  IFS=:
  printf '%s' "${NVIDIA_LIB_DIRS[*]}"
)"
export LD_LIBRARY_PATH="${COMPAT_ROOT}:${LANE_LIBRARY_PATH}:/usr/local/cuda/lib64"
export CUDA_VISIBLE_DEVICES=""

"$PYTHON" -c '
import importlib.metadata
import json
import pathlib
import sglang
import torch

print(json.dumps({
    "python": __import__("sys").version,
    "python_executable": __import__("sys").executable,
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "torch_cuda_initialized": torch.cuda.is_initialized(),
    "torch_import_path": str(pathlib.Path(torch.__file__).resolve()),
    "sglang_version": importlib.metadata.version("sglang"),
    "sglang_import_path": str(pathlib.Path(sglang.__file__).resolve()),
}, indent=2, sort_keys=True))
' >"$SCRATCH/import_identity.json"

printf 'finished_at=%s\nstatus=PASS\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
