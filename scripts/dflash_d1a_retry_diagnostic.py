#!/usr/bin/env python3
"""Capture read-only evidence for an in-process D1A curl restart."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone


REVISION = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
SCRIPT = (
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-dflash/scripts/dflash_d1a_acquire_publish.py"
)
ROOT = pathlib.Path("/tmp/deepspec-hedge-dflash/d1a")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def argv(pid: int) -> list[str]:
    raw = (pathlib.Path("/proc") / str(pid) / "cmdline").read_bytes()
    return [
        item.decode(errors="replace") for item in raw.split(b"\0") if item
    ]


def proc_text(pid: int, name: str) -> str:
    return (pathlib.Path("/proc") / str(pid) / name).read_text(
        errors="replace"
    )


def process_record(pid: int) -> dict[str, object]:
    proc = pathlib.Path("/proc") / str(pid)
    fds = {}
    for candidate in sorted(
        (proc / "fd").iterdir(), key=lambda path: int(path.name)
    ):
        try:
            fds[candidate.name] = os.readlink(candidate)
        except OSError as error:
            fds[candidate.name] = f"<unavailable: {error}>"
    ps = subprocess.run(
        [
            "ps",
            "-o",
            "pid=,ppid=,pgid=,sid=,lstart=,etime=,stat=,args=",
            "-p",
            str(pid),
        ],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    ).stdout.strip()
    return {
        "pid": pid,
        "argv": argv(pid),
        "ps": ps,
        "io": proc_text(pid, "io"),
        "status": proc_text(pid, "status"),
        "wchan": proc_text(pid, "wchan").strip(),
        "file_descriptors": fds,
    }


def sanitized_events(path: pathlib.Path) -> list[dict[str, object]]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text().splitlines():
        if not line:
            continue
        raw = json.loads(line)
        curl_stdout = raw.pop("curl_stdout", "")
        if curl_stdout:
            inner = json.loads(curl_stdout)
            effective = inner.pop("url_effective", None)
            if effective:
                inner["effective_endpoint"] = urllib.parse.urlsplit(
                    effective
                ).hostname
                inner["effective_url_query_redacted"] = True
            raw["curl_result"] = inner
        rows.append(raw)
    return rows


def stat_record(path: pathlib.Path) -> dict[str, object]:
    value = path.stat()
    return {
        "path": str(path),
        "size_bytes": value.st_size,
        "device": value.st_dev,
        "inode": value.st_ino,
        "link_count": value.st_nlink,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
        "mtime_utc": datetime.fromtimestamp(
            value.st_mtime, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "ctime_utc": datetime.fromtimestamp(
            value.st_ctime, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_id")
    args = parser.parse_args()
    if not re.fullmatch(
        r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", args.attempt_id
    ):
        raise SystemExit("invalid attempt id")

    acquisition_pids = []
    curl_pids = []
    for candidate in pathlib.Path("/proc").iterdir():
        if not candidate.name.isdigit():
            continue
        pid = int(candidate.name)
        try:
            command = argv(pid)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if SCRIPT in command and args.attempt_id in command:
            acquisition_pids.append(pid)
        if (
            command
            and pathlib.Path(command[0]).name == "curl"
            and any(REVISION in item for item in command)
            and any("model.safetensors" in item for item in command)
        ):
            curl_pids.append(pid)
    if len(curl_pids) != 1:
        raise RuntimeError(f"expected one active D1A curl, got {curl_pids}")

    partial = (
        ROOT
        / f".staging-primary-{REVISION}-{args.attempt_id}"
        / "model.safetensors.partial"
    )
    attempt = ROOT / "attempts" / args.attempt_id
    heartbeat = json.loads((attempt / "heartbeat.json").read_text())
    diagnostic = {
        "schema_version": 1,
        "attempt_id": args.attempt_id,
        "captured_at_utc": utc_now(),
        "observation": (
            "active model.safetensors.partial size reset after reaching "
            "approximately 3.40 GB; transfer continues in the same curl PID"
        ),
        "root_cause_fingerprint": (
            "curl-internal-retry-restarts-from-invocation-offset-zero"
        ),
        "root_cause_status": "strong inference; active stderr is parent-captured",
        "curl_configuration_evidence": {
            "continue_at_auto": True,
            "retry_all_errors": True,
            "retry_count": 8,
            "risk": (
                "curl determines the auto-resume offset at process invocation; "
                "an internal retry can reopen/truncate from that original offset"
            ),
        },
        "heartbeat": heartbeat,
        "partial_file": stat_record(partial),
        "acquisition_processes": [
            process_record(pid) for pid in sorted(acquisition_pids)
        ],
        "curl_process": process_record(curl_pids[0]),
        "completed_download_events_sanitized": sanitized_events(
            attempt / "download_events.jsonl"
        ),
        "active_curl_stderr_status": (
            "not consumed: stderr is captured by the acquisition parent and "
            "will be persisted only after curl exits; reading the pipe would "
            "interfere with the active transfer"
        ),
        "active_transfer_continues": True,
        "current_strategy": (
            "do not interrupt the active transfer; if it exits unsuccessfully, "
            "use an external bounded retry loop that re-invokes curl so "
            "--continue-at - recomputes the then-current partial size"
        ),
        "fallback_checkpoint_enabled": False,
    }
    output = attempt / "retry_reset_diagnostic.json"
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(diagnostic, indent=2, sort_keys=True) + "\n")
    os.rename(temporary, output)
    print(json.dumps({"path": str(output), **diagnostic}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
