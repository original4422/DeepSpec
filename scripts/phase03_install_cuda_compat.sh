#!/usr/bin/env bash
set -euo pipefail

readonly PACKAGE_VERSION="580.173.02-1"
readonly PACKAGE_FILE="cuda-compat-13-0_580.173.02-1_amd64.deb"
readonly EXPECTED_SHA256="2fb9026a83487f19d98c21671af4d93cc78ec35285f6e034c7f4b6baaaadefd9"
readonly BASE_URL="https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64"
readonly CACHE_ROOT="/home/tiger/.cache/deepspec-phase03-20260728T163751Z"
readonly ARCHIVE="${CACHE_ROOT}/${PACKAGE_FILE}"
readonly FINAL_PREFIX="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02"
readonly STAGING_PREFIX="/home/tiger/toolchains/.deepspec-cuda-compat-13.0-580.173.02.staging-20260728T163751Z"
readonly EXPECTED_COMPAT_DIR="${FINAL_PREFIX}/usr/local/cuda-13.0/compat"

if [[ -f "${EXPECTED_COMPAT_DIR}/libcuda.so.1" ]]; then
  printf 'package_version=%s\ncompat_dir=%s\n' \
    "${PACKAGE_VERSION}" "${EXPECTED_COMPAT_DIR}"
  sha256sum "${EXPECTED_COMPAT_DIR}/libcuda.so.1"
  exit 0
fi

if [[ -e "${FINAL_PREFIX}" || -e "${STAGING_PREFIX}" ]]; then
  echo "Refusing to overwrite unknown CUDA compatibility prefix or staging" >&2
  exit 1
fi

mkdir -p "${CACHE_ROOT}" "${STAGING_PREFIX}"
curl --fail --location --retry 3 --connect-timeout 30 --max-time 600 \
  "${BASE_URL}/${PACKAGE_FILE}" -o "${ARCHIVE}"
printf '%s  %s\n' "${EXPECTED_SHA256}" "${ARCHIVE}" | sha256sum --check
dpkg-deb --extract "${ARCHIVE}" "${STAGING_PREFIX}"

staging_compat="${STAGING_PREFIX}/usr/local/cuda-13.0/compat"
[[ -f "${staging_compat}/libcuda.so.1" ]] || {
  echo "Extracted package does not contain expected CUDA 13.0 compat library" >&2
  exit 1
}
mv "${STAGING_PREFIX}" "${FINAL_PREFIX}"

printf 'package_version=%s\ncompat_dir=%s\n' \
  "${PACKAGE_VERSION}" "${EXPECTED_COMPAT_DIR}"
sha256sum "${EXPECTED_COMPAT_DIR}/libcuda.so.1"
