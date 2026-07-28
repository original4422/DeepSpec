#!/usr/bin/env python3
"""Record the accidental default uv-cache use without cleaning it."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Sequence


EXPECTED_COMMAND = (
    "/home/tiger/.local/bin/uv pip install --python "
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python --no-deps "
    "/tmp/deepspec-hedge-v4-eagle3/direct-torch-04/"
    "torch-2.11.0+cu130-cp311-cp311-manylinux_2_28_x86_64.whl"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--raw-processes", type=Path, required=True)
    parser.add_argument("--direct-install", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    raw_processes = args.raw_processes.read_text(encoding="utf-8")
    install = json.loads(args.direct_install.read_text(encoding="utf-8"))
    if inventory.get("compute_context_count") != 0:
        raise RuntimeError("observation did not prove zero CUDA contexts")
    if EXPECTED_COMMAND not in raw_processes:
        raise RuntimeError("raw process evidence lacks exact uv command")
    if install.get("uv_returncode") != 0:
        raise RuntimeError("local uv install did not finish successfully")
    payload = {
        "schema_version": 1,
        "status": "IMPLEMENTATION_DEFECT_RECORDED",
        "recorded_at": utc_now(),
        "defect": (
            "The direct local-wheel install launcher omitted UV_CACHE_DIR, "
            "so uv used the shared default /home/tiger/.cache/uv instead of "
            "the Eagle3 lane-owned NVMe cache."
        ),
        "worker_id": "4099544",
        "process": {
            "pid": 273248,
            "ppid": 273175,
            "pgid": 273175,
            "sid": 273175,
            "started_at": "2026-07-28T22:02:01Z",
            "command_display": EXPECTED_COMMAND,
            "natural_exit": True,
            "uv_returncode": 0,
        },
        "affected_cache_path": "/home/tiger/.cache/uv",
        "intended_cache_path": (
            "/tmp/deepspec-hedge-v4-eagle3/uv-cache"
        ),
        "cache_mutation_scope_quantified": False,
        "cache_cleanup_performed": False,
        "signal_sent": False,
        "cuda_context_count_during_observation": 0,
        "inventory": str(args.inventory),
        "raw_processes": str(args.raw_processes),
        "direct_install": str(args.direct_install),
        "remediation": {
            "launcher_patched": True,
            "future_policy": (
                "Every uv launcher exports and exact-matches the lane-owned "
                "UV_CACHE_DIR before invoking uv."
            ),
            "shared_cache_left_untouched": True,
        },
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"SHARED_CACHE_DEFECT_RECORDED output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"cache defect record error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
