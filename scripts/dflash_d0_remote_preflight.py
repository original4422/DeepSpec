#!/usr/bin/env python3
"""Collect the read-only DFlash D0 worker inventory as one JSON document."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import pathlib
import pwd
import socket
import subprocess
from typing import Any, Sequence


EXPECTED_GPU_COUNT = 8
EXPECTED_GPU_NAME = "NVIDIA H20"
API_PORT = 31457
CAPACITY_PATHS = (
    "/",
    "/tmp",
    "/mnt/hdfs/pengzegang/DeepSpec",
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: Sequence[str],
    *,
    timeout: float = 20.0,
    check: bool = False,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result = {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if check and completed.returncode != 0:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def parse_csv(payload: str) -> list[list[str]]:
    return [
        [field.strip() for field in row]
        for row in csv.reader(io.StringIO(payload))
        if any(field.strip() for field in row)
    ]


def gpu_inventory() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fields = (
        "index",
        "uuid",
        "name",
        "memory.total",
        "memory.used",
        "utilization.gpu",
        "compute_cap",
        "driver_version",
    )
    result = run(
        (
            "nvidia-smi",
            f"--query-gpu={','.join(fields)}",
            "--format=csv,noheader,nounits",
        ),
        check=True,
    )
    rows = parse_csv(result["stdout"])
    inventory: list[dict[str, Any]] = []
    for row in rows:
        if len(row) != len(fields):
            raise RuntimeError(f"unexpected GPU row: {row!r}")
        inventory.append(
            {
                "index": int(row[0]),
                "uuid": row[1],
                "name": row[2],
                "memory_total_mib": int(row[3]),
                "memory_used_mib": int(row[4]),
                "utilization_gpu_percent": int(row[5]),
                "compute_capability": row[6],
                "driver_version": row[7],
            }
        )
    expected_indices = list(range(EXPECTED_GPU_COUNT))
    actual_indices = [gpu["index"] for gpu in inventory]
    identity_ok = (
        actual_indices == expected_indices
        and all(gpu["name"] == EXPECTED_GPU_NAME for gpu in inventory)
    )
    return inventory, {
        "expected_count": EXPECTED_GPU_COUNT,
        "expected_indices": expected_indices,
        "expected_name": EXPECTED_GPU_NAME,
        "identity_ok": identity_ok,
    }


def proc_record(pid: int) -> dict[str, Any]:
    proc = pathlib.Path("/proc") / str(pid)
    record: dict[str, Any] = {"pid": pid}
    try:
        stat = proc.stat()
        record["uid"] = stat.st_uid
        record["user"] = pwd.getpwuid(stat.st_uid).pw_name
    except (FileNotFoundError, KeyError, PermissionError):
        record["user"] = None
    for field, target in (("exe", "exe"), ("cwd", "cwd")):
        try:
            record[field] = os.readlink(proc / target)
        except (FileNotFoundError, PermissionError):
            record[field] = None
    try:
        raw = (proc / "cmdline").read_bytes()
        record["argv"] = [
            item.decode(errors="replace") for item in raw.split(b"\0") if item
        ]
    except (FileNotFoundError, PermissionError):
        record["argv"] = []
    ps = run(
        (
            "ps",
            "-o",
            "pid=,ppid=,pgid=,sid=,lstart=,etime=,stat=",
            "-p",
            str(pid),
        ),
        timeout=5.0,
    )
    record["ps_identity"] = ps["stdout"].strip()
    return record


def compute_processes() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = run(
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ),
        check=True,
    )
    rows = parse_csv(result["stdout"])
    applications: list[dict[str, Any]] = []
    process_details: dict[int, dict[str, Any]] = {}
    for row in rows:
        if len(row) != 4:
            raise RuntimeError(f"unexpected compute-app row: {row!r}")
        pid = int(row[1])
        applications.append(
            {
                "gpu_uuid": row[0],
                "pid": pid,
                "process_name": row[2],
                "used_gpu_memory_mib": (
                    None if row[3] in {"[N/A]", "N/A"} else int(row[3])
                ),
            }
        )
        process_details.setdefault(pid, proc_record(pid))
    return applications, {
        str(pid): record for pid, record in sorted(process_details.items())
    }


def capacity_inventory() -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in CAPACITY_PATHS:
        exists = os.path.exists(path)
        record: dict[str, Any] = {"path": path, "exists": exists}
        if exists:
            df = run(
                (
                    "df",
                    "-B1",
                    "--output=source,fstype,size,used,avail,pcent,target",
                    path,
                ),
                check=True,
            )
            lines = [line.strip() for line in df["stdout"].splitlines() if line]
            record["df_header"] = lines[0] if lines else ""
            record["df_row"] = lines[-1] if lines else ""
        inventory.append(record)
    return inventory


def port_inventory() -> dict[str, Any]:
    result = run(("ss", "-H", "-ltnp"), timeout=10.0)
    matching = [
        line
        for line in result["stdout"].splitlines()
        if f":{API_PORT} " in f"{line} "
        or f":{API_PORT}\n" in f"{line}\n"
    ]
    return {
        "port": API_PORT,
        "query_returncode": result["returncode"],
        "listeners": matching,
        "available": result["returncode"] == 0 and not matching,
        "query_stderr": result["stderr"],
    }


def main() -> int:
    gpus, gpu_expectation = gpu_inventory()
    compute_apps, process_details = compute_processes()
    topology = run(("nvidia-smi", "topo", "-m"), check=True)
    full_smi = run(("nvidia-smi",), check=True)
    uname = run(("uname", "-a"), check=True)
    document = {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "phase": "D0",
        "lane": "dflash",
        "worker_id": "4099543",
        "hostname": socket.gethostname(),
        "gpu_expectation": gpu_expectation,
        "gpus": gpus,
        "compute_applications": compute_apps,
        "compute_process_details": process_details,
        "legacy_gpu_task_present": bool(compute_apps),
        "topology": topology["stdout"],
        "nvidia_smi": full_smi["stdout"],
        "uname": uname["stdout"].strip(),
        "capacity": capacity_inventory(),
        "api_port": port_inventory(),
        "keepalive_runtime": {
            "venv": "/home/tiger/venvs/deepspec-hedge-dflash",
            "python_exists": os.path.isfile(
                "/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
            ),
            "state_dir": "/tmp/deepspec-hedge-dflash/keepalive",
            "state_dir_exists": os.path.isdir(
                "/tmp/deepspec-hedge-dflash/keepalive"
            ),
        },
    }
    document["safe_to_start_keepalive"] = (
        gpu_expectation["identity_ok"]
        and not compute_apps
        and document["api_port"]["available"]
    )
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0 if gpu_expectation["identity_ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "captured_at_utc": utc_now(),
                    "phase": "D0",
                    "lane": "dflash",
                    "worker_id": "4099543",
                    "fatal_error": repr(error),
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from error
