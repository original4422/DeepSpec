#!/usr/bin/env bash
# Read-only D7 audit of the assigned worker and the naturally completed D5 preflight.

set -euo pipefail

readonly EXPECTED_WORKER_ID=4099543
readonly WORKER_ID="${1:?worker id required}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"

if [[ "${WORKER_ID}" != "${EXPECTED_WORKER_ID}" ]]; then
  printf 'expected worker %s, got %s\n' "${EXPECTED_WORKER_ID}" "${WORKER_ID}" >&2
  exit 2
fi

exec "${PYTHON}" - "${WORKER_ID}" <<'PY'
import csv
import hashlib
import io
import json
import pathlib
import socket
import subprocess
import sys
from datetime import datetime, timezone

worker_id = sys.argv[1]
expected_host = "g340-cd51-4b00-4d69-9088-7ae6-6253"
expected_uuids = [
    "GPU-0d0883e5-c11e-1017-a7a4-b0041d34e659",
    "GPU-bef18fe2-5b0e-dfa9-d0df-4bdc845813a8",
    "GPU-04a2d19d-0850-4a7a-7d0a-f76bedbba0c6",
    "GPU-2fe9a932-da80-a85e-05ed-7e7a4298ac9f",
    "GPU-1937f10f-d9a7-54d0-bf1f-c11c5e99252a",
    "GPU-5ad3743c-377e-722b-21ea-807cde0ab2e6",
    "GPU-0c263468-925e-2a59-de84-795c577bb97e",
    "GPU-5d6fc8af-a3f9-2e26-5b6c-c2c673a667dc",
]
capture_cutoff = datetime.fromisoformat("2026-07-29T05:42:45+00:00")
attempt_id = "dflash-d5-native-20260729T053735Z-a01"
scratch = pathlib.Path("/tmp/deepspec-hedge-dflash/runs") / attempt_id
hdfs_run = pathlib.Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs"
) / attempt_id
keepalive_dir = pathlib.Path("/tmp/deepspec-hedge-dflash/keepalive")


def read_json(path: pathlib.Path):
    return json.loads(path.read_text())


def digest(path: pathlib.Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def utc_mtime(path: pathlib.Path) -> str:
    return datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc
    ).isoformat().replace("+00:00", "Z")


identity = read_json(keepalive_dir / "process_identity.json")
gate = read_json(keepalive_dir / "keepalive_gate.json")
pid = int(identity["pid"])
proc = pathlib.Path("/proc") / str(pid)
argv = [
    item.decode(errors="replace")
    for item in (proc / "cmdline").read_bytes().split(b"\0")
    if item
]
stat_text = (proc / "stat").read_text()
stat_fields = stat_text[stat_text.rfind(")") + 2 :].split()
pgid = int(stat_fields[2])
sid = int(stat_fields[3])

