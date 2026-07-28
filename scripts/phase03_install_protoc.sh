#!/usr/bin/env bash
set -euo pipefail

readonly VERSION="35.0"
readonly EXPECTED_SHA256="a45cda0989c17dd950db55f6fbe1e5814c50fda08e87aa422980ac1f89dddbbc"
readonly CACHE_ROOT="/home/tiger/.cache/deepspec-phase03-20260728T163751Z"
readonly ARCHIVE="${CACHE_ROOT}/protoc-${VERSION}-linux-x86_64.zip"
readonly FINAL_PREFIX="/home/tiger/toolchains/deepspec-protoc-${VERSION}"
readonly STAGING_PREFIX="/home/tiger/toolchains/.deepspec-protoc-${VERSION}.staging-20260728T163751Z"
readonly URL="https://github.com/protocolbuffers/protobuf/releases/download/v${VERSION}/protoc-${VERSION}-linux-x86_64.zip"

if [[ -x "${FINAL_PREFIX}/bin/protoc" ]]; then
  actual_version="$("${FINAL_PREFIX}/bin/protoc" --version)"
  [[ "${actual_version}" == "libprotoc ${VERSION}" ]] || {
    echo "Existing Phase 03 protoc has unexpected version: ${actual_version}" >&2
    exit 1
  }
  printf '%s\n' "${actual_version}"
  sha256sum "${FINAL_PREFIX}/bin/protoc"
  exit 0
fi

if [[ -e "${FINAL_PREFIX}" || -e "${STAGING_PREFIX}" ]]; then
  echo "Refusing to overwrite unknown protoc prefix or staging directory" >&2
  exit 1
fi

mkdir -p "${CACHE_ROOT}" "${STAGING_PREFIX}"
curl --fail --location --retry 3 --connect-timeout 30 --max-time 300 \
  "${URL}" -o "${ARCHIVE}"
printf '%s  %s\n' "${EXPECTED_SHA256}" "${ARCHIVE}" | sha256sum --check
unzip -q "${ARCHIVE}" -d "${STAGING_PREFIX}"

actual_version="$("${STAGING_PREFIX}/bin/protoc" --version)"
[[ "${actual_version}" == "libprotoc ${VERSION}" ]] || {
  echo "Downloaded protoc has unexpected version: ${actual_version}" >&2
  exit 1
}
mv "${STAGING_PREFIX}" "${FINAL_PREFIX}"

"${FINAL_PREFIX}/bin/protoc" --version
sha256sum "${FINAL_PREFIX}/bin/protoc"
