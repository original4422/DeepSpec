#!/usr/bin/env python3
"""Record an exact eight-GPU sample every second for a P04 attempt."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


EXPECTED_GPUS = 8
_STOP_REQUESTED = False


def parse_gpu_sample(payload: str) -> list[dict[str, int | str]]:
    """Parse one exact index/UUID/utilization/memory inventory."""

    rows: list[dict[str, int | str]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        fields = [field.strip() for field in raw_line.split(",")]
        if len(fields) != 5:
            raise ValueError(f"unexpected nvidia-smi sample row: {raw_line!r}")
        try:
            index = int(fields[0])
            utilization = int(fields[2])
            memory_used = int(fields[3])
            memory_total = int(fields[4])
        except ValueError as error:
            raise ValueError(
                f"non-numeric nvidia-smi sample row: {raw_line!r}"
            ) from error
        rows.append(
            {
                "gpu_index": index,
                "gpu_uuid": fields[1],
                "utilization_gpu_percent": utilization,
                "memory_used_mib": memory_used,
                "memory_total_mib": memory_total,
            }
        )
    if [row["gpu_index"] for row in rows] != list(range(EXPECTED_GPUS)):
        raise ValueError("sample GPU indices must be exactly 0 through 7")
    uuids = [str(row["gpu_uuid"]) for row in rows]
    if len(set(uuids)) != EXPECTED_GPUS or any(
        not uuid.startswith("GPU-") for uuid in uuids
    ):
        raise ValueError("sample must contain eight unique GPU UUIDs")
    if any(
        not 0 <= int(row["utilization_gpu_percent"]) <= 100
        or int(row["memory_used_mib"]) < 0
        or int(row["memory_total_mib"]) <= 0
        or int(row["memory_used_mib"]) > int(row["memory_total_mib"])
        for row in rows
    ):
        raise ValueError("sample contains invalid utilization or memory values")
    return rows


def _query_nvidia_smi() -> str:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "nvidia-smi sampling failed: " + completed.stderr.strip()
        )
    return completed.stdout


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run_sampler(
    *,
    output: Path,
    query: Callable[[], str] = _query_nvidia_smi,
    should_continue: Callable[[], bool],
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    utc_now: Callable[[], str] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Run the public sampler loop until its registered owner stops it."""

    if interval_seconds != 1.0:
        raise ValueError("P04 GPU sampling interval must be exactly 1 second")
    expected_uuids: list[str] | None = None
    sample_count = 0
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "sample_ordinal",
                "timestamp_utc",
                "monotonic_ns",
                "gpu_index",
                "gpu_uuid",
                "utilization_gpu_percent",
                "memory_used_mib",
                "memory_total_mib",
            ],
        )
        writer.writeheader()
        stream.flush()
        while should_continue():
            try:
                payload = query()
            except Exception:
                if not should_continue():
                    break
                raise
            rows = parse_gpu_sample(payload)
            uuids = [str(row["gpu_uuid"]) for row in rows]
            if expected_uuids is None:
                expected_uuids = uuids
            elif uuids != expected_uuids:
                raise RuntimeError("GPU UUID inventory changed during sampling")
            timestamp = utc_now()
            timestamp_monotonic_ns = monotonic_ns()
            for row in rows:
                writer.writerow(
                    {
                        "sample_ordinal": sample_count,
                        "timestamp_utc": timestamp,
                        "monotonic_ns": timestamp_monotonic_ns,
                        **row,
                    }
                )
            stream.flush()
            sample_count += 1
            sleeper(interval_seconds)
    return {
        "schema_version": 1,
        "status": "stopped",
        "sample_count": sample_count,
        "expected_gpus": EXPECTED_GPUS,
        "gpu_uuids": expected_uuids or [],
        "interval_seconds": interval_seconds,
    }


def _start_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    suffix = stat[stat.rfind(")") + 2 :].split()
    return suffix[19] if len(suffix) > 19 else None


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _request_stop(signum: int, frame: object) -> None:
    del signum, frame
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--owner-pid", type=int, required=True)
    parser.add_argument("--owner-start-ticks", required=True)
    parser.add_argument("--expected-gpus", type=int, default=EXPECTED_GPUS)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.expected_gpus != EXPECTED_GPUS:
        parser.error("P04 sampler requires exactly 8 GPUs")
    if args.interval != 1.0:
        parser.error("P04 sampler interval must be exactly 1 second")
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGHUP, _request_stop)

    def owner_is_registered() -> bool:
        return (
            not _STOP_REQUESTED
            and _start_ticks(args.owner_pid) == args.owner_start_ticks
        )

    try:
        status = run_sampler(
            output=args.output,
            should_continue=owner_is_registered,
            interval_seconds=args.interval,
        )
    except BaseException as error:
        status = {
            "schema_version": 1,
            "status": "FAIL",
            "error_type": type(error).__name__,
            "error": repr(error),
        }
        _atomic_json(args.status_output, status)
        raise
    _atomic_json(args.status_output, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
