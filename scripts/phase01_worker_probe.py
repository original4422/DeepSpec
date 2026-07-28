#!/usr/bin/env python3
"""Collect Phase 01 worker evidence without starting the model.

The ``baseline`` and ``aggregate`` commands use only the Python standard
library.  The ``nccl`` command is intended to run under torchrun while the
project keepalive is paused.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import urllib.request
from typing import Any, Sequence


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: Sequence[str],
    *,
    timeout: float = 60.0,
    check: bool = False,
) -> dict[str, Any]:
    started = utc_now()
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        result: dict[str, Any] = {
            "argv": list(command),
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        result = {
            "argv": list(command),
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "returncode": None,
            "stdout": getattr(error, "stdout", "") or "",
            "stderr": getattr(error, "stderr", "") or str(error),
            "exception": type(error).__name__,
        }
    if check and result["returncode"] != 0:
        raise RuntimeError(
            f"command failed: {command!r}: {result['stderr'].strip()}"
        )
    return result


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    path = pathlib.Path("/etc/os-release")
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def parse_gpu_inventory(payload: str) -> list[dict[str, Any]]:
    fields = (
        "index",
        "uuid",
        "name",
        "memory_total_mib",
        "compute_capability",
        "driver_version",
        "pci_bus_id",
    )
    records: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        values = [value.strip() for value in raw_line.split(",")]
        if len(values) != len(fields):
            raise ValueError(f"unexpected nvidia-smi row: {raw_line!r}")
        record = dict(zip(fields, values, strict=True))
        record["index"] = int(record["index"])
        record["memory_total_mib"] = int(record["memory_total_mib"])
        records.append(record)
    return records


def statvfs(path: pathlib.Path) -> dict[str, Any]:
    stats = os.statvfs(path)
    return {
        "path": str(path),
        "block_size": stats.f_frsize,
        "total_bytes": stats.f_blocks * stats.f_frsize,
        "free_bytes": stats.f_bfree * stats.f_frsize,
        "available_bytes": stats.f_bavail * stats.f_frsize,
    }


def command_version(command: str, arguments: Sequence[str]) -> dict[str, Any]:
    resolved = shutil.which(command)
    result: dict[str, Any] = {"name": command, "path": resolved}
    if resolved is None:
        result["available"] = False
        return result
    result["available"] = True
    result["probe"] = run([resolved, *arguments], timeout=30.0)
    return result


def baseline(args: argparse.Namespace) -> int:
    artifact_dir = pathlib.Path(args.artifact_dir)
    query = run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,compute_cap,"
            "driver_version,pci.bus_id",
            "--format=csv,noheader,nounits",
        ],
        check=True,
    )
    gpus = parse_gpu_inventory(query["stdout"])
    expected_inventory = (
        len(gpus) == 4
        and [gpu["index"] for gpu in gpus] == list(range(4))
        and all(gpu["name"] == "NVIDIA H20" for gpu in gpus)
    )

    topology = run(["nvidia-smi", "topo", "-m"], check=True)
    p2p_read = run(["nvidia-smi", "topo", "-p2p", "r"])
    p2p_write = run(["nvidia-smi", "topo", "-p2p", "w"])
    full_smi = run(["nvidia-smi", "-q"], timeout=120.0)
    driver_proc = pathlib.Path("/proc/driver/nvidia/version")

    tools = [
        command_version("python3", ["--version"]),
        command_version("uv", ["--version"]),
        command_version("gcc", ["--version"]),
        command_version("g++", ["--version"]),
        command_version("cmake", ["--version"]),
        command_version("ninja", ["--version"]),
        command_version("rustc", ["--version"]),
        command_version("cargo", ["--version"]),
        command_version("nvcc", ["--version"]),
    ]
    ldconfig = run(["ldconfig", "-p"])
    nccl_lines = [
        line
        for line in ldconfig["stdout"].splitlines()
        if "nccl" in line.lower()
    ]

    compute_contexts = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    payload = {
        "schema_version": 1,
        "authorized_phase": "Phase 01",
        "observed_at_utc": utc_now(),
        "worker_id": args.worker_id,
        "hostname": platform.node(),
        "pid_namespace": os.readlink("/proc/self/ns/pid"),
        "os": {
            "release": parse_os_release(),
            "uname": platform.uname()._asdict(),
        },
        "gpu_count": len(gpus),
        "gpu_inventory_matches_exact_4xh20": expected_inventory,
        "gpus": gpus,
        "nvidia_smi_query": query,
        "nvidia_smi_full": full_smi,
        "nvidia_driver_proc": (
            driver_proc.read_text(encoding="utf-8")
            if driver_proc.is_file()
            else None
        ),
        "topology": topology,
        "p2p_read_capability": p2p_read,
        "p2p_write_capability": p2p_write,
        "compute_contexts_during_keepalive": compute_contexts,
        "nccl_ldconfig_entries": nccl_lines,
        "tools": tools,
        "storage": {
            "worker_tmp": statvfs(pathlib.Path("/tmp")),
            "repo_root": statvfs(pathlib.Path(args.repo_root)),
            "hdfs_root": statvfs(pathlib.Path(args.hdfs_root)),
        },
    }
    write_json(artifact_dir / "worker_inventory.json", payload)
    write_json(
        artifact_dir / "storage_report_worker.json",
        {
            "schema_version": 1,
            "observed_at_utc": payload["observed_at_utc"],
            "worker_id": args.worker_id,
            **payload["storage"],
        },
    )
    if not expected_inventory:
        print(json.dumps(payload, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "worker_id": args.worker_id,
                "hostname": payload["hostname"],
                "gpu_count": len(gpus),
                "gpu_uuids": [gpu["uuid"] for gpu in gpus],
                "inventory_passed": True,
            },
            sort_keys=True,
        )
    )
    return 0


def nccl_probe(args: argparse.Namespace) -> int:
    import torch
    import torch.distributed as dist

    artifact_dir = pathlib.Path(args.artifact_dir)
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    record: dict[str, Any] = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "rank": rank,
        "local_rank": local_rank,
        "world_size": world_size,
        "status": "running",
    }
    return_code = 1
    try:
        if world_size != args.expected_gpus:
            raise RuntimeError(
                f"world_size={world_size}, expected={args.expected_gpus}"
            )
        torch.cuda.set_device(local_rank)
        dist.init_process_group(backend="nccl")
        properties = torch.cuda.get_device_properties(local_rank)
        value = torch.tensor(
            [float(rank + 1)],
            dtype=torch.float32,
            device=f"cuda:{local_rank}",
        )
        dist.all_reduce(value, op=dist.ReduceOp.SUM)
        torch.cuda.synchronize(local_rank)
        expected_sum = world_size * (world_size + 1) / 2
        observed_sum = float(value.item())
        peer_matrix = None
        if rank == 0:
            peer_matrix = [
                [
                    (
                        True
                        if source == target
                        else bool(
                            torch.cuda.can_device_access_peer(source, target)
                        )
                    )
                    for target in range(world_size)
                ]
                for source in range(world_size)
            ]
        record.update(
            {
                "status": "pass" if observed_sum == expected_sum else "fail",
                "torch_version": torch.__version__,
                "torch_cuda_version": torch.version.cuda,
                "nccl_available": bool(torch.cuda.nccl.is_available([])),
                "nccl_version": list(torch.cuda.nccl.version()),
                "device": {
                    "index": local_rank,
                    "name": properties.name,
                    "uuid": (
                        str(properties.uuid)
                        if getattr(properties, "uuid", None) is not None
                        else None
                    ),
                    "total_memory_bytes": properties.total_memory,
                    "compute_capability": [
                        properties.major,
                        properties.minor,
                    ],
                },
                "all_reduce": {
                    "input": float(rank + 1),
                    "expected_sum": expected_sum,
                    "observed_sum": observed_sum,
                    "passed": observed_sum == expected_sum,
                },
                "peer_access_matrix": peer_matrix,
            }
        )
        return_code = 0 if record["status"] == "pass" else 1
    except Exception as error:
        record.update(
            {
                "status": "fail",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    finally:
        if dist.is_initialized():
            dist.destroy_process_group()
        write_json(artifact_dir / f"gpu_probe_rank_{rank}.json", record)
    return return_code


def aggregate(args: argparse.Namespace) -> int:
    artifact_dir = pathlib.Path(args.artifact_dir)
    records = []
    errors: list[str] = []
    for rank in range(args.expected_gpus):
        path = artifact_dir / f"gpu_probe_rank_{rank}.json"
        if not path.is_file():
            errors.append(f"missing {path.name}")
            continue
        records.append(json.loads(path.read_text(encoding="utf-8")))
    if len(records) != args.expected_gpus:
        errors.append(
            f"record_count={len(records)}, expected={args.expected_gpus}"
        )
    for record in records:
        if record.get("status") != "pass":
            errors.append(
                f"rank {record.get('rank')} status={record.get('status')}"
            )
    peer_matrix = records[0].get("peer_access_matrix") if records else None
    if peer_matrix is None or not all(all(row) for row in peer_matrix):
        errors.append("full CUDA peer-access matrix is not true")
    payload = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "status": "pass" if not errors else "fail",
        "expected_gpus": args.expected_gpus,
        "nccl_all_reduce_passed": not any(
            "rank " in error for error in errors
        ),
        "full_peer_access_passed": (
            peer_matrix is not None and all(all(row) for row in peer_matrix)
        ),
        "errors": errors,
        "ranks": records,
    }
    write_json(artifact_dir / "gpu_probe.json", payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if not errors else 1


def process_inventory(args: argparse.Namespace) -> int:
    artifact_dir = pathlib.Path(args.artifact_dir)
    matches: list[dict[str, Any]] = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            arguments = (
                (entry / "cmdline")
                .read_bytes()
                .rstrip(b"\0")
                .split(b"\0")
            )
            decoded = [
                argument.decode("utf-8", errors="replace")
                for argument in arguments
            ]
            joined = " ".join(decoded)
            if not any(
                marker in joined
                for marker in (
                    "phase01_worker_probe.py",
                    "torch.distributed.run",
                    "phase01_remote_preflight.sh",
                )
            ):
                continue
            pid = int(entry.name)
            matches.append(
                {
                    "pid": pid,
                    "pgid": os.getpgid(pid),
                    "sid": os.getsid(pid),
                    "argv": decoded,
                }
            )
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    active_probe_processes = [
        record
        for record in matches
        if (
            "nccl" in record["argv"]
            or "-m" in record["argv"]
            and "torch.distributed.run" in record["argv"]
        )
    ]
    contexts = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    payload = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "worker_id": args.worker_id,
        "matching_processes": matches,
        "active_probe_processes": active_probe_processes,
        "active_probe_process_count": len(active_probe_processes),
        "nvidia_compute_contexts": contexts,
    }
    write_json(
        artifact_dir / "process_inventory_after_incident.json",
        payload,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if not active_probe_processes else 1


def connectivity(args: argparse.Namespace) -> int:
    artifact_dir = pathlib.Path(args.artifact_dir)
    results = []
    for url in (
        "https://github.com",
        "https://huggingface.co",
        "https://www.modelscope.cn",
    ):
        started_at = utc_now()
        try:
            request = urllib.request.Request(
                url,
                method="HEAD",
                headers={
                    "User-Agent": "DeepSpec-Phase01-Worker-Preflight/1"
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                results.append(
                    {
                        "url": url,
                        "started_at_utc": started_at,
                        "finished_at_utc": utc_now(),
                        "reachable": True,
                        "status": response.status,
                        "final_url": response.url,
                    }
                )
        except Exception as error:
            results.append(
                {
                    "url": url,
                    "started_at_utc": started_at,
                    "finished_at_utc": utc_now(),
                    "reachable": False,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
    payload = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "worker_id": args.worker_id,
        "results": results,
        "all_reachable": all(result["reachable"] for result in results),
    }
    write_json(artifact_dir / "worker_connectivity.json", payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["all_reachable"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline_parser = subparsers.add_parser("baseline")
    baseline_parser.add_argument("--artifact-dir", required=True)
    baseline_parser.add_argument("--worker-id", required=True)
    baseline_parser.add_argument("--repo-root", required=True)
    baseline_parser.add_argument("--hdfs-root", required=True)
    baseline_parser.set_defaults(handler=baseline)

    nccl_parser = subparsers.add_parser("nccl")
    nccl_parser.add_argument("--artifact-dir", required=True)
    nccl_parser.add_argument("--expected-gpus", type=int, default=4)
    nccl_parser.set_defaults(handler=nccl_probe)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--artifact-dir", required=True)
    aggregate_parser.add_argument("--expected-gpus", type=int, default=4)
    aggregate_parser.set_defaults(handler=aggregate)

    processes_parser = subparsers.add_parser("processes")
    processes_parser.add_argument("--artifact-dir", required=True)
    processes_parser.add_argument("--worker-id", required=True)
    processes_parser.set_defaults(handler=process_inventory)

    connectivity_parser = subparsers.add_parser("connectivity")
    connectivity_parser.add_argument("--artifact-dir", required=True)
    connectivity_parser.add_argument("--worker-id", required=True)
    connectivity_parser.set_defaults(handler=connectivity)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
