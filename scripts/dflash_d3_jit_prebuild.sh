#!/usr/bin/env bash
# Prebuild the isolated FlashInfer SM90 fused-MoE JIT while keepalive stays active.
set -Eeuo pipefail

readonly ATTEMPT_ID="${1:?attempt id required}"
readonly WORKER_ID=4099543
readonly EXPECTED_HOST="g340-cd51-4b00-4d69-9088-7ae6-6253"
readonly REPO="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly KEEPALIVE="${REPO}/scripts/dflash_keepalive.sh"
readonly KEEPALIVE_STATE="/tmp/deepspec-hedge-dflash/keepalive"
readonly CUDA_VIEW_HELPER="${REPO}/scripts/dflash_d3_cuda_view.sh"
readonly PREBUILD_HELPER="${REPO}/scripts/dflash_d3_jit_prebuild.py"
readonly CUDA_VIEW="/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0"
readonly CU13_PAYLOAD="/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13"
readonly CUDA_COMPAT_DIR="/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
readonly FLASHINFER_WORKSPACE_BASE="/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
readonly SHARED_CACHE="/home/tiger/.cache/flashinfer"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/jit-prebuild/${ATTEMPT_ID}"

[[ "${ATTEMPT_ID}" =~ ^dflash-d3-jit-prebuild-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ ! -e "${SCRATCH}" ]]
mkdir -p "${SCRATCH}"
exec > >(tee -a "${SCRATCH}/runner.log") 2>&1

export CUDA_VIEW
export CUDA_VISIBLE_DEVICES=''
export CUDA_HOME="${CUDA_VIEW}"
export LD_LIBRARY_PATH="${CUDA_COMPAT_DIR}:${CU13_PAYLOAD}/lib"
export PATH="/home/tiger/venvs/deepspec-hedge-dflash/bin:${CUDA_VIEW}/bin:/usr/bin:/bin"
export FLASHINFER_WORKSPACE_BASE
export FLASHINFER_CUDA_ARCH_LIST=9.0
export MAX_JOBS=16
export PYTHONNOUSERSITE=1

MAIN_COMPLETE=false
BEFORE_COMPLETE=false

utc_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

require_worker_identity() {
  [[ "$(hostname)" = "${EXPECTED_HOST}" ]]
  nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits \
    >"${SCRATCH}/gpu_identity.csv"
  awk -F, '
    {
      gsub(/^[ \t]+|[ \t]+$/, "", $1)
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      gsub(/^[ \t]+|[ \t]+$/, "", $3)
      if (($1 + 0) != NR - 1 || $2 !~ /^GPU-/ || $3 != "NVIDIA H20") bad=1
    }
    END { exit !(NR == 8 && !bad) }
  ' "${SCRATCH}/gpu_identity.csv"
}

