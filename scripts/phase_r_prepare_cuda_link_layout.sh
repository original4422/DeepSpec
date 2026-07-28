#!/usr/bin/env bash
# Capture the known RED probe, apply the minimal link-layout fix, then prove GREEN.
set -euo pipefail

readonly EVIDENCE_DIR="${1:?absolute evidence directory is required}"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly PROBE="${REPO_ROOT}/scripts/phase05_cuda_link_probe.sh"
readonly FIX="${REPO_ROOT}/scripts/phase_r_fix_cuda_link_layout.sh"

[[ "${EVIDENCE_DIR}" == /tmp/deepspec-phase-r-* ]] || {
  printf 'evidence directory must be under /tmp/deepspec-phase-r-*: %s\n' \
    "${EVIDENCE_DIR}" >&2
  exit 1
}
[[ ! -e "${EVIDENCE_DIR}" ]] || {
  printf 'evidence directory already exists: %s\n' "${EVIDENCE_DIR}" >&2
  exit 1
}
mkdir -p "${EVIDENCE_DIR}"

set +e
bash "${PROBE}" current >"${EVIDENCE_DIR}/cuda_link_probe_red.txt" 2>&1
red_rc=$?
set -e
[[ "${red_rc}" -ne 0 ]] || {
  printf 'expected current probe to be RED before the fix\n' >&2
  exit 1
}
grep -q 'cannot find -lcudart' \
  "${EVIDENCE_DIR}/cuda_link_probe_red.txt"
grep -q 'cannot find -lnvrtc' \
  "${EVIDENCE_DIR}/cuda_link_probe_red.txt"

bash "${FIX}" >"${EVIDENCE_DIR}/cuda_link_layout_fix.txt" 2>&1
bash "${PROBE}" current \
  >"${EVIDENCE_DIR}/cuda_link_probe_green.txt" 2>&1
grep -q '^returncode=0$' \
  "${EVIDENCE_DIR}/cuda_link_probe_green.txt"

printf 'phase_r_cuda_link_layout=PASS\n'
printf 'evidence_dir=%s\n' "${EVIDENCE_DIR}"
