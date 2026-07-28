#!/usr/bin/env python3
"""Capture Torch ELF dependencies and the complete currently missing SONAME set."""

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


def run_to_file(
    command: Sequence[str],
    path: Path,
    *,
    environment: dict[str, str],
) -> int:
    completed = subprocess.run(
        tuple(command),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    path.write_text(
        completed.stdout
        + (
            "\n[stderr]\n" + completed.stderr
            if completed.stderr
            else ""
        ),
        encoding="utf-8",
    )
    return completed.returncode


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
        "--output-name",
        default="torch_elf_closure",
        help="Single safe directory name below the attempt directory.",
    )
    args = parser.parse_args(argv)
    attempt = args.attempt_dir.resolve()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.output_name):
        raise RuntimeError("unsafe ELF closure output name")
    output_dir = attempt / args.output_name
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite: {output_dir}")
    output_dir.mkdir()
    site = ENV / "lib/python3.11/site-packages"
    torch_dir = site / "torch"
    nvidia_lib_dirs = sorted(
        path
        for path in (site / "nvidia").glob("*/lib")
        if path.is_dir()
    )
    library_path_parts = [
        str(COMPAT_ROOT),
        *(str(path) for path in nvidia_lib_dirs),
        "/usr/local/cuda/lib64",
    ]
    environment = dict(os.environ)
    environment["LD_LIBRARY_PATH"] = ":".join(library_path_parts)
    (output_dir / "resolved_ld_library_path.txt").write_text(
        environment["LD_LIBRARY_PATH"] + "\n",
        encoding="utf-8",
    )

    libraries = sorted(
        {
            torch_dir / "_C.cpython-311-x86_64-linux-gnu.so",
            torch_dir / "lib/libtorch_global_deps.so",
            *(
                path
                for path in (torch_dir / "lib").glob("*.so*")
                if path.is_file()
            ),
        }
    )
    missing: set[str] = set()
    records: list[dict[str, object]] = []
    for index, library in enumerate(libraries):
        if not library.is_file():
            raise RuntimeError(f"required Torch ELF is absent: {library}")
        prefix = f"{index:02d}-{library.name}"
        ldd_path = output_dir / f"{prefix}.ldd.txt"
        readelf_path = output_dir / f"{prefix}.readelf-d.txt"
        ldd_rc = run_to_file(
            ("ldd", str(library)),
            ldd_path,
            environment=environment,
        )
        readelf_rc = run_to_file(
            ("readelf", "-d", str(library)),
            readelf_path,
            environment=environment,
        )
        ldd_text = ldd_path.read_text(encoding="utf-8")
        missing.update(
            match.group(1)
            for match in re.finditer(
                r"^\s*(\S+)\s+=>\s+not found\s*$",
                ldd_text,
                flags=re.MULTILINE,
            )
        )
        records.append(
            {
                "library": str(library),
                "ldd_returncode": ldd_rc,
                "ldd_path": str(ldd_path),
                "readelf_returncode": readelf_rc,
                "readelf_path": str(readelf_path),
            }
        )

    metadata_candidates = sorted(site.glob("torch-*.dist-info/METADATA"))
    if len(metadata_candidates) != 1:
        raise RuntimeError("Torch METADATA identity is not unique")
    metadata = metadata_candidates[0]
    metadata_copy = output_dir / "torch.METADATA"
    metadata_copy.write_bytes(metadata.read_bytes())
    contexts = cuda_context_count()
    if contexts != 0:
        raise RuntimeError("ELF closure capture unexpectedly saw CUDA contexts")
    summary = {
        "schema_version": 1,
        "status": "ELF_CLOSURE_CAPTURED",
        "worker_id": "4099544",
        "libraries": records,
        "resolved_ld_library_path": environment["LD_LIBRARY_PATH"],
        "nvidia_lib_dirs": [str(path) for path in nvidia_lib_dirs],
        "missing_sonames": sorted(missing),
        "torch_metadata": str(metadata_copy),
        "cuda_context_count": contexts,
        "cuda_operation_performed": False,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "ELF_CLOSURE_CAPTURED "
        f"missing={json.dumps(sorted(missing))} summary={summary_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ELF closure capture error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
