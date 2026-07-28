#!/usr/bin/env bash
# Idempotently expose CUDA 13 runtime libraries at FlashInfer's lib64 link seam.
set -euo pipefail

readonly CUDA_ROOT="/home/tiger/venvs/deepspec-dspark/lib/python3.11/site-packages/nvidia/cu13"
readonly CUDA_LIB="${CUDA_ROOT}/lib"
readonly CUDA_LIB64="${CUDA_ROOT}/lib64"

[[ -d "${CUDA_ROOT}" ]] || {
  printf 'expected CUDA root is missing: %s\n' "${CUDA_ROOT}" >&2
  exit 1
}
[[ ! -L "${CUDA_LIB64}" ]] || {
  printf 'refusing symlinked lib64 directory: %s\n' "${CUDA_LIB64}" >&2
  exit 1
}

for library in libcudart.so.13 libnvrtc.so.13; do
  [[ -f "${CUDA_LIB}/${library}" ]] || {
    printf 'required source library is missing: %s\n' \
      "${CUDA_LIB}/${library}" >&2
    exit 1
  }
done

mkdir -p "${CUDA_LIB64}"

ensure_relative_link() {
  local link_name="$1"
  local source_name="$2"
  local expected_target="../lib/${source_name}"
  local destination="${CUDA_LIB64}/${link_name}"

  if [[ -L "${destination}" ]]; then
    [[ "$(readlink "${destination}")" = "${expected_target}" ]] || {
      printf 'refusing conflicting symlink: %s -> %s\n' \
        "${destination}" "$(readlink "${destination}")" >&2
      return 1
    }
  elif [[ -e "${destination}" ]]; then
    printf 'refusing existing non-symlink: %s\n' "${destination}" >&2
    return 1
  else
    ln -s "${expected_target}" "${destination}"
  fi

  [[ "$(realpath -e "${destination}")" = \
    "$(realpath -e "${CUDA_LIB}/${source_name}")" ]] || {
    printf 'resolved target mismatch: %s\n' "${destination}" >&2
    return 1
  }
  printf '%s -> %s\n' "${destination}" "$(readlink "${destination}")"
}

ensure_relative_link libcudart.so libcudart.so.13
ensure_relative_link libnvrtc.so libnvrtc.so.13
