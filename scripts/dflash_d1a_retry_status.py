#!/usr/bin/env python3
"""Append a compact read-only monitor sample for the active D1A curl."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from datetime import datetime, timezone


REVISION = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
EXPECTED_BYTES = 3607596760
ROOT = pathlib.Path("/tmp/deepspec-hedge-dflash/d1a")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def argv(pid: int) -> list[str]:
    raw = (pathlib.Path("/proc") / str(pid) / "cmdline").read_bytes()
    return [
        item.decode(errors="replace") for item in raw.split(b"\0") if item
    ]


def proc_io(pid: int) -> dict[str, int]:
    result = {}
    for line in (
        pathlib.Path("/proc") / str(pid) / "io"
    ).read_text().splitlines():
        key, raw_value = line.split(":", 1)
        result[key] = int(raw_value.strip())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_id")
    args = parser.parse_args()
    if not re.fullmatch(
        r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", args.attempt_id
    ):
        raise SystemExit("invalid attempt id")
    attempt = ROOT / "attempts" / args.attempt_id
    partial = (
        ROOT
        / f".staging-primary-{REVISION}-{args.attempt_id}"
        / "model.safetensors.partial"
    )
    curl_pids = []
    curl_argv: list[str] | None = None
    for candidate in pathlib.Path("/proc").iterdir():
        if not candidate.name.isdigit():
            continue
        pid = int(candidate.name)
        try:
            command = argv(pid)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if (
            command
            and pathlib.Path(command[0]).name == "curl"
            and any(REVISION in item for item in command)
            and any("model.safetensors" in item for item in command)
        ):
            curl_pids.append(pid)
            curl_argv = command
    if len(curl_pids) > 1:
        raise RuntimeError(f"multiple D1A weight curls: {curl_pids}")

    monitor_path = attempt / "retry_monitor.jsonl"
    prior_rows = []
    if monitor_path.is_file():
        prior_rows = [
            json.loads(line)
            for line in monitor_path.read_text().splitlines()
            if line
        ]
    stat = partial.stat() if partial.exists() else None
    row: dict[str, object] = {
        "timestamp_utc": utc_now(),
        "attempt_id": args.attempt_id,
        "expected_size_bytes": EXPECTED_BYTES,
        "partial_present": stat is not None,
        "partial_size_bytes": stat.st_size if stat else None,
        "partial_device": stat.st_dev if stat else None,
        "partial_inode": stat.st_ino if stat else None,
        "partial_mtime_ns": stat.st_mtime_ns if stat else None,
        "curl_pid": curl_pids[0] if curl_pids else None,
        "curl_active": len(curl_pids) == 1,
        "curl_has_continue_at_auto": (
            "--continue-at" in curl_argv and "-" in curl_argv
            if curl_argv
            else None
        ),
        "curl_has_retry_all_errors": (
            "--retry-all-errors" in curl_argv if curl_argv else None
        ),
        "keepalive_pid": int(
            pathlib.Path(
                "/tmp/deepspec-hedge-dflash/keepalive/supervisor.pid"
            ).read_text()
        ),
    }
    if curl_pids:
        io = proc_io(curl_pids[0])
        row["curl_wchar_bytes"] = io["wchar"]
        row["curl_write_bytes"] = io["write_bytes"]
    prior_sizes = [
        item["partial_size_bytes"]
        for item in prior_rows
        if isinstance(item.get("partial_size_bytes"), int)
    ]
    row["decreased_from_previous_monitor"] = bool(
        prior_sizes
        and isinstance(row["partial_size_bytes"], int)
        and row["partial_size_bytes"] < prior_sizes[-1]
    )
    with monitor_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
