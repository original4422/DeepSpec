#!/usr/bin/env python3
"""Install only the locked CUDA runtime proven missing by torch import."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Sequence


PACKAGE = "nvidia-cuda-runtime"
VERSION = "13.0.96"
URL = (
    "https://files.pythonhosted.org/packages/2e/24/"
    "d1558f3b68b1d26e706813b1d10aa1d785e4698c425af8db8edc3dced472/"
    "nvidia_cuda_runtime-13.0.96-py3-none-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.whl"
)
SHA256 = "7f82250d7782aa23b6cfe765ecc7db554bd3c2870c43f3d1821f1d18aebf0548"
REPO = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
ENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
UV = Path("/home/tiger/.local/bin/uv")
UV_CACHE = Path("/tmp/deepspec-hedge-v4-eagle3/uv-cache")
DEP_DIR = Path("/tmp/deepspec-hedge-v4-eagle3/direct-torch-04/deps")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: Sequence[str],
    *,
    stdout: Path,
    stderr: Path,
    environment: dict[str, str] | None = None,
) -> int:
    with stdout.open("w", encoding="utf-8") as stdout_stream, stderr.open(
        "w",
        encoding="utf-8",
    ) as stderr_stream:
        completed = subprocess.run(
            tuple(command),
            check=False,
            stdout=stdout_stream,
            stderr=stderr_stream,
            text=True,
            env=environment,
        )
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    attempt = args.attempt_dir.resolve()
    run_root = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
    ).resolve()
    if run_root not in attempt.parents:
        raise RuntimeError("attempt is outside Eagle3 run root")
    previous_path = attempt / "typing_extensions_install.json"
    output = attempt / "nvidia_cuda_runtime_install.json"
    if output.exists():
        raise RuntimeError(f"refusing to overwrite: {output}")
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("status") != "IMPORT_FAILED":
        raise RuntimeError("previous import is not a failed dependency probe")
    if "OSError: libcudart.so.13" not in previous.get("import_stderr", ""):
        raise RuntimeError("first dynamic-library blocker is not libcudart.so.13")

    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    matches = [
        package
        for package in lock["package"]
        if package.get("name") == PACKAGE
        and package.get("version") == VERSION
    ]
    if len(matches) != 1:
        raise RuntimeError("CUDA runtime lock identity is not unique")
    wheels = [wheel for wheel in matches[0]["wheels"] if wheel["url"] == URL]
    if len(wheels) != 1 or wheels[0]["hash"] != f"sha256:{SHA256}":
        raise RuntimeError("CUDA runtime wheel identity differs from uv.lock")

    UV_CACHE.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(UV_CACHE)
    if environment["UV_CACHE_DIR"] != (
        "/tmp/deepspec-hedge-v4-eagle3/uv-cache"
    ):
        raise RuntimeError("refusing non-lane uv cache")
    DEP_DIR.mkdir(parents=True, exist_ok=True)
    wheel = DEP_DIR / Path(URL).name
    partial = wheel.with_suffix(f"{wheel.suffix}.partial")
    if wheel.exists() or partial.exists():
        raise RuntimeError("refusing to reuse dependency scratch")
    subprocess.run(
        (
            "curl",
            "--fail",
            "--location",
            "--max-time",
            "180",
            "--silent",
            "--show-error",
            "--output",
            str(partial),
            URL,
        ),
        check=True,
    )
    if sha256(partial) != SHA256:
        raise RuntimeError("CUDA runtime wheel SHA-256 mismatch")
    partial.rename(wheel)

    uv_stdout = attempt / "nvidia_cuda_runtime_uv.stdout.txt"
    uv_stderr = attempt / "nvidia_cuda_runtime_uv.stderr.txt"
    uv_rc = run(
        (
            str(UV),
            "pip",
            "install",
            "--python",
            str(ENV / "bin/python"),
            "--no-deps",
            str(wheel),
        ),
        stdout=uv_stdout,
        stderr=uv_stderr,
        environment=environment,
    )
    if uv_rc != 0:
        raise RuntimeError(f"uv local CUDA runtime install failed: {uv_rc}")

    import_environment = dict(environment)
    import_environment["LD_LIBRARY_PATH"] = (
        "/usr/local/cuda/compat:/usr/local/cuda/lib64:"
        f"{environment.get('LD_LIBRARY_PATH', '')}"
    )
    import_stdout = attempt / "nvidia_cuda_runtime_import.stdout.txt"
    import_stderr = attempt / "nvidia_cuda_runtime_import.stderr.txt"
    import_rc = run(
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
        stdout=import_stdout,
        stderr=import_stderr,
        environment=import_environment,
    )
    payload = {
        "schema_version": 1,
        "status": "IMPORT_PASS" if import_rc == 0 else "IMPORT_FAILED",
        "dependency": f"{PACKAGE}=={VERSION}",
        "wheel_path": str(wheel),
        "wheel_sha256": SHA256,
        "uv_cache_dir": str(UV_CACHE),
        "uv_local_no_deps": True,
        "uv_returncode": uv_rc,
        "import_returncode": import_rc,
        "import_stdout": import_stdout.read_text(encoding="utf-8"),
        "import_stderr": import_stderr.read_text(encoding="utf-8"),
        "cuda_operation_performed": False,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"CUDA_RUNTIME_{payload['status']} evidence={output}",
        file=sys.stdout if import_rc == 0 else sys.stderr,
    )
    return import_rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"CUDA runtime dependency error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
