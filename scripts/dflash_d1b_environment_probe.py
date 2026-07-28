#!/usr/bin/env python3
"""Record the pinned DFlash environment without allocating a CUDA context."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import pathlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Sequence


EXPECTED_WORKER_ID = "4099543"
EXPECTED_SOURCE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
EXPECTED_SOURCE_TAG = "v0.5.16"
EXPECTED_PYTHON = pathlib.Path(
    "/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
)
EXPECTED_SOURCE = pathlib.Path(
    "/home/tiger/src/deepspec-sglang-hedge-dflash"
)
EXPECTED_WORKTREE = pathlib.Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
EXPECTED_STATUS_SCRIPT = (
    EXPECTED_WORKTREE / "scripts/dflash_d0_keepalive_status.sh"
)
EXPECTED_CUDA_ROOT = (
    EXPECTED_PYTHON.parent.parent
    / "lib/python3.11/site-packages/nvidia/cu13"
)
EXPECTED_COMPAT_ROOT = pathlib.Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)
EXPECTED_UV = pathlib.Path("/home/tiger/.local/bin/uv")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    argv: Sequence[str],
    *,
    cwd: pathlib.Path | None = None,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {list(argv)!r}\n"
            f"{result.stdout}"
        )
    return result


def git(path: pathlib.Path, *args: str) -> str:
    return run(["git", "-C", str(path), *args]).stdout.strip()


def distribution(name: str) -> dict[str, Any]:
    dist = importlib.metadata.distribution(name)
    direct_url: dict[str, Any] | None = None
    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text:
        direct_url = json.loads(direct_url_text)
    return {
        "name": name,
        "version": dist.version,
        "location": str(pathlib.Path(dist.locate_file("")).resolve()),
        "direct_url": direct_url,
    }


def module_identity(name: str) -> dict[str, str | None]:
    module = importlib.import_module(name)
    return {
        "module": name,
        "version": getattr(module, "__version__", None),
        "file": str(pathlib.Path(module.__file__).resolve())
        if getattr(module, "__file__", None)
        else None,
    }


def compute_apps() -> list[dict[str, str]]:
    result = run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name",
            "--format=csv,noheader,nounits",
        ]
    )
    records: list[dict[str, str]] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line == "No running processes found":
            continue
        fields = [item.strip() for item in line.split(",", maxsplit=2)]
        if len(fields) != 3:
            raise RuntimeError(f"unexpected nvidia-smi compute row: {raw_line!r}")
        records.append(
            {
                "gpu_uuid": fields[0],
                "host_pid": fields[1],
                "process_name": fields[2],
            }
        )
    return sorted(
        records,
        key=lambda item: (
            item["gpu_uuid"],
            item["host_pid"],
            item["process_name"],
        ),
    )


def package_versions() -> dict[str, Any]:
    import torch

    modules = {
        "sglang": module_identity("sglang"),
        "sgl_kernel": module_identity("sgl_kernel"),
        "flashinfer": module_identity("flashinfer"),
        "triton": module_identity("triton"),
        "torch": module_identity("torch"),
    }
    distributions = {
        name: distribution(name)
        for name in (
            "flashinfer-python",
            "nvidia-nccl-cu13",
            "sglang",
            "sglang-kernel",
            "torch",
            "triton",
        )
    }
    nvcc = run([str(EXPECTED_CUDA_ROOT / "bin/nvcc"), "--version"]).stdout.strip()
    return {
        "python": {
            "executable": str(pathlib.Path(sys.executable).resolve()),
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "prefix": str(pathlib.Path(sys.prefix).resolve()),
        },
        "modules": modules,
        "distributions": distributions,
        "torch": {
            "version": torch.__version__,
            "compiled_cuda": torch.version.cuda,
            "nccl_runtime": list(torch.cuda.nccl.version()),
        },
        "cuda_toolkit": {
            "cuda_home": os.environ.get("CUDA_HOME"),
            "nvcc": str((EXPECTED_CUDA_ROOT / "bin/nvcc").resolve()),
            "nvcc_version": nvcc,
            "compat_root": str(EXPECTED_COMPAT_ROOT.resolve()),
            "compat_libcuda": str(
                (EXPECTED_COMPAT_ROOT / "libcuda.so.1").resolve()
            ),
        },
    }


def source_identity() -> dict[str, Any]:
    source_head = git(EXPECTED_SOURCE, "rev-parse", "HEAD")
    exact_tag = git(EXPECTED_SOURCE, "describe", "--tags", "--exact-match")
    source_status = git(EXPECTED_SOURCE, "status", "--porcelain")
    source_origin = git(EXPECTED_SOURCE, "remote", "get-url", "origin")
    donor_origin = git(
        pathlib.Path(source_origin), "remote", "get-url", "origin"
    )
    return {
        "expected_commit": EXPECTED_SOURCE_SHA,
        "expected_tag": EXPECTED_SOURCE_TAG,
        "checkout": str(EXPECTED_SOURCE.resolve()),
        "head": source_head,
        "exact_tag": exact_tag,
        "detached": run(
            ["git", "-C", str(EXPECTED_SOURCE), "symbolic-ref", "-q", "HEAD"],
            check=False,
        ).returncode == 1,
        "status_porcelain": source_status,
        "clone_origin": source_origin,
        "upstream_origin": donor_origin,
        "identity_pass": (
            source_head == EXPECTED_SOURCE_SHA
            and exact_tag == EXPECTED_SOURCE_TAG
            and source_status == ""
        ),
    }


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--artifact-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    if args.worker_id != EXPECTED_WORKER_ID:
        errors.append(
            f"worker mismatch: expected {EXPECTED_WORKER_ID}, got {args.worker_id}"
        )
    if pathlib.Path(sys.executable).resolve() != EXPECTED_PYTHON.resolve():
        errors.append(
            f"python mismatch: expected {EXPECTED_PYTHON.resolve()}, "
            f"got {pathlib.Path(sys.executable).resolve()}"
        )
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        errors.append("CUDA_VISIBLE_DEVICES must be the empty string")
    if pathlib.Path(os.environ.get("CUDA_HOME", "")).resolve() != (
        EXPECTED_CUDA_ROOT.resolve()
    ):
        errors.append("CUDA_HOME does not resolve to the pinned cu13 toolkit")
    for required in (
        EXPECTED_SOURCE,
        EXPECTED_STATUS_SCRIPT,
        EXPECTED_CUDA_ROOT / "bin/nvcc",
        EXPECTED_COMPAT_ROOT / "libcuda.so.1",
        EXPECTED_UV,
        EXPECTED_WORKTREE / "pyproject.toml",
        EXPECTED_WORKTREE / "uv.lock",
    ):
        if not required.exists():
            errors.append(f"required path is missing: {required}")
    if errors:
        raise RuntimeError("; ".join(errors))

    before_status = run(
        ["bash", str(EXPECTED_STATUS_SCRIPT)], timeout=90
    ).stdout
    before_apps = compute_apps()

    versions = package_versions()
    source = source_identity()

    after_apps = compute_apps()
    after_status = run(
        ["bash", str(EXPECTED_STATUS_SCRIPT)], timeout=90
    ).stdout
    context_inventory_unchanged = before_apps == after_apps

    uv_version = run([str(EXPECTED_UV), "--version"]).stdout.strip()
    pyproject = EXPECTED_WORKTREE / "pyproject.toml"
    lockfile = EXPECTED_WORKTREE / "uv.lock"
    lock = {
        "schema_version": 1,
        "recorded_at": utc_now(),
        "worker_id": args.worker_id,
        "formal_environment": str(EXPECTED_PYTHON.parent.parent.resolve()),
        "uv_version": uv_version,
        "sync_command": (
            "SGLANG_BUILD_RUST_EXTS=none "
            "UV_PROJECT_ENVIRONMENT=/home/tiger/venvs/"
            "deepspec-hedge-dflash "
            "uv sync --frozen --no-install-project --link-mode copy"
        ),
        "source_overlay_command": (
            "SGLANG_BUILD_RUST_EXTS=none uv pip install "
            "--python /home/tiger/venvs/deepspec-hedge-dflash/bin/python "
            "--no-deps --editable "
            "/home/tiger/src/deepspec-sglang-hedge-dflash/python"
        ),
        "build_rust_exts": "none",
        "pyproject": {
            "path": str(pyproject),
            "sha256": sha256_file(pyproject),
        },
        "uv_lock": {
            "path": str(lockfile),
            "sha256": sha256_file(lockfile),
        },
        "source": source,
        "dependencies": versions,
        "pass": source["identity_pass"] and context_inventory_unchanged,
    }
    worker_evidence = {
        "schema_version": 1,
        "recorded_at": utc_now(),
        "worker_id": args.worker_id,
        "cuda_visible_devices_for_import_probe": "",
        "probe_scope": (
            "Metadata imports and version queries only; no CUDA tensor, "
            "kernel, device-count, or model operation was requested."
        ),
        "compute_apps_before": before_apps,
        "compute_apps_after": after_apps,
        "compute_inventory_unchanged": context_inventory_unchanged,
        "keepalive_status_before": before_status.splitlines(),
        "keepalive_status_after": after_status.splitlines(),
        "pass": context_inventory_unchanged
        and "HEALTHY" in before_status
        and "HEALTHY" in after_status,
    }

    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        args.artifact_dir / "dflash_d1b_environment_lock.json", lock
    )
    write_json(
        args.artifact_dir / "dflash_d1b_source_identity.json", source
    )
    write_json(
        args.artifact_dir / "dflash_d1b_dependency_versions.json", versions
    )
    write_json(
        args.artifact_dir / "dflash_d1b_worker_probe.json", worker_evidence
    )

    summary = {
        "environment_lock_pass": lock["pass"],
        "worker_probe_pass": worker_evidence["pass"],
        "source_head": source["head"],
        "sglang": versions["distributions"]["sglang"]["version"],
        "sglang_kernel": versions["distributions"]["sglang-kernel"]["version"],
        "torch": versions["torch"]["version"],
        "compiled_cuda": versions["torch"]["compiled_cuda"],
        "nccl_runtime": versions["torch"]["nccl_runtime"],
        "flashinfer": versions["distributions"]["flashinfer-python"]["version"],
        "triton": versions["distributions"]["triton"]["version"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if lock["pass"] and worker_evidence["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
