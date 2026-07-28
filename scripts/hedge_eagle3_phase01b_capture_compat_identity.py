#!/usr/bin/env python3
"""Verify the existing CUDA 13.0 forward-compat prefix against Phase 03."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


EXPECTED_PACKAGE_SHA256 = (
    "2fb9026a83487f19d98c21671af4d93cc78ec35285f6e034c7f4b6baaaadefd9"
)
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)
ARCHIVE = Path(
    "/home/tiger/.cache/deepspec-phase03-20260728T163751Z/"
    "cuda-compat-13-0_580.173.02-1_amd64.deb"
)
PHASE03_EVIDENCE = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/runs/"
    "20260728T171850Z-phase03-minimal-03/cuda_toolchain.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    prior = json.loads(PHASE03_EVIDENCE.read_text(encoding="utf-8"))
    forward = prior.get("forward_compatibility", {})
    if (
        prior.get("status") != "PASS"
        or forward.get("path") != str(COMPAT_ROOT)
        or forward.get("package_sha256") != EXPECTED_PACKAGE_SHA256
        or forward.get("package")
        != "cuda-compat-13-0_580.173.02-1_amd64.deb"
    ):
        raise RuntimeError("Phase 03 compatibility evidence differs")
    archive_hash = sha256(ARCHIVE)
    if archive_hash != EXPECTED_PACKAGE_SHA256:
        raise RuntimeError("cached compatibility package SHA-256 differs")
    libcuda_link = COMPAT_ROOT / "libcuda.so"
    libcuda_soname_link = COMPAT_ROOT / "libcuda.so.1"
    if not libcuda_link.is_symlink() or not libcuda_soname_link.is_symlink():
        raise RuntimeError("expected libcuda symlink chain is absent")
    if os.readlink(libcuda_link) != "libcuda.so.1":
        raise RuntimeError("libcuda.so symlink target differs")
    if os.readlink(libcuda_soname_link) != "libcuda.so.580.173.02":
        raise RuntimeError("libcuda.so.1 symlink target differs")
    resolved = libcuda_soname_link.resolve(strict=True)
    if resolved != COMPAT_ROOT / "libcuda.so.580.173.02":
        raise RuntimeError("resolved libcuda entity differs")
    readelf = subprocess.run(
        ("readelf", "-d", str(resolved)),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    if "Library soname: [libcuda.so.1]" not in readelf:
        raise RuntimeError("compat libcuda SONAME differs")
    contexts = cuda_context_count()
    if contexts != 0:
        raise RuntimeError("compat verification requires zero contexts")
    payload = {
        "schema_version": 1,
        "status": "PASS",
        "worker_id": "4099544",
        "phase03_evidence": str(PHASE03_EVIDENCE),
        "phase03_validation_status": prior["status"],
        "compat_root": str(COMPAT_ROOT),
        "package_archive": str(ARCHIVE),
        "package_sha256": archive_hash,
        "libcuda_symlinks": {
            str(libcuda_link): os.readlink(libcuda_link),
            str(libcuda_soname_link): os.readlink(libcuda_soname_link),
        },
        "libcuda_resolved_path": str(resolved),
        "libcuda_size": resolved.stat().st_size,
        "libcuda_sha256": sha256(resolved),
        "libcuda_soname": "libcuda.so.1",
        "cuda_context_count": contexts,
        "mutation_performed": False,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"COMPAT_IDENTITY_PASS evidence={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"compat identity error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
