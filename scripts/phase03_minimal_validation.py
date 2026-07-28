#!/usr/bin/env python3
"""Collect the user-authorized minimal Phase 03 environment evidence."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import pathlib
import subprocess
import sys
from typing import Any


ATTEMPT_ID = "20260728T171850Z-phase03-minimal-03"
VALIDATION_LEVEL = "operational_minimal_user_authorized"
EXPECTED_COMMIT = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
EXPECTED_VENV = pathlib.Path("/home/tiger/venvs/deepspec-dspark")
SOURCE_ROOT = pathlib.Path(
    "/home/tiger/src/"
    "deepspec-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
)
CUDA_ROOT = EXPECTED_VENV / "lib/python3.11/site-packages/nvidia/cu13"
COMPAT_ROOT = pathlib.Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)
RUST_ROOT = pathlib.Path("/home/tiger/toolchains/deepspec-rust-1.90.0")
PROTOC = pathlib.Path("/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc")


def run(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout.strip()


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def package_record(name: str) -> dict[str, str]:
    distribution = importlib.metadata.distribution(name)
    return {
        "version": distribution.version,
        "location": str(pathlib.Path(distribution.locate_file("")).resolve()),
    }


def source_matches(pattern: str, relative_root: str) -> list[str]:
    output = run(
        "rg",
        "-n",
        "--glob",
        "*.py",
        "-m",
        "5",
        pattern,
        str(SOURCE_ROOT / relative_root),
    )
    return output.splitlines()


def collect_identity(output_dir: pathlib.Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    print("minimal identity: checking uv dependency consistency", flush=True)
    pip_check = subprocess.run(
        [
            "/home/tiger/.local/bin/uv",
            "pip",
            "check",
            "--python",
            str(EXPECTED_VENV / "bin/python"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (output_dir / "uv_pip_check.log").write_text(
        pip_check.stdout, encoding="utf-8"
    )
    if pip_check.returncode != 0:
        errors.append(f"uv pip check returned {pip_check.returncode}")

    print("minimal identity: importing torch", flush=True)
    import torch

    print("minimal identity: imported torch; importing sglang", flush=True)
    import sglang

    print("minimal identity: imported sglang", flush=True)
    sglang_distribution = importlib.metadata.distribution("sglang")
    direct_url_path = next(
        pathlib.Path(sglang_distribution.locate_file(file))
        for file in sglang_distribution.files or []
        if str(file).endswith("direct_url.json")
    )
    direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
    installed_commit = direct_url.get("vcs_info", {}).get("commit_id")
    source_commit = run("git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD")
    source_status = run(
        "git", "-C", str(SOURCE_ROOT), "status", "--porcelain=v1"
    )
    source_tag = run(
        "git", "-C", str(SOURCE_ROOT), "describe", "--tags", "--exact-match", "HEAD"
    )
    source_origin = run(
        "git", "-C", str(SOURCE_ROOT), "remote", "get-url", "origin"
    )
    sglang_path = pathlib.Path(sglang.__file__).resolve()
    torch_path = pathlib.Path(torch.__file__).resolve()

    if pip_check.returncode != 0:
        errors.append("formal environment has dependency conflicts")
    if not str(sys.executable).startswith(str(EXPECTED_VENV)):
        errors.append(f"unexpected Python executable: {sys.executable}")
    if not str(sglang_path).startswith(str(EXPECTED_VENV)):
        errors.append(f"SGLang imported outside formal venv: {sglang_path}")
    if not str(torch_path).startswith(str(EXPECTED_VENV)):
        errors.append(f"PyTorch imported outside formal venv: {torch_path}")
    if sglang_distribution.version != "0.5.16":
        errors.append(f"unexpected SGLang version: {sglang_distribution.version}")
    if installed_commit != EXPECTED_COMMIT:
        errors.append(f"unexpected installed SGLang commit: {installed_commit}")
    if source_commit != EXPECTED_COMMIT:
        errors.append(f"unexpected source commit: {source_commit}")
    if source_status:
        errors.append("registered SGLang source worktree is dirty")
    if source_tag != "v0.5.16":
        errors.append(f"unexpected source tag: {source_tag}")
    if source_origin != "https://github.com/sgl-project/sglang.git":
        errors.append(f"unexpected source origin: {source_origin}")
    print("minimal identity: checking DSpark and packed-FP4 source markers", flush=True)
    marker_queries = {
        "dspark": (
            "DSPARK",
            "python/sglang/srt/speculative/spec_info.py",
        ),
        "flashinfer_mxfp4": (
            'FLASHINFER_MXFP4 = "flashinfer_mxfp4"',
            "python/sglang/srt/layers/moe/utils.py",
        ),
        "marlin": (
            'MARLIN = "marlin"',
            "python/sglang/srt/layers/moe/utils.py",
        ),
    }
    markers: dict[str, list[str]] = {}
    for name, (pattern, relative_root) in marker_queries.items():
        try:
            markers[name] = source_matches(pattern, relative_root)
        except subprocess.CalledProcessError as error:
            markers[name] = []
            errors.append(f"missing source marker {name}: exit {error.returncode}")

    package_names = (
        "cuda-bindings",
        "cuda-python",
        "flashinfer-python",
        "nvidia-cuda-cccl",
        "nvidia-cuda-crt",
        "nvidia-cuda-nvcc",
        "nvidia-cuda-nvrtc",
        "nvidia-cuda-runtime",
        "nvidia-nccl-cu13",
        "nvidia-nvjitlink",
        "nvidia-nvvm",
        "sglang",
        "sglang-kernel",
        "torch",
        "torchaudio",
        "torchvision",
        "triton",
    )
    packages = {name: package_record(name) for name in package_names}
    dependency_report = {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS" if pip_check.returncode == 0 else "FAIL",
        "validation_level": VALIDATION_LEVEL,
        "uv": {
            "version": run("/home/tiger/.local/bin/uv", "--version"),
            "pip_check_return_code": pip_check.returncode,
            "pip_check_log": "uv_pip_check.log",
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version,
        },
        "torch_runtime_visibility": {
            "built_for_cuda": torch.version.cuda,
            "import_path": str(torch_path),
            "worker_visibility_artifact": "worker_cuda_visibility.json",
        },
        "packages": packages,
    }
    write_json(output_dir / "dependency_versions.json", dependency_report)

    source_report = {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS" if not errors else "FAIL",
        "validation_level": VALIDATION_LEVEL,
        "release": sglang_distribution.version,
        "import_path": str(sglang_path),
        "direct_url_path": str(direct_url_path),
        "direct_url": direct_url,
        "registered_source": {
            "path": str(SOURCE_ROOT),
            "commit": source_commit,
            "tag": source_tag,
            "origin": source_origin,
            "clean": not bool(source_status),
        },
        "required_source_markers": markers,
        "errors": errors,
    }
    write_json(output_dir / "sglang_source_identity.json", source_report)

    nvcc = CUDA_ROOT / "bin/nvcc"
    ptxas = CUDA_ROOT / "bin/ptxas"
    cuda_header = CUDA_ROOT / "include/cuda.h"
    runtime_header = CUDA_ROOT / "include/cuda_runtime.h"
    compat_libcuda = COMPAT_ROOT / "libcuda.so.1"
    toolchain_report = {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "validation_level": VALIDATION_LEVEL,
        "pytorch_cuda_build": torch.version.cuda,
        "cuda_home": str(CUDA_ROOT),
        "nvcc_version": run(str(nvcc), "--version"),
        "ptxas_version": run(str(ptxas), "--version"),
        "cuda_version_macro": run(
            "rg", "^#define CUDA_VERSION ", str(cuda_header)
        ),
        "forward_compatibility": {
            "path": str(COMPAT_ROOT),
            "package": "cuda-compat-13-0_580.173.02-1_amd64.deb",
            "package_sha256": (
                "2fb9026a83487f19d98c21671af4d93c"
                "c78ec35285f6e034c7f4b6baaaadefd9"
            ),
            "libcuda_path": str(compat_libcuda),
        },
        "rust": {
            "rustc": run(str(RUST_ROOT / "cargo/bin/rustc"), "--version"),
            "cargo": run(str(RUST_ROOT / "cargo/bin/cargo"), "--version"),
        },
        "protoc": {
            "path": str(PROTOC),
            "version": run(str(PROTOC), "--version"),
        },
        "errors": [],
    }
    write_json(output_dir / "cuda_toolchain.json", toolchain_report)
    print("minimal identity: PASS" if not errors else "minimal identity: FAIL", flush=True)
    return 0 if not errors else 1


def collect_worker_visibility(output_path: pathlib.Path) -> int:
    print("worker visibility: importing torch", flush=True)
    import torch

    available = bool(torch.cuda.is_available())
    count = int(torch.cuda.device_count())
    errors: list[str] = []
    if not available:
        errors.append("torch.cuda.is_available() is false")
    if count != 4:
        errors.append(f"torch.cuda.device_count() is {count}, expected 4")

    report = {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS" if not errors else "FAIL",
        "validation_level": VALIDATION_LEVEL,
        "python_executable": sys.executable,
        "torch_import_path": str(pathlib.Path(torch.__file__).resolve()),
        "torch_cuda_available": available,
        "torch_cuda_device_count": count,
        "cuda_arithmetic_performed": False,
        "model_loaded": False,
        "errors": errors,
    }
    write_json(output_path, report)
    print(
        f"worker visibility: available={available} device_count={count}",
        flush=True,
    )
    return 0 if not errors else 1


def finalize(output_dir: pathlib.Path) -> int:
    dependency = json.loads(
        (output_dir / "dependency_versions.json").read_text(encoding="utf-8")
    )
    source = json.loads(
        (output_dir / "sglang_source_identity.json").read_text(encoding="utf-8")
    )
    toolchain = json.loads(
        (output_dir / "cuda_toolchain.json").read_text(encoding="utf-8")
    )
    worker_visibility = json.loads(
        (output_dir / "worker_cuda_visibility.json").read_text(encoding="utf-8")
    )
    keepalive_text = (output_dir / "keepalive_after.txt").read_text(
        encoding="utf-8"
    )
    checks = {
        "uv_pip_check": dependency["status"] == "PASS",
        "formal_python_imported_torch_and_sglang": (
            str(dependency["python"]["executable"]).startswith(str(EXPECTED_VENV))
            and str(source["import_path"]).startswith(str(EXPECTED_VENV))
        ),
        "torch_cuda_available": worker_visibility["torch_cuda_available"] is True,
        "torch_cuda_device_count_4": (
            worker_visibility["torch_cuda_device_count"] == 4
        ),
        "sglang_fixed_commit": (
            source["direct_url"].get("vcs_info", {}).get("commit_id")
            == EXPECTED_COMMIT
            and source["registered_source"]["commit"] == EXPECTED_COMMIT
        ),
        "required_source_markers": all(source["required_source_markers"].values()),
        "keepalive_restored": "HEALTHY" in keepalive_text,
        "model_not_loaded": True,
    }
    gate = {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation_level": VALIDATION_LEVEL,
        "checks": checks,
        "model_loaded": False,
        "scope": (
            "Phase 03 environment-only validation; no checkpoint access, "
            "model load, server start, or kernel/backend execution"
        ),
        "limitations": [
            "No CUDA arithmetic, kernel execution, or per-GPU operation was run.",
            "DSpark and MoE backends were verified as fixed-source markers, not executed.",
        ],
    }
    write_json(output_dir / "phase03_gate.json", gate)
    return 0 if gate["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("identity", "worker", "finalize"))
    parser.add_argument("path", type=pathlib.Path)
    args = parser.parse_args()
    if args.mode == "identity":
        return collect_identity(args.path)
    if args.mode == "worker":
        return collect_worker_visibility(args.path)
    return finalize(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
