#!/usr/bin/env bash
# Atomic native-only lifecycle for the P06 DSpark formal-500 arm.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly PYTHON="/home/tiger/venvs/hedge-v4-dspark/bin/python"
readonly PREPARE="$REPO_ROOT/scripts/hedge_dspark_p06_prepare.py"
readonly PROCESS_GUARD="$REPO_ROOT/scripts/hedge_dspark_p04_process.py"
readonly SAMPLER="$REPO_ROOT/scripts/hedge_dspark_p04_gpu_sampler.py"
readonly CLIENT="$REPO_ROOT/scripts/hedge_dspark_p06_client.py"
readonly VALIDATOR="$REPO_ROOT/scripts/hedge_dspark_p06_validate.py"
readonly KEEPALIVE="$REPO_ROOT/scripts/hedge_dspark_keepalive.sh"
readonly CALIBRATION="$REPO_ROOT/artifacts/hedge-dspark/p01-protocol/gsm8k_calibration_32.jsonl"
readonly FORMAL="$REPO_ROOT/artifacts/hedge-dspark/p01-protocol/gsm8k_formal_500.jsonl"
readonly EXPECTED_WORKER="4106666"
readonly FIXED_PORT="31066"

if [[ "${1:-}" == "--print-contract" ]]; then
  printf '%s\n' \
    '{"arms":["native"],"worker_id":"4106666","expected_gpus":8,'\
'"tp_size":8,"proposal_width":5,"port":31066,"warmup_count":10,'\
'"formal_count":500,"hedge_enabled":false,"resume_allowed":false,'\
'"lifecycle":["preflight","pause_keepalive","prove_contexts_none",'\
'"start_registered_server_and_sampler",'\
'"run_atomic_warmup_10_and_formal_500","validate_live_evidence",'\
'"terminate_registered_server","prove_contexts_none",'\
'"terminate_registered_sampler","resume_and_validate_keepalive",'\
'"archive_without_overwrite"]}'
  exit 0
fi

if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 <worker-id> <unique-p06-native-formal-attempt-id>" >&2
  exit 2
fi

readonly WORKER_ID="$1"
readonly ATTEMPT_ID="$2"
readonly EXPECTED_ATTEMPT_PATTERN='^[0-9]{8}T[0-9]{6}Z-p06-native-formal(-[a-z0-9][a-z0-9-]{0,63})?$'

if [[ "$WORKER_ID" != "$EXPECTED_WORKER" ]]; then
  echo "refusing worker $WORKER_ID; only $EXPECTED_WORKER is authorized" >&2
  exit 2
fi
if [[ ! "$ATTEMPT_ID" =~ $EXPECTED_ATTEMPT_PATTERN ]]; then
  echo "invalid P06 native formal attempt-id: $ATTEMPT_ID" >&2
  exit 2
fi

readonly SCRATCH="/tmp/deepspec-hedge-dspark-$ATTEMPT_ID"
readonly HDFS_RUN="$RUN_ROOT/$ATTEMPT_ID"
readonly SERVER_IDENTITY="$SCRATCH/server_process.json"
readonly SAMPLER_IDENTITY="$SCRATCH/sampler_process.json"

if [[ -e "$SCRATCH" || -e "$HDFS_RUN" ]]; then
  echo "refusing to overwrite existing attempt: $ATTEMPT_ID" >&2
  exit 1
fi
mkdir -- "$SCRATCH"
mkdir -- "$HDFS_RUN"
exec >>"$SCRATCH/lifecycle.log" 2>&1

server_pid=""
sampler_pid=""
server_started=0
sampler_started=0
keepalive_transition_started=0
attempt_completed=0
cleanup_started=0
signal_name=""

record_stage() {
  local stage="$1"
  local now
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"stage":"%s","at_utc":"%s"}\n' "$stage" "$now" \
    >>"$SCRATCH/lifecycle_events.jsonl"
  printf '%s stage=%s\n' "$now" "$stage"
}

