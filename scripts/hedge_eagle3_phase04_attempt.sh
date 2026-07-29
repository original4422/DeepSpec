#!/usr/bin/env bash
# Exact-eight lifecycle for one frozen-source Phase 04 calibration arm.

set -euo pipefail

readonly MODE="${1:?usage: hedge_eagle3_phase04_attempt.sh native|B0|B+ ATTEMPT_ID [GATE]}"
readonly ATTEMPT_ID="${2:?usage: hedge_eagle3_phase04_attempt.sh native|B0|B+ ATTEMPT_ID [GATE]}"
readonly GATE="${3:-}"
readonly WORKER_ID="4099544"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-v4-eagle3/${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/${ATTEMPT_ID}"
readonly MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-20260728T205627Z/keepalive-active.json"
readonly RUNTIME="${REPO_ROOT}/scripts/hedge_eagle3_phase02_runtime.py"
readonly RESOLVER="${REPO_ROOT}/scripts/hedge_eagle3_phase04_resolve.py"
readonly RUNNER="${REPO_ROOT}/scripts/hedge_eagle3_phase04_run.py"
readonly FREEZER="${REPO_ROOT}/scripts/hedge_eagle3_phase04_freeze.py"
readonly FREEZE_MANIFEST="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T043500Z-phase-04-tooling-freeze-02/tooling_freeze.json"
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
resolver_gate_args=()

copy_artifacts() {
  local file target staging source_hash target_hash
  mkdir -p "${HDFS_RUN}"
  for file in "${SCRATCH}"/*; do
    [ -f "${file}" ] || continue
    target="${HDFS_RUN}/$(basename "${file}")"
    staging="${target}.phase04-staging-$$"
    if [ -e "${staging}" ]; then
      echo "refusing unexpected Phase 04 HDFS staging path: ${staging}" >&2
      return 1
    fi
    cp -p -- "${file}" "${staging}"
    source_hash="$(sha256sum -- "${file}" | cut -d ' ' -f 1)"
    target_hash="$(sha256sum -- "${staging}" | cut -d ' ' -f 1)"
    if [ "${source_hash}" != "${target_hash}" ]; then
      echo "Phase 04 HDFS staging hash differs: ${file}" >&2
      return 1
    fi
    mv -f -- "${staging}" "${target}"
    target_hash="$(sha256sum -- "${target}" | cut -d ' ' -f 1)"
    if [ "${source_hash}" != "${target_hash}" ]; then
      echo "Phase 04 published artifact hash differs: ${file}" >&2
      return 1
    fi
  done
}

terminate_if_registered() {
  local identity="$1" output="$2"
  if [ -f "${identity}" ]; then
    "${PYTHON}" "${RUNTIME}" terminate-process \
      --identity "${identity}" \
      --output "${output}" \
      --timeout 60
  fi
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
  copy_artifacts || cleanup_rc=1
  if [ "${original_rc}" -ne 0 ] || [ "${cleanup_rc}" -ne 0 ]; then
    exit 1
  fi
  exit 0
}

on_interrupt() {
  exit 130
}

on_terminate() {
  exit 143
}

case "${MODE}" in
  native|B0)
    if [ -n "${GATE}" ]; then
      echo "gate is only valid for B+" >&2
      exit 2
    fi
    ;;
  B+)
    if [ -z "${GATE}" ]; then
      echo "B+ requires a calibrated gate" >&2
      exit 2
    fi
    resolver_gate_args=(--gate "${GATE}")
    ;;
  *)
    echo "mode must be native, B0, or B+" >&2
    exit 2
    ;;
esac
case "${ATTEMPT_ID}" in
  20??????T??????Z-phase-04-*)
    ;;
  *)
    echo "invalid Phase 04 attempt ID: ${ATTEMPT_ID}" >&2
    exit 2
    ;;
esac
if [ -e "${SCRATCH}" ] || [ -e "${HDFS_RUN}" ]; then
  echo "refusing to reuse Phase 04 attempt: ${ATTEMPT_ID}" >&2
  exit 2
fi
test -x "${PYTHON}"
test -f "${MARKER}"
for helper in \
  "${RUNTIME}" "${RESOLVER}" "${RUNNER}" "${FREEZER}" "${SAMPLER}" \
  "${WATCHDOG}" "${WAITER}" "${REVIEWED_PATCH}" "${FREEZE_MANIFEST}"; do
  test -f "${helper}"
done

umask 027
mkdir -p "${SCRATCH}" "${HDFS_RUN}"
exec > >(tee "${SCRATCH}/lifecycle.log") 2>&1
trap cleanup EXIT
trap on_interrupt INT
trap on_terminate TERM

printf 'attempt_started_at=%s mode=%s worker=%s hostname=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${MODE}" "${WORKER_ID}" "$(hostname)"
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
  --mode "${MODE}" "${resolver_gate_args[@]}" \
  --attempt-id "${ATTEMPT_ID}" \
  --assert-worker-hostname \
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
    --mode "${MODE}" "${resolver_gate_args[@]}" \
    --attempt-id "${ATTEMPT_ID}" \
    --assert-worker-hostname \
    --print-command-null
)
mapfile -d '' -t launch_environment < <(
  "${PYTHON}" "${RESOLVER}" \
    --mode "${MODE}" "${resolver_gate_args[@]}" \
    --attempt-id "${ATTEMPT_ID}" \
    --assert-worker-hostname \
    --print-environment-null
)
unset SGLANG_DSV4_FP4_DEQUANT
unset SGLANG_EAGLE3_HEDGE_CONFIG_JSON
unset SGLANG_EAGLE3_HEDGE_MODE
for entry in "${launch_environment[@]}"; do
  export "${entry}"
done

setsid "${launch_command[@]}" >"${SCRATCH}/server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" >"${SCRATCH}/server.pid"
for _ in $(seq 1 100); do
  if [ -r "/proc/${server_pid}/cmdline" ]; then
    break
  fi
  sleep 0.1
done
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${server_pid}" --fragment "--port 31001" \
  --output "${SCRATCH}/server_identity.json"
cp -p -- "${SCRATCH}/server_identity.json" "${SCRATCH}/process_identity.json"

setsid "${PYTHON}" "${SAMPLER}" \
  --output "${SCRATCH}/gpu_samples.csv" \
  --server-pid "${server_pid}" &
sampler_pid=$!
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${sampler_pid}" --fragment "hedge_eagle3_phase02_gpu_sampler.py" \
  --output "${SCRATCH}/sampler_identity.json"

owner_start_ticks="$(
  "${PYTHON}" "${RUNTIME}" start-ticks --pid "$$"
)"
server_start_ticks="$(
  "${PYTHON}" "${RUNTIME}" start-ticks --pid "${server_pid}"
)"
setsid "${PYTHON}" "${WATCHDOG}" \
  --owner-pid "$$" --owner-start-ticks "${owner_start_ticks}" \
  --server-pid "${server_pid}" --server-start-ticks "${server_start_ticks}" \
  --fragment "--port 31001" --repo-root "${REPO_ROOT}" \
  --scratch "${SCRATCH}" --hdfs-run "${HDFS_RUN}" \
  >"${SCRATCH}/watchdog.log" 2>&1 &
watchdog_pid=$!
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${watchdog_pid}" --fragment "hedge_eagle3_phase02_watchdog.py" \
  --output "${SCRATCH}/watchdog_identity.json"

"${PYTHON}" "${WAITER}" \
  --base-url http://127.0.0.1:31001 \
  --server-pid "${server_pid}" \
  --timeout 3600 \
  --output "${SCRATCH}/startup.json"
"${PYTHON}" "${RUNTIME}" capture-process \
  --pid "${server_pid}" --fragment "--port 31001" \
  --output "${SCRATCH}/server_ready_identity.json"
"${PYTHON}" "${RUNTIME}" wait-contexts \
  --output "${SCRATCH}/cuda_contexts_ready.json" \
  --timeout 30 --expect eight

"${PYTHON}" "${RUNNER}" \
  --base-url http://127.0.0.1:31001 \
  --model deepseek-v4-flash-eagle3 \
  --mode "${MODE}" \
  --output-dir "${SCRATCH}"
sleep 5
main_complete=1
printf 'attempt_main_complete_at=%s mode=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${MODE}"

exit 0
