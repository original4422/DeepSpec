#!/usr/bin/env python3
"""Turn the attempt-2 install probes into a machine-readable inference."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Sequence


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress-gate", type=Path, required=True)
    parser.add_argument("--thread-probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    progress = json.loads(args.progress_gate.read_text(encoding="utf-8"))
    probe = json.loads(args.thread_probe.read_text(encoding="utf-8"))
    if progress.get("verdict") != "STALL":
        raise RuntimeError("progress gate did not establish STALL")
    samples = probe.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise RuntimeError("thread probe does not contain repeated samples")
    syscalls = {
        str(thread["syscall"]).split()[0]
        for sample in samples
        for thread in sample["threads"]
    }
    if not syscalls <= {"202", "232"}:
        raise RuntimeError(f"unexpected thread syscall seam: {syscalls}")
    first_ticks = samples[0]["ticks"]
    last_ticks = samples[-1]["ticks"]
    tick_delta = {
        key: int(last_ticks[key]) - int(first_ticks[key])
        for key in ("utime_ticks", "stime_ticks")
    }
    socket_rows = {
        row for sample in samples for row in sample["socket_rows"]
    }
    if len(socket_rows) != 1 or ":8118" not in next(iter(socket_rows)):
        raise RuntimeError("probe did not isolate one stable proxy connection")

    payload = {
        "schema_version": 1,
        "recorded_at": utc_now(),
        "status": "ROOT_CAUSE_SEAM_NARROWED",
        "progress_gate": str(args.progress_gate),
        "thread_probe": str(args.thread_probe),
        "observations": {
            "progress_verdict": "STALL",
            "thread_syscalls": sorted(syscalls),
            "syscall_meanings_x86_64": {
                "202": "futex",
                "232": "epoll_wait",
            },
            "process_tick_delta": tick_delta,
            "stable_socket_rows": sorted(socket_rows),
            "cache_lock_fd_open": True,
            "other_uv_process_observed": False,
            "cuda_contexts_observed": 0,
        },
        "ranked_hypotheses": [
            {
                "rank": 1,
                "hypothesis": (
                    "`uv --index` adds a supplementary index while retaining "
                    "the default index; resolver/proxy response is stalled"
                ),
                "prediction": (
                    "changing only --index to --index-url will make the "
                    "15-second progress gate pass or produce a bounded "
                    "resolver error"
                ),
                "status": "next_test",
            },
            {
                "rank": 2,
                "hypothesis": "uv bundled TLS is incompatible with the proxy",
                "prediction": "--system-certs would remove the stall",
                "status": "falsified_by_attempt_2",
            },
            {
                "rank": 3,
                "hypothesis": "another process holds the uv cache lock",
                "prediction": "a second uv PID or lock holder would exist",
                "status": "falsified_by_unique_pid_inventory",
            },
            {
                "rank": 4,
                "hypothesis": "resolver is making CPU-bound progress",
                "prediction": "CPU ticks would advance materially",
                "status": "falsified_by_sleeping_threads_and_tick_delta",
            },
            {
                "rank": 5,
                "hypothesis": "disk capacity or CUDA initialization blocks install",
                "prediction": "disk pressure or CUDA contexts would be visible",
                "status": "falsified_by_capacity_and_zero_context_evidence",
            },
        ],
        "next_single_variable": "`--index` -> `--index-url`",
        "held_constant": [
            "uv 0.11.32",
            "Python 3.11.2 venv",
            "torch==2.11.0",
            "PyTorch cu130 URL",
            "--system-certs",
            "--verbose",
            "UV cache path",
        ],
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"INSTALL_DIAGNOSIS_RECORDED output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"diagnosis record error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