register_started_process() {
  local pid="$1"
  local role="$2"
  local required_arg="$3"
  local output="$4"
  local attempt

  for attempt in $(seq 1 100); do
    if "$PYTHON" "$PROCESS_GUARD" register \
      --pid "$pid" \
      --role "$role" \
      --required-arg "$required_arg" \
      --output "$output" \
      >"$SCRATCH/${role}_registration.txt" 2>&1; then
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  echo "failed to register exact $role process identity for pid=$pid" >&2
  return 1
}

settle_unregistered_process() {
  local pid="$1"
  local role="$2"
  local output="$3"

  "$PYTHON" "$PROCESS_GUARD" settle-unregistered \
    --pid "$pid" \
    --role "$role" \
    --output "$output"
}

cleanup() {
  local original_rc=$?
  local cleanup_rc=0
  local contexts_proven=1
  local keepalive_ready=0
  local final_rc

  if [[ "$cleanup_started" -eq 1 ]]; then
    exit "$original_rc"
  fi
  cleanup_started=1
  trap - EXIT INT TERM HUP
  set +e

  record_stage "terminate_registered_server"
  if [[ "$server_started" -eq 1 ]]; then
    if [[ ! -f "$SERVER_IDENTITY" && -n "$server_pid" ]]; then
      register_started_process \
        "$server_pid" server sglang.launch_server "$SERVER_IDENTITY" \
        || settle_unregistered_process \
          "$server_pid" server "$SCRATCH/server_shutdown.json" \
          >>"$SCRATCH/server_shutdown.txt" 2>&1 \
        || cleanup_rc=1
    fi
    if [[ -f "$SERVER_IDENTITY" ]]; then
      "$PYTHON" "$PROCESS_GUARD" terminate \
        --identity "$SERVER_IDENTITY" \
        --output "$SCRATCH/server_shutdown.json" \
        --timeout 30 \
        >>"$SCRATCH/server_shutdown.txt" 2>&1 \
        || cleanup_rc=1
    elif [[ ! -f "$SCRATCH/server_shutdown.json" ]]; then
      echo "server identity unavailable; refusing unregistered cleanup" >&2
      cleanup_rc=1
    fi
  fi

  record_stage "prove_cuda_contexts_none"
  if [[ "$keepalive_transition_started" -eq 1 || "$server_started" -eq 1 ]]; then
    "$PYTHON" "$PREPARE" wait-no-contexts \
      --worker-id "$WORKER_ID" \
      --output "$SCRATCH/cuda_contexts_after.txt" \
      --timeout 120 \
      || {
        contexts_proven=0
        cleanup_rc=1
      }
  else
    printf '%s contexts=not-queried-keepalive-never-paused\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      >"$SCRATCH/cuda_contexts_after.txt"
  fi

  record_stage "terminate_registered_sampler"
  if [[ "$sampler_started" -eq 1 ]]; then
    if [[ ! -f "$SAMPLER_IDENTITY" && -n "$sampler_pid" ]]; then
      register_started_process \
        "$sampler_pid" sampler "$SAMPLER" "$SAMPLER_IDENTITY" \
        || settle_unregistered_process \
          "$sampler_pid" sampler "$SCRATCH/sampler_shutdown.json" \
          >>"$SCRATCH/sampler_shutdown.txt" 2>&1 \
        || cleanup_rc=1
    fi
    if [[ -f "$SAMPLER_IDENTITY" ]]; then
      "$PYTHON" "$PROCESS_GUARD" terminate \
        --identity "$SAMPLER_IDENTITY" \
        --output "$SCRATCH/sampler_shutdown.json" \
        --timeout 10 \
        >>"$SCRATCH/sampler_shutdown.txt" 2>&1 \
        || cleanup_rc=1
    elif [[ ! -f "$SCRATCH/sampler_shutdown.json" ]]; then
      echo "sampler identity unavailable; refusing unregistered cleanup" >&2
      cleanup_rc=1
    fi
  fi

  record_stage "resume_keepalive_if_cleanup_proven"
  if [[ "$keepalive_transition_started" -eq 1 ]]; then
    if [[ "$cleanup_rc" -eq 0 && "$contexts_proven" -eq 1 ]]; then
      bash "$KEEPALIVE" resume "$WORKER_ID" \
        >"$SCRATCH/keepalive_resume.txt" 2>&1 \
        || cleanup_rc=1
    else
      printf '%s\n' \
        "FAIL_CLOSED: keepalive not resumed because cleanup/contexts are unproven" \
        >"$SCRATCH/keepalive_resume.txt"
    fi
  else
    printf '%s\n' "keepalive was never paused" \
      >"$SCRATCH/keepalive_resume.txt"
  fi

  record_stage "validate_keepalive_8x10_mean_ge_40"
  if [[ "$keepalive_transition_started" -eq 0 || \
        ( "$cleanup_rc" -eq 0 && "$contexts_proven" -eq 1 ) ]]; then
    if bash "$KEEPALIVE" status "$WORKER_ID" \
      >"$SCRATCH/keepalive_after.txt" 2>&1; then
      if "$PYTHON" "$PREPARE" parse-keepalive \
        --worker-id "$WORKER_ID" \
        --input "$SCRATCH/keepalive_after.txt" \
        --output "$SCRATCH/keepalive_after.json"; then
        keepalive_ready=1
      else
        cleanup_rc=1
      fi
    else
      cleanup_rc=1
    fi
  fi

  "$PYTHON" "$VALIDATOR" record-shutdown \
    --scratch "$SCRATCH" \
    --attempt-id "$ATTEMPT_ID" \
    --original-returncode "$original_rc" \
    --cleanup-returncode "$cleanup_rc" \
    --contexts-proven "$contexts_proven" \
    --keepalive-ready "$keepalive_ready" \
    --signal-name "$signal_name" \
    || cleanup_rc=1

  record_stage "validate_required_artifacts"
  "$PYTHON" "$VALIDATOR" final \
    --scratch "$SCRATCH" \
    --attempt-id "$ATTEMPT_ID" \
    || cleanup_rc=1

  record_stage "archive_without_overwrite"
  "$PYTHON" "$VALIDATOR" archive \
    --scratch "$SCRATCH" \
    --hdfs-run "$HDFS_RUN" \
    || cleanup_rc=1

  final_rc="$original_rc"
  if [[ "$attempt_completed" -ne 1 || "$cleanup_rc" -ne 0 ]]; then
    final_rc=1
  fi
  exit "$final_rc"
}

