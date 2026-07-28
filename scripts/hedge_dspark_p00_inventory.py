#!/usr/bin/env python3
"""Collect a read-only P00 inventory for the dedicated DSpark HEDGE lane."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any, Sequence


EXPECTED_WORKER = "4106666"
EXPECTED_GPUS = 8
EXPECTED_GPU_NAME = "NVIDIA H20"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(argv: Sequence[str], timeout: float = 120.0) -> dict[str, Any]:
    started_at = utc_now()
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "argv": list(argv),
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(argv),
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "returncode": None,
            "stdout": getattr(error, "stdout", "") or "",
            "stderr": getattr(error, "stderr", "") or str(error),
            "exception": type(error).__name__,
        }


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_gpu_rows(payload: str) -> list[dict[str, Any]]:
    keys = (
        "index",
        "uuid",
        "name",
        "memory_total_mib",
        "compute_capability",
        "driver_version",
        "pci_bus_id",
    )
    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        values = [value.strip() for value in raw_line.split(",")]
        if len(values) != len(keys):
            raise ValueError(f"unexpected nvidia-smi GPU row: {raw_line!r}")
        row = dict(zip(keys, values, strict=True))
        row["index"] = int(row["index"])
        row["memory_total_mib"] = int(row["memory_total_mib"])
        rows.append(row)
    return rows


def parse_compute_rows(payload: str) -> list[dict[str, Any]]:
    keys = ("gpu_uuid", "host_pid", "process_name", "used_memory_mib")
    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        values = [value.strip() for value in raw_line.split(",")]
        if len(values) != len(keys):
            raise ValueError(
                f"unexpected nvidia-smi compute row: {raw_line!r}"
            )
        row = dict(zip(keys, values, strict=True))
        if row["host_pid"].isdigit():
            row["host_pid"] = int(row["host_pid"])
        if row["used_memory_mib"].isdigit():
            row["used_memory_mib"] = int(row["used_memory_mib"])
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.worker_id != EXPECTED_WORKER:
        raise SystemExit(
            f"refusing worker {args.worker_id}; expected {EXPECTED_WORKER}"
        )

    gpu_query = run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,compute_cap,"
            "driver_version,pci.bus_id",
            "--format=csv,noheader,nounits",
        ]
    )
    compute_query = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus = (
        parse_gpu_rows(gpu_query["stdout"])
        if gpu_query["returncode"] == 0
        else []
    )
    compute_contexts = (
        parse_compute_rows(compute_query["stdout"])
        if compute_query["returncode"] == 0
        else []
    )
    exact_inventory = (
        len(gpus) == EXPECTED_GPUS
        and [gpu["index"] for gpu in gpus] == list(range(EXPECTED_GPUS))
        and all(gpu["name"] == EXPECTED_GPU_NAME for gpu in gpus)
    )

    process_inventory = run(
        [
            "ps",
            "-eo",
            "pid=,ppid=,pgid=,sid=,user=,stat=,etimes=,args=",
            "--sort=pid",
        ]
    )
    payload = {
        "schema_version": 1,
        "authorized_phase": "P00",
        "worker_id": args.worker_id,
        "observed_at_utc": utc_now(),
        "hostname": platform.node(),
        "pid_namespace": os.readlink("/proc/self/ns/pid"),
        "expected_gpu_count": EXPECTED_GPUS,
        "expected_gpu_name": EXPECTED_GPU_NAME,
        "inventory_passed": exact_inventory,
        "gpus": gpus,
        "gpu_query": gpu_query,
        "topology": run(["nvidia-smi", "topo", "-m"]),
        "compute_contexts": compute_contexts,
        "compute_query": compute_query,
        "pmon": run(["nvidia-smi", "pmon", "-c", "1"]),
        "process_inventory": process_inventory,
        "dedicated_keepalive_state": run(
            [
                "find",
                "/home/tiger/.deepspec-hedge-dspark-keepalive",
                "-maxdepth",
                "1",
                "-printf",
                "%f %y %s %TY-%Tm-%TdT%TH:%TM:%TS%Tz\n",
            ]
        ),
    }
    atomic_json(args.artifact_dir / "worker_inventory.json", payload)
    print(
        json.dumps(
            {
                "worker_id": args.worker_id,
                "hostname": payload["hostname"],
                "gpu_count": len(gpus),
                "inventory_passed": exact_inventory,
                "compute_context_count": len(compute_contexts),
                "compute_contexts": compute_contexts,
            },
            sort_keys=True,
        )
    )
    return 0 if exact_inventory else 1


if __name__ == "__main__":
    raise SystemExit(main())
