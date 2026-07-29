#!/usr/bin/env bash
# One-shot exact-eight lifecycle for the final native Eagle3 baseline.

set -euo pipefail

readonly ATTEMPT_ID="${1:?usage: hedge_eagle3_phase05_attempt.sh ATTEMPT_ID}"
readonly WORKER_ID="4099544"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-v4-eagle3/${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/${ATTEMPT_ID}"
readonly HDFS_STAGING="${HDFS_RUN}.phase05-staging"
readonly ACCEPTED_MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-native-formal.complete.json"
readonly MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-20260728T205627Z/keepalive-active.json"
readonly RUNTIME="${REPO_ROOT}/scripts/hedge_eagle3_phase02_runtime.py"
readonly RESOLVER="${REPO_ROOT}/scripts/hedge_eagle3_phase05_resolve.py"
readonly RUNNER="${REPO_ROOT}/scripts/hedge_eagle3_phase05_run.py"
readonly FREEZER="${REPO_ROOT}/scripts/hedge_eagle3_phase05_freeze.py"
readonly FREEZE_MANIFEST="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T060800Z-phase-05-tooling-freeze-04/tooling_freeze.json"
readonly SAMPLER="${REPO_ROOT}/scripts/hedge_eagle3_phase02_gpu_sampler.py"
readonly WATCHDOG="${REPO_ROOT}/scripts/hedge_eagle3_phase02_watchdog.py"
readonly CONTROLLER="${REPO_ROOT}/scripts/hedge_eagle3_keepalive.sh"
readonly WAITER="${REPO_ROOT}/scripts/phase05_wait_ready.py"
readonly REVIEWED_PATCH="${REPO_ROOT}/patches/hedge_eagle3_phase04/sglang-final-candidate.patch"

server_pid=""
sampler_pid=""
watchdog_pid=""
keepalive_may_be_paused=0
main_complete=0

terminate_if_registered() {
  local identity="$1" output="$2"
  if [ -f "${identity}" ]; then
    "${PYTHON}" "${RUNTIME}" terminate-process \
      --identity "${identity}" --output "${output}" --timeout 60
  fi
}

publish_artifacts() {
  local file target source_hash target_hash
  if [ -e "${HDFS_RUN}" ] || [ -e "${HDFS_STAGING}" ]; then
    echo "refusing Phase 05 HDFS path reuse" >&2
    return 1
  fi
  mkdir -p "${HDFS_STAGING}"
  for file in "${SCRATCH}"/*; do
    [ -f "${file}" ] || continue
    target="${HDFS_STAGING}/$(basename "${file}")"
    cp -p -- "${file}" "${target}"
    source_hash="$(sha256sum -- "${file}" | cut -d ' ' -f 1)"
    target_hash="$(sha256sum -- "${target}" | cut -d ' ' -f 1)"
    if [ "${source_hash}" != "${target_hash}" ]; then
      echo "Phase 05 HDFS staging hash differs: ${file}" >&2
      return 1
    fi
  done
  mv -- "${HDFS_STAGING}" "${HDFS_RUN}"
}

cleanup() {
  local original_rc=$?
  local cleanup_rc=0
  trap - EXIT INT TERM
  set +e
  if [ "${main_complete}" -ne 1 ]; then
    original_rc=1
  fi
  terminate_if_registered \
    "${SCRATCH}/watchdog_identity.json" \
    "${SCRATCH}/watchdog_shutdown.json" || cleanup_rc=1
  terminate_if_registered \
    "${SCRATCH}/sampler_identity.json" \
    "${SCRATCH}/sampler_shutdown.json" || cleanup_rc=1
  terminate_if_registered \
    "${SCRATCH}/server_identity.json" \
    "${SCRATCH}/server_shutdown.json" || cleanup_rc=1
  "${PYTHON}" "${RUNTIME}" wait-contexts \
    --output "${SCRATCH}/cuda_contexts_after.json" \
    --timeout 90 --expect empty || cleanup_rc=1
  if [ -f "${SCRATCH}/server_shutdown.json" ]; then
    cp -p -- "${SCRATCH}/server_shutdown.json" "${SCRATCH}/shutdown.json"
  fi
  if [ "${keepalive_may_be_paused}" -eq 1 ]; then
    if [ "${cleanup_rc}" -eq 0 ]; then
      bash "${CONTROLLER}" resume "${WORKER_ID}" \
        >"${SCRATCH}/keepalive_resume.stdout.txt" \
        2>"${SCRATCH}/keepalive_resume.stderr.txt" || cleanup_rc=1
      bash "${CONTROLLER}" status "${WORKER_ID}" \
        >"${SCRATCH}/keepalive_after.txt" \
        2>"${SCRATCH}/keepalive_after.stderr.txt" || cleanup_rc=1
      if [ "${cleanup_rc}" -eq 0 ]; then
        "${PYTHON}" "${RUNTIME}" snapshot-keepalive \
          --marker "${MARKER}" \
          --output "${SCRATCH}/keepalive_after_identity.json" || cleanup_rc=1
      fi
    else
      printf '%s\n' \
        'keepalive not resumed: model context cleanup was not proven' \
        >"${SCRATCH}/keepalive_after.txt"
    fi
  fi
  "${PYTHON}" "${RUNTIME}" manifest \
    --directory "${SCRATCH}" \
    --output "${SCRATCH}/artifact_manifest.json" || cleanup_rc=1
  publish_artifacts || cleanup_rc=1
  if [ "${original_rc}" -ne 0 ] || [ "${cleanup_rc}" -ne 0 ]; then
    exit 1
  fi
  exit 0
}

case "${ATTEMPT_ID}" in
  20??????T??????Z-phase-05-native-formal-*) ;;
  *)
    echo "invalid Phase 05 attempt ID: ${ATTEMPT_ID}" >&2
    exit 2
    ;;
esac
if [ -e "${SCRATCH}" ] || [ -e "${HDFS_RUN}" ] || \
   [ -e "${HDFS_STAGING}" ] || [ -e "${ACCEPTED_MARKER}" ]; then
  echo "refusing reused attempt or repeated native formal result" >&2
  exit 2
fi
for helper in \
  "${PYTHON}" "${MARKER}" "${RUNTIME}" "${RESOLVER}" "${RUNNER}" \
  "${FREEZER}" "${FREEZE_MANIFEST}" "${SAMPLER}" "${WATCHDOG}" \
  "${CONTROLLER}" "${WAITER}" "${REVIEWED_PATCH}"; do
  test -e "${helper}"
done

umask 027
mkdir -p "${SCRATCH}"
exec >>"${SCRATCH}/lifecycle.log" 2>&1
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${PYTHON}" "${FREEZER}" verify \
  --manifest "${FREEZE_MANIFEST}" \
  --output "${SCRATCH}/tooling_freeze_verification.json"
bash "${CONTROLLER}" status "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_before.txt" \
  2>"${SCRATCH}/keepalive_before.stderr.txt"
"${PYTHON}" "${RUNTIME}" snapshot-keepalive \
  --marker "${MARKER}" \
  --output "${SCRATCH}/keepalive_before_identity.json"
"${PYTHON}" "${RESOLVER}" \
  --attempt-id "${ATTEMPT_ID}" --assert-worker-hostname \
  --assert-no-complete-result \
  --output "${SCRATCH}/resolved_config.json" \
  --evidence-dir "${SCRATCH}"
cp -p -- "${REVIEWED_PATCH}" "${SCRATCH}/sglang.patch"

keepalive_may_be_paused=1
bash "${CONTROLLER}" pause "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_pause.stdout.txt" \
  2>"${SCRATCH}/keepalive_pause.stderr.txt"
"${PYTHON}" "${RUNTIME}" wait-contexts \
  --output "${SCRATCH}/cuda_contexts_after_pause.json" \
  --timeout 60 --expect empty

mapfile -d '' -t launch_command < <(
  "${PYTHON}" "${RESOLVER}" \
    --attempt-id "${ATTEMPT_ID}" --assert-worker-hostname \
    --assert-no-complete-result --print-command-null
)
mapfile -d '' -t launch_environment < <(
  "${PYTHON}" "${RESOLVER}" \
    --attempt-id "${ATTEMPT_ID}" --assert-worker-hostname \
    --assert-no-complete-result --print-environment-null
)
unset SGLANG_DSV4_FP4_DEQUANT
unset SGLANG_EAGLE3_HEDGE_CONFIG_JSON
unset SGLANG_EAGLE3_HEDGE_MODE
for entry in "${launch_environment[@]}"; do export "${entry}"; done

setsid "${launch_command[@]}" >"${SCRATCH}/server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" >"${SCRATCH}/server.pid"
for _ in $(seq 1 100); do
  [ -r "/proc/${server_pid}/cmdline" ] && break
  sleep 0.1
done
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${server_pid}" --fragment "--port 31001" \
  --output "${SCRATCH}/server_identity.json"
cp -p -- "${SCRATCH}/server_identity.json" "${SCRATCH}/process_identity.json"

setsid "${PYTHON}" "${SAMPLER}" \
  --output "${SCRATCH}/gpu_samples.csv" --server-pid "${server_pid}" &
sampler_pid=$!
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${sampler_pid}" --fragment "hedge_eagle3_phase02_gpu_sampler.py" \
  --output "${SCRATCH}/sampler_identity.json"

owner_start_ticks="$("${PYTHON}" "${RUNTIME}" start-ticks --pid "$$")"
server_start_ticks="$("${PYTHON}" "${RUNTIME}" start-ticks --pid "${server_pid}")"
setsid "${PYTHON}" "${WATCHDOG}" \
  --owner-pid "$$" --owner-start-ticks "${owner_start_ticks}" \
  --server-pid "${server_pid}" --server-start-ticks "${server_start_ticks}" \
  --fragment "--port 31001" --repo-root "${REPO_ROOT}" \
  --scratch "${SCRATCH}" --hdfs-run "${HDFS_STAGING}" \
  >"${SCRATCH}/watchdog.log" 2>&1 &
watchdog_pid=$!
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${watchdog_pid}" --fragment "hedge_eagle3_phase02_watchdog.py" \
  --output "${SCRATCH}/watchdog_identity.json"

"${PYTHON}" "${WAITER}" \
  --base-url http://127.0.0.1:31001 \
  --server-pid "${server_pid}" --timeout 3600 \
  --output "${SCRATCH}/startup.json"
"${PYTHON}" "${RUNTIME}" wait-contexts \
  --output "${SCRATCH}/cuda_contexts_ready.json" \
  --timeout 30 --expect eight
"${PYTHON}" "${RUNNER}" \
  --base-url http://127.0.0.1:31001 \
  --model deepseek-v4-flash-eagle3 \
  --output-dir "${SCRATCH}"
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${server_pid}" --fragment "--port 31001" \
  --output "${SCRATCH}/server_after_formal_identity.json"
main_complete=1
exit 0