on_signal() {
  signal_name="$1"
  case "$signal_name" in
    INT) exit 130 ;;
    TERM) exit 143 ;;
    HUP) exit 129 ;;
    *) exit 1 ;;
  esac
}

trap cleanup EXIT
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM
trap 'on_signal HUP' HUP

record_stage "preflight_fixed_port"
"$PYTHON" "$PREPARE" check-port --worker-id "$WORKER_ID"

record_stage "preflight_identities"
mkdir -- \
  "$SCRATCH/flashinfer" \
  "$SCRATCH/sglang-cache" \
  "$SCRATCH/torch-extensions" \
  "$SCRATCH/triton-cache"
"$PYTHON" "$PREPARE" prepare \
  --worker-id "$WORKER_ID" \
  --attempt-id "$ATTEMPT_ID" \
  --scratch "$SCRATCH"

mapfile -d '' -t server_command < <(
  "$PYTHON" "$PREPARE" emit-command \
    --resolved "$SCRATCH/resolved_config.json"
)
mapfile -d '' -t server_environment < <(
  "$PYTHON" "$PREPARE" emit-environment \
    --resolved "$SCRATCH/resolved_config.json"
)
if [[ "${#server_command[@]}" -lt 3 || "${#server_environment[@]}" -lt 1 ]]; then
  echo "resolved server command/environment is empty" >&2
  exit 1
fi

record_stage "keepalive_status_before"
bash "$KEEPALIVE" status "$WORKER_ID" \
  >"$SCRATCH/keepalive_before.txt" 2>&1
"$PYTHON" "$PREPARE" parse-keepalive \
  --worker-id "$WORKER_ID" \
  --input "$SCRATCH/keepalive_before.txt" \
  --output "$SCRATCH/keepalive_before.json"

record_stage "keepalive_pause"
keepalive_transition_started=1
bash "$KEEPALIVE" pause "$WORKER_ID" \
  >"$SCRATCH/keepalive_pause.txt" 2>&1