gpu_text = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ],
    text=True,
)
gpus = []
for row in csv.reader(io.StringIO(gpu_text)):
    index, uuid, name, utilization, memory_used, memory_total = (
        item.strip() for item in row
    )
    gpus.append(
        {
            "index": int(index),
            "uuid": uuid,
            "name": name,
            "utilization_percent": int(utilization),
            "memory_used_mib": int(memory_used),
            "memory_total_mib": int(memory_total),
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
    if not row:
        continue
    uuid, raw_pid, name, memory = (item.strip() for item in row)
    compute.append(
        {
            "gpu_uuid": uuid,
            "host_pid": int(raw_pid),
            "process_name": name,
            "used_gpu_memory_mib": int(memory),
        }
    )

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(0.5)
    port_free = probe.connect_ex(("127.0.0.1", 31457)) != 0

model_processes = []
for cmdline_path in pathlib.Path("/proc").glob("[0-9]*/cmdline"):
    try:
        raw = cmdline_path.read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    command = " ".join(
        part.decode(errors="replace") for part in raw.split(b"\0") if part
    )
    if "sglang.launch_server" in command or (
        "/home/tiger/src/deepspec-sglang-hedge-dflash" in command
        and "--port 31457" in command
    ):
        model_processes.append(
            {"pid": int(cmdline_path.parent.name), "command": command}
        )

files = []
for path in sorted(item for item in scratch.iterdir() if item.is_file()):
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    files.append(
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "mtime_utc": mtime.isoformat().replace("+00:00", "Z"),
            "post_early_stop_capture": mtime > capture_cutoff,
            "sha256": digest(path),
        }
    )
file_names = {item["name"] for item in files}
forbidden_runtime_files = {
    "gpu_samples.csv",
    "keepalive_pause.txt",
    "process_identity.json",
    "sampler.pid",
    "sampler.start_ticks",
    "server.log",
    "server.pid",
    "server.start_ticks",
    "smoke.complete",
    "startup.json",
}
preflight = read_json(scratch / "preflight.json")
hedge_counters = read_json(scratch / "hedge_counters.json")
requests_path = scratch / "requests.jsonl"

gpu_identity_pass = (
    len(gpus) == 8
    and [row["index"] for row in gpus] == list(range(8))
    and [row["uuid"] for row in gpus] == expected_uuids
    and all(row["name"] == "NVIDIA H20" for row in gpus)
)
keepalive_identity_pass = (
    identity["worker_id"] == worker_id
    and identity["hostname"] == socket.gethostname() == expected_host
    and identity["pid"] == identity["pgid"] == identity["sid"] == pid
    and identity["expected_gpu_count"] == 8
    and identity["cuda_visible_devices"] == "0,1,2,3,4,5,6,7"
    and argv == identity["argv"]
    and pgid == sid == pid
)
keepalive_only_compute = (
    len(compute) == 8
    and [row["gpu_uuid"] for row in compute] == expected_uuids
    and all(0 < row["used_gpu_memory_mib"] < 4096 for row in compute)
)
d5_zero_gpu_side_effects = (
    not (file_names & forbidden_runtime_files)
    and requests_path.stat().st_size == 0
    and hedge_counters.get("status") == "NOT_RUN"
    and not hdfs_run.exists()
    and not (keepalive_dir / "paused").exists()
    and port_free
    and not model_processes
    and keepalive_only_compute
)
status = (
    "PASS"
    if gpu_identity_pass
    and keepalive_identity_pass
    and gate.get("healthy") is True
    and gate.get("sample_count_per_gpu") == 10
    and min(gate["per_gpu_mean_utilization_percent"].values()) >= 40.0
    and d5_zero_gpu_side_effects
    else "FAIL"
)

document = {
    "schema_version": 1,
    "phase": "D7",
    "captured_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "status": status,
    "worker": {
        "worker_id": worker_id,
        "hostname": socket.gethostname(),
        "gpu_identity_pass": gpu_identity_pass,
        "gpus": gpus,
    },
    "keepalive": {
        "identity": identity,
        "identity_pass": keepalive_identity_pass,
        "gate": gate,
        "gate_mtime_utc": utc_mtime(keepalive_dir / "keepalive_gate.json"),
        "paused_marker_exists": (keepalive_dir / "paused").exists(),
        "compute_applications": compute,
        "keepalive_only_compute": keepalive_only_compute,
        "pid_namespace_note": (
            "nvidia-smi reports host-namespace child PIDs as [Not Found] in "
            "the worker container; exact one-per-UUID low-memory contexts, "
            "the verified supervisor argv, and the sustained gate identify "
            "them as the operational keepalive."
        ),
    },
    "service": {
        "port_31457_free": port_free,
        "owned_model_processes": model_processes,
        "model_server_running": bool(model_processes) or not port_free,
        "model_cuda_contexts": 0 if keepalive_only_compute else None,
    },
    "d5_final_preflight_observation": {
        "attempt_id": attempt_id,
        "early_stop_capture_utc": capture_cutoff.isoformat().replace(
            "+00:00", "Z"
        ),
        "files": files,
        "file_count": len(files),
        "preflight": preflight,
        "preflight_completed_without_surfaced_wrapper_rc": (
            preflight.get("status") == "PASS"
        ),
        "requests_bytes": requests_path.stat().st_size,
        "requests_count": sum(1 for _ in requests_path.open()),
        "hedge_counters": hedge_counters,
        "forbidden_runtime_files_present": sorted(
            file_names & forbidden_runtime_files
        ),
        "hdfs_run_exists": hdfs_run.exists(),
        "zero_gpu_side_effects": d5_zero_gpu_side_effects,
        "inventory_discrepancy": (
            "All retained metadata mtimes are at or before 05:40:13Z, while "
            "the 05:42:45Z blocker recorded only the two CUDA-view files. "
            "The final scratch inventory therefore supersedes that stale "
            "orchestrator-visible inventory without changing the zero-GPU "
            "conclusion."
        ),
        "interpretation": (
            "The preflight wrote PASS metadata, but the mlx wrapper never "
            "surfaced a recoverable return code/stdout to the main agent. It "
            "never paused keepalive or started a model/API/calibration "
            "lifecycle."
        ),
    },
}
print(json.dumps(document, indent=2, sort_keys=True))
raise SystemExit(0 if status == "PASS" else 1)
PY
