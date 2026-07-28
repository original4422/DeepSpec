#!/usr/bin/env python3
"""Record a successfully installed minimal Eagle3 keepalive environment."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Sequence


UV = "/home/tiger/.local/bin/uv"
ENV = "/home/tiger/venvs/deepspec-hedge-v4-eagle3"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--single-variable-change", required=True)
    args = parser.parse_args(argv)
    environment_path = args.output_dir / "minimal_environment.json"
    status_path = args.output_dir / "attempt_status.json"
    freeze_path = args.output_dir / "minimal_uv_freeze.txt"
    if any(path.exists() for path in (environment_path, status_path, freeze_path)):
        raise RuntimeError("refusing to overwrite minimal environment evidence")

    import torch

    freeze = subprocess.run(
        (UV, "pip", "freeze", "--python", sys.executable),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    freeze_path.write_text(freeze, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        "purpose": "minimal Eagle3 operational keepalive prerequisite",
        "worker_id": "4099544",
        "hostname": platform.node(),
        "environment": ENV,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_initialized": torch.cuda.is_initialized(),
        "cuda_operation_performed": False,
        "uv_version": subprocess.run(
            (UV, "--version"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "uv_cache_dir": os.environ["UV_CACHE_DIR"],
        "freeze_path": str(freeze_path),
        "freeze_sha256": hashlib.sha256(freeze.encode("utf-8")).hexdigest(),
        "single_variable_change": args.single_variable_change,
        "install_stdout": str(args.output_dir / "uv-install.stdout.txt"),
        "install_stderr": str(args.output_dir / "uv-install.stderr.txt"),
    }
    if payload["cuda_initialized"]:
        raise RuntimeError("minimal environment record unexpectedly initialized CUDA")
    environment_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASS",
                "finished_at": utc_now(),
                "single_variable_change": args.single_variable_change,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"MINIMAL_UV_READY artifact={environment_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"minimal environment record error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
