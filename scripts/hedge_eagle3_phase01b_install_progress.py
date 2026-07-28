#!/usr/bin/env python3
"""Detect substantive progress in one exactly identified uv install."""

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


UV_CACHE = Path("/tmp/deepspec-hedge-v4-eagle3/uv-cache")
VENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
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


def command_line(pid: int) -> list[str]:
    payload = Path(f"/proc/{pid}/cmdline").read_bytes()
    return [
        part.decode("utf-8", errors="surrogateescape")
        for part in payload.rstrip(b"\0").split(b"\0")
        if part
    ]


def expected_command(mode: str) -> list[str]:
    if mode == "initial":
        return [*BASE_COMMAND, "torch==2.11.0"]
    if mode == "system-certs":
        return [*BASE_COMMAND, "--system-certs", "--verbose", "torch==2.11.0"]
    if mode == "index-url":
        command = list(BASE_COMMAND)
        command[5] = "--index-url"
        return [*command, "--system-certs", "--verbose", "torch==2.11.0"]
    raise ValueError(f"unsupported mode: {mode}")


def parse_proc_io(pid: int) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path(f"/proc/{pid}/io").read_text(encoding="utf-8").splitlines():
        name, raw_value = line.split(":", maxsplit=1)
        values[name] = int(raw_value.strip())
    return values


def tree_metrics(root: Path) -> dict[str, int]:
    file_count = 0
    total_bytes = 0
    newest_mtime_ns = root.stat().st_mtime_ns
    entry_count = 1
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                stat = entry.stat(follow_symlinks=False)
                entry_count += 1
                newest_mtime_ns = max(newest_mtime_ns, stat.st_mtime_ns)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    file_count += 1
                    total_bytes += stat.st_size
    return {
        "entry_count": entry_count,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "newest_mtime_ns": newest_mtime_ns,
    }


def snapshot(pid: int) -> dict[str, Any]:
    return {
        "captured_at": utc_now(),
        "monotonic_ns": time.monotonic_ns(),
        "proc_io": parse_proc_io(pid),
        "uv_cache": tree_metrics(UV_CACHE),
        "venv": tree_metrics(VENV),
    }


def delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before.get(key, 0) for key in after}


def write_json_new(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite progress evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("initial", "system-certs", "index-url"),
        required=True,
    )
    parser.add_argument("--sample-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)
    if not 1.0 <= args.sample_seconds <= 30.0:
        raise ValueError("sample interval must be in [1, 30] seconds")

    expected = expected_command(args.mode)
    observed = command_line(args.pid)
    if observed != expected:
        raise RuntimeError(
            "unowned or changed uv command: "
            f"expected={shlex.join(expected)} observed={shlex.join(observed)}"
        )
    before = snapshot(args.pid)
    time.sleep(args.sample_seconds)
    try:
        observed_after = command_line(args.pid)
    except FileNotFoundError:
        payload = {
            "schema_version": 1,
            "verdict": "PASS",
            "reason": "owned install process exited during observation",
            "pid": args.pid,
            "mode": args.mode,
            "expected_command": expected,
            "sample_seconds": args.sample_seconds,
            "before": before,
            "finished_at": utc_now(),
        }
        write_json_new(args.output, payload)
        print(f"PASS output={args.output} reason=process_exited")
        return 0
    if observed_after != expected:
        raise RuntimeError("owned uv command changed during observation")
    after = snapshot(args.pid)

    proc_delta = delta(after["proc_io"], before["proc_io"])
    cache_delta = delta(after["uv_cache"], before["uv_cache"])
    venv_delta = delta(after["venv"], before["venv"])
    substantive_proc_io = (
        proc_delta.get("read_bytes", 0) >= 1024 * 1024
        or proc_delta.get("write_bytes", 0) >= 1024 * 1024
        or proc_delta.get("rchar", 0) >= 1024 * 1024
        or proc_delta.get("wchar", 0) >= 1024 * 1024
    )
    cache_progress = (
        cache_delta["total_bytes"] > 0
        or cache_delta["file_count"] > 0
        or cache_delta["entry_count"] > 0
        or cache_delta["newest_mtime_ns"] > 0
    )
    venv_progress = (
        venv_delta["total_bytes"] > 0
        or venv_delta["file_count"] > 0
        or venv_delta["entry_count"] > 0
        or venv_delta["newest_mtime_ns"] > 0
    )
    signals = {
        "substantive_proc_io": substantive_proc_io,
        "uv_cache_progress": cache_progress,
        "venv_progress": venv_progress,
    }
    stalled = not any(signals.values())
    payload = {
        "schema_version": 1,
        "verdict": "STALL" if stalled else "PASS",
        "reason": (
            "no substantive proc I/O, uv-cache, or venv progress"
            if stalled
            else "at least one substantive progress signal changed"
        ),
        "pid": args.pid,
        "mode": args.mode,
        "expected_command": expected,
        "sample_seconds": args.sample_seconds,
        "thresholds": {
            "proc_io_minimum_bytes": 1024 * 1024,
            "cache_or_venv_metadata_delta": "strictly positive",
        },
        "before": before,
        "after": after,
        "delta": {
            "proc_io": proc_delta,
            "uv_cache": cache_delta,
            "venv": venv_delta,
        },
        "signals": signals,
        "finished_at": utc_now(),
    }
    write_json_new(args.output, payload)
    print(
        f"{payload['verdict']} output={args.output} "
        f"signals={json.dumps(signals, sort_keys=True)}"
    )
    return 3 if stalled else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"install progress gate error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
