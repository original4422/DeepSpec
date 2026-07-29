#!/usr/bin/env bash
# Read-only recovery audit after a pre-GPU D4-C orchestration interruption.
set -Eeuo pipefail

readonly ATTEMPT_ID="${1:?attempt id required}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/runs/${ATTEMPT_ID}"
readonly HDFS_RUN="/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/${ATTEMPT_ID}"
readonly SOURCE="/home/tiger/src/deepspec-sglang-hedge-dflash"
readonly KEEPALIVE_STATE="/tmp/deepspec-hedge-dflash/keepalive"
readonly OUTPUT="${SCRATCH}/prelaunch_recovery_audit.json"

[[ "${ATTEMPT_ID}" =~ ^dflash-d4-b0-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ -d "${SCRATCH}" ]]

"${PYTHON}" - "${ATTEMPT_ID}" "${SCRATCH}" "${HDFS_RUN}" "${SOURCE}" \
  "${KEEPALIVE_STATE}" "${OUTPUT}" <<'PY'
from __future__ import annotations

import csv
import io
import json
import pathlib
import socket
import subprocess
import sys
from datetime import datetime, timezone


attempt_id = sys.argv[1]
scratch = pathlib.Path(sys.argv[2])
hdfs_run = pathlib.Path(sys.argv[3])
source = pathlib.Path(sys.argv[4])
keepalive_state = pathlib.Path(sys.argv[5])
output = pathlib.Path(sys.argv[6])
expected_source = "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
expected_tree = "53fc45b1b04963736254dc7ed582047313b8075a"
required_files = [
    "checkpoint_identity.json",
    "command.txt",
    "cuda_view_ensure.json",
    "cuda_view_verify.json",
    "dataset_identity.json",
    "environment.json",
    "hedge_counters.json",
    "keepalive_before.txt",
    "keepalive_identity_before.json",
    "preflight.json",
    "requests.jsonl",
    "resolved_config.json",
    "source_identity.json",
]
pause_or_server_files = [
    "cuda_contexts_after_pause.txt",
    "gpu_after_ready.csv",
    "gpu_after_request.csv",
    "gpu_samples.csv",
    "keepalive_pause.txt",
    "process_identity.json",
    "readiness_checks.log",
    "sampler.pid",
    "sampler.start_ticks",
    "server.log",
    "server.pid",
    "server.start_ticks",
    "smoke.complete",
    "startup.json",
]


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def proc_identity(pid: int) -> dict:
    path = pathlib.Path("/proc") / str(pid)
    raw = (path / "cmdline").read_bytes()
    argv = [
        part.decode(errors="replace")
        for part in raw.split(b"\0")
        if part
    ]
    stat = (path / "stat").read_text()
    fields = stat[stat.rfind(")") + 2 :].split()
    return {
        "pid": pid,
        "ppid": int(fields[1]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
        "argv": argv,
    }


missing = [name for name in required_files if not (scratch / name).is_file()]
preflight = read_json(scratch / "preflight.json") if not missing else {}
resolved = read_json(scratch / "resolved_config.json") if not missing else {}
source_identity = read_json(scratch / "source_identity.json") if not missing else {}
before = (
    read_json(scratch / "keepalive_identity_before.json")
    if not missing
    else {}
)
current = read_json(keepalive_state / "process_identity.json")
gate = read_json(keepalive_state / "keepalive_gate.json")
supervisor = proc_identity(int(current["pid"]))

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
    index, uuid, name, utilization, memory = (
        item.strip() for item in row
    )
    gpus.append(
        {
            "index": int(index),
            "uuid": uuid,
            "name": name,
            "utilization_percent": int(utilization),
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
    ["git", "-C", str(source), "rev-parse", "HEAD"],
    text=True,
).strip()
source_tree = subprocess.check_output(
    ["git", "-C", str(source), "rev-parse", "HEAD^{tree}"],
    text=True,
).strip()
source_status = subprocess.check_output(
    ["git", "-C", str(source), "status", "--porcelain"],
    text=True,
)
present_side_effects = [
    name for name in pause_or_server_files if (scratch / name).exists()
]
same_keepalive = all(
    before.get(key) == current.get(key)
    for key in (
        "worker_id",
        "hostname",
        "pid",
        "pgid",
        "sid",
        "argv",
        "physical_gpus",
    )
)
compute_consistent_with_keepalive = (
    len(compute) == 8
    and {row["gpu_uuid"] for row in compute}
    == {gpu["uuid"] for gpu in gpus}
    and all(0 < row["used_gpu_memory_mib"] < 4096 for row in compute)
)
preflight_body_pass = (
    not missing
    and preflight.get("status") == "PASS"
    and preflight.get("source_sha") == expected_source
    and resolved.get("phase") == "D4-C"
    and resolved.get("mode") == "dflash_hedge_b0"
    and source_identity.get("head") == expected_source
)
keepalive_pass = (
    same_keepalive
    and supervisor["pgid"] == current["pgid"] == current["pid"]
    and supervisor["sid"] == current["sid"] == current["pid"]
    and supervisor["argv"] == current["argv"]
    and gate.get("healthy") is True
    and not (keepalive_state / "paused").exists()
    and compute_consistent_with_keepalive
    and len(gpus) == 8
    and [gpu["index"] for gpu in gpus] == list(range(8))
    and all(gpu["name"] == "NVIDIA H20" for gpu in gpus)
)
zero_gpu_side_effects = (
    not present_side_effects
    and not hdfs_run.exists()
    and port_free
    and source_head == expected_source
    and source_tree == expected_tree
    and source_status == ""
    and keepalive_pass
)
document = {
    "schema_version": 1,
    "phase": "D4-C",
    "attempt_id": attempt_id,
    "captured_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "status": (
        "PASS" if preflight_body_pass and zero_gpu_side_effects else "FAIL"
    ),
    "preflight_body_pass": preflight_body_pass,
    "original_wrapper_stdout_complete": False,
    "original_wrapper_returncode_recoverable": False,
    "missing_preflight_files": missing,
    "preflight": preflight,
    "resolved_mode": resolved.get("mode"),
    "present_pause_or_server_files": present_side_effects,
    "zero_gpu_side_effects": zero_gpu_side_effects,
    "hdfs_run_exists": hdfs_run.exists(),
    "port_free": port_free,
    "source": {
        "head": source_head,
        "tree": source_tree,
        "clean": source_status == "",
    },
    "keepalive": {
        "same_as_preflight": same_keepalive,
        "paused_marker_exists": (keepalive_state / "paused").exists(),
        "gate": gate,
        "supervisor": supervisor,
        "compute_applications": compute,
        "compute_consistent_with_keepalive": compute_consistent_with_keepalive,
    },
    "gpus": gpus,
}
output.write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(document, indent=2, sort_keys=True))
raise SystemExit(0 if document["status"] == "PASS" else 1)
PY
