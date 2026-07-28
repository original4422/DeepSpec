#!/usr/bin/env python3
"""Terminate only the exactly identified, stalled Eagle3 uv install group."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
from typing import Any, Sequence


REPO_ROOT = (
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
BOOTSTRAP = f"{REPO_ROOT}/scripts/hedge_eagle3_phase01b_bootstrap_uv.sh"
SYSTEM_CERTS_RETRY = (
    f"{REPO_ROOT}/scripts/hedge_eagle3_phase01b_retry_uv_system_certs.sh"
)
INDEX_URL_RETRY = (
    f"{REPO_ROOT}/scripts/hedge_eagle3_phase01b_retry_uv_index_url.sh"
)
ENV = "/home/tiger/venvs/deepspec-hedge-v4-eagle3"
INDEX = "https://download.pytorch.org/whl/cu130"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def proc_stat(pid: int) -> tuple[int, int]:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close_paren = payload.rfind(")")
    fields = payload[close_paren + 2 :].split()
    return int(fields[1]), int(fields[19])


def command_line(pid: int) -> list[str]:
    payload = Path(f"/proc/{pid}/cmdline").read_bytes()
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in payload.rstrip(b"\0").split(b"\0")
        if value
    ]


def process_record(pid: int) -> dict[str, Any]:
    ppid, start_ticks = proc_stat(pid)
    command = command_line(pid)
    return {
        "pid": pid,
        "ppid": ppid,
        "pgid": os.getpgid(pid),
        "sid": os.getsid(pid),
        "start_ticks": start_ticks,
        "command_line": command,
        "command_display": shlex.join(command),
        "executable": os.path.realpath(f"/proc/{pid}/exe"),
    }


def group_members(pgid: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            if os.getpgid(pid) == pgid:
                records.append(process_record(pid))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return sorted(records, key=lambda record: int(record["pid"]))


def compute_contexts() -> list[dict[str, Any]]:
    completed = subprocess.run(
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,"
            "used_gpu_memory",
            "--format=csv,noheader,nounits",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cannot verify CUDA contexts: {completed.stderr.strip()}"
        )
    records: list[dict[str, Any]] = []
    for fields in csv.reader(
        completed.stdout.splitlines(),
        skipinitialspace=True,
    ):
        if fields:
            records.append(
                {
                    "gpu_uuid": fields[0].strip(),
                    "pid": int(fields[1].strip()),
                    "process_name": fields[2].strip(),
                    "used_gpu_memory": fields[3].strip(),
                }
            )
    return records


def write_json_new(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite evidence: {path}")
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leader-pid", type=int, required=True)
    parser.add_argument("--uv-pid", type=int, required=True)
    parser.add_argument("--attempt-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("initial", "system-certs", "index-url"),
        default="initial",
    )
    args = parser.parse_args(argv)

    script_by_mode = {
        "initial": BOOTSTRAP,
        "system-certs": SYSTEM_CERTS_RETRY,
        "index-url": INDEX_URL_RETRY,
    }
    expected_shell = [
        "bash",
        script_by_mode[args.mode],
        "4099544",
        str(args.attempt_dir),
    ]
    expected_uv = [
        "/home/tiger/.local/bin/uv",
        "pip",
        "install",
        "--python",
        f"{ENV}/bin/python",
        "--index-url" if args.mode == "index-url" else "--index",
        INDEX,
    ]
    if args.mode in {"system-certs", "index-url"}:
        expected_uv.extend(("--system-certs", "--verbose"))
    expected_uv.append("torch==2.11.0")
    leader = process_record(args.leader_pid)
    uv_process = process_record(args.uv_pid)
    if leader["command_line"] != expected_shell:
        raise RuntimeError("install group leader command differs from contract")
    if uv_process["command_line"] != expected_uv:
        raise RuntimeError("uv child command differs from contract")
    if leader["pgid"] != args.leader_pid or leader["sid"] != args.leader_pid:
        raise RuntimeError("install shell is not its PGID/SID leader")
    if uv_process["pgid"] != args.leader_pid:
        raise RuntimeError("uv child is outside the owned install group")
    members = group_members(args.leader_pid)
    if {record["pid"] for record in members} != {
        args.leader_pid,
        args.uv_pid,
    }:
        raise RuntimeError(f"install group contains unknown processes: {members}")
    contexts_before = compute_contexts()
    if contexts_before:
        raise RuntimeError("refusing stop because CUDA contexts now exist")

    before = {
        "schema_version": 1,
        "status": "STALL_CONFIRMED",
        "captured_at": utc_now(),
        "attempt_dir": str(args.attempt_dir),
        "progress_gate": str(args.attempt_dir / "install_progress_gate.json"),
        "group_leader_pid": args.leader_pid,
        "group_pgid": args.leader_pid,
        "group_sid": args.leader_pid,
        "members": members,
        "compute_contexts": contexts_before,
        "planned_signal": "SIGTERM to exactly verified owned PGID",
    }
    write_json_new(args.attempt_dir / "stall_termination_before.json", before)

    expected_start_ticks = {
        int(record["pid"]): int(record["start_ticks"]) for record in members
    }
    os.killpg(args.leader_pid, signal.SIGTERM)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline and group_members(args.leader_pid):
        time.sleep(0.5)
    forced = False
    remaining = group_members(args.leader_pid)
    if remaining:
        for record in remaining:
            if expected_start_ticks.get(int(record["pid"])) != int(
                record["start_ticks"]
            ):
                raise RuntimeError("PID identity changed before forced cleanup")
        os.killpg(args.leader_pid, signal.SIGKILL)
        forced = True
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and group_members(args.leader_pid):
            time.sleep(0.25)
    remaining = group_members(args.leader_pid)
    if remaining:
        raise RuntimeError(f"owned install group remains: {remaining}")
    contexts_after = compute_contexts()
    if contexts_after:
        raise RuntimeError("CUDA contexts appeared during install cleanup")

    after = {
        "schema_version": 1,
        "status": "TARGETED_STOP_COMPLETE",
        "finished_at": utc_now(),
        "group_pgid": args.leader_pid,
        "term_sent": True,
        "kill_sent": forced,
        "remaining_group_members": remaining,
        "compute_contexts": contexts_after,
    }
    write_json_new(args.attempt_dir / "stall_termination_after.json", after)
    print(
        "TARGETED_STOP_COMPLETE "
        f"pgid={args.leader_pid} forced={str(forced).lower()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"targeted install stop error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
