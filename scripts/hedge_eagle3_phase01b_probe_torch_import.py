#!/usr/bin/env python3
"""Probe Torch import after an empty ELF closure without a CUDA operation."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


ENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)


def cuda_context_count() -> int:
    completed = subprocess.run(
        (
            "nvidia-smi",
            "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return len(
        [
            row
            for row in csv.reader(
                completed.stdout.splitlines(),
                skipinitialspace=True,
            )
            if row
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-dir", type=Path, required=True)
    parser.add_argument(
        "--source-closure",
        default="torch_elf_closure_after_batch02",
    )
    parser.add_argument(
        "--output-name",
        default="torch_import_after_empty_elf_closure.json",
    )
    args = parser.parse_args(argv)
    for value in (args.source_closure, args.output_name):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", value):
            raise RuntimeError("unsafe import-probe path component")
    attempt = args.attempt_dir.resolve()
    output = attempt / args.output_name
    if output.exists():
        raise RuntimeError(f"refusing to overwrite: {output}")
    closure = json.loads(
        (
            attempt
            / args.source_closure
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    if closure.get("missing_sonames") != []:
        raise RuntimeError("Torch ELF closure is not empty")
    before = cuda_context_count()
    if before != 0:
        raise RuntimeError("Torch import probe requires zero CUDA contexts")
    site = ENV / "lib/python3.11/site-packages"
    library_dirs = sorted(
        path
        for path in (site / "nvidia").glob("*/lib")
        if path.is_dir()
    )
    environment = dict(os.environ)
    environment["LD_LIBRARY_PATH"] = ":".join(
        [
            str(COMPAT_ROOT),
            *(str(path) for path in library_dirs),
            "/usr/local/cuda/lib64",
        ]
    )
    completed = subprocess.run(
        (
            str(ENV / "bin/python"),
            "-c",
            (
                "import json, torch; "
                "print(json.dumps({"
                "'torch_version': torch.__version__, "
                "'torch_cuda_version': torch.version.cuda, "
                "'cuda_initialized': torch.cuda.is_initialized()"
                "}, sort_keys=True))"
            ),
        ),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    after = cuda_context_count()
    if after != 0:
        raise RuntimeError("Torch import probe unexpectedly created contexts")
    payload = {
        "schema_version": 1,
        "status": (
            "TORCH_IMPORT_PASS"
            if completed.returncode == 0
            else "TORCH_IMPORT_FAILED"
        ),
        "worker_id": "4099544",
        "source_empty_closure": str(
            attempt / args.source_closure / "summary.json"
        ),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "resolved_ld_library_path": environment["LD_LIBRARY_PATH"],
        "cuda_context_count_before": before,
        "cuda_context_count_after": after,
        "cuda_operation_performed": False,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{payload['status']} evidence={output}")
    return completed.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Torch import probe error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
