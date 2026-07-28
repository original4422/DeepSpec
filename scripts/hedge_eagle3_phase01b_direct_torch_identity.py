#!/usr/bin/env python3
"""Resolve and attest the exact local-wheel fallback from uv.lock."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib
from typing import Any, Sequence


EXPECTED_URL = (
    "https://download-r2.pytorch.org/whl/cu130/"
    "torch-2.11.0%2Bcu130-cp311-cp311-manylinux_2_28_x86_64.whl"
)
EXPECTED_HASH = (
    "sha256:225b22e0a4e36ea573d3a68796e6816a"
    "160616f67e8b8c55683a88bf7777f4cd"
)
EXPECTED_UUIDS = (
    "GPU-ea15ff88-dadd-ba7b-179d-484c1f152e63",
    "GPU-eef6edd3-6d93-5640-9e99-3b2c01987c9f",
    "GPU-357ebd70-0a3c-7397-55b2-2ff509736053",
    "GPU-3123de5a-168b-af3d-9f36-57603da3b11b",
    "GPU-eb1b03fe-54ee-0844-0b58-b4958a5a7cc8",
    "GPU-09e26802-d40f-473a-73bd-5220fd48c6f5",
    "GPU-23fcb1c0-804b-2487-0fb3-d7d8e558ca20",
    "GPU-e387b240-1c16-7bed-8291-66a12ba97f06",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: Sequence[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(
        tuple(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {command!r}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def gpu_inventory() -> list[dict[str, Any]]:
    payload = run(
        (
            "nvidia-smi",
            "--query-gpu=index,uuid,name,compute_cap,driver_version",
            "--format=csv,noheader,nounits",
        )
    )
    rows: list[dict[str, Any]] = []
    for fields in csv.reader(payload.splitlines(), skipinitialspace=True):
        rows.append(
            {
                "index": int(fields[0].strip()),
                "uuid": fields[1].strip(),
                "model": fields[2].strip(),
                "compute_capability": fields[3].strip(),
                "driver_version": fields[4].strip(),
            }
        )
    if [row["index"] for row in rows] != list(range(8)):
        raise RuntimeError("not exact physical GPU indices 0..7")
    if tuple(row["uuid"] for row in rows) != EXPECTED_UUIDS:
        raise RuntimeError("GPU UUID mapping differs from Phase 00")
    if not all(row["model"] == "NVIDIA H20" for row in rows):
        raise RuntimeError("not exact 8x NVIDIA H20")
    return rows


def compute_context_count() -> int:
    payload = run(
        (
            "nvidia-smi",
            "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        )
    )
    return len([line for line in payload.splitlines() if line.strip()])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    lock_path = repo / "uv.lock"
    output = args.output.resolve()
    run_root = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
    ).resolve()
    if run_root not in output.parents:
        raise RuntimeError("output is outside the Eagle3 run root")
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=False)
    if run(("git", "diff", "--quiet", "--", "uv.lock"), cwd=repo):
        raise AssertionError("unreachable")
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = [
        package
        for package in lock["package"]
        if package.get("name") == "torch"
        and package.get("version") == "2.11.0+cu130"
    ]
    if len(packages) != 1:
        raise RuntimeError("lock does not contain one pinned torch package")
    wheels = [
        wheel
        for wheel in packages[0]["wheels"]
        if wheel["url"] == EXPECTED_URL
    ]
    if len(wheels) != 1 or wheels[0]["hash"] != EXPECTED_HASH:
        raise RuntimeError("locked cp311 x86_64 wheel identity differs")

    wheel_tag = re.search(
        r"-(cp311)-(cp311)-(manylinux_2_28_x86_64)\.whl$",
        EXPECTED_URL,
    )
    if wheel_tag is None:
        raise RuntimeError("wheel tag does not match pinned expectation")
    libc_name, libc_version = platform.libc_ver()
    libc_parts = tuple(int(value) for value in libc_version.split(".")[:2])
    python_compatible = sys.version_info[:2] == (3, 11)
    architecture_compatible = platform.machine() == "x86_64"
    libc_compatible = libc_name == "glibc" and libc_parts >= (2, 28)
    gpus = gpu_inventory()
    contexts = compute_context_count()
    if contexts != 0:
        raise RuntimeError("CUDA contexts exist before direct acquisition")

    payload = {
        "schema_version": 1,
        "status": "DIRECT_ARTIFACT_IDENTITY_PASS",
        "recorded_at": utc_now(),
        "worker_id": "4099544",
        "hostname": platform.node(),
        "repo_root": str(repo),
        "repo_head": run(("git", "rev-parse", "HEAD"), cwd=repo),
        "lock_path": str(lock_path),
        "lock_git_blob": run(("git", "rev-parse", "HEAD:uv.lock"), cwd=repo),
        "lock_last_commit": run(
            ("git", "log", "-1", "--format=%H", "--", "uv.lock"),
            cwd=repo,
        ),
        "lock_sha256": sha256(lock_path),
        "lock_dirty": False,
        "torch_version": packages[0]["version"],
        "wheel_url": EXPECTED_URL,
        "wheel_hash": EXPECTED_HASH,
        "wheel_filename": (
            "torch-2.11.0+cu130-cp311-cp311-"
            "manylinux_2_28_x86_64.whl"
        ),
        "wheel_tags": {
            "python": wheel_tag.group(1),
            "abi": wheel_tag.group(2),
            "platform": wheel_tag.group(3),
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "python_cache_tag": sys.implementation.cache_tag,
            "machine": platform.machine(),
            "libc_name": libc_name,
            "libc_version": libc_version,
        },
        "compatibility": {
            "python_cp311": python_compatible,
            "abi_cp311": python_compatible,
            "x86_64": architecture_compatible,
            "manylinux_2_28": libc_compatible,
            "cpu_wheel_tags_compatible": (
                python_compatible
                and architecture_compatible
                and libc_compatible
            ),
            "cuda_distribution": "cu130",
            "gpu_runtime_candidate": (
                all(row["compute_capability"] == "9.0" for row in gpus)
                and all(row["model"] == "NVIDIA H20" for row in gpus)
            ),
            "gpu_runtime_note": (
                "Wheel tags cover Python/ABI/CPU platform. H20 CUDA usability "
                "remains a real torch import/CUDA gate; keepalive uses the "
                "validated /usr/local/cuda/compat:/usr/local/cuda/lib64 layout."
            ),
        },
        "gpus": gpus,
        "compute_context_count": contexts,
        "environment_modified": False,
    }
    if not payload["compatibility"]["cpu_wheel_tags_compatible"]:
        raise RuntimeError("locked wheel tags are incompatible with the venv")
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"DIRECT_ARTIFACT_IDENTITY_PASS output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"direct torch identity error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
