#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <patched-sglang-source> <hedge-venv> <unique-scratch>" >&2
  exit 2
fi

sglang_source="$(realpath "$1")"
hedge_venv="$(realpath "$2")"
scratch="$3"
uv_bin="/home/tiger/.local/bin/uv"
repo_root="$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")"
rust_prefix="/home/tiger/toolchains/deepspec-rust-1.90.0"
rustup_home="${rust_prefix}/rustup"
cargo_home="${rust_prefix}/cargo"
protoc="/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc"

if [[ ! -d "${sglang_source}/python" ]]; then
  echo "missing SGLang python project: ${sglang_source}/python" >&2
  exit 1
fi
if [[ ! -x "${hedge_venv}/bin/python" ]]; then
  echo "missing venv Python: ${hedge_venv}/bin/python" >&2
  exit 1
fi
if [[ ! -x "${uv_bin}" ]]; then
  echo "missing uv: ${uv_bin}" >&2
  exit 1
fi
if [[ ! -f "${repo_root}/pyproject.toml" || ! -f "${repo_root}/uv.lock" ]]; then
  echo "missing locked DeepSpec project metadata: ${repo_root}" >&2
  exit 1
fi
if [[ ! -x "${cargo_home}/bin/rustc" || ! -x "${cargo_home}/bin/cargo" ]]; then
  echo "missing fixed Rust 1.90.0 toolchain: ${rust_prefix}" >&2
  exit 1
fi
if [[ ! -x "${protoc}" ]]; then
  echo "missing fixed protoc 35.0: ${protoc}" >&2
  exit 1
fi
if [[ -e "${scratch}" ]]; then
  echo "scratch already exists: ${scratch}" >&2
  exit 1
fi

mkdir -p "${scratch}/wheel"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export RUSTUP_HOME="${rustup_home}"
export CARGO_HOME="${cargo_home}"
export PATH="${cargo_home}/bin:${PATH}"
export PROTOC="${protoc}"

"${uv_bin}" lock --check --project "${repo_root}"
VIRTUAL_ENV="${hedge_venv}" "${uv_bin}" sync \
  --project "${repo_root}" \
  --active \
  --frozen \
  --only-group p03-build \
  --inexact

"${hedge_venv}/bin/python" - <<'PY'
from importlib.metadata import version

expected = {
    "build": "1.5.0",
    "setuptools": "81.0.0",
    "setuptools-rust": "1.13.0",
    "setuptools-scm": "10.2.1",
    "wheel": "0.47.0",
}
for distribution, expected_version in expected.items():
    actual_version = version(distribution)
    if actual_version != expected_version:
        raise SystemExit(
            f"unexpected {distribution} version: "
            f"{actual_version} != {expected_version}"
        )
    print(f"build_dependency={distribution}=={actual_version}")
PY

rustc_version="$(rustc --version)"
[[ "${rustc_version}" == "rustc 1.90.0"* ]] || {
  echo "unexpected Rust compiler: ${rustc_version}" >&2
  exit 1
}
printf 'rustc=%s\n' "${rustc_version}"
printf 'cargo=%s\n' "$(cargo --version)"
protoc_version="$("${PROTOC}" --version)"
[[ "${protoc_version}" == "libprotoc 35.0" ]] || {
  echo "unexpected protoc: ${protoc_version}" >&2
  exit 1
}
printf 'protoc=%s\n' "${protoc_version}"

"${hedge_venv}/bin/python" -m build \
  --wheel \
  --no-isolation \
  --outdir "${scratch}/wheel" \
  "${sglang_source}/python"

mapfile -t wheels < <(find "${scratch}/wheel" -maxdepth 1 -type f -name '*.whl')
if [[ "${#wheels[@]}" -ne 1 ]]; then
  echo "expected exactly one wheel, found ${#wheels[@]}" >&2
  exit 1
fi

sha256sum "${wheels[0]}"
"${uv_bin}" pip install \
  --python "${hedge_venv}/bin/python" \
  --reinstall \
  --no-deps \
  "${wheels[0]}"

echo "wheel=${wheels[0]}"
