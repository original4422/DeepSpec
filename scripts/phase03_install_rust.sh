#!/usr/bin/env bash
set -euo pipefail

readonly RUST_PREFIX="/home/tiger/toolchains/deepspec-rust-1.90.0"
readonly RUSTUP_DIR="${RUST_PREFIX}/rustup"
readonly CARGO_DIR="${RUST_PREFIX}/cargo"
readonly CACHE_DIR="/home/tiger/.cache/deepspec-phase03-20260728T163751Z"
readonly INSTALLER="${CACHE_DIR}/rustup-init.sh"
readonly EXPECTED_VERSION="rustc 1.90.0"

if [[ -x "${CARGO_DIR}/bin/rustc" ]]; then
  actual_version="$(
    RUSTUP_HOME="${RUSTUP_DIR}" CARGO_HOME="${CARGO_DIR}" \
      "${CARGO_DIR}/bin/rustc" --version
  )"
  [[ "${actual_version}" == "${EXPECTED_VERSION}"* ]] || {
    echo "Existing Phase 03 Rust toolchain has unexpected version: ${actual_version}" >&2
    exit 1
  }
  RUSTUP_HOME="${RUSTUP_DIR}" CARGO_HOME="${CARGO_DIR}" \
    "${CARGO_DIR}/bin/cargo" --version
  printf '%s\n' "${actual_version}"
  exit 0
fi

if [[ -e "${RUST_PREFIX}" ]]; then
  echo "Refusing to overwrite incomplete or unknown Rust prefix: ${RUST_PREFIX}" >&2
  exit 1
fi

mkdir -p "${CACHE_DIR}"
curl --fail --location --retry 3 --connect-timeout 30 --max-time 300 \
  https://sh.rustup.rs -o "${INSTALLER}"
sha256sum "${INSTALLER}"

mkdir -p "${RUST_PREFIX}"
RUSTUP_HOME="${RUSTUP_DIR}" CARGO_HOME="${CARGO_DIR}" \
  sh "${INSTALLER}" -y --profile minimal --default-toolchain 1.90.0 \
  --no-modify-path

RUSTUP_HOME="${RUSTUP_DIR}" CARGO_HOME="${CARGO_DIR}" \
  "${CARGO_DIR}/bin/cargo" --version
RUSTUP_HOME="${RUSTUP_DIR}" CARGO_HOME="${CARGO_DIR}" \
  "${CARGO_DIR}/bin/rustc" --version
