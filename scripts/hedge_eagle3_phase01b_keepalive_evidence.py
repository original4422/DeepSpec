#!/usr/bin/env python3
"""Fail-closed evidence collection for the Eagle3 operational keepalive."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
from typing import Any, Sequence


EXPECTED_WORKER = "4099544"
EXPECTED_UUIDS = (
    "GPU-ea15ff88-dadd-ba7b-179d-484c1f152e63",
    "GPU-eef6edd3-6d93-5640-9e99-3b2c01987c9f",
    "GPU-357ebd70-0a3c-7397-55b2-2ff509736053",
    "GPU-3123de5a-168b-af3d-9f36-57603da3b11b",
    "GPU-eb1b03fe-54ee-0844-0b58-b4958a5a7cc8",
    "GPU-09e26802-d40f-473a-73bd-5220fd48c6f5",
    "GPU-23fcb1c0-804b-2487-0fb3-d7d8e558ca20",
    "GPU-e387b240-1c16-7bed-8291-66a12ba97f06",
)
EXPECTED_PYTHON = Path(
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
)
EXPECTED_LOAD_SCRIPT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3/scripts/keepalive_load.py"
)
STATE_DIR = Path("/home/tiger/.deepspec-hedge-v4-eagle3/keepalive")
SITE_PACKAGES = (
    EXPECTED_PYTHON.parent.parent
    / "lib/python3.11/site-packages"
)
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: Sequence[str]) -> str:
    completed = subprocess.run(
        tuple(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): "
            f"{shlex.join(command)}: {completed.stderr.strip()}"
        )
    return completed.stdout


def gpu_inventory() -> list[dict[str, Any]]:
    payload = run(
        (
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,compute_cap,"
            "driver_version,pci.bus_id",
            "--format=csv,noheader,nounits",
        )
    )
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(payload.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 7:
            raise RuntimeError(f"unexpected GPU row: {fields!r}")
        rows.append(
            {
                "index": int(fields[0].strip()),
                "uuid": fields[1].strip(),
                "model": fields[2].strip(),
                "memory_total_mib": int(fields[3].strip()),
                "compute_capability": fields[4].strip(),
                "driver_version": fields[5].strip(),
                "pci_bus_id": fields[6].strip(),
            }
        )
    if [row["index"] for row in rows] != list(range(8)):
        raise RuntimeError("GPU inventory is not exactly physical indices 0..7")
    if tuple(row["uuid"] for row in rows) != EXPECTED_UUIDS:
        raise RuntimeError("GPU UUID mapping differs from Phase 00 assignment")
    if not all(row["model"] == "NVIDIA H20" for row in rows):
        raise RuntimeError("assigned worker is not exact 8x NVIDIA H20")
    return rows


def compute_contexts() -> list[dict[str, Any]]:
    payload = run(
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,"
            "used_gpu_memory",
            "--format=csv,noheader,nounits",
        )
    )
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(payload.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 4:
            raise RuntimeError(f"unexpected compute row: {fields!r}")
        memory = fields[3].strip()
        rows.append(
            {
                "gpu_uuid": fields[0].strip(),
                "pid": int(fields[1].strip()),
                "process_name": fields[2].strip(),
                "used_gpu_memory_mib": (
                    None if memory in {"N/A", "[N/A]"} else int(memory)
                ),
            }
        )
    return rows


def proc_stat(pid: int) -> tuple[int, int]:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close_paren = payload.rfind(")")
    if close_paren < 0:
        raise RuntimeError(f"malformed /proc/{pid}/stat")
    fields = payload[close_paren + 2 :].split()
    return int(fields[1]), int(fields[19])


def namespace_pids(pid: int) -> list[int]:
    status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    for line in status.splitlines():
        if line.startswith("NSpid:"):
            values = [int(value) for value in line.split()[1:]]
            if not values:
                break
            return values
    raise RuntimeError(f"/proc/{pid}/status has no NSpid mapping")


def command_line(pid: int) -> list[str]:
    payload = Path(f"/proc/{pid}/cmdline").read_bytes()
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in payload.rstrip(b"\0").split(b"\0")
        if value
    ]


def selected_environment(pid: int) -> dict[str, str]:
    payload = Path(f"/proc/{pid}/environ").read_bytes()
    environment: dict[str, str] = {}
    selected = {"CUDA_VISIBLE_DEVICES", "LD_LIBRARY_PATH"}
    for raw_value in payload.rstrip(b"\0").split(b"\0"):
        if not raw_value or b"=" not in raw_value:
            continue
        raw_name, raw_content = raw_value.split(b"=", maxsplit=1)
        name = raw_name.decode("utf-8", errors="surrogateescape")
        if name in selected:
            environment[name] = raw_content.decode(
                "utf-8",
                errors="surrogateescape",
            )
    return environment


def expected_ld_library_path() -> str:
    lane_libraries = sorted(
        path
        for path in (SITE_PACKAGES / "nvidia").glob("*/lib")
        if path.is_dir()
    )
    if not lane_libraries:
        raise RuntimeError("no lane-local NVIDIA library directories found")
    return ":".join(
        [
            str(COMPAT_ROOT),
            *(str(path) for path in lane_libraries),
            "/usr/local/cuda/lib64",
        ]
    )


def process_record(pid: int) -> dict[str, Any]:
    ppid, start_ticks = proc_stat(pid)
    argv = command_line(pid)
    return {
        "pid": pid,
        "ppid": ppid,
        "pgid": os.getpgid(pid),
        "sid": os.getsid(pid),
        "start_ticks": start_ticks,
        "namespace_pids": namespace_pids(pid),
        "pid_namespace": os.readlink(f"/proc/{pid}/ns/pid"),
        "executable": os.path.realpath(f"/proc/{pid}/exe"),
        "command_line": argv,
        "command_display": shlex.join(argv),
        "selected_environment": selected_environment(pid),
    }


def is_descendant(pid: int, ancestor: int) -> bool:
    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        try:
            current = proc_stat(current)[0]
        except (FileNotFoundError, ProcessLookupError):
            return False
    return False


def ready_worker_processes(
    pid_file: Path,
    owner_pid: int,
) -> tuple[Path, dict[int, dict[str, Any]]]:
    log_path = pid_file.with_suffix(".log")
    candidates: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("event") == "all_gpus_ready"
            and value.get("expected_gpus") == 8
            and value.get("matrix_size") == 8192
        ):
            candidates.append(value)
    if not candidates:
        raise RuntimeError("keepalive log has no exact-eight readiness event")
    for candidate in reversed(candidates):
        workers = candidate.get("workers")
        if not isinstance(workers, list) or len(workers) != 8:
            continue
        records: dict[int, dict[str, Any]] = {}
        try:
            for worker in workers:
                index = int(worker["gpu_index"])
                pid = int(worker["pid"])
                if worker.get("ready") is not True:
                    raise RuntimeError("worker readiness flag differs")
                if not is_descendant(pid, owner_pid):
                    raise RuntimeError("ready worker is not owner descendant")
                records[index] = process_record(pid)
        except (FileNotFoundError, ProcessLookupError, RuntimeError):
            continue
        if set(records) == set(range(8)):
            return log_path, records
    raise RuntimeError("no live readiness event maps to owned descendants")


def device_users(devices: Sequence[str]) -> dict[str, list[int]]:
    records: dict[str, list[int]] = {}
    for device in devices:
        completed = subprocess.run(
            ("fuser", device),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"cannot identify device users for {device}: "
                f"{completed.stderr.strip()}"
            )
        try:
            records[device] = sorted(
                {int(value) for value in completed.stdout.split()}
            )
        except ValueError as error:
            raise RuntimeError(
                f"unexpected fuser output for {device}: {completed.stdout!r}"
            ) from error
    return records


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def preflight(output: Path) -> None:
    gpus = gpu_inventory()
    contexts = compute_contexts()
    if contexts:
        raise RuntimeError(
            "refusing keepalive start while compute contexts exist: "
            f"{contexts!r}"
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "status": "PASS",
            "checked_at": utc_now(),
            "worker_id": EXPECTED_WORKER,
            "hostname": platform.node(),
            "gpus": gpus,
            "compute_contexts": contexts,
            "compute_context_count": 0,
            "signal_sent": False,
        },
    )


def parse_health_report(status_stdout: str) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for line in status_stdout.splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "per_gpu" in value:
            reports.append(value)
    if len(reports) != 1:
        raise RuntimeError("status output does not contain one health report")
    report = reports[0]
    if report.get("healthy") is not True:
        raise RuntimeError("keepalive health report is not healthy")
    if report.get("sample_count") != 10:
        raise RuntimeError("keepalive gate is not exactly 10 samples")
    if report.get("expected_gpus") != 8:
        raise RuntimeError("keepalive gate is not exact-eight-GPU")
    per_gpu = report.get("per_gpu")
    if not isinstance(per_gpu, dict) or set(per_gpu) != {
        str(index) for index in range(8)
    }:
        raise RuntimeError("health report does not cover logical GPU 0..7")
    for index in range(8):
        record = per_gpu[str(index)]
        if record.get("sample_count") != 10:
            raise RuntimeError(f"GPU {index} does not have 10 samples")
        if float(record.get("mean_utilization", -1)) < 40.0:
            raise RuntimeError(f"GPU {index} mean utilization is below 40%")
    return report


def exactly_one_pid_file() -> Path:
    candidates = sorted(STATE_DIR.glob("*.pid"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one Eagle3 keepalive PID file: {candidates!r}"
        )
    return candidates[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite marker: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    write_json(temporary, value)
    os.replace(temporary, path)


def finalize(output_dir: Path, marker_path: Path) -> None:
    status_path = output_dir / "keepalive_status.stdout.txt"
    preflight_path = output_dir / "preflight.json"
    health = parse_health_report(status_path.read_text(encoding="utf-8"))
    preflight_value = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight_value.get("compute_context_count") != 0:
        raise RuntimeError("preflight did not prove empty compute contexts")

    pid_file = exactly_one_pid_file()
    owner_pid = int(pid_file.read_text(encoding="utf-8").strip())
    owner = process_record(owner_pid)
    expected_command = [
        str(EXPECTED_PYTHON),
        str(EXPECTED_LOAD_SCRIPT),
        "load",
        "--expected-gpus",
        "8",
        "--matrix-size",
        "8192",
    ]
    if owner["command_line"] != expected_command:
        raise RuntimeError("keepalive owner command line differs from contract")
    if owner["executable"] != str(EXPECTED_PYTHON.resolve()):
        raise RuntimeError("keepalive owner executable differs from lane venv")
    if owner["pgid"] != owner_pid or owner["sid"] != owner_pid:
        raise RuntimeError("keepalive owner is not its own PGID/SID leader")
    if owner["selected_environment"].get("CUDA_VISIBLE_DEVICES") != (
        "0,1,2,3,4,5,6,7"
    ):
        raise RuntimeError("keepalive owner has incorrect CUDA visibility")
    expected_library_path = expected_ld_library_path()
    if owner["selected_environment"].get("LD_LIBRARY_PATH") != (
        expected_library_path
    ):
        raise RuntimeError("keepalive owner has incorrect library precedence")

    gpus = gpu_inventory()
    contexts = compute_contexts()
    if len(contexts) != 8:
        raise RuntimeError("keepalive does not have exactly eight contexts")
    if {row["gpu_uuid"] for row in contexts} != set(EXPECTED_UUIDS):
        raise RuntimeError("keepalive contexts do not cover all assigned GPUs")
    if len({int(row["pid"]) for row in contexts}) != 8:
        raise RuntimeError("keepalive contexts do not have eight host PIDs")
    log_path, ready_processes = ready_worker_processes(pid_file, owner_pid)
    expected_device_users = {owner_pid} | {
        int(process["pid"]) for process in ready_processes.values()
    }
    devices = [f"/dev/nvidia{index}" for index in range(8)]
    observed_device_users = device_users(devices)
    for device, users in observed_device_users.items():
        if set(users) != expected_device_users:
            raise RuntimeError(
                f"{device} users differ from owned keepalive tree: {users!r}"
            )
    context_by_uuid = {row["gpu_uuid"]: row for row in contexts}
    context_pid_mappings: list[dict[str, Any]] = []
    for index, uuid in enumerate(EXPECTED_UUIDS):
        context = context_by_uuid[uuid]
        process = ready_processes[index]
        context_pid_mappings.append(
            {
                "gpu_index": index,
                "gpu_uuid": uuid,
                "nvidia_smi_host_pid": int(context["pid"]),
                "ready_worker_namespace_pid": int(process["pid"]),
                "mapping_basis": (
                    "same exact physical GPU index in the readiness event "
                    "and nvidia-smi; host PIDs are outside the container "
                    "PID namespace"
                ),
            }
        )
    for process in ready_processes.values():
        if process["selected_environment"].get("LD_LIBRARY_PATH") != (
            expected_library_path
        ):
            raise RuntimeError(
                "keepalive context process has incorrect library precedence"
            )
        if process["selected_environment"].get(
            "CUDA_VISIBLE_DEVICES"
        ) != "0,1,2,3,4,5,6,7":
            raise RuntimeError(
                "keepalive context process has incorrect CUDA visibility"
            )

    created_at = utc_now()
    evidence_path = output_dir / "keepalive_active.json"
    payload = {
        "schema_version": 1,
        "status": "active",
        "kind": "operational_keepalive",
        "session": "hedge-v4-eagle3",
        "worker_id": EXPECTED_WORKER,
        "hostname": platform.node(),
        "created_at": created_at,
        "cuda_visible_devices": "0,1,2,3,4,5,6,7",
        "expected_gpu_count": 8,
        "gpu_uuids": list(EXPECTED_UUIDS),
        "gpus": gpus,
        "owner_pid": owner_pid,
        "owner_pgid": owner["pgid"],
        "owner_sid": owner["sid"],
        "owner_start_ticks": owner["start_ticks"],
        "owner_command_line": owner["command_line"],
        "owner_command_display": owner["command_display"],
        "owner_executable": owner["executable"],
        "owner_selected_environment": owner["selected_environment"],
        "expected_ld_library_path": expected_library_path,
        "pid_file": str(pid_file),
        "state_dir": str(STATE_DIR),
        "ready_worker_processes": [
            {
                "gpu_index": index,
                **ready_processes[index],
            }
            for index in range(8)
        ],
        "context_pid_mappings": context_pid_mappings,
        "load_log_path": str(log_path),
        "load_log_sha256": sha256(log_path),
        "device_users": observed_device_users,
        "device_user_ownership_basis": (
            "preflight had zero contexts; all eight ready workers are live "
            "owner descendants; every physical GPU device is used only by "
            "the registered owner and those eight descendants"
        ),
        "compute_contexts": contexts,
        "health_gate": health,
        "preflight_path": str(preflight_path),
        "preflight_sha256": sha256(preflight_path),
        "status_stdout_path": str(status_path),
        "status_stdout_sha256": sha256(status_path),
        "evidence_path": str(evidence_path),
        "coordination_marker": str(marker_path),
        "signal_sent": False,
        "model_experiment": False,
    }
    write_json(evidence_path, payload)
    marker_payload = {
        **payload,
        "evidence_sha256": sha256(evidence_path),
    }
    atomic_write_json(marker_path, marker_payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--output", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser.add_argument("--marker", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        preflight(args.output)
    else:
        finalize(args.output_dir, args.marker)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"keepalive evidence error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
