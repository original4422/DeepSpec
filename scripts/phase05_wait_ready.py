#!/usr/bin/env python3
"""Bounded SGLang startup waiter that also watches the registered server PID."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    checks: list[dict] = []
    result = {"started_at": utc_now(), "server_pid": args.server_pid}
    while time.monotonic() - started < args.timeout:
        if not Path(f"/proc/{args.server_pid}").exists():
            result.update(
                status="server_exited",
                finished_at=utc_now(),
                elapsed_seconds=time.monotonic() - started,
                checks=checks,
            )
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            raise SystemExit(1)
        try:
            with LOCAL_OPENER.open(
                f"{args.base_url}/health", timeout=5
            ) as response:
                status = response.status
            checks.append({"at": utc_now(), "http_status": status})
            if status == 200:
                result.update(
                    status="ready",
                    finished_at=utc_now(),
                    elapsed_seconds=time.monotonic() - started,
                    checks=checks[-20:],
                )
                args.output.write_text(json.dumps(result, indent=2) + "\n")
                return
        except OSError as error:
            checks.append({"at": utc_now(), "error": repr(error)})
        time.sleep(5)
    result.update(
        status="timeout",
        finished_at=utc_now(),
        elapsed_seconds=time.monotonic() - started,
        checks=checks[-20:],
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    os.kill(args.server_pid, 0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