record_stage "contexts_after_pause"
"$PYTHON" "$PREPARE" wait-no-contexts \
  --worker-id "$WORKER_ID" \
  --output "$SCRATCH/cuda_contexts_after_pause.txt" \
  --timeout 120

record_stage "server_start"
unset \
  HEDGE_CONFIG \
  HEDGE_ENABLED \
  SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE \
  SGLANG_DSPARK_HEDGE_CONFIG_JSON \
  SGLANG_DSPARK_HEDGE_CONFIG_PATH \
  SGLANG_DSPARK_HEDGE_MODE \
  SGLANG_DSPARK_HEDGE_TRACE_CAPACITY \
  SGLANG_DSV4_FP4_DEQUANT
(
  export "${server_environment[@]}"
  exec setsid "${server_command[@]}"
) >"$SCRATCH/server.log" 2>&1 &
server_pid=$!
server_started=1

record_stage "server_register"
register_started_process \
  "$server_pid" server sglang.launch_server "$SERVER_IDENTITY"
server_start_ticks="$(
  "$PYTHON" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["start_ticks"])' \
    "$SERVER_IDENTITY"
)"

owner_start_ticks="$(
  "$PYTHON" "$PROCESS_GUARD" start-ticks --pid "$$"
)"
record_stage "sampler_start"
setsid "$PYTHON" "$SAMPLER" \
  --output "$SCRATCH/gpu_samples.csv" \
  --status-output "$SCRATCH/gpu_sampler_status.json" \
  --owner-pid "$$" \
  --owner-start-ticks "$owner_start_ticks" \
  --expected-gpus 8 \
  --interval 1 \
  >"$SCRATCH/gpu_sampler.log" 2>&1 &
sampler_pid=$!
sampler_started=1

record_stage "sampler_register"
register_started_process \
  "$sampler_pid" sampler "$SAMPLER" "$SAMPLER_IDENTITY"
for _ in $(seq 1 100); do
  if [[ -f "$SCRATCH/gpu_samples.csv" ]] && \
    [[ "$(wc -l <"$SCRATCH/gpu_samples.csv")" -ge 9 ]]; then
    break
  fi
  "$PYTHON" "$PROCESS_GUARD" check --identity "$SAMPLER_IDENTITY" >/dev/null
  sleep 0.1
done
if [[ ! -f "$SCRATCH/gpu_samples.csv" ]] || \
  [[ "$(wc -l <"$SCRATCH/gpu_samples.csv")" -lt 9 ]]; then
  echo "GPU sampler did not produce an exact first sample" >&2
  exit 1
fi

record_stage "wait_ready"
"$PYTHON" "$CLIENT" wait-ready \
  --base-url "http://127.0.0.1:$FIXED_PORT" \
  --server-pid "$server_pid" \
  --server-start-ticks "$server_start_ticks" \
  --timeout 3600 \
  --output "$SCRATCH/startup.json"
"$PYTHON" "$PROCESS_GUARD" check --identity "$SERVER_IDENTITY" >/dev/null
"$PYTHON" "$PROCESS_GUARD" check --identity "$SAMPLER_IDENTITY" >/dev/null

record_stage "client_warmup_10_and_formal_500"
"$PYTHON" "$CLIENT" run \
  --base-url "http://127.0.0.1:$FIXED_PORT" \
  --calibration "$CALIBRATION" \
  --formal "$FORMAL" \
  --artifact-dir "$SCRATCH"

record_stage "live_validate"
"$PYTHON" "$PROCESS_GUARD" check --identity "$SERVER_IDENTITY" >/dev/null
"$PYTHON" "$PROCESS_GUARD" check --identity "$SAMPLER_IDENTITY" >/dev/null
sleep 2
"$PYTHON" "$VALIDATOR" live \
  --scratch "$SCRATCH" \
  --attempt-id "$ATTEMPT_ID"
"$PYTHON" "$PROCESS_GUARD" check --identity "$SERVER_IDENTITY" >/dev/null
"$PYTHON" "$PROCESS_GUARD" check --identity "$SAMPLER_IDENTITY" >/dev/null

attempt_completed=1
