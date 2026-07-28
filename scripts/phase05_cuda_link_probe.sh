#!/usr/bin/env bash
# Seconds-long reproduction for the FlashInfer CUDA link-layout failure.
set -euo pipefail

readonly MODE="${1:?mode must be current or overlay}"
readonly CUDA_ROOT="/home/tiger/venvs/deepspec-dspark/lib/python3.11/site-packages/nvidia/cu13"

probe_root=""
cleanup() {
  if [[ -n "${probe_root}" && "${probe_root}" == /tmp/deepspec-phase05-link-overlay.* ]]; then
    rm -rf -- "${probe_root}"
  fi
}
trap cleanup EXIT

case "${MODE}" in
  current)
    link_dir="${CUDA_ROOT}/lib64"
    ;;
  overlay)
    probe_root="$(mktemp -d /tmp/deepspec-phase05-link-overlay.XXXXXX)"
    mkdir -p "${probe_root}/lib64"
    ln -s "${CUDA_ROOT}/lib/libcudart.so.13" \
      "${probe_root}/lib64/libcudart.so"
    ln -s "${CUDA_ROOT}/lib/libnvrtc.so.13" \
      "${probe_root}/lib64/libnvrtc.so"
    link_dir="${probe_root}/lib64"
    ;;
  *)
    printf 'unsupported mode: %s\n' "${MODE}" >&2
    exit 2
    ;;
esac

set +e
output="$(
  /usr/bin/cc -shared -Wl,--no-as-needed \
    -L"${link_dir}" -lcudart -lnvrtc -o /dev/null 2>&1
)"
rc=$?
set -e

printf 'mode=%s\nlink_dir=%s\nreturncode=%s\n' \
  "${MODE}" "${link_dir}" "${rc}"
printf '%s\n' "${output}"

if [[ "${MODE}" = current ]]; then
  if [[ "${rc}" -ne 0 ]]; then
    grep -q 'cannot find -lcudart' <<<"${output}"
    grep -q 'cannot find -lnvrtc' <<<"${output}"
  fi
  exit "${rc}"
fi
if [[ "${rc}" -ne 0 ]]; then
  printf 'overlay probe failed with return code %s\n' "${rc}" >&2
  exit "${rc}"
fi