capture_keepalive() {
  local suffix="$1"
  bash "${KEEPALIVE}" status "${WORKER_ID}" \
    >"${SCRATCH}/keepalive_status_${suffix}.txt"
  grep -Eq "^HEALTHY worker=${WORKER_ID} host=${EXPECTED_HOST} pid=[1-9][0-9]*$" \
    "${SCRATCH}/keepalive_status_${suffix}.txt"
  cp "${KEEPALIVE_STATE}/process_identity.json" \
    "${SCRATCH}/keepalive_identity_${suffix}.json"
  cp "${KEEPALIVE_STATE}/keepalive_gate.json" \
    "${SCRATCH}/keepalive_gate_${suffix}.json"
  nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name \
    --format=csv,noheader,nounits \
    >"${SCRATCH}/compute_apps_${suffix}.csv"
  "${PYTHON}" - "${SCRATCH}" "${suffix}" "${WORKER_ID}" \
    "${EXPECTED_HOST}" "${KEEPALIVE_STATE}" <<'PY'
import csv
import collections
import json
import os
import pathlib
import socket
import sys

scratch = pathlib.Path(sys.argv[1])
suffix = sys.argv[2]
worker_id = sys.argv[3]
expected_host = sys.argv[4]
state = pathlib.Path(sys.argv[5])
identity = json.loads(
    (scratch / f"keepalive_identity_{suffix}.json").read_text()
)
gate = json.loads((scratch / f"keepalive_gate_{suffix}.json").read_text())
assert identity["worker_id"] == worker_id
assert identity["hostname"] == expected_host == socket.gethostname()
assert identity["expected_gpu_count"] == 8
assert identity["pid"] == identity["pgid"] == identity["sid"]
assert identity["cuda_visible_devices"] == "0,1,2,3,4,5,6,7"
assert [gpu["index"] for gpu in identity["physical_gpus"]] == list(range(8))
assert all(gpu["name"] == "NVIDIA H20" for gpu in identity["physical_gpus"])
assert gate["healthy"] is True
assert gate["expected_gpus"] == 8
assert gate["sample_count_per_gpu"] == 10
assert set(gate["per_gpu_mean_utilization_percent"]) == {
    str(index) for index in range(8)
}
assert all(
    value >= gate["minimum_mean_utilization_percent"]
    for value in gate["per_gpu_mean_utilization_percent"].values()
)
pid = int(identity["pid"])
raw = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
argv = [part.decode(errors="replace") for part in raw.split(b"\0") if part]
assert argv == identity["argv"]
assert os.getpgid(pid) == pid and os.getsid(pid) == pid
assert pathlib.Path(state / "supervisor.pid").read_text().strip() == str(pid)

apps = []
with (scratch / f"compute_apps_{suffix}.csv").open(newline="") as handle:
    for row in csv.reader(handle):
        if not row or not "".join(row).strip():
            continue
        assert len(row) == 3, row
        apps.append(tuple(item.strip() for item in row))
# nvidia-smi exposes host-namespace PIDs, while /proc above exposes the
# container-local supervisor PID. Prove the two identities independently.
expected_uuids = {gpu["uuid"] for gpu in identity["physical_gpus"]}
uuid_counts = collections.Counter(row[0] for row in apps)
host_pids = [row[1] for row in apps]
assert len(apps) == 8
assert set(uuid_counts) == expected_uuids
assert all(count == 1 for count in uuid_counts.values())
assert all(value.isdigit() and int(value) > 0 for value in host_pids)
assert len(set(host_pids)) == 8
(scratch / f"compute_apps_{suffix}.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "pid_namespace": {
                "nvidia_smi_rows": "host",
                "keepalive_supervisor_proc": "container-local",
                "direct_pid_equality_expected": False,
            },
            "local_keepalive_supervisor_pid": pid,
            "host_compute_pids": sorted(int(value) for value in host_pids),
            "gpu_uuids": sorted(uuid_counts),
            "row_count": len(apps),
            "one_row_per_physical_gpu": True,
            "process_names": sorted({row[2] for row in apps}),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
PY
}

