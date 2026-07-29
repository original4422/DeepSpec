#!/usr/bin/env python3
"""Sample all eight assigned GPUs while the registered server remains alive."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    with args.output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "timestamp_utc",
                "gpu_index",
                "gpu_uuid",
                "utilization_gpu_percent",
                "memory_used_mib",
                "memory_total_mib",
                "server_pid_alive",
            )
        )
        while Path(f"/proc/{args.server_pid}").exists():
            output = subprocess.run(
                (
                    "nvidia-smi",
                    "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout
            rows = [
                [item.strip() for item in line.split(",")]
                for line in output.splitlines()
                if line.strip()
            ]
            if len(rows) != 8 or [int(row[0]) for row in rows] != list(range(8)):
                raise RuntimeError(f"expected physical GPU 0..7: {rows!r}")
            timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
            for row in rows:
                writer.writerow((timestamp, *row, True))
            stream.flush()
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
