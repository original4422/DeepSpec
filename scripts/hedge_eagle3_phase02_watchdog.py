#!/usr/bin/env python3
"""Recover an orphaned Phase 02 server and restore the Eagle3 keepalive."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import datetime as dt


def start_ticks(pid: int) -> int | None:
    try:
        payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    return int(payload[payload.rfind(")") + 2 :].split()[19])


def command_line(pid: int) -> str:
    return (
        Path(f"/proc/{pid}/cmdline")
        .read_bytes()
        .replace(b"\0", b" ")
        .decode(errors="replace")
    )


def owned(pid: int, ticks: int, fragment: str) -> bool:
    try:
        return (
            start_ticks(pid) == ticks
            and fragment in command_line(pid)
            and os.getpgid(pid) == pid
            and os.getsid(pid) == pid
        )
    except (FileNotFoundError, ProcessLookupError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-pid", type=int, required=True)
    parser.add_argument("--owner-start-ticks", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--server-start-ticks", type=int, required=True)
    parser.add_argument("--fragment", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--hdfs-run", type=Path, required=True)
    args = parser.parse_args()
    while start_ticks(args.owner_pid) == args.owner_start_ticks:
        time.sleep(5)
    cleanup = "already_exited_or_identity_changed"
    if owned(args.server_pid, args.server_start_ticks, args.fragment):
        os.killpg(args.server_pid, signal.SIGTERM)
        cleanup = "sigterm"
        for _ in range(60):
            if start_ticks(args.server_pid) is None:
                cleanup = "terminated"
                break
            time.sleep(1)
        else:
            if owned(
                args.server_pid,
                args.server_start_ticks,
                args.fragment,
            ):
                os.killpg(args.server_pid, signal.SIGKILL)
                cleanup = "sigkill_after_timeout"
    contexts = ""
    for _ in range(60):
        contexts = subprocess.run(
            (
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid",
                "--format=csv,noheader,nounits",
            ),
            check=False,
            capture_output=True,
            text=True,
        ).stdout
        if not contexts.strip():
            break
        time.sleep(1)
    resume = None
    status = None
    if not contexts.strip():
        resume = subprocess.run(
            (
                "bash",
                str(args.repo_root / "scripts/hedge_eagle3_keepalive.sh"),
                "resume",
                "4099544",
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            (
                "bash",
                str(args.repo_root / "scripts/hedge_eagle3_keepalive.sh"),
                "status",
                "4099544",
            ),
            check=False,
            capture_output=True,
            text=True,
        )
    record = {
        "recovered_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reason": "lifecycle_owner_disappeared",
        "server_cleanup": cleanup,
        "contexts_after": contexts,
        "keepalive_resume_returncode": (
            None if resume is None else resume.returncode
        ),
        "keepalive_resume_stdout": (
            None if resume is None else resume.stdout
        ),
        "keepalive_resume_stderr": (
            None if resume is None else resume.stderr
        ),
        "keepalive_status_returncode": (
            None if status is None else status.returncode
        ),
        "keepalive_status_stdout": (
            None if status is None else status.stdout
        ),
        "keepalive_status_stderr": (
            None if status is None else status.stderr
        ),
    }
    recovery = args.scratch / "watchdog_recovery.json"
    recovery.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.hdfs_run.mkdir(parents=True, exist_ok=True)
    for artifact in args.scratch.iterdir():
        if artifact.is_file():
            (args.hdfs_run / artifact.name).write_bytes(artifact.read_bytes())
    if (
        contexts.strip()
        or resume is None
        or resume.returncode
        or status is None
        or status.returncode
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