fingerprint_shared_cache() {
  local output="$1"
  "${PYTHON}" - "${SHARED_CACHE}" "${output}" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
entries = []
total_regular_bytes = 0
if root.is_symlink():
    raise RuntimeError(f"shared cache root must not be a symlink: {root}")
if root.exists():
    if not root.is_dir():
        raise RuntimeError(f"shared cache root must be a directory: {root}")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        directory = pathlib.Path(dirpath)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            path = directory / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISREG(info.st_mode):
                kind = "file"
                total_regular_bytes += info.st_size
                target = None
            elif stat.S_ISDIR(info.st_mode):
                kind = "directory"
                target = None
            elif stat.S_ISLNK(info.st_mode):
                kind = "symlink"
                target = os.readlink(path)
            else:
                kind = "other"
                target = None
            entries.append(
                {
                    "path": relative,
                    "kind": kind,
                    "mode": stat.S_IMODE(info.st_mode),
                    "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns,
                    "ctime_ns": info.st_ctime_ns,
                    "target": target,
                }
            )
payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
document = {
    "schema_version": 1,
    "root": str(root),
    "exists": root.exists(),
    "fingerprint_kind": "lstat-tree-metadata-v1",
    "fingerprint_sha256": hashlib.sha256(payload).hexdigest(),
    "entry_count": len(entries),
    "total_regular_bytes": total_regular_bytes,
}
output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

compare_keepalive_identity() {
  "${PYTHON}" - \
    "${SCRATCH}/keepalive_identity_before.json" \
    "${SCRATCH}/keepalive_identity_after.json" <<'PY'
import json
import pathlib
import sys

before = json.loads(pathlib.Path(sys.argv[1]).read_text())
after = json.loads(pathlib.Path(sys.argv[2]).read_text())
stable = (
    "schema_version",
    "lane",
    "worker_id",
    "hostname",
    "pid",
    "pgid",
    "sid",
    "argv",
    "expected_gpu_count",
    "cuda_visible_devices",
    "physical_gpus",
    "started_at_utc",
)
for key in stable:
    assert before[key] == after[key], key
PY
}

compare_compute_apps() {
  "${PYTHON}" - \
    "${SCRATCH}/compute_apps_before.csv" \
    "${SCRATCH}/compute_apps_after.csv" <<'PY'
import csv
import pathlib
import sys

def normalized(path: pathlib.Path) -> list[tuple[str, str, str]]:
    rows = []
    with path.open(newline="") as handle:
        for row in csv.reader(handle):
            if not row or not "".join(row).strip():
                continue
            assert len(row) == 3, row
            rows.append(tuple(item.strip() for item in row))
    return sorted(rows)

before = normalized(pathlib.Path(sys.argv[1]))
after = normalized(pathlib.Path(sys.argv[2]))
assert before == after, (before, after)
PY
}

compare_shared_cache() {
  "${PYTHON}" - \
    "${SCRATCH}/shared_cache_before.json" \
    "${SCRATCH}/shared_cache_after.json" <<'PY'
import json
import pathlib
import sys

before = json.loads(pathlib.Path(sys.argv[1]).read_text())
after = json.loads(pathlib.Path(sys.argv[2]).read_text())
for key in (
    "root",
    "exists",
    "fingerprint_kind",
    "fingerprint_sha256",
    "entry_count",
    "total_regular_bytes",
):
    assert before[key] == after[key], key
PY
}

validate_build_artifacts() {
  "${PYTHON}" - "${SCRATCH}/jit_prebuild.json" \
    "${FLASHINFER_WORKSPACE_BASE}" "${SCRATCH}/artifact_validation.json" <<'PY'
import json
import pathlib
import sys

result = json.loads(pathlib.Path(sys.argv[1]).read_text())
workspace_base = pathlib.Path(sys.argv[2]).resolve(strict=True)
output = pathlib.Path(sys.argv[3])
assert result["status"] == "PASS"
assert pathlib.Path(result["workspace_base"]).resolve(strict=True) == workspace_base
build_dir = pathlib.Path(result["build_dir"]).resolve(strict=True)
ninja_file = pathlib.Path(result["ninja_file"]).resolve(strict=True)
shared_object = pathlib.Path(result["shared_object"]["path"]).resolve(strict=True)
assert build_dir.is_relative_to(workspace_base)
assert ninja_file.is_relative_to(build_dir) and ninja_file.is_file()
assert shared_object.is_relative_to(build_dir) and shared_object.is_file()
forbidden = {
    "eagle": b"eagle",
    "shared_home_cache": b"/home/tiger/.cache/flashinfer",
    "cuda_12_6_dash": b"cuda-12.6",
    "cuda_12_6_compact": b"cuda12.6",
    "cuda_12_6_space": b"cuda 12.6",
    "cu126": b"cu126",
}
matches = {}
for path in (ninja_file, shared_object):
    content = path.read_bytes().lower()
    hits = sorted(name for name, marker in forbidden.items() if marker in content)
    matches[str(path)] = hits
    assert not hits, (path, hits)
output.write_text(
    json.dumps(
        {
            "schema_version": 1,
            "status": "PASS",
            "workspace_base": str(workspace_base),
            "build_dir": str(build_dir),
            "build_ninja": str(ninja_file),
            "shared_object": str(shared_object),
            "forbidden_markers": sorted(forbidden),
            "matches": matches,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
PY
  local shared_object
  shared_object="$(
    "${PYTHON}" -c \
      'import json,sys; print(json.load(open(sys.argv[1]))["shared_object"]["path"])' \
      "${SCRATCH}/jit_prebuild.json"
  )"
  readelf -d "${shared_object}" >"${SCRATCH}/readelf_dynamic.txt" 2>&1
  ldd "${shared_object}" >"${SCRATCH}/ldd.txt" 2>&1
  ! grep -Eiq 'not found' "${SCRATCH}/readelf_dynamic.txt" "${SCRATCH}/ldd.txt"
}

write_invocation_artifacts() {
  local -a command=(
    "${PYTHON}" "${PREBUILD_HELPER}"
    --output "${SCRATCH}/jit_prebuild.json"
  )
  printf '%q ' "${command[@]}" >"${SCRATCH}/command.txt"
  printf '\n' >>"${SCRATCH}/command.txt"
  "${PYTHON}" - "${SCRATCH}/environment.json" "${ATTEMPT_ID}" <<'PY'
import json
import os
import pathlib
import socket
import sys
from datetime import datetime, timezone

names = (
    "CUDA_VIEW",
    "CUDA_VISIBLE_DEVICES",
    "CUDA_HOME",
    "LD_LIBRARY_PATH",
    "PATH",
    "FLASHINFER_WORKSPACE_BASE",
    "FLASHINFER_CUDA_ARCH_LIST",
    "MAX_JOBS",
    "PYTHONNOUSERSITE",
)
pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "phase": "D3",
            "attempt_id": sys.argv[2],
            "captured_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "hostname": socket.gethostname(),
            "environment": {name: os.environ.get(name) for name in names},
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
PY
}

postflight() {
  local rc=0
  fingerprint_shared_cache "${SCRATCH}/shared_cache_after.json" || rc=1
  if [[ "${BEFORE_COMPLETE}" = true ]]; then
    compare_shared_cache || rc=1
  else
    rc=1
  fi
  capture_keepalive after || rc=1
  if [[ -f "${SCRATCH}/keepalive_identity_before.json" ]]; then
    compare_keepalive_identity || rc=1
  else
    rc=1
  fi
  if [[ -f "${SCRATCH}/compute_apps_before.csv" \
    && -f "${SCRATCH}/compute_apps_after.csv" ]]; then
    compare_compute_apps || rc=1
  else
    rc=1
  fi
  return "${rc}"
}

write_summary() {
  local original_rc="$1" postflight_rc="$2" final_rc="$3"
  "${PYTHON}" - "${SCRATCH}" "${ATTEMPT_ID}" "${original_rc}" \
    "${postflight_rc}" "${final_rc}" "${MAIN_COMPLETE}" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

scratch = pathlib.Path(sys.argv[1])
attempt_id = sys.argv[2]
original_rc, postflight_rc, final_rc = map(int, sys.argv[3:6])
main_complete = sys.argv[6] == "true"
document = {
    "schema_version": 1,
    "phase": "D3",
    "attempt_id": attempt_id,
    "operation": "flashinfer_fused_moe_sm90_prebuild",
    "status": "PASS" if final_rc == 0 and main_complete else "FAIL",
    "main_complete": main_complete,
    "main_returncode": original_rc,
    "postflight_returncode": postflight_rc,
    "final_returncode": final_rc,
    "keepalive_paused": False,
    "shared_cache_modified": (
        None
        if not (
            (scratch / "shared_cache_before.json").is_file()
            and (scratch / "shared_cache_after.json").is_file()
        )
        else json.loads((scratch / "shared_cache_before.json").read_text())[
            "fingerprint_sha256"
        ]
        != json.loads((scratch / "shared_cache_after.json").read_text())[
            "fingerprint_sha256"
        ]
    ),
    "finished_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
}
(scratch / "summary.json").write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n"
)
PY
}

finalize() {
  local original_rc=$? postflight_rc final_rc
  trap - EXIT
  set +e
  postflight
  postflight_rc=$?
  final_rc="${original_rc}"
  if [[ "${original_rc}" -eq 0 && "${postflight_rc}" -ne 0 ]]; then
    final_rc=1
  fi
  write_summary "${original_rc}" "${postflight_rc}" "${final_rc}"
  local summary_rc=$?
  if [[ "${summary_rc}" -ne 0 ]]; then
    printf 'FAIL unable to write summary rc=%s\n' "${summary_rc}" >&2
    final_rc=1
  fi
  printf 'FINISHED attempt=%s status=%s scratch=%s\n' \
    "${ATTEMPT_ID}" "$([[ "${final_rc}" -eq 0 ]] && printf PASS || printf FAIL)" \
    "${SCRATCH}"
  exit "${final_rc}"
}
trap finalize EXIT

printf 'START attempt=%s worker=%s host=%s scratch=%s\n' \
  "${ATTEMPT_ID}" "${WORKER_ID}" "${EXPECTED_HOST}" "${SCRATCH}"
write_invocation_artifacts
require_worker_identity
capture_keepalive before
fingerprint_shared_cache "${SCRATCH}/shared_cache_before.json"
BEFORE_COMPLETE=true
bash "${CUDA_VIEW_HELPER}" ensure >"${SCRATCH}/cuda_view_ensure.json"
bash "${CUDA_VIEW_HELPER}" verify >"${SCRATCH}/cuda_view_verify.json"

readonly -a PREBUILD_COMMAND=(
  "${PYTHON}" "${PREBUILD_HELPER}"
  --output "${SCRATCH}/jit_prebuild.json"
)
"${PREBUILD_COMMAND[@]}" >"${SCRATCH}/jit_prebuild.log" 2>&1
validate_build_artifacts
MAIN_COMPLETE=true
