#!/usr/bin/env python3
"""Fail-closed FlashInfer SM90 fused-MoE JIT prebuild for DFlash D3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import traceback
from datetime import datetime, timezone


CUDA_VIEW = pathlib.Path("/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0")
PAYLOAD = pathlib.Path(
    "/home/tiger/venvs/deepspec-hedge-dflash/"
    "lib/python3.11/site-packages/nvidia/cu13"
)
COMPAT_DIR = pathlib.Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
    "usr/local/cuda-13.0/compat"
)
COMPAT_LIB = COMPAT_DIR / "libcuda.so.580.173.02"
WORKSPACE_BASE = pathlib.Path(
    "/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
)
EXPECTED_LINKS = {
    CUDA_VIEW / "bin": PAYLOAD / "bin",
    CUDA_VIEW / "include": PAYLOAD / "include",
    CUDA_VIEW / "nvvm": PAYLOAD / "nvvm",
    CUDA_VIEW / "lib64/libcudart.so": PAYLOAD / "lib/libcudart.so.13",
    CUDA_VIEW / "lib64/libnvrtc.so": PAYLOAD / "lib/libnvrtc.so.13",
    CUDA_VIEW / "lib64/stubs/libcuda.so": COMPAT_LIB,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_preimport_environment() -> dict[str, object]:
    expected = {
        "CUDA_HOME": str(CUDA_VIEW),
        "CUDA_VISIBLE_DEVICES": "",
        "FLASHINFER_WORKSPACE_BASE": str(WORKSPACE_BASE),
        "FLASHINFER_CUDA_ARCH_LIST": "9.0",
        "MAX_JOBS": "16",
        "PYTHONNOUSERSITE": "1",
    }
    for name, value in expected.items():
        assert os.environ.get(name) == value, (name, os.environ.get(name), value)

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    ld_parts = os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
    assert str(CUDA_VIEW / "bin") in path_parts, path_parts
    assert ld_parts[:2] == [str(COMPAT_DIR), str(PAYLOAD / "lib")], ld_parts
    checked_env = [
        os.environ.get("CUDA_HOME", ""),
        os.environ.get("PATH", ""),
        os.environ.get("LD_LIBRARY_PATH", ""),
        os.environ.get("FLASHINFER_WORKSPACE_BASE", ""),
    ]
    assert all("cuda-12.6" not in value.lower() for value in checked_env), checked_env
    assert not WORKSPACE_BASE.is_relative_to(pathlib.Path.home()), WORKSPACE_BASE

    links = {}
    for link, target in EXPECTED_LINKS.items():
        assert link.is_symlink(), link
        assert os.readlink(link) == str(target), (link, os.readlink(link), target)
        assert link.resolve(strict=True) == target.resolve(strict=True), (link, target)
        links[str(link)] = str(target)

    nvcc = shutil.which("nvcc")
    assert nvcc is not None
    assert pathlib.Path(nvcc).resolve(strict=True) == (
        PAYLOAD / "bin/nvcc"
    ).resolve(strict=True), nvcc
    nvcc_version = subprocess.check_output(
        [str(CUDA_VIEW / "bin/nvcc"), "--version"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    assert "release 13.0" in nvcc_version, nvcc_version
    return {
        "environment": expected,
        "path_nvcc": nvcc,
        "nvcc_version": nvcc_version.strip(),
        "links": links,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, object] = {
        "schema_version": 1,
        "phase": "D3",
        "operation": "flashinfer_fused_moe_sm90_prebuild",
        "started_at_utc": utc_now(),
        "status": "FAIL",
    }
    try:
        document["preimport"] = assert_preimport_environment()
        WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)

        # These imports must remain after the fail-closed environment assertions.
        import flashinfer
        from flashinfer.jit import env as jit_env
        from flashinfer.jit.fused_moe import gen_cutlass_fused_moe_sm90_module

        spec = gen_cutlass_fused_moe_sm90_module(False)
        spec.build(verbose=True)

        workspace = jit_env.FLASHINFER_WORKSPACE_DIR
        build_dir = spec.build_dir
        library = spec.jit_library_path
        assert jit_env.FLASHINFER_BASE_DIR == WORKSPACE_BASE
        assert workspace.is_relative_to(WORKSPACE_BASE)
        assert build_dir.is_relative_to(workspace)
        assert library.is_file() and not library.is_symlink(), library
        document.update(
            {
                "status": "PASS",
                "flashinfer_version": flashinfer.__version__,
                "flashinfer_module": str(pathlib.Path(flashinfer.__file__).resolve()),
                "workspace_base": str(jit_env.FLASHINFER_BASE_DIR),
                "workspace": str(workspace.resolve()),
                "generated_source_dir": str(jit_env.FLASHINFER_GEN_SRC_DIR.resolve()),
                "module_name": spec.name,
                "build_dir": str(build_dir.resolve()),
                "ninja_file": str(spec.ninja_path.resolve()),
                "source_count": len(spec.sources),
                "object_file_count": sum(
                    path.is_file() for path in spec.get_object_paths()
                ),
                "shared_object": {
                    "path": str(library.resolve()),
                    "size_bytes": library.stat().st_size,
                    "sha256": sha256_file(library),
                },
            }
        )
    except BaseException as error:
        document["error_type"] = type(error).__name__
        document["error"] = str(error)
        document["traceback"] = traceback.format_exc()
        raise
    finally:
        document["finished_at_utc"] = utc_now()
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
