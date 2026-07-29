#!/usr/bin/env bash
# Phase D5 strict-native calibration and B=0 lifecycle for the assigned TP=8 worker.
set -Eeuo pipefail

if [[ "$#" -lt 5 ]]; then
  echo "usage: $0 ACTION ATTEMPT_ID {native|b0} NATIVE_ATTEMPT_ID HARD_STOP_UTC" >&2
  exit 2
fi

readonly ACTION="${1:?action required}"
readonly ATTEMPT_ID="${2:?attempt id required}"
readonly ARM="${3:?arm required: native or b0}"
readonly NATIVE_ATTEMPT_ID="${4:-none}"
readonly HARD_STOP_UTC="${5}"
readonly WORKER_ID=4099543
readonly EXPECTED_HOST="g340-cd51-4b00-4d69-9088-7ae6-6253"
readonly REPO="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly SOURCE="/home/tiger/src/deepspec-sglang-hedge-dflash"
readonly SOURCE_SHA="9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
readonly SOURCE_PARENT="1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5"
readonly SOURCE_BASE="fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly KEEPALIVE="${REPO}/scripts/dflash_keepalive.sh"
readonly API_HELPER="${REPO}/scripts/dflash_d5_api.py"
readonly D1C_HARNESS="${REPO}/scripts/dflash_d1c_harness.py"
readonly CALIBRATION_DATA="${REPO}/docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1c/dflash_d1c_gsm8k_calibration_32.jsonl"
readonly CALIBRATION_INDICES="${REPO}/docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1c/dflash_d1c_calibration_indices.json"
readonly DATASET_IDENTITY="${REPO}/docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1c/dflash_d1c_dataset_identity.json"
readonly CUDA_VIEW_HELPER="${REPO}/scripts/dflash_d3_cuda_view.sh"
readonly JIT_PREBUILD_HELPER="${REPO}/scripts/dflash_d3_jit_prebuild.py"
readonly CUDA_VIEW="/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0"
readonly CU13_PAYLOAD="/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13"
readonly CUDA_COMPAT_DIR="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
readonly FLASHINFER_WORKSPACE_BASE="/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
readonly PORT=31457
readonly MODEL_NAME="deepseek-v4-flash"
readonly TARGET_REV="60d8d70770c6776ff598c94bb586a859a38244f1"
readonly DRAFT_REV="e44fc94ceb1e7ed45550d15e782aeadd08050483"
readonly TARGET="/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash/snapshots/huggingface-${TARGET_REV}"
readonly DRAFT="/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft/RedHatAI--DeepSeek-V4-Flash-speculator.dflash/${DRAFT_REV}"
readonly TARGET_MARKER="/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/target-deepseek-v4-flash-${TARGET_REV}.complete.json"
readonly DRAFT_POINTER="/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft_pointer.json"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/runs/${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/${ATTEMPT_ID}"
readonly BASE_URL="http://127.0.0.1:${PORT}"

if [[ ! "${HARD_STOP_UTC}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  echo "hard stop UTC must use exact YYYY-MM-DDTHH:MM:SSZ format" >&2
  exit 2
fi
if ! parsed_hard_stop_utc="$(date -u -d "${HARD_STOP_UTC}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"; then
  echo "hard stop UTC is not parseable: ${HARD_STOP_UTC}" >&2
  exit 2
fi
if [[ "${parsed_hard_stop_utc}" != "${HARD_STOP_UTC}" ]]; then
  echo "hard stop UTC is not canonical UTC: ${HARD_STOP_UTC}" >&2
  exit 2
fi
readonly HARD_STOP_EPOCH="$(date -u -d "${HARD_STOP_UTC}" +%s)"
unset parsed_hard_stop_utc

case "${ARM}" in
  native)
    [[ "${ATTEMPT_ID}" =~ ^dflash-d5-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
    [[ "${NATIVE_ATTEMPT_ID}" = none ]]
    readonly HEDGE_CONFIG=null
    readonly HEDGE_ENABLED_VALUE=0
    readonly CALIBRATION_TRACE_VALUE=1
    ;;
  b0)
    [[ "${ATTEMPT_ID}" =~ ^dflash-d5-b0-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
    [[ "${NATIVE_ATTEMPT_ID}" =~ ^dflash-d5-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
    readonly HEDGE_CONFIG="$("${PYTHON}" "${API_HELPER}" config \
      --native-run "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/${NATIVE_ATTEMPT_ID}")"
    readonly HEDGE_ENABLED_VALUE=1
    readonly CALIBRATION_TRACE_VALUE=0
    ;;
  *)
    echo "arm must be native or b0" >&2
    exit 2
    ;;
esac

# Establish the complete private runtime environment before any Python import.
export CUDA_VIEW
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export CUDA_HOME="${CUDA_VIEW}"
export LD_LIBRARY_PATH="${CUDA_COMPAT_DIR}:${CU13_PAYLOAD}/lib"
export PATH="/home/tiger/venvs/deepspec-hedge-dflash/bin:${CUDA_VIEW}/bin:/usr/bin:/bin"
export FLASHINFER_WORKSPACE_BASE
export FLASHINFER_CUDA_ARCH_LIST=9.0
export PYTHONNOUSERSITE=1 TOKENIZERS_PARALLELISM=false
export SGLANG_RAGGED_VERIFY_MODE=static SGLANG_DSV4_FP4_EXPERTS=1
export SGLANG_CACHE_DIR=/tmp/deepspec-hedge-dflash/cache/sglang
export SGLANG_DG_CACHE_DIR=/tmp/deepspec-hedge-dflash/cache/deep_gemm
export TRITON_CACHE_DIR=/tmp/deepspec-hedge-dflash/cache/triton
export TORCH_EXTENSIONS_DIR=/tmp/deepspec-hedge-dflash/cache/torch_extensions
export HEDGE_ENABLED="${HEDGE_ENABLED_VALUE}"
export SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE="${CALIBRATION_TRACE_VALUE}"
if [[ "${ARM}" = b0 ]]; then
  export SGLANG_DFLASH_HEDGE_CONFIG_JSON="${HEDGE_CONFIG}"
else
  unset SGLANG_DFLASH_HEDGE_CONFIG_JSON
fi
unset SGLANG_DSV4_FP4_DEQUANT
unset SGLANG_DFLASH_HEDGE_CONFIG_PATH

COMMAND=(
  "${PYTHON}" -m sglang.launch_server
  --model-path "${TARGET}"
  --served-model-name "${MODEL_NAME}"
  --host 127.0.0.1
  --port "${PORT}"
  --tp-size 8
  --speculative-algorithm DFLASH
  --speculative-draft-model-path "${DRAFT}"
  --speculative-dflash-block-size 8
  --speculative-num-steps 1
  --speculative-eagle-topk 1
  --moe-runner-backend flashinfer_mxfp4
  --context-length 4096
  --max-running-requests 1
  --mem-fraction-static 0.80
  --disable-cuda-graph
  --disable-overlap-schedule
  --disable-radix-cache
)

utc_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

before_hard_stop() {
  [[ "$(date -u +%s)" -lt "${HARD_STOP_EPOCH}" ]]
}

require_worker_identity() {
  [[ "$(hostname)" = "${EXPECTED_HOST}" ]]
  local rows
  rows="$(nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits)"
  awk -F, '
    {
      gsub(/^[ \t]+|[ \t]+$/, "", $3)
      if (($1 + 0) != NR - 1 || $3 != "NVIDIA H20") bad=1
    }
    END { exit !(NR == 8 && !bad) }
  ' <<<"${rows}"
}

require_source_and_markers() {
  [[ -x "${PYTHON}" ]]
  [[ -f "${API_HELPER}" && -f "${D1C_HARNESS}" ]]
  [[ -f "${CALIBRATION_DATA}" && -f "${CALIBRATION_INDICES}" ]]
  [[ -f "${DATASET_IDENTITY}" ]]
  [[ -x "${CUDA_VIEW_HELPER}" ]]
  [[ -f "${JIT_PREBUILD_HELPER}" ]]
  [[ -d "${CU13_PAYLOAD}" ]]
  [[ -f "${CUDA_COMPAT_DIR}/libcuda.so.580.173.02" ]]
  bash "${CUDA_VIEW_HELPER}" verify >/dev/null
  [[ "$(git -C "${SOURCE}" rev-parse HEAD)" = "${SOURCE_SHA}" ]]
  [[ "$(git -C "${SOURCE}" rev-parse HEAD^)" = "${SOURCE_PARENT}" ]]
  git -C "${SOURCE}" merge-base --is-ancestor "${SOURCE_BASE}" "${SOURCE_SHA}"
  [[ -z "$(git -C "${SOURCE}" status --porcelain)" ]]
  "${PYTHON}" - "${SOURCE}" <<'PY'
import pathlib, sglang, sys
source = pathlib.Path(sys.argv[1]).resolve()
module = pathlib.Path(sglang.__file__).resolve()
assert module.is_relative_to(source / "python"), (module, source)
assert sglang.__version__ == "0.5.16"
PY
  "${PYTHON}" - "${TARGET_MARKER}" "${DRAFT_POINTER}" "${TARGET}" "${DRAFT}" \
    "${TARGET_REV}" "${DRAFT_REV}" "${SCRATCH}/checkpoint_identity.json" <<'PY'
import hashlib
import json
import pathlib
import sys

tm_path = pathlib.Path(sys.argv[1])
dp_path = pathlib.Path(sys.argv[2])
target = pathlib.Path(sys.argv[3])
draft = pathlib.Path(sys.argv[4])
target_rev = sys.argv[5]
draft_rev = sys.argv[6]
output = pathlib.Path(sys.argv[7])

tm = json.loads(tm_path.read_text())
dp = json.loads(dp_path.read_text())
complete_path = pathlib.Path(dp["complete_path"])
dc = json.loads(complete_path.read_text())
assert tm["status"].lower() == "complete"
assert tm["immutable"] is True
assert tm["repo_id"] == "deepseek-ai/DeepSeek-V4-Flash"
assert tm["revision"] == target_rev
assert pathlib.Path(tm["snapshot_path"]) == target
assert tm["weight_shard_count"] == 46
assert tm["file_count"] == 73
assert tm["total_bytes"] == 159630041626
manifest_path = pathlib.Path(tm["manifest_path"])
manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
assert manifest_hash == tm["manifest_sha256"]

target_files = sorted(p for p in target.rglob("*") if p.is_file())
assert len(target_files) == tm["file_count"]
assert sum(p.stat().st_size for p in target_files) == tm["total_bytes"]
assert not any(p.is_symlink() or p.stat().st_nlink != 1 for p in target_files)
target_config = json.loads((target / "config.json").read_text())
assert target_config["architectures"] == ["DeepseekV4ForCausalLM"]
assert target_config["model_type"] == "deepseek_v4"
assert (target / "tokenizer.json").is_file()
assert (target / "tokenizer_config.json").is_file()
assert (target / "generation_config.json").is_file()
index = json.loads((target / "model.safetensors.index.json").read_text())
shards = sorted(set(index["weight_map"].values()))
assert len(shards) == 46
assert all((target / shard).is_file() for shard in shards)

assert dp["status"] == "COMPLETE"
assert dp["repo_id"] == "RedHatAI/DeepSeek-V4-Flash-speculator.dflash"
assert dp["revision"] == draft_rev
assert pathlib.Path(dp["formal_path"]) == draft
assert dp["file_count"] == 6
assert dp["total_size_bytes"] == 3607606957
assert dc["status"] == "COMPLETE"
assert dc["revision"] == draft_rev
draft_files = sorted(
    p for p in draft.iterdir() if p.is_file() and p.name != ".complete"
)
assert len(draft_files) == dp["file_count"]
assert sum(p.stat().st_size for p in draft_files) == dp["total_size_bytes"]
assert not any(p.is_symlink() or p.stat().st_nlink != 1 for p in draft_files)
draft_config = json.loads((draft / "config.json").read_text())
spec = draft_config["speculators_config"]
assert spec["algorithm"] == "dflash"
assert draft_config["block_size"] == 8
assert draft_config["aux_hidden_state_layer_ids"] == [3, 13, 23, 32, 42]

document = {
    "schema_version": 1,
    "phase": "D5",
    "target": {
        "repo_id": tm["repo_id"],
        "revision": target_rev,
        "formal_path": str(target),
        "completion_marker": str(tm_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_hash,
        "file_count": len(target_files),
        "total_bytes": sum(p.stat().st_size for p in target_files),
        "weight_shard_count": len(shards),
        "architecture": target_config["architectures"][0],
    },
    "draft": {
        "repo_id": dp["repo_id"],
        "revision": draft_rev,
        "formal_path": str(draft),
        "pointer": str(dp_path),
        "completion_marker": str(complete_path),
        "file_count": len(draft_files),
        "total_bytes": sum(p.stat().st_size for p in draft_files),
        "algorithm": spec["algorithm"],
        "block_size": draft_config["block_size"],
        "proposal_candidates": draft_config["block_size"] - 1,
        "aux_hidden_state_layer_ids": draft_config["aux_hidden_state_layer_ids"],
    },
    "pass": True,
}
output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

require_port_free() {
  ! ss -H -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"
}

wait_no_contexts() {
  local output="$1" rows attempt
  : >"${output}"
  for attempt in $(seq 1 60); do
    rows="$(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory --format=csv,noheader,nounits 2>&1)"
    printf '%s attempt=%s contexts=%s\n' "$(utc_now)" "${attempt}" "${rows:-none}" >>"${output}"
    if ! grep -q '[^[:space:]]' <<<"${rows}"; then return 0; fi
    [[ "${attempt}" -eq 60 ]] || sleep 1
  done
  return 1
}

process_matches_server() {
  local pid="$1" expected_ticks="$2" ticks pgid sid
  [[ "${pid}" =~ ^[1-9][0-9]*$ && -r "/proc/${pid}/cmdline" ]] || return 1
  ticks="$("${PYTHON}" - "${pid}" <<'PY'
from pathlib import Path
import sys
s=Path(f"/proc/{sys.argv[1]}/stat").read_text()
print(s[s.rfind(")")+2:].split()[19])
PY
)"
  [[ "${ticks}" = "${expected_ticks}" ]] || return 1
  pgid="$(ps -o pgid= -p "${pid}" | tr -d ' ')"
  sid="$(ps -o sid= -p "${pid}" | tr -d ' ')"
  [[ "${pgid}" = "${pid}" && "${sid}" = "${pid}" ]] || return 1
  "${PYTHON}" - "${pid}" "${SCRATCH}/resolved_config.json" <<'PY'
import json, pathlib, sys
pid=int(sys.argv[1])
expected=json.loads(pathlib.Path(sys.argv[2]).read_text())["command"]
actual=[x.decode(errors="replace") for x in pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if x]
raise SystemExit(0 if actual == expected else 1)
PY
}

sample_gpus() {
  local server_pid="$1" start_ticks="$2"
  local deadline=$((SECONDS + 4500))
  local phase interval
  printf 'timestamp_utc,phase,gpu_index,gpu_uuid,utilization_percent,memory_used_mib,memory_total_mib,server_alive\n' >"${SCRATCH}/gpu_samples.csv"
  while [[ "${SECONDS}" -lt "${deadline}" ]] && process_matches_server "${server_pid}" "${start_ticks}"; do
    if [[ -f "${SCRATCH}/request.active" ]]; then
      phase=request
      interval=0.1
    else
      phase=lifecycle
      interval=1
    fi
    while IFS=, read -r index uuid util used total; do
      printf '%s,%s,%s,%s,%s,%s,%s,true\n' "$(utc_now)" "${phase}" \
        "${index// /}" "${uuid// /}" "${util// /}" "${used// /}" "${total// /}" \
        >>"${SCRATCH}/gpu_samples.csv"
    done < <(nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits)
    sleep "${interval}"
  done
}

write_preflight_artifacts() {
  "${PYTHON}" - "${SCRATCH}" "${SOURCE}" "${SOURCE_SHA}" "${SOURCE_PARENT}" \
    "${SOURCE_BASE}" \
    "${WORKER_ID}" "${EXPECTED_HOST}" "${PORT}" "${ARM}" "${HEDGE_CONFIG}" \
    "${HEDGE_ENABLED_VALUE}" "${CALIBRATION_TRACE_VALUE}" \
    "${NATIVE_ATTEMPT_ID}" "${HARD_STOP_UTC}" "${COMMAND[@]}" <<'PY'
import csv
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
from datetime import datetime, timezone

scratch = pathlib.Path(sys.argv[1])
source = pathlib.Path(sys.argv[2])
source_sha, source_parent, source_base = sys.argv[3:6]
worker_id, expected_host, port = sys.argv[6:9]
arm = sys.argv[9]
hedge_config = json.loads(sys.argv[10])
hedge_enabled = sys.argv[11] == "1"
calibration_trace = sys.argv[12] == "1"
native_attempt_id = sys.argv[13]
hard_stop_utc = sys.argv[14]
command = sys.argv[15:]
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
gpu_text = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ],
    text=True,
)
gpus = []
for row in csv.reader(io.StringIO(gpu_text)):
    index, uuid, name, total, used, util = (item.strip() for item in row)
    gpus.append(
        {
            "index": int(index),
            "uuid": uuid,
            "name": name,
            "memory_total_mib": int(total),
            "memory_used_mib": int(used),
            "utilization_percent": int(util),
            "tp_rank": int(index),
        }
    )
assert len(gpus) == 8
assert [gpu["index"] for gpu in gpus] == list(range(8))
assert all(gpu["name"] == "NVIDIA H20" for gpu in gpus)
keepalive = json.loads(
    pathlib.Path(
        "/tmp/deepspec-hedge-dflash/keepalive/process_identity.json"
    ).read_text()
)
assert keepalive["worker_id"] == worker_id
assert keepalive["hostname"] == expected_host == socket.gethostname()
assert keepalive["expected_gpu_count"] == 8
assert keepalive["pid"] == keepalive["pgid"] == keepalive["sid"]
pid = int(keepalive["pid"])
assert pathlib.Path(f"/proc/{pid}").exists()
actual = [
    x.decode(errors="replace")
    for x in pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    if x
]
assert actual == keepalive["argv"]
assert actual[1].endswith("/scripts/keepalive_load.py")
assert actual[2:] == ["load", "--expected-gpus", "8", "--matrix-size", "8192"]
compute = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ],
    text=True,
).splitlines()

resolved = {
    "schema_version": 1,
    "phase": "D5",
    "attempt_id": scratch.name,
    "worker_id": worker_id,
    "host": expected_host,
    "port": int(port),
    "mode": f"dflash_d5_{arm}",
    "arm": arm,
    "hedge_enabled": hedge_enabled,
    "calibration_trace": calibration_trace,
    "hedge_config": hedge_config,
    "native_attempt_id": native_attempt_id,
    "hard_stop_utc": hard_stop_utc,
    "tp_size": 8,
    "block_size": 8,
    "draft_candidates": 7,
    "command": command,
    "environment": {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "CUDA_HOME": "/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0",
        "LD_LIBRARY_PATH": "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat:/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13/lib",
        "PATH": "/home/tiger/venvs/deepspec-hedge-dflash/bin:/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0/bin:/usr/bin:/bin",
        "FLASHINFER_WORKSPACE_BASE": "/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace",
        "FLASHINFER_CUDA_ARCH_LIST": "9.0",
        "PYTHONNOUSERSITE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_CACHE_DIR": "/tmp/deepspec-hedge-dflash/cache/sglang",
        "SGLANG_DG_CACHE_DIR": "/tmp/deepspec-hedge-dflash/cache/deep_gemm",
        "TRITON_CACHE_DIR": "/tmp/deepspec-hedge-dflash/cache/triton",
        "TORCH_EXTENSIONS_DIR": "/tmp/deepspec-hedge-dflash/cache/torch_extensions",
        "HEDGE_ENABLED": "1" if hedge_enabled else "0",
        "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": (
            "1" if calibration_trace else "0"
        ),
        **(
            {"SGLANG_DFLASH_HEDGE_CONFIG_JSON": json.dumps(
                hedge_config, sort_keys=True, separators=(",", ":")
            )}
            if hedge_enabled
            else {}
        ),
    },
    "unset_environment": [
        "SGLANG_DSV4_FP4_DEQUANT",
        "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
    ],
    "cuda_view": {
        "path": "/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0",
        "ensure_artifact": "cuda_view_ensure.json",
        "verify_artifact": "cuda_view_verify.json",
    },
    "jit_prebuild_helper": (
        "/mlx_devbox/users/pengzegang/playground/github/"
        "DeepSpec-hedge-dflash/scripts/dflash_d3_jit_prebuild.py"
    ),
}
(scratch / "resolved_config.json").write_text(
    json.dumps(resolved, indent=2, sort_keys=True) + "\n"
)
(scratch / "environment.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "captured_at_utc": now,
            "worker_id": worker_id,
            "hostname": socket.gethostname(),
            "gpus": gpus,
            "keepalive": keepalive,
            "compute_applications_before_pause": compute,
            "resolved_environment": resolved["environment"],
            "unset_environment": resolved["unset_environment"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
(scratch / "source_identity.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "checkout": str(source),
            "head": source_sha,
            "parent": source_parent,
            "fixed_base": source_base,
            "fixed_base_is_ancestor": True,
            "status_porcelain": "",
            "hedge_enabled": hedge_enabled,
            "calibration_trace": calibration_trace,
            "hedge_config": resolved["hedge_config"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
(scratch / "command.txt").write_text(
    subprocess.list2cmdline(command) + "\n"
)
(scratch / "requests.jsonl").touch()
(scratch / "hedge_counters.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "NOT_RUN",
            "hedge_enabled": hedge_enabled,
            "mode": f"dflash_d5_{arm}",
            "config": resolved["hedge_config"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
(scratch / "preflight.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "PASS",
            "captured_at_utc": now,
            "worker_id": worker_id,
            "hostname": socket.gethostname(),
            "gpu_count": len(gpus),
            "port": int(port),
            "port_free": True,
            "keepalive_pid": pid,
            "source_sha": source_sha,
            "hard_stop_utc": hard_stop_utc,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
PY
}

record_process_identity() {
  local pid="$1" ticks="$2"
  "${PYTHON}" - "${pid}" "${ticks}" "${SCRATCH}/process_identity.json" \
    "${SCRATCH}/resolved_config.json" "${ATTEMPT_ID}" <<'PY'
import json, os, pathlib, socket, sys
import csv, io, subprocess
from datetime import datetime, timezone
pid, ticks, output, config_path, attempt_id = sys.argv[1:]
pid = int(pid)
config = json.loads(pathlib.Path(config_path).read_text())
actual = [
    x.decode(errors="replace")
    for x in pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    if x
]
assert actual == config["command"]
assert os.getpgid(pid) == pid and os.getsid(pid) == pid
document = {
    "schema_version": 1,
    "phase": "D5",
    "attempt_id": attempt_id,
    "worker_id": "4099543",
    "hostname": socket.gethostname(),
    "pid": pid,
    "pgid": os.getpgid(pid),
    "sid": os.getsid(pid),
    "start_ticks": ticks,
    "argv": actual,
    "port": 31457,
    "cuda_visible_devices": "0,1,2,3,4,5,6,7",
    "rank_to_physical_gpu": [],
    "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
gpu_text = subprocess.check_output(
    ["nvidia-smi", "--query-gpu=index,uuid,name", "--format=csv,noheader,nounits"],
    text=True,
)
for row in csv.reader(io.StringIO(gpu_text)):
    index, uuid, name = (item.strip() for item in row)
    document["rank_to_physical_gpu"].append(
        {
            "tp_rank": int(index),
            "physical_index": int(index),
            "gpu_uuid": uuid,
            "gpu_name": name,
        }
    )
assert len(document["rank_to_physical_gpu"]) == 8
pathlib.Path(output).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

proc_start_ticks() {
  "${PYTHON}" - "${1}" <<'PY'
from pathlib import Path
import sys
s=Path(f"/proc/{sys.argv[1]}/stat").read_text()
print(s[s.rfind(")")+2:].split()[19])
PY
}

stop_sampler() {
  [[ -f "${SCRATCH}/sampler.pid" && -f "${SCRATCH}/sampler.start_ticks" ]] || return 0
  local pid ticks actual pgid sid
  pid="$(<"${SCRATCH}/sampler.pid")"
  ticks="$(<"${SCRATCH}/sampler.start_ticks")"
  [[ -r "/proc/${pid}/cmdline" ]] || return 0
  actual="$(proc_start_ticks "${pid}")"
  [[ "${actual}" = "${ticks}" ]] || return 1
  pgid="$(ps -o pgid= -p "${pid}" | tr -d ' ')"
  sid="$(ps -o sid= -p "${pid}" | tr -d ' ')"
  [[ "${pgid}" = "${pid}" && "${sid}" = "${pid}" ]] || return 1
  "${PYTHON}" - "${pid}" "${REPO}/scripts/dflash_d5_attempt.sh" \
    "${ATTEMPT_ID}" "${ARM}" "${NATIVE_ATTEMPT_ID}" \
    "${HARD_STOP_UTC}" <<'PY'
import pathlib, sys
raw=pathlib.Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes()
argv=[x.decode(errors="replace") for x in raw.split(b"\0") if x]
expected=[
    "bash", sys.argv[2], "_sample", sys.argv[3], sys.argv[4], sys.argv[5],
    sys.argv[6],
]
raise SystemExit(0 if argv[:7] == expected else 1)
PY
  kill -TERM -- "-${pid}"
  for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 1
  done
  return 1
}

stop_server() {
  [[ -f "${SCRATCH}/server.pid" && -f "${SCRATCH}/server.start_ticks" ]] || return 0
  local pid ticks
  pid="$(<"${SCRATCH}/server.pid")"
  ticks="$(<"${SCRATCH}/server.start_ticks")"
  if ! kill -0 "${pid}" 2>/dev/null; then return 0; fi
  process_matches_server "${pid}" "${ticks}"
  kill -TERM -- "-${pid}"
  for _ in $(seq 1 90); do
    if ! kill -0 -- "-${pid}" 2>/dev/null; then return 0; fi
    sleep 1
  done
  # Fail closed instead of sending SIGKILL after the registered leader exited
  # or changed identity.
  process_matches_server "${pid}" "${ticks}" || return 1
  kill -KILL -- "-${pid}"
}

write_cleanup_and_seal() {
  local cleanup_status="$1" contexts_clear="$2" resume_rc="$3"
  "${PYTHON}" - "${SCRATCH}" "${HDFS_RUN}" "${ATTEMPT_ID}" \
    "${cleanup_status}" "${contexts_clear}" "${resume_rc}" "${SOURCE_SHA}" \
    "${HEDGE_CONFIG}" "${ARM}" "${HEDGE_ENABLED_VALUE}" \
    "${CALIBRATION_TRACE_VALUE}" "${NATIVE_ATTEMPT_ID}" \
    "${HARD_STOP_UTC}" <<'PY'
import hashlib
import json
import os
import pathlib
import shutil
import sys
from datetime import datetime, timezone

scratch = pathlib.Path(sys.argv[1])
hdfs_run = pathlib.Path(sys.argv[2])
attempt_id = sys.argv[3]
cleanup_status = sys.argv[4]
contexts_clear = sys.argv[5] == "true"
resume_rc = int(sys.argv[6])
source_sha = sys.argv[7]
hedge_config = json.loads(sys.argv[8])
arm = sys.argv[9]
hedge_enabled = sys.argv[10] == "1"
calibration_trace = sys.argv[11] == "1"
native_attempt_id = sys.argv[12]
hard_stop_utc = sys.argv[13]
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
api_path = scratch / "api_smoke.json"
startup_path = scratch / "startup.json"
counter_path = scratch / "hedge_counters.json"
api = json.loads(api_path.read_text()) if api_path.exists() else {}
counters = json.loads(counter_path.read_text()) if counter_path.exists() else {}
api_status = api.get("status", "NOT_RUN")
counter_status = counters.get("status", "NOT_RUN")
arm_pass = api.get("arm_pass", False)
startup_status = (
    json.loads(startup_path.read_text()).get("status")
    if startup_path.exists()
    else "NOT_READY"
)
cleanup = {
    "schema_version": 1,
    "phase": "D5",
    "attempt_id": attempt_id,
    "status": cleanup_status,
    "contexts_clear": contexts_clear,
    "keepalive_resume_returncode": resume_rc,
    "hard_stop_utc": hard_stop_utc,
    "finished_at_utc": now,
}
(scratch / "cleanup.json").write_text(
    json.dumps(cleanup, indent=2, sort_keys=True) + "\n"
)
status = (
    "PASS"
    if cleanup_status == "PASS"
    and contexts_clear
    and resume_rc == 0
    and startup_status == "ready"
    and api_status == "PASS"
    and counter_status == "PASS"
    and arm_pass is True
    else "FAIL"
)
summary = {
    "schema_version": 1,
    "phase": "D5",
    "attempt_id": attempt_id,
    "mode": f"dflash_d5_{arm}",
    "arm": arm,
    "status": status,
    "startup_status": startup_status,
    "api_status": api_status,
    "hedge_counter_status": counter_status,
    "arm_pass": arm_pass,
    "cleanup_status": cleanup_status,
    "hedge_enabled": hedge_enabled,
    "calibration_trace": calibration_trace,
    "hedge_config": hedge_config,
    "native_attempt_id": native_attempt_id,
    "hard_stop_utc": hard_stop_utc,
    "source_sha": source_sha,
    "benchmark": False,
    "finished_at_utc": now,
}
(scratch / "summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n"
)
files = sorted(
    path for path in scratch.iterdir()
    if path.is_file() and path.name not in {"artifact_manifest.sha256"}
)
manifest_lines = []
for path in files:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_lines.append(f"{digest}  {path.name}")
(scratch / "artifact_manifest.sha256").write_text(
    "\n".join(manifest_lines) + "\n"
)
if hdfs_run.exists():
    raise RuntimeError(f"refusing to overwrite HDFS run: {hdfs_run}")
staging = hdfs_run.with_name(
    f".{hdfs_run.name}.staging-{os.getpid()}"
)
staging.mkdir(parents=True, exist_ok=False)
for path in sorted(p for p in scratch.iterdir() if p.is_file()):
    shutil.copy2(path, staging / path.name)
for path in sorted(p for p in scratch.iterdir() if p.is_file()):
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    target_hash = hashlib.sha256((staging / path.name).read_bytes()).hexdigest()
    if source_hash != target_hash:
        raise RuntimeError(f"HDFS copy hash mismatch: {path.name}")
(staging / ".complete.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "status": status,
            "manifest_sha256": hashlib.sha256(
                (scratch / "artifact_manifest.sha256").read_bytes()
            ).hexdigest(),
            "published_at_utc": now,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
staging.rename(hdfs_run)
raise SystemExit(0 if status == "PASS" else 1)
PY
}

case "${ACTION}" in
  audit-preflight)
    [[ -d "${SCRATCH}" ]]
    "${PYTHON}" - "${ATTEMPT_ID}" "${SCRATCH}" "${HDFS_RUN}" "${SOURCE}" <<'PY'
import csv
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
from datetime import datetime, timezone

attempt_id = sys.argv[1]
scratch = pathlib.Path(sys.argv[2])
hdfs_run = pathlib.Path(sys.argv[3])
source = pathlib.Path(sys.argv[4])
keepalive = pathlib.Path("/tmp/deepspec-hedge-dflash/keepalive")

files = sorted(path.name for path in scratch.iterdir() if path.is_file())
forbidden = {
    "keepalive_pause.txt", "server.pid", "server.start_ticks", "server.log",
    "process_identity.json", "startup.json", "gpu_samples.csv",
}
identity = json.loads((keepalive / "process_identity.json").read_text())
gate = json.loads((keepalive / "keepalive_gate.json").read_text())
pid = int(identity["pid"])
proc = pathlib.Path(f"/proc/{pid}")
argv = [
    part.decode(errors="replace")
    for part in (proc / "cmdline").read_bytes().split(b"\0")
    if part
]
stat = (proc / "stat").read_text()
fields = stat[stat.rfind(")") + 2:].split()
pgid, sid = int(fields[2]), int(fields[3])

gpu_text = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
    ],
    text=True,
)
gpus = []
for row in csv.reader(io.StringIO(gpu_text)):
    index, uuid, name, util, memory = (item.strip() for item in row)
    gpus.append(
        {
            "index": int(index),
            "uuid": uuid,
            "name": name,
            "utilization_percent": int(util),
            "memory_used_mib": int(memory),
        }
    )
compute_text = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ],
    text=True,
)
compute = []
for row in csv.reader(io.StringIO(compute_text)):
    uuid, raw_pid, name, memory = (item.strip() for item in row)
    compute.append(
        {
            "gpu_uuid": uuid,
            "pid": int(raw_pid),
            "process_name": name,
            "used_gpu_memory_mib": int(memory),
        }
    )
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(0.5)
    port_free = probe.connect_ex(("127.0.0.1", 31457)) != 0
source_head = subprocess.check_output(
    ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
).strip()
source_status = subprocess.check_output(
    ["git", "-C", str(source), "status", "--porcelain"], text=True
)
keepalive_only = (
    len(compute) == 8
    and {row["gpu_uuid"] for row in compute} == {row["uuid"] for row in gpus}
    and all(0 < row["used_gpu_memory_mib"] < 4096 for row in compute)
)
zero_gpu_side_effects = (
    not (forbidden & set(files))
    and not hdfs_run.exists()
    and not (keepalive / "paused").exists()
    and port_free
    and keepalive_only
)
document = {
    "schema_version": 1,
    "phase": "D5",
    "attempt_id": attempt_id,
    "status": "PREFLIGHT_BLOCKED",
    "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "blocker": "preflight stalled at isolated SGLang import before keepalive pause",
    "scratch_files": files,
    "preflight_pass": False,
    "native_calibration_status": "NOT_RUN",
    "b0_status": "NOT_RUN",
    "zero_gpu_side_effects": zero_gpu_side_effects,
    "hdfs_run_exists": hdfs_run.exists(),
    "port_31457_free": port_free,
    "source": {
        "head": source_head,
        "clean": source_status == "",
    },
    "keepalive": {
        "identity": identity,
        "supervisor_argv_matches": argv == identity["argv"],
        "supervisor_pgid": pgid,
        "supervisor_sid": sid,
        "paused_marker_exists": (keepalive / "paused").exists(),
        "gate": gate,
        "gate_mtime_utc": datetime.fromtimestamp(
            (keepalive / "keepalive_gate.json").stat().st_mtime, timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "compute_applications": compute,
        "keepalive_only_compute": keepalive_only,
    },
    "gpus": gpus,
    "pty_limitation": (
        "mlx login PTY did not preserve the original wrapper return code/output; "
        "diagnostic wrappers were left to exit naturally and were never signaled"
    ),
}
print(json.dumps(document, indent=2, sort_keys=True))
raise SystemExit(0 if zero_gpu_side_effects and gate.get("healthy") is True else 1)
PY
    ;;
  diagnose-preflight)
    printf 'host=%s expected=%s\n' "$(hostname)" "${EXPECTED_HOST}"
    nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits
    require_worker_identity
    echo worker_identity=PASS
    set -x
    require_source_and_markers
    set +x
    echo source_and_markers=PASS
    require_port_free
    echo port_free=PASS
    bash "${KEEPALIVE}" status "${WORKER_ID}"
    echo keepalive=PASS
    ;;
  contract)
    "${PYTHON}" - "${SOURCE_SHA}" "${SOURCE_PARENT}" "${SOURCE_BASE}" \
      "${WORKER_ID}" "${PORT}" "${TARGET_REV}" "${DRAFT_REV}" \
      "${ARM}" "${HEDGE_CONFIG}" "${HEDGE_ENABLED_VALUE}" \
      "${CALIBRATION_TRACE_VALUE}" "${NATIVE_ATTEMPT_ID}" \
      "${HARD_STOP_UTC}" "${COMMAND[@]}" <<'PY'
import json
import sys

(
    source_sha,
    source_parent,
    source_base,
    worker_id,
    port,
    target_revision,
    draft_revision,
    arm,
    hedge_config,
    hedge_enabled,
    calibration_trace,
    native_attempt_id,
    hard_stop_utc,
    *command
) = sys.argv[1:]
print(
    json.dumps(
        {
            "schema_version": 1,
            "phase": "D5",
            "mode": f"dflash_d5_{arm}",
            "arm": arm,
            "source_sha": source_sha,
            "source_parent": source_parent,
            "source_base": source_base,
            "worker_id": worker_id,
            "port": int(port),
            "tp_size": 8,
            "dflash_block_size": 8,
            "proposal_width": 7,
            "target_revision": target_revision,
            "draft_revision": draft_revision,
            "hedge_config": json.loads(hedge_config),
            "native_attempt_id": native_attempt_id,
            "hard_stop_utc": hard_stop_utc,
            "environment": {
                "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
                "CUDA_HOME": (
                    "/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0"
                ),
                "FLASHINFER_WORKSPACE_BASE": (
                    "/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
                ),
                "SGLANG_RAGGED_VERIFY_MODE": "static",
                "SGLANG_DSV4_FP4_EXPERTS": "1",
                "HEDGE_ENABLED": hedge_enabled,
                "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": calibration_trace,
                **(
                    {"SGLANG_DFLASH_HEDGE_CONFIG_JSON": hedge_config}
                    if hedge_enabled == "1"
                    else {}
                ),
            },
            "unset_environment": [
                "SGLANG_DSV4_FP4_DEQUANT",
                "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
            ],
            "command": command,
            "gpu_action": False,
        },
        indent=2,
        sort_keys=True,
    )
)
PY
    ;;
  preflight)
    [[ ! -e "${SCRATCH}" && ! -e "${HDFS_RUN}" ]]
    mkdir -p "${SCRATCH}"
    mkdir -p /tmp/deepspec-hedge-dflash/cache/{sglang,deep_gemm,triton,torch_extensions,flashinfer-workspace}
    bash "${CUDA_VIEW_HELPER}" ensure >"${SCRATCH}/cuda_view_ensure.json"
    bash "${CUDA_VIEW_HELPER}" verify >"${SCRATCH}/cuda_view_verify.json"
    require_worker_identity
    require_source_and_markers
    require_port_free
    bash "${KEEPALIVE}" status "${WORKER_ID}" >"${SCRATCH}/keepalive_before.txt"
    cp /tmp/deepspec-hedge-dflash/keepalive/process_identity.json \
      "${SCRATCH}/keepalive_identity_before.json"
    write_preflight_artifacts
    cp "${DATASET_IDENTITY}" "${SCRATCH}/dataset_identity.json"
    cp "${CALIBRATION_INDICES}" "${SCRATCH}/calibration_indices.json"
    printf 'PASS attempt=%s worker=%s host=%s keepalive_pid=%s\n' \
      "${ATTEMPT_ID}" "${WORKER_ID}" "${EXPECTED_HOST}" \
      "$("${PYTHON}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "${SCRATCH}/keepalive_identity_before.json")"
    ;;
  pause-launch)
    [[ -d "${SCRATCH}" && -f "${SCRATCH}/keepalive_identity_before.json" ]]
    require_worker_identity
    require_source_and_markers
    require_port_free
    before_hard_stop
    bash "${KEEPALIVE}" status "${WORKER_ID}" >"${SCRATCH}/keepalive_immediate_before_pause.txt"
    cp /tmp/deepspec-hedge-dflash/keepalive/process_identity.json \
      "${SCRATCH}/keepalive_identity_immediate_before_pause.json"
    "${PYTHON}" - "${SCRATCH}/keepalive_identity_before.json" \
      "${SCRATCH}/keepalive_identity_immediate_before_pause.json" <<'PY'
import json, sys
before=json.load(open(sys.argv[1]))
now=json.load(open(sys.argv[2]))
for key in ("worker_id", "hostname", "pid", "pgid", "sid", "argv", "physical_gpus"):
    assert before[key] == now[key], key
PY
    trap 'exit 130' INT TERM
    trap 'rc=$?; trap - EXIT INT TERM; if [[ $rc -ne 0 ]]; then bash "$0" cleanup-resume "${ATTEMPT_ID}" "${ARM}" "${NATIVE_ATTEMPT_ID}" "${HARD_STOP_UTC}" || true; fi; exit $rc' EXIT
    bash "${KEEPALIVE}" pause "${WORKER_ID}" >"${SCRATCH}/keepalive_pause.txt"
    wait_no_contexts "${SCRATCH}/cuda_contexts_after_pause.txt"
    setsid "${COMMAND[@]}" >"${SCRATCH}/server.log" 2>&1 &
    server_pid=$!
    printf '%s\n' "${server_pid}" >"${SCRATCH}/server.pid"
    server_ticks=""
    for _ in $(seq 1 10); do
      if [[ -r "/proc/${server_pid}/stat" ]]; then
        server_ticks="$(proc_start_ticks "${server_pid}")"
        printf '%s\n' "${server_ticks}" >"${SCRATCH}/server.start_ticks"
        break
      fi
      sleep 0.1
    done
    [[ -n "${server_ticks}" && -f "${SCRATCH}/server.start_ticks" ]]
    for _ in $(seq 1 30); do
      if [[ -r "/proc/${server_pid}/cmdline" ]]; then
        if process_matches_server "${server_pid}" "${server_ticks}"; then break; fi
      fi
      sleep 1
    done
    process_matches_server "${server_pid}" "${server_ticks}"
    record_process_identity "${server_pid}" "${server_ticks}"
    setsid nohup bash "$0" _sample \
      "${ATTEMPT_ID}" "${ARM}" "${NATIVE_ATTEMPT_ID}" "${HARD_STOP_UTC}" \
      "${server_pid}" "${server_ticks}" \
      >"${SCRATCH}/sampler.log" 2>&1 &
    sampler_pid=$!
    printf '%s\n' "${sampler_pid}" >"${SCRATCH}/sampler.pid"
    printf '%s\n' "$(proc_start_ticks "${sampler_pid}")" >"${SCRATCH}/sampler.start_ticks"
    ready=0
    ready_started="$(utc_now)"
    deadline=$((SECONDS + 3600))
    : >"${SCRATCH}/readiness_checks.log"
    while [[ "${SECONDS}" -lt "${deadline}" ]]; do
      before_hard_stop
      process_matches_server "${server_pid}" "${server_ticks}"
      if curl --noproxy '*' --silent --show-error --fail --max-time 5 \
        "${BASE_URL}/health" >>"${SCRATCH}/readiness_checks.log" 2>&1; then
        ready=1
        break
      fi
      printf '\n%s not-ready\n' "$(utc_now)" >>"${SCRATCH}/readiness_checks.log"
      sleep 5
    done
    "${PYTHON}" - "${SCRATCH}/startup.json" "${ready}" "${ready_started}" \
      "${HARD_STOP_UTC}" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone
path, ready, started, hard_stop_utc = sys.argv[1:]
pathlib.Path(path).write_text(json.dumps({
  "schema_version": 1,
  "status": "ready" if ready == "1" else "timeout",
  "started_at_utc": started,
  "finished_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
  "timeout_seconds": 3600,
  "hard_stop_utc": hard_stop_utc,
}, indent=2, sort_keys=True) + "\n")
PY
    [[ "${ready}" -eq 1 ]]
    before_hard_stop
    nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total \
      --format=csv,noheader,nounits >"${SCRATCH}/gpu_after_ready.csv"
    "${PYTHON}" "${API_HELPER}" run --arm "${ARM}" \
      --base-url "${BASE_URL}" --model "${MODEL_NAME}" \
      --dataset "${CALIBRATION_DATA}" --scratch "${SCRATCH}" \
      --native-run "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/${NATIVE_ATTEMPT_ID}" \
      --hard-stop-utc "${HARD_STOP_UTC}" --timeout 300
    before_hard_stop
    nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total \
      --format=csv,noheader,nounits >"${SCRATCH}/gpu_after_request.csv"
    : >"${SCRATCH}/smoke.complete"
    trap - EXIT INT TERM
    printf 'READY_AND_SMOKE_PASS attempt=%s server_pid=%s\n' "${ATTEMPT_ID}" "${server_pid}"
    ;;
  status)
    [[ -d "${SCRATCH}" ]]
    printf 'checked_at=%s attempt=%s\n' "$(utc_now)" "${ATTEMPT_ID}"
    find "${SCRATCH}" -maxdepth 1 -type f -printf 'artifact=%f bytes=%s\n' | sort
    if [[ -f "${SCRATCH}/server.pid" && -f "${SCRATCH}/server.start_ticks" ]]; then
      server_pid="$(<"${SCRATCH}/server.pid")"
      server_ticks="$(<"${SCRATCH}/server.start_ticks")"
      if process_matches_server "${server_pid}" "${server_ticks}"; then
        printf 'server=OWNED_RUNNING pid=%s\n' "${server_pid}"
        ps -o pid=,ppid=,pgid=,sid=,stat=,etime= -p "${server_pid}"
      else
        printf 'server=NOT_RUNNING_OR_IDENTITY_CHANGED pid=%s\n' "${server_pid}"
      fi
    else
      printf 'server=NOT_LAUNCHED\n'
    fi
    nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total \
      --format=csv,noheader,nounits
    nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory \
      --format=csv,noheader,nounits || true
    tail -n 120 "${SCRATCH}/server.log" 2>/dev/null || true
    ;;
  cleanup-resume)
    [[ -d "${SCRATCH}" ]]
    cleanup_status=PASS
    stop_server || cleanup_status=FAIL
    stop_sampler || cleanup_status=FAIL
    contexts_clear=true
    if ! wait_no_contexts "${SCRATCH}/cuda_contexts_after_server.txt"; then
      contexts_clear=false
      cleanup_status=FAIL
    fi
    resume_rc=1
    if [[ "${contexts_clear}" = true ]]; then
      set +e
      bash "${KEEPALIVE}" resume "${WORKER_ID}" >"${SCRATCH}/keepalive_resume.txt" 2>&1
      resume_rc=$?
      set -e
      if [[ "${resume_rc}" -eq 0 ]]; then
        cp /tmp/deepspec-hedge-dflash/keepalive/process_identity.json \
          "${SCRATCH}/keepalive_identity_after.json"
        cp /tmp/deepspec-hedge-dflash/keepalive/keepalive_gpu_samples.csv \
          "${SCRATCH}/keepalive_resume_gpu_samples.csv"
        cp /tmp/deepspec-hedge-dflash/keepalive/keepalive_gate.json \
          "${SCRATCH}/keepalive_resume_gate.json"
      else
        cleanup_status=FAIL
      fi
    fi
    write_cleanup_and_seal "${cleanup_status}" "${contexts_clear}" "${resume_rc}"
    [[ "${cleanup_status}" = PASS && "${contexts_clear}" = true && "${resume_rc}" -eq 0 ]]
    printf 'CLEANUP_RESUME_PASS attempt=%s hdfs=%s\n' "${ATTEMPT_ID}" "${HDFS_RUN}"
    ;;
  _sample)
    sample_gpus "${6:?server pid}" "${7:?start ticks}"
    ;;
  *)
    echo "usage: $0 {contract|preflight|pause-launch|status|cleanup-resume} ATTEMPT_ID {native|b0} NATIVE_ATTEMPT_ID HARD_STOP_UTC" >&2
    exit 2
    ;;
esac
