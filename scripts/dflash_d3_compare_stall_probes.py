#!/usr/bin/env python3
"""Compare two read-only D3 process/GPU snapshots."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ATTEMPT_RE = re.compile(
    r"^dflash-d3-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$"
)
LABEL_RE = re.compile(r"^[a-z0-9_-]+$")
SCRATCH_ROOT = Path("/tmp/deepspec-hedge-dflash/runs")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    args = parser.parse_args()
    if not ATTEMPT_RE.fullmatch(args.attempt_id):
        raise ValueError(f"invalid attempt id: {args.attempt_id}")
    if not LABEL_RE.fullmatch(args.first) or not LABEL_RE.fullmatch(args.second):
        raise ValueError("invalid snapshot label")

    scratch = SCRATCH_ROOT / args.attempt_id
    first = json.loads(
        (scratch / f"stall_probe_{args.first}.json").read_text()
    )
    second = json.loads(
        (scratch / f"stall_probe_{args.second}.json").read_text()
    )
    first_processes = {
        int(item["pid"]): item for item in first["proc_process_group"]
    }
    second_processes = {
        int(item["pid"]): item for item in second["proc_process_group"]
    }
    common = sorted(set(first_processes) & set(second_processes))
    deltas = []
    for pid in common:
        before = first_processes[pid]
        after = second_processes[pid]
        io_delta = {
            key: after["io"].get(key, 0) - before["io"].get(key, 0)
            for key in sorted(set(before["io"]) | set(after["io"]))
        }
        voluntary_delta = int(
            after["status"].get("voluntary_ctxt_switches") or 0
        ) - int(before["status"].get("voluntary_ctxt_switches") or 0)
        nonvoluntary_delta = int(
            after["status"].get("nonvoluntary_ctxt_switches") or 0
        ) - int(before["status"].get("nonvoluntary_ctxt_switches") or 0)
        deltas.append(
            {
                "pid": pid,
                "name": after["name"],
                "state_before": before["state"],
                "state_after": after["state"],
                "wchan_before": before["wchan"],
                "wchan_after": after["wchan"],
                "utime_ticks_delta": (
                    after["utime_ticks"] - before["utime_ticks"]
                ),
                "stime_ticks_delta": (
                    after["stime_ticks"] - before["stime_ticks"]
                ),
                "total_cpu_ticks_delta": (
                    after["utime_ticks"]
                    + after["stime_ticks"]
                    - before["utime_ticks"]
                    - before["stime_ticks"]
                ),
                "voluntary_context_switches_delta": voluntary_delta,
                "nonvoluntary_context_switches_delta": nonvoluntary_delta,
                "io_delta": io_delta,
                "cmdline": after["cmdline"],
            }
        )

    interval = (
        parse_time(second["captured_at_utc"])
        - parse_time(first["captured_at_utc"])
    ).total_seconds()
    total_cpu_ticks = sum(
        item["total_cpu_ticks_delta"] for item in deltas
    )
    total_read_bytes = sum(
        item["io_delta"].get("read_bytes", 0) for item in deltas
    )
    total_write_bytes = sum(
        item["io_delta"].get("write_bytes", 0) for item in deltas
    )
    total_context_switches = sum(
        item["voluntary_context_switches_delta"]
        + item["nonvoluntary_context_switches_delta"]
        for item in deltas
    )
    output = scratch / "stall_probe_comparison.json"
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": "D3",
                "attempt_id": args.attempt_id,
                "first_captured_at_utc": first["captured_at_utc"],
                "second_captured_at_utc": second["captured_at_utc"],
                "interval_seconds": interval,
                "process_count_first": len(first_processes),
                "process_count_second": len(second_processes),
                "common_process_count": len(common),
                "new_pids": sorted(set(second_processes) - set(first_processes)),
                "exited_pids": sorted(
                    set(first_processes) - set(second_processes)
                ),
                "aggregate": {
                    "total_cpu_ticks_delta": total_cpu_ticks,
                    "total_read_bytes_delta": total_read_bytes,
                    "total_write_bytes_delta": total_write_bytes,
                    "total_context_switches_delta": total_context_switches,
                    "observable_progress": bool(
                        total_cpu_ticks
                        or total_read_bytes
                        or total_write_bytes
                        or total_context_switches
                    ),
                },
                "process_deltas": deltas,
                "gpu_snapshot_first": first["gpus"],
                "gpu_snapshot_second": second["gpus"],
                "compute_applications_first": first[
                    "compute_applications"
                ],
                "compute_applications_second": second[
                    "compute_applications"
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
