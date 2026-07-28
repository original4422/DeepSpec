#!/usr/bin/env bash
# Append a fresh keepalive gate and seal Phase R link-layout evidence into the attempt.
set -euo pipefail

readonly WORKER_ID="${1:?worker ID is required}"
readonly ATTEMPT_ID="${2:?attempt ID is required}"
readonly LINK_EVIDENCE="${3:?link-layout evidence directory is required}"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
readonly SCRATCH="/tmp/deepspec-${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}"

[[ "${WORKER_ID}" =~ ^[0-9]+$ ]]
[[ "${ATTEMPT_ID}" =~ ^[0-9]{8}T[0-9]{6}Z-phase05- ]]
[[ "${LINK_EVIDENCE}" == /tmp/deepspec-phase-r-* ]]
[[ -d "${SCRATCH}" && -d "${HDFS_RUN}" ]]

for filename in \
  cuda_link_probe_red.txt \
  cuda_link_layout_fix.txt \
  cuda_link_probe_green.txt; do
  [[ -f "${LINK_EVIDENCE}/${filename}" ]]
  cp -f "${LINK_EVIDENCE}/${filename}" "${SCRATCH}/${filename}"
done

{
  printf '\nphase_r_post_lifecycle_status_utc=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  bash "${REPO_ROOT}/scripts/keepalive.sh" status "${WORKER_ID}"
} >>"${SCRATCH}/keepalive_after.txt" 2>&1

for filename in \
  cuda_link_probe_red.txt \
  cuda_link_layout_fix.txt \
  cuda_link_probe_green.txt \
  keepalive_after.txt; do
  cp -f "${SCRATCH}/${filename}" "${HDFS_RUN}/${filename}"
  cmp "${SCRATCH}/${filename}" "${HDFS_RUN}/${filename}"
done

printf 'phase_r_finalize=PASS\n'
printf 'attempt_id=%s\n' "${ATTEMPT_ID}"
printf 'artifact_dir=%s\n' "${HDFS_RUN}"
