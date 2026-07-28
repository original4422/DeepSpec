#!/usr/bin/env python3
"""Create and verify the known CUDA 13.0 wheel-root lib64 link layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


CUDA_ROOT = Path(
    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/"
    "lib/python3.11/site-packages/nvidia/cu13"
)
EXPECTED_LINKS = {
    "libcudart.so": "../lib/libcudart.so.13",
    "libnvrtc.so": "../lib/libnvrtc.so.13",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(*command: str) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    lib = CUDA_ROOT / "lib"
    lib64 = CUDA_ROOT / "lib64"
    targets = {
        name: (lib64 / name, lib / Path(target).name)
        for name, target in EXPECTED_LINKS.items()
    }
    for name, (_, target) in targets.items():
        if not target.is_file():
            raise RuntimeError(f"required CUDA provider is absent for {name}")
    existing = list(lib64.iterdir()) if lib64.exists() else []
    if existing:
        for name, target_text in EXPECTED_LINKS.items():
            link = lib64 / name
            if not link.is_symlink() or os.readlink(link) != target_text:
                raise RuntimeError("existing CUDA lib64 layout differs")
        if set(existing) != {lib64 / name for name in EXPECTED_LINKS}:
            raise RuntimeError("CUDA lib64 contains unregistered entries")
        mutation = "already_valid"
    else:
        lib64.mkdir(parents=False, exist_ok=True)
        for name, target_text in EXPECTED_LINKS.items():
            (lib64 / name).symlink_to(target_text)
        mutation = "created"
    records: dict[str, dict[str, object]] = {}
    for name, (link, target) in targets.items():
        if link.resolve(strict=True) != target.resolve(strict=True):
            raise RuntimeError(f"resolved CUDA link differs for {name}")
        records[name] = {
            "link_path": str(link),
            "link_target": os.readlink(link),
            "resolved_path": str(target.resolve(strict=True)),
            "provider_size": target.stat().st_size,
            "provider_sha256": sha256(target),
        }
    payload = {
        "schema_version": 1,
        "status": "PASS",
        "cuda_root": str(CUDA_ROOT),
        "cuda_root_realpath": str(CUDA_ROOT.resolve(strict=True)),
        "mutation": mutation,
        "links": records,
        "nvcc_version": command_output(
            str(CUDA_ROOT / "bin/nvcc"), "--version"
        ),
        "ptxas_version": command_output(
            str(CUDA_ROOT / "bin/ptxas"), "--version"
        ),
        "cuda_operation_performed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"CUDA_LINK_LAYOUT_PASS evidence={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"CUDA link-layout error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
