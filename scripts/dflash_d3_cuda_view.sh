#!/usr/bin/env bash
# Build or verify the private CUDA 13.0 filesystem view used by DFlash D3.
set -Eeuo pipefail

readonly ACTION="${1:?action required: ensure or verify}"
readonly VIEW="/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0"
readonly PAYLOAD="/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13"
readonly COMPAT_LIB="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat/libcuda.so.580.173.02"

[[ "${ACTION}" = "ensure" || "${ACTION}" = "verify" ]]

fail() {
  printf 'FAIL action=%s reason=%s\n' "${ACTION}" "$*" >&2
  exit 1
}

require_target_dir() {
  [[ -d "$1" && ! -L "$1" ]] || fail "missing or invalid target directory: $1"
}

require_target_file() {
  [[ -f "$1" && ! -L "$1" ]] || fail "missing or invalid target file: $1"
}

ensure_real_dir() {
  local path="$1"
  if [[ -L "${path}" ]]; then
    fail "refusing symlink directory: ${path}"
  elif [[ -e "${path}" ]]; then
    [[ -d "${path}" ]] || fail "refusing non-directory entity: ${path}"
  elif [[ "${ACTION}" = "ensure" ]]; then
    mkdir -- "${path}"
  else
    fail "missing directory: ${path}"
  fi
}

ensure_exact_link() {
  local link="$1" target="$2"
  if [[ -e "${link}" || -L "${link}" ]]; then
    [[ -L "${link}" ]] || fail "refusing existing non-symlink entity: ${link}"
    [[ "$(readlink -- "${link}")" = "${target}" ]] \
      || fail "symlink target mismatch: ${link}"
  elif [[ "${ACTION}" = "ensure" ]]; then
    ln -s -- "${target}" "${link}"
  else
    fail "missing symlink: ${link}"
  fi
  [[ -L "${link}" ]] || fail "not a symlink after ${ACTION}: ${link}"
  [[ "$(readlink -- "${link}")" = "${target}" ]] \
    || fail "symlink target mismatch after ${ACTION}: ${link}"
  [[ "$(readlink -f -- "${link}")" = "$(readlink -f -- "${target}")" ]] \
    || fail "resolved symlink target mismatch: ${link}"
}

require_target_dir "${PAYLOAD}/bin"
require_target_dir "${PAYLOAD}/include"
require_target_dir "${PAYLOAD}/nvvm"
require_target_file "${PAYLOAD}/lib/libcudart.so.13"
require_target_file "${PAYLOAD}/lib/libnvrtc.so.13"
require_target_file "${COMPAT_LIB}"

ensure_real_dir "/tmp/deepspec-hedge-dflash"
ensure_real_dir "/tmp/deepspec-hedge-dflash/toolchains"
ensure_real_dir "${VIEW}"
ensure_real_dir "${VIEW}/lib64"
ensure_real_dir "${VIEW}/lib64/stubs"

ensure_exact_link "${VIEW}/bin" "${PAYLOAD}/bin"
ensure_exact_link "${VIEW}/include" "${PAYLOAD}/include"
ensure_exact_link "${VIEW}/nvvm" "${PAYLOAD}/nvvm"
ensure_exact_link "${VIEW}/lib64/libcudart.so" "${PAYLOAD}/lib/libcudart.so.13"
ensure_exact_link "${VIEW}/lib64/libnvrtc.so" "${PAYLOAD}/lib/libnvrtc.so.13"
ensure_exact_link "${VIEW}/lib64/stubs/libcuda.so" "${COMPAT_LIB}"

printf '{"schema_version":1,"status":"PASS","action":"%s","cuda_view":"%s","payload":"%s","compat_libcuda":"%s"}\n' \
  "${ACTION}" "${VIEW}" "${PAYLOAD}" "${COMPAT_LIB}"
