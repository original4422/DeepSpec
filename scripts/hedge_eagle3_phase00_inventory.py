#!/usr/bin/env python3
"""Collect Phase 00 worker evidence without signalling or creating GPU load."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import shlex
import subprocess
from typing import Any, Sequence


EXPECTED_WORKER = "4099544"
EXPECTED_GPUS = 8


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_proc_cmdline(pid: int) -> list[str] | None:
    try:
        payload = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None
    return [
        part.decode("utf-8", errors="surrogateescape")
        for part in payload.rstrip(b"\0").split(b"\0")
        if part
    ]


def read_start_ticks(pid: int) -> int | None:
    try:
        payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None
    close_paren = payload.rfind(")")
    if close_paren < 0:
        return None
    fields_from_state = payload[close_paren + 2 :].split()
    try:
        return int(fields_from_state[19])
    except (IndexError, ValueError):
        return None


def process_record(pid: int) -> dict[str, Any]:
    command_line = read_proc_cmdline(pid)
    record: dict[str, Any] = {
        "pid": pid,
        "command_line": command_line,
        "command_display": (
            shlex.join(command_line) if command_line is not None else None
        ),
        "start_ticks": read_start_ticks(pid),
    }
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        uid_line = next(
            line for line in status.splitlines() if line.startswith("Uid:")
        )
        uid = int(uid_line.split()[1])
        record["uid"] = uid
        record["user"] = pwd.getpwuid(uid).pw_name
    except (
        FileNotFoundError,
        PermissionError,
        ProcessLookupError,
        StopIteration,
        ValueError,
        KeyError,
    ):
        record["uid"] = None
        record["user"] = None
    try:
        record["ppid"] = int(
            Path(f"/proc/{pid}/stat")
            .read_text(encoding="utf-8")
            .split(")", maxsplit=1)[1]
            .split()[1]
        )
        record["pgid"] = os.getpgid(pid)
        record["sid"] = os.getsid(pid)
    except (
        FileNotFoundError,
        PermissionError,
        ProcessLookupError,
        IndexError,
        ValueError,
    ):
        record["ppid"] = None
        record["pgid"] = None
        record["sid"] = None
    try:
        record["executable"] = os.readlink(f"/proc/{pid}/exe")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        record["executable"] = None
    try:
        record["cgroups"] = Path(f"/proc/{pid}/cgroup").read_text(
            encoding="utf-8"
        ).splitlines()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        record["cgroups"] = None
    return record


class Collector:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.raw_dir = output_dir / "raw"
        self.raw_dir.mkdir()
        self.commands: list[dict[str, Any]] = []

    def run(
        self,
        name: str,
        command: Sequence[str],
        *,
        required: bool,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            tuple(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        (self.raw_dir / f"{name}.stdout.txt").write_text(
            completed.stdout,
            encoding="utf-8",
        )
        (self.raw_dir / f"{name}.stderr.txt").write_text(
            completed.stderr,
            encoding="utf-8",
        )
        self.commands.append(
            {
                "name": name,
                "command": list(command),
                "returncode": completed.returncode,
                "stdout_path": str(
                    self.raw_dir / f"{name}.stdout.txt"
                ),
                "stderr_path": str(
                    self.raw_dir / f"{name}.stderr.txt"
                ),
            }
        )
        if required and completed.returncode != 0:
            raise RuntimeError(
                f"required command failed: {name}: "
                f"{completed.stderr.strip()}"
            )
        return completed


def parse_gpu_rows(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(payload.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 7:
            raise ValueError(f"unexpected GPU row: {fields!r}")
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
    return rows


def parse_compute_rows(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(payload.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 4:
            raise ValueError(f"unexpected compute row: {fields!r}")
        rows.append(
            {
                "gpu_uuid": fields[0].strip(),
                "pid": int(fields[1].strip()),
                "process_name": fields[2].strip(),
                "used_gpu_memory_mib": (
                    None
                    if fields[3].strip() in {"N/A", "[N/A]"}
                    else int(fields[3].strip())
                ),
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.worker_id != EXPECTED_WORKER:
        raise ValueError(f"unassigned worker: {args.worker_id}")
    output_dir = args.output_dir.resolve()
    if any(output_dir.iterdir()):
        raise ValueError(f"output directory is not empty: {output_dir}")

    collected_at = utc_now()
    collector = Collector(output_dir)
    hostname = collector.run(
        "hostname", ("hostname",), required=True
    ).stdout.strip()
    collector.run("uname", ("uname", "-a"), required=True)
    collector.run("identity", ("id",), required=True)
    collector.run("nvidia_smi_full", ("nvidia-smi",), required=True)
    collector.run("nvidia_smi_list", ("nvidia-smi", "-L"), required=True)
    gpu_query = collector.run(
        "gpu_inventory",
        (
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,compute_cap,"
            "driver_version,pci.bus_id",
            "--format=csv,noheader,nounits",
        ),
        required=True,
    )
    topology = collector.run(
        "gpu_topology", ("nvidia-smi", "topo", "-m"), required=True
    )
    compute_query = collector.run(
        "compute_apps",
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,"
            "used_gpu_memory",
            "--format=csv,noheader,nounits",
        ),
        required=True,
    )
    collector.run(
        "all_processes",
        (
            "ps",
            "-eww",
            "-o",
            "user:32,uid,pid,ppid,pgid,sid,lstart,etimes,stat,args",
            "--sort=pid",
        ),
        required=True,
    )
    capacities: dict[str, dict[str, Any]] = {}
    for name, path in (
        ("worker_tmp", "/tmp"),
        ("hdfs", "/mnt/hdfs/pengzegang/DeepSpec"),
        (
            "shared_worktree",
            "/mlx_devbox/users/pengzegang/playground/github/"
            "DeepSpec-hedge-v4-eagle3",
        ),
    ):
        result = collector.run(
            f"capacity_{name}",
            (
                "df",
                "-B1",
                "--output=source,size,used,avail,pcent,target",
                path,
            ),
            required=False,
        )
        capacities[name] = {
            "path": path,
            "returncode": result.returncode,
            "output": result.stdout,
            "error": result.stderr,
        }

    gpus = parse_gpu_rows(gpu_query.stdout)
    if [gpu["index"] for gpu in gpus] != list(range(EXPECTED_GPUS)):
        raise RuntimeError("worker does not expose exact physical GPU 0..7")
    compute_rows = parse_compute_rows(compute_query.stdout)
    uuid_to_index = {gpu["uuid"]: gpu["index"] for gpu in gpus}
    compute_by_pid: dict[int, list[dict[str, Any]]] = {}
    for row in compute_rows:
        row["gpu_index"] = uuid_to_index.get(row["gpu_uuid"])
        compute_by_pid.setdefault(row["pid"], []).append(row)

    keepalive_pids: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        command_line = read_proc_cmdline(pid)
        if command_line is None:
            continue
        folded = "\0".join(command_line).lower()
        if "keepalive" in folded:
            keepalive_pids.add(pid)

    all_relevant_pids = sorted(set(compute_by_pid) | keepalive_pids)
    processes: list[dict[str, Any]] = []
    for pid in all_relevant_pids:
        record = process_record(pid)
        record["gpu_contexts"] = compute_by_pid.get(pid, [])
        folded = (record.get("command_display") or "").lower()
        if "keepalive" in folded:
            record["classification"] = "known_keepalive"
            record["classification_evidence"] = (
                "full command line contains keepalive"
            )
        else:
            record["classification"] = "leave_untouched"
            record["classification_evidence"] = (
                "existing compute PID has no verified Eagle3 owner marker"
            )
        record["disposition"] = "leave_natural"
        record["signal_sent"] = False
        processes.append(record)

    worker_inventory = {
        "schema_version": 1,
        "worker_id": args.worker_id,
        "collected_at": collected_at,
        "hostname": hostname,
        "expected_gpu_count": EXPECTED_GPUS,
        "observed_gpu_count": len(gpus),
        "exact_gpu_count": len(gpus) == EXPECTED_GPUS,
        "all_h20": all("H20" in str(gpu["model"]) for gpu in gpus),
        "gpus": gpus,
        "topology_raw_path": str(
            collector.raw_dir / "gpu_topology.stdout.txt"
        ),
        "compute_context_count": len(compute_rows),
        "compute_contexts": compute_rows,
        "capacities": capacities,
        "signals_sent": [],
        "raw_command_manifest": str(output_dir / "raw_commands.json"),
    }
    existing_processes = {
        "schema_version": 1,
        "worker_id": args.worker_id,
        "hostname": hostname,
        "collected_at": collected_at,
        "policy": (
            "No existing process is Eagle3-owned during Phase 00; "
            "all observed processes are left to exit naturally."
        ),
        "processes": processes,
        "compute_pid_count": len(compute_by_pid),
        "keepalive_candidate_pid_count": len(keepalive_pids),
        "signal_sent": False,
        "signal_actions": [],
    }
    write_json(output_dir / "worker_inventory.json", worker_inventory)
    write_json(output_dir / "existing_processes.json", existing_processes)
    write_json(output_dir / "raw_commands.json", collector.commands)
    print(
        json.dumps(
            {
                "status": "PASS",
                "worker_id": args.worker_id,
                "hostname": hostname,
                "gpu_count": len(gpus),
                "compute_pid_count": len(compute_by_pid),
                "keepalive_candidate_pid_count": len(keepalive_pids),
                "output_dir": str(output_dir),
                "signal_sent": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
