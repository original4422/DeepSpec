#!/usr/bin/env python3
"""Sample all four GPUs until the registered server PID exits."""

from __future__ import annotations

import argparse
import csv
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    with args.output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "timestamp_utc",
                "gpu_index",
                "gpu_uuid",
                "utilization_gpu_percent",
                "memory_used_mib",
                "memory_total_mib",
                "server_pid_alive",
            ]
        )
        while Path(f"/proc/{args.server_pid}").exists():
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
            )
            rows = [line.split(",") for line in output.splitlines() if line.strip()]
            if len(rows) != 4:
                raise RuntimeError(f"expected 4 GPUs, observed {len(rows)}")
            timestamp = datetime.now(timezone.utc).isoformat()
            for row in rows:
                writer.writerow(
                    [timestamp, *(item.strip() for item in row), True]
                )
            stream.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
