#!/usr/bin/env python3
"""Install one lock-pinned dependency proven missing by the last torch import."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any, Sequence


SPECS: dict[str, dict[str, str]] = {
    "cupti": {
        "package": "nvidia-cuda-cupti",
        "version": "13.0.85",
        "url": (
            "https://files.pythonhosted.org/packages/33/6d/"
            "737d164b4837a9bbd202f5ae3078975f0525a55730fe871d8ed4e3b952b0/"
            "nvidia_cuda_cupti-13.0.85-py3-none-manylinux_2_25_x86_64.whl"
        ),
        "sha256": (
            "4eb01c08e859bf924d222250d2e8f8b8ff6d3db4721288cf35d14252a4d933c8"
        ),
        "previous": "nvidia_cuda_runtime_install.json",
        "required_error": "ImportError: libcupti.so.13",
        "output": "nvidia_cuda_cupti_install.json",
    },
    "cufft": {
        "package": "nvidia-cufft",
        "version": "12.0.0.61",
        "url": (
            "https://files.pythonhosted.org/packages/a8/2f/"
            "7b57e29836ea8714f81e9898409196f47d772d5ddedddf1592eadb8ab743/"
            "nvidia_cufft-12.0.0.61-py3-none-manylinux2014_x86_64."
            "manylinux_2_17_x86_64.whl"
        ),
        "sha256": (
            "6c44f692dce8fd5ffd3e3df134b6cdb9c2f72d99cf40b62c32dde45eea9ddad3"
        ),
        "previous": "nvidia_cuda_cupti_install.json",
        "required_error": "ImportError: libcufft.so.12",
        "output": "nvidia_cufft_install.json",
    },
    "cublas": {
        "package": "nvidia-cublas",
        "version": "13.1.0.3",
        "url": (
            "https://files.pythonhosted.org/packages/e7/44/"
            "423ac00af4dd95a5aeb27207e2c0d9b7118702149bf4704c3ddb55bb7429/"
            "nvidia_cublas-13.1.0.3-py3-none-manylinux_2_27_x86_64.whl"
        ),
        "sha256": (
            "ee8722c1f0145ab246bccb9e452153b5e0515fd094c3678df50b2a0888b8b171"
        ),
        "previous": "nvidia_cufft_install.json",
        "required_error": "ImportError: libcublas.so.13",
        "output": "nvidia_cublas_install.json",
    },
}
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
    environment: dict[str, str],
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
    parser.add_argument("--dependency", choices=sorted(SPECS), required=True)
    args = parser.parse_args(argv)
    spec: dict[str, Any] = SPECS[args.dependency]
    attempt = args.attempt_dir.resolve()
    run_root = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
    ).resolve()
    if run_root not in attempt.parents:
        raise RuntimeError("attempt is outside Eagle3 run root")
    previous_path = attempt / spec["previous"]
    output = attempt / spec["output"]
    if output.exists():
        raise RuntimeError(f"refusing to overwrite: {output}")
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("status") != "IMPORT_FAILED":
        raise RuntimeError("previous import is not a failed dependency probe")
    if spec["required_error"] not in previous.get("import_stderr", ""):
        raise RuntimeError("requested dependency does not match the actual error")

    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    matches = [
        package
        for package in lock["package"]
        if package.get("name") == spec["package"]
        and package.get("version") == spec["version"]
    ]
    if len(matches) != 1:
        raise RuntimeError("dependency lock identity is not unique")
    wheels = [
        wheel
        for wheel in matches[0]["wheels"]
        if wheel["url"] == spec["url"]
    ]
    if (
        len(wheels) != 1
        or wheels[0]["hash"] != f"sha256:{spec['sha256']}"
    ):
        raise RuntimeError("dependency wheel identity differs from uv.lock")

    UV_CACHE.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(UV_CACHE)
    if environment["UV_CACHE_DIR"] != (
        "/tmp/deepspec-hedge-v4-eagle3/uv-cache"
    ):
        raise RuntimeError("refusing non-lane uv cache")
    DEP_DIR.mkdir(parents=True, exist_ok=True)
    wheel = DEP_DIR / Path(spec["url"]).name
    partial = wheel.with_suffix(f"{wheel.suffix}.partial")
    if wheel.exists() or partial.exists():
        raise RuntimeError("refusing to reuse dependency scratch")
    subprocess.run(
        (
            "curl",
            "--fail",
            "--location",
            "--max-time",
            "300",
            "--silent",
            "--show-error",
            "--output",
            str(partial),
            spec["url"],
        ),
        check=True,
    )
    if sha256(partial) != spec["sha256"]:
        raise RuntimeError("dependency wheel SHA-256 mismatch")
    partial.rename(wheel)

    prefix = spec["output"].removesuffix("_install.json")
    uv_stdout = attempt / f"{prefix}_uv.stdout.txt"
    uv_stderr = attempt / f"{prefix}_uv.stderr.txt"
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
        raise RuntimeError(f"uv local dependency install failed: {uv_rc}")

    import_environment = dict(environment)
    import_environment["LD_LIBRARY_PATH"] = (
        "/usr/local/cuda/compat:/usr/local/cuda/lib64:"
        f"{environment.get('LD_LIBRARY_PATH', '')}"
    )
    import_stdout = attempt / f"{prefix}_import.stdout.txt"
    import_stderr = attempt / f"{prefix}_import.stderr.txt"
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
        "dependency": f"{spec['package']}=={spec['version']}",
        "wheel_path": str(wheel),
        "wheel_sha256": spec["sha256"],
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
        f"{args.dependency.upper()}_{payload['status']} evidence={output}",
        file=sys.stdout if import_rc == 0 else sys.stderr,
    )
    return import_rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"locked dependency error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
