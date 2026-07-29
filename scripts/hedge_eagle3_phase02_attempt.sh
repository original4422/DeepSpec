#!/usr/bin/env bash
# Atomic exact-eight-GPU lifecycle for Phase 02 target/native attempts.

set -euo pipefail

readonly MODE="${1:?usage: hedge_eagle3_phase02_attempt.sh target|native ATTEMPT_ID}"
readonly ATTEMPT_ID="${2:?usage: hedge_eagle3_phase02_attempt.sh target|native ATTEMPT_ID}"
readonly WORKER_ID="4099544"
readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-v4-eagle3/${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/${ATTEMPT_ID}"
readonly MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-20260728T205627Z/keepalive-active.json"
readonly RUNTIME="${REPO_ROOT}/scripts/hedge_eagle3_phase02_runtime.py"
readonly RESOLVER="${REPO_ROOT}/scripts/hedge_eagle3_phase02_resolve.py"
readonly SAMPLER="${REPO_ROOT}/scripts/hedge_eagle3_phase02_gpu_sampler.py"
readonly API="${REPO_ROOT}/scripts/hedge_eagle3_phase02_api.py"
readonly WATCHDOG="${REPO_ROOT}/scripts/hedge_eagle3_phase02_watchdog.py"
readonly CONTROLLER="${REPO_ROOT}/scripts/hedge_eagle3_keepalive.sh"
readonly WAITER="${REPO_ROOT}/scripts/phase05_wait_ready.py"

server_pid=""
sampler_pid=""
watchdog_pid=""
keepalive_may_be_paused=0
main_complete=0

copy_artifacts() {
  local file target
  mkdir -p "${HDFS_RUN}"
  for file in "${SCRATCH}"/*; do
    [ -f "${file}" ] || continue
    target="${HDFS_RUN}/$(basename "${file}")"
    if [ -e "${target}" ]; then
      continue
    fi
    cp -p -- "${file}" "${target}"
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
  target|native)
    ;;
  *)
    echo "mode must be target or native" >&2
    exit 2
    ;;
esac
case "${ATTEMPT_ID}" in
  20??????T??????Z-phase-02-*)
    ;;
  *)
    echo "invalid Phase 02 attempt ID: ${ATTEMPT_ID}" >&2
    exit 2
    ;;
esac
if [ -e "${SCRATCH}" ] || [ -e "${HDFS_RUN}" ]; then
  echo "refusing to reuse Phase 02 attempt: ${ATTEMPT_ID}" >&2
  exit 2
fi
test -x "${PYTHON}"
test -f "${MARKER}"
for helper in \
  "${RUNTIME}" "${RESOLVER}" "${SAMPLER}" "${API}" "${WATCHDOG}" \
  "${WAITER}"; do
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
bash "${CONTROLLER}" status "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_before.txt" \
  2>"${SCRATCH}/keepalive_before.stderr.txt"
"${PYTHON}" "${RUNTIME}" snapshot-keepalive \
  --marker "${MARKER}" \
  --output "${SCRATCH}/keepalive_before_identity.json"
"${PYTHON}" "${RESOLVER}" \
  --mode "${MODE}" --attempt-id "${ATTEMPT_ID}" \
  --assert-worker-hostname \
  --output "${SCRATCH}/resolved_config.json"
git -C /home/tiger/src/sglang-hedge-v4-eagle3 diff --binary \
  fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1 -- \
  >"${SCRATCH}/sglang.patch"

keepalive_may_be_paused=1
bash "${CONTROLLER}" pause "${WORKER_ID}" \
  >"${SCRATCH}/keepalive_pause.stdout.txt" \
  2>"${SCRATCH}/keepalive_pause.stderr.txt"
"${PYTHON}" "${RUNTIME}" wait-contexts \
  --output "${SCRATCH}/cuda_contexts_after_pause.json" \
  --timeout 60 --expect empty

mapfile -d '' -t launch_command < <(
  "${PYTHON}" "${RESOLVER}" \
    --mode "${MODE}" --attempt-id "${ATTEMPT_ID}" \
    --assert-worker-hostname \
    --print-command-null
)
mapfile -d '' -t launch_environment < <(
  "${PYTHON}" "${RESOLVER}" \
    --mode "${MODE}" --attempt-id "${ATTEMPT_ID}" \
    --assert-worker-hostname \
    --print-environment-null
)
for entry in "${launch_environment[@]}"; do
  export "${entry}"
done
unset SGLANG_DSV4_FP4_DEQUANT

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

served_model="deepseek-v4-flash-target-diagnostic"
if [ "${MODE}" = "native" ]; then
  served_model="deepseek-v4-flash-eagle3-native"
fi
"${PYTHON}" "${API}" \
  --base-url http://127.0.0.1:31001 \
  --model "${served_model}" \
  --mode "${MODE}" \
  --output "${SCRATCH}/api_smoke.json"
sleep 5
main_complete=1
printf 'attempt_main_complete_at=%s mode=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${MODE}"
