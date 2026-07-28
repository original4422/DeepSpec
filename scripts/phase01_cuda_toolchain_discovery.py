#!/usr/bin/env python3
"""Read-only discovery of system and private CUDA toolchain prefixes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Sequence


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: Sequence[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return {
            "argv": list(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(command),
            "returncode": None,
            "stdout": getattr(error, "stdout", "") or "",
            "stderr": getattr(error, "stderr", "") or str(error),
            "exception": type(error).__name__,
        }


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def marker(path: pathlib.Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "marker_path": str(path),
        "marker_exists": path.is_file(),
    }
    if not path.is_file():
        return result
    value = path.read_text(encoding="utf-8").strip()
    target = pathlib.Path(value)
    result.update(
        {
            "value": value,
            "target_exists": target.exists(),
            "target_realpath": (
                str(target.resolve()) if target.exists() else None
            ),
        }
    )
    return result


def write_json(path: pathlib.Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    artifact_dir = pathlib.Path(args.artifact_dir)

    compat = marker(pathlib.Path("/home/tiger/cuda13compat/COMPAT_DIR"))
    if compat.get("target_exists"):
        compat_dir = pathlib.Path(compat["value"])
        candidates = sorted(compat_dir.glob("libcuda.so*"))
        compat["libcuda_files"] = [
            {
                "path": str(path),
                "realpath": str(path.resolve()),
                "size_bytes": path.resolve().stat().st_size,
                "sha256": sha256_file(path.resolve()),
            }
            for path in candidates
            if path.resolve().is_file()
        ]

    ptxas = marker(pathlib.Path("/home/tiger/cuda13nvcc/PTXAS"))
    if ptxas.get("target_exists"):
        ptxas_path = pathlib.Path(ptxas["value"])
        ptxas["size_bytes"] = ptxas_path.stat().st_size
        ptxas["sha256"] = sha256_file(ptxas_path)
        ptxas["version_probe"] = run([str(ptxas_path), "--version"])

    payload = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "worker_id": args.worker_id,
        "probe_created_cuda_context": False,
        "system_nvcc": run(["/usr/local/cuda/bin/nvcc", "--version"]),
        "private_cuda_compat_discovery": compat,
        "private_ptxas_discovery": ptxas,
        "formal_toolchain_selected": False,
        "phase03_constraint": (
            "Provision and validate one self-consistent CUDA 13.0 JIT "
            "toolchain and driver forward-compatibility prefix. The "
            "discovered CUDA 13.3 private compiler/compat artifacts must "
            "not be mixed with CUDA 13.0 runtime headers."
        ),
    }
    write_json(artifact_dir / "cuda_toolchain_discovery.json", payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
