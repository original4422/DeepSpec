#!/usr/bin/env bash
# Bounded, read-only probe for building the lane-local operational runtime.

set -euo pipefail

timeout --signal=TERM --kill-after=5s 45s python3 - <<'PY'
import json
import os
import pathlib
import shutil
import subprocess
from datetime import datetime, timezone


def run(argv):
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "argv": argv,
            "timed_out": True,
            "timeout_seconds": 10,
            "stdout": (error.stdout or b"").decode(errors="replace")
            if isinstance(error.stdout, bytes)
            else (error.stdout or ""),
            "stderr": (error.stderr or b"").decode(errors="replace")
            if isinstance(error.stderr, bytes)
            else (error.stderr or ""),
        }
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


candidates = [
    "/home/tiger/venvs/deepspec-hedge-dflash/bin/python",
    "/home/tiger/venvs/hedge-deepspec/bin/python",
    "/usr/bin/python3",
    "/usr/local/bin/python3",
]
records = []
for candidate in candidates:
    path = pathlib.Path(candidate)
    record = {
        "path": candidate,
        "exists": path.is_file(),
        "realpath": os.path.realpath(candidate) if path.exists() else None,
    }
    if path.is_file():
        record["version"] = run([candidate, "--version"])
        record["torch_metadata"] = run(
            [
                candidate,
                "-c",
                "import importlib.metadata as m; print(m.version('torch'))",
            ]
        )
    records.append(record)

uv = shutil.which("uv")
document = {
    "schema_version": 1,
    "captured_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "worker_id": "4099543",
    "hostname": os.uname().nodename,
    "uv_path": uv,
    "uv_version": run([uv, "--version"]) if uv else None,
    "python_candidates": records,
    "nvcc": run(["bash", "-lc", "command -v nvcc; nvcc --version"]),
    "state_parent": {
        "path": "/tmp",
        "writable": os.access("/tmp", os.W_OK),
    },
}
print(json.dumps(document, indent=2, sort_keys=True))
PY
