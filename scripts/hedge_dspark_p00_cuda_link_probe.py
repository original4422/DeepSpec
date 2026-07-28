#!/usr/bin/env python3
"""Guard and verify the CUDA 13 lib64 linker seam for the P00 venv."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from typing import Any


CUDA_ROOT = Path(
    "/home/tiger/venvs/hedge-v4-dspark/"
    "lib/python3.11/site-packages/nvidia/cu13"
)
LINKS = {
    "libcudart.so": "../lib/libcudart.so.13",
    "libnvrtc.so": "../lib/libnvrtc.so.13",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(argv: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        argv, capture_output=True, text=True, check=False, timeout=30
    )
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def ensure_links() -> list[dict[str, Any]]:
    source_dir = CUDA_ROOT / "lib"
    link_dir = CUDA_ROOT / "lib64"
    if not CUDA_ROOT.is_dir() or not source_dir.is_dir():
        raise RuntimeError(f"missing fixed CUDA root: {CUDA_ROOT}")
    if link_dir.is_symlink():
        raise RuntimeError(f"refusing symlinked lib64 directory: {link_dir}")
    link_dir.mkdir(exist_ok=True)

    records: list[dict[str, Any]] = []
    for link_name, target in LINKS.items():
        destination = link_dir / link_name
        source = (link_dir / target).resolve(strict=True)
        if destination.is_symlink():
            if os.readlink(destination) != target:
                raise RuntimeError(
                    f"conflicting link: {destination} -> "
                    f"{os.readlink(destination)}"
                )
            action = "verified"
        elif destination.exists():
            raise RuntimeError(f"refusing non-symlink: {destination}")
        else:
            destination.symlink_to(target)
            action = "created"
        if destination.resolve(strict=True) != source:
            raise RuntimeError(f"resolved link mismatch: {destination}")
        records.append(
            {
                "path": str(destination),
                "target": os.readlink(destination),
                "resolved": str(destination.resolve(strict=True)),
                "action": action,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    before = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    first = ensure_links()
    second = ensure_links()
    probe = run(
        [
            "/usr/bin/cc",
            "-shared",
            "-Wl,--no-as-needed",
            f"-L{CUDA_ROOT / 'lib64'}",
            "-lcudart",
            "-lnvrtc",
            "-o",
            "/dev/null",
        ]
    )
    after = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    errors = []
    if probe["returncode"] != 0:
        errors.append("link probe failed")
    if any(record["action"] != "verified" for record in second):
        errors.append("second guarded link pass was not idempotent")
    if before["returncode"] != 0 or after["returncode"] != 0:
        errors.append("could not query CUDA contexts")
    if before["stdout"] != after["stdout"]:
        errors.append("CUDA context inventory changed during CPU link probe")
    payload = {
        "schema_version": 1,
        "authorized_phase": "P00",
        "observed_at_utc": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "cuda_root": str(CUDA_ROOT),
        "first_guarded_pass": first,
        "second_guarded_pass": second,
        "probe": probe,
        "contexts_before": before,
        "contexts_after": after,
        "errors": errors,
        "model_started": False,
    }
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    output = args.artifact_dir / "cuda_link_probe.json"
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    print(json.dumps({"status": payload["status"], "errors": errors}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
