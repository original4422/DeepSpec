#!/usr/bin/env python3
"""Observe local-wheel unpack progress without making a stall inference."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any, Sequence


EXPECTED_COMMAND = [
    "/home/tiger/.local/bin/uv",
    "pip",
    "install",
    "--python",
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python",
    "--no-deps",
    (
        "/tmp/deepspec-hedge-v4-eagle3/direct-torch-04/"
        "torch-2.11.0+cu130-cp311-cp311-manylinux_2_28_x86_64.whl"
    ),
]
VENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def command_line(pid: int) -> list[str]:
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in Path(f"/proc/{pid}/cmdline")
        .read_bytes()
        .rstrip(b"\0")
        .split(b"\0")
        if value
    ]


def proc_io(pid: int) -> dict[str, int]:
    return {
        name: int(raw_value.strip())
        for name, raw_value in (
            line.split(":", maxsplit=1)
            for line in Path(f"/proc/{pid}/io")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }


def tree_metrics(root: Path) -> dict[str, int]:
    files = 0
    bytes_total = 0
    newest_mtime_ns = root.stat().st_mtime_ns
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                stat = entry.stat(follow_symlinks=False)
                newest_mtime_ns = max(newest_mtime_ns, stat.st_mtime_ns)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files += 1
                    bytes_total += stat.st_size
    return {
        "files": files,
        "bytes": bytes_total,
        "newest_mtime_ns": newest_mtime_ns,
    }


def selected_fds(pid: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(entry)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if "torch-2.11.0" in target or "/uv" in target:
            records.append({"fd": int(entry.name), "target": target})
    return sorted(records, key=lambda value: int(value["fd"]))


def delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before.get(key, 0) for key in after}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    if command_line(args.pid) != EXPECTED_COMMAND:
        raise RuntimeError("local install command identity differs")
    before = {
        "captured_at": utc_now(),
        "proc_io": proc_io(args.pid),
        "venv": tree_metrics(VENV),
        "selected_fds": selected_fds(args.pid),
    }
    time.sleep(args.sample_seconds)
    try:
        command_after = command_line(args.pid)
    except FileNotFoundError:
        command_after = []
    if command_after and command_after != EXPECTED_COMMAND:
        raise RuntimeError("local install identity changed during probe")
    after = {
        "captured_at": utc_now(),
        "process_exited": not command_after,
        "proc_io": proc_io(args.pid) if command_after else None,
        "venv": tree_metrics(VENV),
        "selected_fds": selected_fds(args.pid) if command_after else [],
    }
    io_delta = (
        delta(after["proc_io"], before["proc_io"])
        if after["proc_io"] is not None
        else None
    )
    venv_delta = delta(after["venv"], before["venv"])
    progress = (
        after["process_exited"]
        or venv_delta["bytes"] > 0
        or venv_delta["files"] > 0
        or (
            io_delta is not None
            and (
                io_delta.get("read_bytes", 0) > 0
                or io_delta.get("write_bytes", 0) > 0
                or io_delta.get("rchar", 0) > 0
                or io_delta.get("wchar", 0) > 0
            )
        )
    )
    payload = {
        "schema_version": 1,
        "verdict": "PROGRESS" if progress else "INCONCLUSIVE",
        "reason": (
            "local file I/O, venv growth, or process completion observed"
            if progress
            else "no observed change; no stall inference is made"
        ),
        "pid": args.pid,
        "command_line": EXPECTED_COMMAND,
        "sample_seconds": args.sample_seconds,
        "before": before,
        "after": after,
        "delta": {"proc_io": io_delta, "venv": venv_delta},
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{payload['verdict']} output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"local install probe error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
