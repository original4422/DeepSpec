#!/usr/bin/env python3
"""Safely reserve the small Phase 00 Eagle3 namespaces."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
from typing import Sequence


STATE_DIR = Path("/home/tiger/.deepspec-hedge-v4-eagle3")
SCRATCH_DIR = Path("/tmp/deepspec-hedge-v4-eagle3")
COORD_ROOT = Path("/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4")
COORD_DIR = COORD_ROOT / "eagle3-20260728T205627Z"


def write_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    args = parser.parse_args(argv)
    if args.worker_id != "4099544":
        raise ValueError(f"unassigned worker: {args.worker_id}")
    run_dir = args.run_dir.resolve()
    expected_prefix = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
    ).resolve()
    if run_dir.parent != expected_prefix:
        raise ValueError(f"unexpected run directory: {run_dir}")
    if not (run_dir / "worker_inventory.json").is_file():
        raise ValueError("worker inventory must precede namespace reservation")

    conflicts = [
        str(path)
        for path in (STATE_DIR, SCRATCH_DIR, COORD_DIR)
        if path.exists()
    ]
    if conflicts:
        raise FileExistsError(f"namespace conflicts: {conflicts}")

    port_check = subprocess.run(
        ("ss", "-H", "-ltnp", "sport", "=", ":31001"),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if port_check.returncode != 0 or port_check.stdout.strip():
        raise RuntimeError(
            "port 31001 is not proven free: "
            f"rc={port_check.returncode} stdout={port_check.stdout!r} "
            f"stderr={port_check.stderr!r}"
        )

    COORD_ROOT.mkdir(parents=True, exist_ok=True)
    for path in (STATE_DIR, SCRATCH_DIR, COORD_DIR):
        path.mkdir(mode=0o750)

    created_at = (
        dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    marker = {
        "schema_version": 1,
        "kind": "phase00_namespace_owner",
        "session": "hedge-v4-eagle3",
        "status": "reserved_not_active",
        "worker_id": args.worker_id,
        "started_at": args.started_at,
        "created_at": created_at,
        "state_dir": str(STATE_DIR),
        "scratch_root": str(SCRATCH_DIR),
        "coordination_dir": str(COORD_DIR),
        "run_dir": str(run_dir),
        "gpu_workload_started": False,
        "keepalive_started": False,
        "signal_sent": False,
    }
    for path in (STATE_DIR, SCRATCH_DIR, COORD_DIR):
        write_exclusive(path / "session-owner.json", marker)
    evidence = {
        **marker,
        "port": 31001,
        "port_available": True,
        "port_check": {
            "command": [
                "ss",
                "-H",
                "-ltnp",
                "sport",
                "=",
                ":31001",
            ],
            "returncode": port_check.returncode,
            "stdout": port_check.stdout,
            "stderr": port_check.stderr,
        },
        "markers": [
            str(STATE_DIR / "session-owner.json"),
            str(SCRATCH_DIR / "session-owner.json"),
            str(COORD_DIR / "session-owner.json"),
        ],
    }
    write_exclusive(run_dir / "namespace_bootstrap.json", evidence)
    print(
        json.dumps(
            {
                "status": "PASS",
                "state_dir": str(STATE_DIR),
                "scratch_root": str(SCRATCH_DIR),
                "coordination_dir": str(COORD_DIR),
                "port_available": True,
                "keepalive_started": False,
                "gpu_workload_started": False,
                "signal_sent": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
