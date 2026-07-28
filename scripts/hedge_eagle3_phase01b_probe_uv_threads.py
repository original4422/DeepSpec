#!/usr/bin/env python3
"""Read-only targeted instrumentation for one exact uv install."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Sequence


BASE_COMMAND = [
    "/home/tiger/.local/bin/uv",
    "pip",
    "install",
    "--python",
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python",
    "--index",
    "https://download.pytorch.org/whl/cu130",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def expected_command(mode: str) -> list[str]:
    if mode == "system-certs":
        return [*BASE_COMMAND, "--system-certs", "--verbose", "torch==2.11.0"]
    if mode == "initial":
        return [*BASE_COMMAND, "torch==2.11.0"]
    if mode == "index-url":
        command = list(BASE_COMMAND)
        command[5] = "--index-url"
        return [*command, "--system-certs", "--verbose", "torch==2.11.0"]
    raise ValueError(mode)


def command_line(pid: int) -> list[str]:
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in Path(f"/proc/{pid}/cmdline")
        .read_bytes()
        .rstrip(b"\0")
        .split(b"\0")
        if value
    ]


def read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None


def thread_snapshot(pid: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for task in sorted(
        Path(f"/proc/{pid}/task").iterdir(),
        key=lambda path: int(path.name),
    ):
        tid = int(task.name)
        status = read_optional(task / "status") or ""
        state_line = next(
            (
                line.split(":", maxsplit=1)[1].strip()
                for line in status.splitlines()
                if line.startswith("State:")
            ),
            None,
        )
        records.append(
            {
                "tid": tid,
                "state": state_line,
                "wchan": read_optional(task / "wchan"),
                "syscall": read_optional(task / "syscall"),
            }
        )
    return records


def process_ticks(pid: int) -> dict[str, int]:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    fields = payload[payload.rfind(")") + 2 :].split()
    return {
        "utime_ticks": int(fields[11]),
        "stime_ticks": int(fields[12]),
        "num_threads": int(fields[17]),
    }


def file_descriptors(pid: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in sorted(
        Path(f"/proc/{pid}/fd").iterdir(),
        key=lambda path: int(path.name),
    ):
        try:
            target = os.readlink(entry)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if target.startswith("socket:") or "uv-cache" in target:
            records.append({"fd": int(entry.name), "target": target})
    return records


def socket_rows(pid: int) -> list[str]:
    completed = subprocess.run(
        ("ss", "--tcp", "--process", "--numeric", "state", "all"),
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        return [f"ss failed: {completed.stderr.strip()}"]
    needle = f"pid={pid},"
    return [line for line in completed.stdout.splitlines() if needle in line]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument(
        "--mode",
        choices=("initial", "system-certs", "index-url"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args(argv)
    if not 2 <= args.samples <= 15:
        raise ValueError("samples must be in [2, 15]")
    expected = expected_command(args.mode)
    observed = command_line(args.pid)
    if observed != expected:
        raise RuntimeError(
            f"command mismatch: {shlex.join(observed)}"
        )
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")

    samples: list[dict[str, Any]] = []
    for sample_index in range(args.samples):
        if command_line(args.pid) != expected:
            raise RuntimeError("command identity changed during probe")
        samples.append(
            {
                "captured_at": utc_now(),
                "ticks": process_ticks(args.pid),
                "threads": thread_snapshot(args.pid),
                "file_descriptors": file_descriptors(args.pid),
                "socket_rows": socket_rows(args.pid),
            }
        )
        if sample_index + 1 < args.samples:
            time.sleep(1.0)
    payload = {
        "schema_version": 1,
        "status": "PASS",
        "pid": args.pid,
        "mode": args.mode,
        "command_line": expected,
        "samples": samples,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"THREAD_PROBE_PASS output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"thread probe error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
