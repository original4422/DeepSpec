#!/usr/bin/env python3
"""Read-only process/GPU snapshot for a registered D3 server attempt."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ATTEMPT_RE = re.compile(
    r"^dflash-d3-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$"
)
SCRATCH_ROOT = Path("/tmp/deepspec-hedge-dflash/runs")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_stat(pid: int) -> dict:
    raw = Path(f"/proc/{pid}/stat").read_text()
    close = raw.rfind(")")
    name = raw[raw.find("(") + 1 : close]
    fields = raw[close + 2 :].split()
    return {
        "pid": pid,
        "name": name,
        "state": fields[0],
        "ppid": int(fields[1]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
        "utime_ticks": int(fields[11]),
        "stime_ticks": int(fields[12]),
        "start_ticks": int(fields[19]),
    }


def read_key_values(path: Path, separator: str = ":") -> dict:
    result = {}
    if not path.is_file():
        return result
    for line in path.read_text(errors="replace").splitlines():
        if separator not in line:
            continue
        key, value = line.split(separator, 1)
        result[key.strip()] = value.strip()
    return result


def read_process(pid: int, expected_pgid: int) -> dict | None:
    try:
        stat = parse_stat(pid)
        if stat["pgid"] != expected_pgid:
            return None
        status = read_key_values(Path(f"/proc/{pid}/status"))
        io_values = read_key_values(Path(f"/proc/{pid}/io"))
        cmdline = [
            item.decode(errors="replace")
            for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if item
        ]
        wchan_path = Path(f"/proc/{pid}/wchan")
        stat.update(
            {
                "cmdline": cmdline,
                "wchan": (
                    wchan_path.read_text(errors="replace").strip()
                    if wchan_path.is_file()
                    else None
                ),
                "status": {
                    key: status.get(key)
                    for key in (
                        "Name",
                        "State",
                        "VmRSS",
                        "VmSize",
                        "Threads",
                        "voluntary_ctxt_switches",
                        "nonvoluntary_ctxt_switches",
                    )
                },
                "io": {
                    key: int(io_values[key])
                    for key in (
                        "rchar",
                        "wchar",
                        "syscr",
                        "syscw",
                        "read_bytes",
                        "write_bytes",
                        "cancelled_write_bytes",
                    )
                    if key in io_values
                },
            }
        )
        return stat
    except (FileNotFoundError, ProcessLookupError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    if not ATTEMPT_RE.fullmatch(args.attempt_id):
        raise ValueError(f"invalid attempt id: {args.attempt_id}")
    if not re.fullmatch(r"[a-z0-9_-]+", args.label):
        raise ValueError(f"invalid label: {args.label}")

    scratch = SCRATCH_ROOT / args.attempt_id
    identity = json.loads((scratch / "process_identity.json").read_text())
    leader = int(identity["pid"])
    expected_ticks = int(identity["start_ticks"])
    leader_stat = parse_stat(leader)
    if leader_stat["start_ticks"] != expected_ticks:
        raise RuntimeError("registered server leader start ticks changed")
    if leader_stat["pgid"] != leader or leader_stat["sid"] != leader:
        raise RuntimeError("registered server leader PGID/SID changed")

    ps_text = subprocess.check_output(
        [
            "ps",
            "-eo",
            "pid=,ppid=,pgid=,sid=,stat=,etime=,pcpu=,pmem=,wchan:40=,args=",
        ],
        text=True,
    )
    ps_rows = []
    for line in ps_text.splitlines():
        fields = line.split(None, 9)
        if len(fields) < 10:
            continue
        if int(fields[2]) != leader:
            continue
        ps_rows.append(
            {
                "pid": int(fields[0]),
                "ppid": int(fields[1]),
                "pgid": int(fields[2]),
                "sid": int(fields[3]),
                "stat": fields[4],
                "etime": fields[5],
                "cpu_percent": float(fields[6]),
                "memory_percent": float(fields[7]),
                "wchan": fields[8],
                "args": fields[9],
            }
        )

    processes = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        process = read_process(int(path.name), leader)
        if process is not None:
            processes.append(process)
    processes.sort(key=lambda item: item["pid"])

    gpu_rows = []
    gpu_text = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    for row in csv.reader(io.StringIO(gpu_text)):
        index, uuid, utilization, used, total = (
            item.strip() for item in row
        )
        gpu_rows.append(
            {
                "index": int(index),
                "uuid": uuid,
                "utilization_percent": int(utilization),
                "memory_used_mib": int(used),
                "memory_total_mib": int(total),
            }
        )

    compute_rows = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).splitlines()

    output = scratch / f"stall_probe_{args.label}.json"
    if output.exists():
        raise FileExistsError(output)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": "D3",
                "attempt_id": args.attempt_id,
                "label": args.label,
                "captured_at_utc": utc_now(),
                "clock_ticks_per_second": os.sysconf(
                    os.sysconf_names["SC_CLK_TCK"]
                ),
                "server_identity": identity,
                "ps_process_group": ps_rows,
                "proc_process_group": processes,
                "gpus": gpu_rows,
                "compute_applications": compute_rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
