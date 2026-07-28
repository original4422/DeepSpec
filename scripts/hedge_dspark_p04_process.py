#!/usr/bin/env python3
"""Register and stop only exact P04 setsid process groups."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import signal
import socket
import time
from pathlib import Path
from typing import Any, Callable, Mapping


class ProcessIdentityError(RuntimeError):
    """A PID exists but no longer has the registered immutable identity."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _cmdline_sha256(cmdline: list[str]) -> str:
    digest = hashlib.sha256()
    for argument in cmdline:
        digest.update(argument.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
    return digest.hexdigest()


def _snapshot(pid: int) -> dict[str, Any] | None:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("PID must be a positive integer")
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        raw_cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        executable = os.path.realpath(f"/proc/{pid}/exe")
    except (FileNotFoundError, ProcessLookupError):
        return None
    right_parenthesis = stat.rfind(")")
    if right_parenthesis < 0:
        raise ProcessIdentityError(f"cannot parse /proc/{pid}/stat")
    fields = stat[right_parenthesis + 2 :].split()
    if len(fields) <= 19:
        raise ProcessIdentityError(f"truncated /proc/{pid}/stat")
    cmdline = [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw_cmdline.split(b"\0")
        if item
    ]
    return {
        "pid": pid,
        "hostname": socket.gethostname(),
        "state": fields[0],
        "ppid": int(fields[1]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
        "start_ticks": fields[19],
        "cmdline": cmdline,
        "cmdline_sha256": _cmdline_sha256(cmdline),
        "executable": executable,
    }


def capture_identity(
    *, pid: int, role: str, required_arg: str
) -> dict[str, Any]:
    """Capture an already-started setsid process after exact marker checking."""

    if not role or not required_arg:
        raise ValueError("role and required_arg must be non-empty")
    snapshot = _snapshot(pid)
    if snapshot is None or snapshot["state"] == "Z":
        raise ProcessIdentityError("process exited before registration")
    if (
        snapshot["pid"] != snapshot["pgid"]
        or snapshot["pid"] != snapshot["sid"]
    ):
        raise ProcessIdentityError("registered process must have PID=PGID=SID")
    if required_arg not in snapshot["cmdline"]:
        raise ProcessIdentityError(
            f"required exact command argument is absent: {required_arg!r}"
        )
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "registered_at_utc": _utc_now(),
        "role": role,
        "required_arg": required_arg,
        **snapshot,
    }


def verify_registered(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current snapshot only when every identity field still matches."""

    try:
        pid = int(identity["pid"])
    except (KeyError, TypeError, ValueError) as error:
        raise ProcessIdentityError("registered PID is invalid") from error
    current = _snapshot(pid)
    if current is None or current["state"] == "Z":
        raise ProcessIdentityError("registered process already exited")
    if str(current["start_ticks"]) != str(identity.get("start_ticks")):
        raise ProcessIdentityError("registered process start ticks changed")
    if current["hostname"] != identity.get("hostname"):
        raise ProcessIdentityError("registered process hostname changed")
    if current["cmdline"] != identity.get("cmdline"):
        raise ProcessIdentityError("registered process cmdline changed")
    if current["cmdline_sha256"] != identity.get("cmdline_sha256"):
        raise ProcessIdentityError("registered process cmdline hash changed")
    if current["executable"] != identity.get("executable"):
        raise ProcessIdentityError("registered process executable changed")
    if (
        current["pid"] != current["pgid"]
        or current["pid"] != current["sid"]
        or current["pgid"] != identity.get("pgid")
        or current["sid"] != identity.get("sid")
    ):
        raise ProcessIdentityError(
            "registered process no longer has PID=PGID=SID"
        )
    required_arg = identity.get("required_arg")
    if (
        not isinstance(required_arg, str)
        or required_arg not in current["cmdline"]
    ):
        raise ProcessIdentityError("registered exact command marker changed")
    return current


def _has_exited(pid: int) -> bool:
    snapshot = _snapshot(pid)
    return snapshot is None or snapshot["state"] == "Z"


def terminate_registered(
    identity: Mapping[str, Any],
    *,
    timeout_seconds: float = 30.0,
    kill_group: Callable[[int, int], None] = os.killpg,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """TERM, then optionally KILL, only the still-exact registered group."""

    if timeout_seconds <= 0:
        raise ValueError("termination timeout must be positive")
    pid = int(identity["pid"])
    if _has_exited(pid):
        return {
            "schema_version": 1,
            "role": identity.get("role"),
            "pid": pid,
            "status": "already_exited",
        }
    verify_registered(identity)
    try:
        kill_group(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {
            "schema_version": 1,
            "role": identity.get("role"),
            "pid": pid,
            "status": "already_exited",
        }
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        if _has_exited(pid):
            return {
                "schema_version": 1,
                "role": identity.get("role"),
                "pid": pid,
                "status": "terminated",
                "signal": "SIGTERM",
            }
        sleeper(min(0.1, max(deadline - clock(), 0.0)))

    verify_registered(identity)
    kill_group(pid, signal.SIGKILL)
    kill_deadline = clock() + min(timeout_seconds, 10.0)
    while clock() < kill_deadline:
        if _has_exited(pid):
            return {
                "schema_version": 1,
                "role": identity.get("role"),
                "pid": pid,
                "status": "terminated",
                "signal": "SIGKILL",
            }
        sleeper(min(0.1, max(kill_deadline - clock(), 0.0)))
    raise ProcessIdentityError(
        "registered process group remains after bounded TERM/KILL"
    )


def record_unregistered_exit(*, pid: int, role: str) -> dict[str, Any]:
    """Accept no-identity cleanup only when the exact PID is gone or a zombie."""

    if not role:
        raise ValueError("role must be non-empty")
    snapshot = _snapshot(pid)
    if snapshot is not None and snapshot["state"] != "Z":
        raise ProcessIdentityError(
            "unregistered process is still alive; refusing to signal it"
        )
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "role": role,
        "pid": pid,
        "hostname": socket.gethostname(),
        "status": "already_exited",
        "observed_state": (
            "not_present" if snapshot is None else "zombie"
        ),
    }


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("--pid", type=int, required=True)
    register.add_argument("--role", required=True)
    register.add_argument("--required-arg", required=True)
    register.add_argument("--output", type=Path, required=True)

    check = subparsers.add_parser("check")
    check.add_argument("--identity", type=Path, required=True)

    terminate = subparsers.add_parser("terminate")
    terminate.add_argument("--identity", type=Path, required=True)
    terminate.add_argument("--output", type=Path, required=True)
    terminate.add_argument("--timeout", type=float, default=30.0)

    settled = subparsers.add_parser("settle-unregistered")
    settled.add_argument("--pid", type=int, required=True)
    settled.add_argument("--role", required=True)
    settled.add_argument("--output", type=Path, required=True)

    ticks = subparsers.add_parser("start-ticks")
    ticks.add_argument("--pid", type=int, required=True)

    args = parser.parse_args()
    if args.command == "register":
        identity = capture_identity(
            pid=args.pid,
            role=args.role,
            required_arg=args.required_arg,
        )
        _atomic_json(args.output, identity)
        print(json.dumps(identity, sort_keys=True))
        return 0
    if args.command == "check":
        identity = json.loads(args.identity.read_text(encoding="utf-8"))
        current = verify_registered(identity)
        print(json.dumps(current, sort_keys=True))
        return 0
    if args.command == "terminate":
        identity = json.loads(args.identity.read_text(encoding="utf-8"))
        result = terminate_registered(
            identity, timeout_seconds=args.timeout
        )
        _atomic_json(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "settle-unregistered":
        result = record_unregistered_exit(pid=args.pid, role=args.role)
        _atomic_json(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "start-ticks":
        snapshot = _snapshot(args.pid)
        if snapshot is None or snapshot["state"] == "Z":
            raise SystemExit("process is not alive")
        print(snapshot["start_ticks"])
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
