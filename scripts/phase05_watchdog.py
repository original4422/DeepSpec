#!/usr/bin/env python3
"""Recover an orphaned Phase 05 server and restore operational keepalive."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def start_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return None
    return stat[stat.rfind(")") + 2 :].split()[19]


def cmdline(pid: int) -> str:
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()


def owned(pid: int, ticks: str, marker: str) -> bool:
    try:
        return (
            start_ticks(pid) == ticks
            and marker in cmdline(pid)
            and os.getpgid(pid) == pid
            and os.getsid(pid) == pid
        )
    except (FileNotFoundError, ProcessLookupError):
        return False


def terminate_owned_group(pid: int, ticks: str, marker: str) -> str:
    if not owned(pid, ticks, marker):
        return "already_exited_or_identity_changed"
    os.killpg(pid, signal.SIGTERM)
    for _ in range(30):
        if start_ticks(pid) is None:
            return "terminated"
        time.sleep(1)
    if owned(pid, ticks, marker):
        os.killpg(pid, signal.SIGKILL)
    return "killed_after_timeout"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-pid", type=int, required=True)
    parser.add_argument("--owner-start-ticks", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--server-start-ticks", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--hdfs-run", type=Path, required=True)
    args = parser.parse_args()
    while start_ticks(args.owner_pid) == args.owner_start_ticks:
        time.sleep(5)
    outcome = terminate_owned_group(
        args.server_pid, args.server_start_ticks, "sglang.launch_server"
    )
    resume = subprocess.run(
        [
            "bash",
            str(args.repo_root / "scripts/keepalive.sh"),
            "resume",
            args.worker_id,
        ],
        text=True,
        capture_output=True,
    )
    record = {
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "reason": "lifecycle_owner_disappeared",
        "server_cleanup": outcome,
        "keepalive_resume_returncode": resume.returncode,
        "keepalive_stdout": resume.stdout,
        "keepalive_stderr": resume.stderr,
    }
    path = args.scratch / "watchdog_recovery.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    args.hdfs_run.mkdir(parents=True, exist_ok=True)
    for artifact in args.scratch.iterdir():
        if artifact.is_file():
            target = args.hdfs_run / artifact.name
            target.write_bytes(artifact.read_bytes())
    if resume.returncode:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
