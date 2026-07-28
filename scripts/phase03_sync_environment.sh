#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly VENV_PATH="/home/tiger/venvs/deepspec-dspark"
readonly CACHE_ROOT="/home/tiger/.cache/deepspec-phase03-20260728T163751Z"
readonly UV_CACHE_PATH="${CACHE_ROOT}/uv-cache"
readonly LOG_PATH="${CACHE_ROOT}/uv-sync.log"
readonly RUST_PREFIX="/home/tiger/toolchains/deepspec-rust-1.90.0"
readonly RUSTUP_PATH="${RUST_PREFIX}/rustup"
readonly CARGO_PATH="${RUST_PREFIX}/cargo"
readonly PROTOC_PATH="/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc"

cd "${REPO_ROOT}"
[[ -s pyproject.toml ]] || {
  echo "Missing pyproject.toml" >&2
  exit 1
}
[[ -s uv.lock ]] || {
  echo "Missing uv.lock" >&2
  exit 1
}
[[ -x "${PROTOC_PATH}" ]] || {
  echo "Missing fixed protoc build tool: ${PROTOC_PATH}" >&2
  exit 1
}

if [[ -e "${VENV_PATH}" && ! -f "${VENV_PATH}/pyvenv.cfg" ]]; then
  echo "Refusing to overwrite unknown formal environment path: ${VENV_PATH}" >&2
  exit 1
fi

mkdir -p "${CACHE_ROOT}" "${UV_CACHE_PATH}"
printf 'pid=%s pgid=%s started_at=%s\n' \
  "$$" "$(ps -o pgid= -p "$$" | tr -d ' ')" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > "${CACHE_ROOT}/uv-sync.identity"

export RUSTUP_HOME="${RUSTUP_PATH}"
export CARGO_HOME="${CARGO_PATH}"
export PATH="${CARGO_PATH}/bin:${PATH}"
export PROTOC="${PROTOC_PATH}"
export UV_PROJECT_ENVIRONMENT="${VENV_PATH}"
export UV_CACHE_DIR="${UV_CACHE_PATH}"
export UV_HTTP_TIMEOUT=600
export UV_LINK_MODE=copy

uv sync --frozen --python 3.11 2>&1 | tee "${LOG_PATH}"

"${VENV_PATH}/bin/python" --version
uv pip check --python "${VENV_PATH}/bin/python"
printf 'finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  >> "${CACHE_ROOT}/uv-sync.identity"
