#!/usr/bin/env python3
"""Fail-closed process, keepalive, CUDA-context, and artifact operations."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
from typing import Any, Iterable, Sequence


WORKER_ID = "4099544"
EXPECTED_UUIDS = (
    "GPU-ea15ff88-dadd-ba7b-179d-484c1f152e63",
    "GPU-eef6edd3-6d93-5640-9e99-3b2c01987c9f",
    "GPU-357ebd70-0a3c-7397-55b2-2ff509736053",
    "GPU-3123de5a-168b-af3d-9f36-57603da3b11b",
    "GPU-eb1b03fe-54ee-0844-0b58-b4958a5a7cc8",
    "GPU-09e26802-d40f-473a-73bd-5220fd48c6f5",
    "GPU-23fcb1c0-804b-2487-0fb3-d7d8e558ca20",
    "GPU-e387b240-1c16-7bed-8291-66a12ba97f06",
)
STATE_DIR = Path("/home/tiger/.deepspec-hedge-v4-eagle3/keepalive")
EXPECTED_KEEPALIVE_PYTHON_ARGV = Path(
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python"
)
EXPECTED_KEEPALIVE_EXECUTABLE = EXPECTED_KEEPALIVE_PYTHON_ARGV.resolve()
EXPECTED_KEEPALIVE_SCRIPT_ARGV = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3/scripts/keepalive_load.py"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def proc_stat(pid: int) -> dict[str, int | str]:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close = payload.rfind(")")
    if close < 0:
        raise RuntimeError(f"malformed /proc/{pid}/stat")
    fields = payload[close + 2 :].split()
    return {
        "state": fields[0],
        "ppid": int(fields[1]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
        "start_ticks": int(fields[19]),
    }


def command_line(pid: int) -> list[str]:
    return [
        part.decode("utf-8", errors="surrogateescape")
        for part in Path(f"/proc/{pid}/cmdline")
        .read_bytes()
        .rstrip(b"\0")
        .split(b"\0")
        if part
    ]


def selected_environment(pid: int) -> dict[str, str]:
    selected = {
        "CUDA_VISIBLE_DEVICES",
        "CUDA_HOME",
        "LD_LIBRARY_PATH",
        "SGLANG_DSV4_FP4_EXPERTS",
        "SGLANG_DSV4_FP4_DEQUANT",
        "SGLANG_RAGGED_VERIFY_MODE",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH",
    }
    result: dict[str, str] = {}
    for raw in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if b"=" not in raw:
            continue
        raw_name, raw_value = raw.split(b"=", maxsplit=1)
        name = raw_name.decode("utf-8", errors="surrogateescape")
        if name in selected:
            result[name] = raw_value.decode(
                "utf-8", errors="surrogateescape"
            )
    return result


def process_record(pid: int) -> dict[str, Any]:
    stat = proc_stat(pid)
    argv = command_line(pid)
    return {
        "pid": pid,
        **stat,
        "command_line": argv,
        "command_display": shlex.join(argv),
        "executable": os.path.realpath(f"/proc/{pid}/exe"),
        "selected_environment": selected_environment(pid),
    }


def iter_pids() -> Iterable[int]:
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            yield int(entry.name)


def is_descendant(pid: int, ancestor: int) -> bool:
    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        try:
            current = int(proc_stat(current)["ppid"])
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return False
    return False


def compute_contexts() -> list[dict[str, Any]]:
    completed = subprocess.run(
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(
        completed.stdout.splitlines(), skipinitialspace=True
    ):
        if not fields:
            continue
        if len(fields) != 4:
            raise RuntimeError(f"unexpected context row: {fields!r}")
        memory = fields[3].strip()
        rows.append(
            {
                "gpu_uuid": fields[0].strip(),
                "host_pid": int(fields[1].strip()),
                "process_name": fields[2].strip(),
                "used_gpu_memory_mib": (
                    None
                    if memory in {"N/A", "[N/A]"}
                    else int(memory)
                ),
            }
        )
    return rows


def exact_assigned_gpu_contexts(contexts: Sequence[dict[str, Any]]) -> bool:
    """Require exactly one compute context on each assigned physical GPU."""
    counts = Counter(str(row["gpu_uuid"]) for row in contexts)
    return (
        len(contexts) == len(EXPECTED_UUIDS)
        and set(counts) == set(EXPECTED_UUIDS)
        and all(counts[uuid] == 1 for uuid in EXPECTED_UUIDS)
    )


def latest_ready_workers(
    owner_pid: int,
) -> tuple[Path, list[dict[str, Any]]]:
    pid_files = sorted(STATE_DIR.glob("*.pid"))
    if len(pid_files) != 1:
        raise RuntimeError(f"expected one keepalive pid file: {pid_files!r}")
    log_path = pid_files[0].with_suffix(".log")
    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            value.get("event") == "all_gpus_ready"
            and value.get("expected_gpus") == 8
            and value.get("matrix_size") == 8192
        ):
            events.append(value)
    for event in reversed(events):
        workers = event.get("workers")
        if not isinstance(workers, list) or len(workers) != 8:
            continue
        records: list[dict[str, Any]] = []
        try:
            for expected_index, worker in enumerate(workers):
                pid = int(worker["pid"])
                if int(worker["gpu_index"]) != expected_index:
                    raise RuntimeError("keepalive worker order differs")
                if worker.get("ready") is not True:
                    raise RuntimeError("keepalive worker is not ready")
                if not is_descendant(pid, owner_pid):
                    raise RuntimeError("keepalive worker is not an owner descendant")
                records.append(
                    {"gpu_index": expected_index, **process_record(pid)}
                )
        except (
            FileNotFoundError,
            ProcessLookupError,
            PermissionError,
            RuntimeError,
        ):
            continue
        return log_path, records
    raise RuntimeError("no live exact-eight keepalive readiness event")


def snapshot_keepalive(
    marker_path: Path,
    output: Path,
    require_baseline_owner: bool = False,
) -> None:
    baseline = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        baseline.get("worker_id") != WORKER_ID
        or baseline.get("expected_gpu_count") != 8
        or tuple(baseline.get("gpu_uuids", [])) != EXPECTED_UUIDS
    ):
        raise RuntimeError("baseline keepalive marker has wrong lane identity")
    pid_files = sorted(STATE_DIR.glob("*.pid"))
    if len(pid_files) != 1:
        raise RuntimeError(f"expected one current keepalive pid file: {pid_files!r}")
    owner_pid = int(pid_files[0].read_text(encoding="utf-8").strip())
    owner = process_record(owner_pid)
    expected_command = [
        str(EXPECTED_KEEPALIVE_PYTHON_ARGV),
        str(EXPECTED_KEEPALIVE_SCRIPT_ARGV),
        "load",
        "--expected-gpus",
        "8",
        "--matrix-size",
        "8192",
    ]
    if owner["command_line"] != expected_command:
        raise RuntimeError("current keepalive owner command differs")
    if owner["executable"] != str(EXPECTED_KEEPALIVE_EXECUTABLE):
        raise RuntimeError("current keepalive executable differs")
    if owner["pgid"] != owner_pid or owner["sid"] != owner_pid:
        raise RuntimeError("current keepalive owner is not PGID/SID leader")
    if owner["selected_environment"].get("CUDA_VISIBLE_DEVICES") != (
        "0,1,2,3,4,5,6,7"
    ):
        raise RuntimeError("current keepalive CUDA visibility differs")
    log_path, workers = latest_ready_workers(owner_pid)
    contexts = compute_contexts()
    if not exact_assigned_gpu_contexts(contexts):
        raise RuntimeError("current contexts are not exact-eight assigned GPUs")
    if len({row["host_pid"] for row in contexts}) != 8:
        raise RuntimeError("current keepalive does not have eight context PIDs")

    baseline_pairs = {
        (row["gpu_uuid"], int(row["nvidia_smi_host_pid"]))
        for row in baseline.get("context_pid_mappings", [])
    }
    current_pairs = {
        (row["gpu_uuid"], int(row["host_pid"])) for row in contexts
    }
    baseline_owner_is_current = (
        int(baseline["owner_pid"]) == owner_pid
        and int(baseline["owner_start_ticks"]) == owner["start_ticks"]
    )
    if require_baseline_owner and not baseline_owner_is_current:
        raise RuntimeError("live keepalive owner differs from Phase 01 marker")
    if require_baseline_owner and baseline_pairs != current_pairs:
        raise RuntimeError("live host PID/UUID mapping differs from Phase 01 marker")
    if baseline_owner_is_current and baseline_pairs != current_pairs:
        raise RuntimeError(
            "live Phase 01 owner has a different host PID/UUID mapping"
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "status": "PASS",
            "checked_at": utc_now(),
            "worker_id": WORKER_ID,
            "baseline_marker": str(marker_path),
            "baseline_owner_is_current": baseline_owner_is_current,
            "baseline_exact_host_pid_uuid_mapping_matches": (
                baseline_pairs == current_pairs
            ),
            "owner": owner,
            "ready_workers": workers,
            "ready_worker_count": len(workers),
            "compute_contexts": contexts,
            "compute_context_count": len(contexts),
            "load_log": str(log_path),
            "signal_sent": False,
        },
    )


def group_members(pgid: int) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for pid in iter_pids():
        try:
            stat = proc_stat(pid)
            if stat["pgid"] == pgid:
                members.append(process_record(pid))
        except (
            FileNotFoundError,
            ProcessLookupError,
            PermissionError,
        ):
            continue
    return sorted(members, key=lambda value: int(value["pid"]))


def capture_process(pid: int, fragment: str, output: Path) -> None:
    record = process_record(pid)
    if record["pgid"] != pid or record["sid"] != pid:
        raise RuntimeError("registered process is not PGID/SID leader")
    if fragment not in record["command_display"]:
        raise RuntimeError("registered command lacks exact attempt fragment")
    record["group_members"] = group_members(pid)
    record["captured_at"] = utc_now()
    record["expected_fragment"] = fragment
    write_json(output, record)


def validate_registered(record: dict[str, Any]) -> dict[str, Any]:
    current = process_record(int(record["pid"]))
    for key in (
        "pid",
        "pgid",
        "sid",
        "start_ticks",
        "command_line",
        "executable",
    ):
        if current[key] != record[key]:
            raise RuntimeError(f"registered process identity changed: {key}")
    if record["expected_fragment"] not in current["command_display"]:
        raise RuntimeError("registered process lost expected fragment")
    if current["pid"] != current["pgid"] or current["pid"] != current["sid"]:
        raise RuntimeError("registered process lost PGID/SID leadership")
    return current


def terminate_registered(
    identity_path: Path,
    output: Path,
    timeout: float,
) -> None:
    record = json.loads(identity_path.read_text(encoding="utf-8"))
    pid = int(record["pid"])
    try:
        validate_registered(record)
    except (FileNotFoundError, ProcessLookupError):
        write_json(
            output,
            {
                "status": "already_exited",
                "checked_at": utc_now(),
                "registered": record,
                "signal_sent": False,
            },
        )
        return
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            stat = proc_stat(pid)
        except (FileNotFoundError, ProcessLookupError):
            write_json(
                output,
                {
                    "status": "terminated",
                    "checked_at": utc_now(),
                    "registered": record,
                    "signal_sent": True,
                    "signal": "SIGTERM",
                    "kill_fallback": False,
                },
            )
            return
        if stat["state"] == "Z":
            live_members = [
                member
                for member in group_members(pid)
                if member["state"] != "Z"
            ]
            if not live_members:
                write_json(
                    output,
                    {
                        "status": "zombie_waiting_for_parent",
                        "checked_at": utc_now(),
                        "registered": record,
                        "signal_sent": True,
                        "signal": "SIGTERM",
                        "kill_fallback": False,
                    },
                )
                return
        time.sleep(1)
    current_stat = proc_stat(pid)
    if current_stat["state"] == "Z":
        for key in ("pgid", "sid", "start_ticks"):
            if current_stat[key] != record[key]:
                raise RuntimeError(
                    f"registered zombie identity changed: {key}"
                )
    else:
        validate_registered(record)
    os.killpg(pid, signal.SIGKILL)
    write_json(
        output,
        {
            "status": "killed_after_timeout",
            "checked_at": utc_now(),
            "registered": record,
            "signal_sent": True,
            "signal": "SIGKILL",
            "kill_fallback": True,
        },
    )


def wait_contexts(output: Path, timeout: float, expect: str) -> None:
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    while True:
        contexts = compute_contexts()
        samples.append({"checked_at": utc_now(), "contexts": contexts})
        condition = (
            not contexts
            if expect == "empty"
            else exact_assigned_gpu_contexts(contexts)
        )
        if condition:
            write_json(
                output,
                {
                    "status": "PASS",
                    "expectation": expect,
                    "elapsed_seconds": time.monotonic() - started,
                    "samples": samples,
                },
            )
            return
        if time.monotonic() - started >= timeout:
            write_json(
                output,
                {
                    "status": "FAIL",
                    "expectation": expect,
                    "elapsed_seconds": time.monotonic() - started,
                    "samples": samples,
                },
            )
            raise RuntimeError(
                f"CUDA context expectation not reached: {expect}"
            )
        time.sleep(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_manifest(directory: Path, output: Path) -> None:
    records = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path == output:
            continue
        records.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "created_at": utc_now(),
            "directory": str(directory),
            "artifacts": records,
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot-keepalive")
    snapshot.add_argument("--marker", type=Path, required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument("--require-baseline-owner", action="store_true")
    capture = subparsers.add_parser("capture-process")
    capture.add_argument("--pid", type=int, required=True)
    capture.add_argument("--fragment", required=True)
    capture.add_argument("--output", type=Path, required=True)
    terminate = subparsers.add_parser("terminate-process")
    terminate.add_argument("--identity", type=Path, required=True)
    terminate.add_argument("--output", type=Path, required=True)
    terminate.add_argument("--timeout", type=float, default=60)
    contexts = subparsers.add_parser("wait-contexts")
    contexts.add_argument("--output", type=Path, required=True)
    contexts.add_argument("--timeout", type=float, default=60)
    contexts.add_argument("--expect", choices=("empty", "eight"), required=True)
    start_ticks = subparsers.add_parser("start-ticks")
    start_ticks.add_argument("--pid", type=int, required=True)
    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--directory", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "snapshot-keepalive":
        snapshot_keepalive(
            args.marker,
            args.output,
            require_baseline_owner=args.require_baseline_owner,
        )
    elif args.command == "capture-process":
        capture_process(args.pid, args.fragment, args.output)
    elif args.command == "terminate-process":
        terminate_registered(args.identity, args.output, args.timeout)
    elif args.command == "wait-contexts":
        wait_contexts(args.output, args.timeout, args.expect)
    elif args.command == "start-ticks":
        print(proc_stat(args.pid)["start_ticks"])
    else:
        artifact_manifest(args.directory, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
