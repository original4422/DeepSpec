#!/usr/bin/env python3
"""Install the exact lock-pinned providers for an observed Torch ELF closure."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any, Sequence
import zipfile


REPO = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
ENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
UV = Path("/home/tiger/.local/bin/uv")
UV_CACHE = Path("/tmp/deepspec-hedge-v4-eagle3/uv-cache")
SCRATCH_ROOT = Path(
    "/tmp/deepspec-hedge-v4-eagle3/direct-torch-04"
)
SPECS_BATCH01: tuple[dict[str, str], ...] = (
    {
        "soname": "libcusolver.so.12",
        "package": "nvidia-cusolver",
        "version": "12.0.4.66",
        "url": (
            "https://files.pythonhosted.org/packages/5f/67/"
            "cba3777620cdacb99102da4042883709c41c709f4b6323c10781a9c3aa34/"
            "nvidia_cusolver-12.0.4.66-py3-none-manylinux_2_27_x86_64.whl"
        ),
        "sha256": (
            "0a759da5dea5c0ea10fd307de75cdeb59e7ea4fcb8add0924859b944babf1112"
        ),
        "authorization": "torch cuda-toolkit[cusolver]==13.0.2 extra",
    },
    {
        "soname": "libnvrtc.so.13",
        "package": "nvidia-cuda-nvrtc",
        "version": "13.0.88",
        "url": (
            "https://files.pythonhosted.org/packages/c3/68/"
            "483a78f5e8f31b08fb1bb671559968c0ca3a065ac7acabfc7cee55214fd6/"
            "nvidia_cuda_nvrtc-13.0.88-py3-none-manylinux2010_x86_64."
            "manylinux_2_12_x86_64.whl"
        ),
        "sha256": (
            "ad9b6d2ead2435f11cbb6868809d2adeeee302e9bb94bcf0539c7a40d80e8575"
        ),
        "authorization": "torch cuda-toolkit[nvrtc]==13.0.2 extra",
    },
    {
        "soname": "libnvshmem_host.so.3",
        "package": "nvidia-nvshmem-cu13",
        "version": "3.4.5",
        "url": (
            "https://files.pythonhosted.org/packages/3c/35/"
            "a9bf80a609e74e3b000fef598933235c908fcefcef9026042b8e6dfde2a9/"
            "nvidia_nvshmem_cu13-3.4.5-py3-none-manylinux2014_x86_64."
            "manylinux_2_17_x86_64.whl"
        ),
        "sha256": (
            "290f0a2ee94c9f3687a02502f3b9299a9f9fe826e6d0287ee18482e78d495b80"
        ),
        "authorization": "torch direct requirement nvidia-nvshmem-cu13==3.4.5",
    },
)
SPECS_BATCH02: tuple[dict[str, str], ...] = (
    {
        "soname": "libnvJitLink.so.13",
        "package": "nvidia-nvjitlink",
        "version": "13.0.88",
        "url": (
            "https://files.pythonhosted.org/packages/56/7a/"
            "123e033aaff487c77107195fa5a2b8686795ca537935a24efae476c41f05/"
            "nvidia_nvjitlink-13.0.88-py3-none-manylinux2010_x86_64."
            "manylinux_2_12_x86_64.whl"
        ),
        "sha256": (
            "13a74f429e23b921c1109976abefacc69835f2f433ebd323d3946e11d804e47b"
        ),
        "authorization": "torch cuda-toolkit[nvjitlink]==13.0.2 extra",
    },
)
SPECS_BATCH03: tuple[dict[str, str], ...] = (
    {
        "soname": "libnccl.so.2",
        "package": "nvidia-nccl-cu13",
        "version": "2.28.9",
        "url": (
            "https://files.pythonhosted.org/packages/b0/b4/"
            "878fefaad5b2bcc6fcf8d474a25e3e3774bc5133e4b58adff4d0bca238bc/"
            "nvidia_nccl_cu13-2.28.9-py3-none-manylinux_2_18_x86_64.whl"
        ),
        "sha256": (
            "e4553a30f34195f3fa1da02a6da3d6337d28f2003943aa0a3d247bbc25fefc42"
        ),
        "authorization": "torch direct requirement nvidia-nccl-cu13==2.28.9",
    },
)
BATCHES: dict[str, dict[str, Any]] = {
    "batch01": {
        "source_closure": "torch_elf_closure",
        "output": "torch_elf_closure_batch01_install.json",
        "scratch": "elf-closure-batch-01",
        "expected_missing": {
            "libcusolver.so.12",
            "libnvrtc.so.13",
            "libnvshmem_host.so.3",
        },
        "specs": SPECS_BATCH01,
    },
    "batch02": {
        "source_closure": "torch_elf_closure_after_batch01",
        "output": "torch_elf_closure_batch02_install.json",
        "scratch": "elf-closure-batch-02",
        "expected_missing": {"libnvJitLink.so.13"},
        "specs": SPECS_BATCH02,
    },
    "batch03": {
        "source_closure": "torch_elf_closure_after_batch02",
        "output": "torch_elf_closure_batch03_install.json",
        "scratch": "elf-closure-batch-03",
        "expected_missing": set(),
        "specs": SPECS_BATCH03,
        "required_import_evidence": "torch_import_after_empty_elf_closure.json",
        "required_import_error": (
            "undefined symbol: ncclCommWindowDeregister"
        ),
        "required_ldd_resolution": (
            "libnccl.so.2 => /lib/x86_64-linux-gnu/libnccl.so.2"
        ),
    },
}


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


def download(spec: dict[str, str], scratch: Path) -> dict[str, Any]:
    wheel = scratch / Path(spec["url"]).name
    partial = Path(f"{wheel}.partial")
    if wheel.exists() or partial.exists():
        raise RuntimeError(f"refusing to reuse closure scratch: {wheel}")
    completed = subprocess.run(
        (
            "curl",
            "--fail",
            "--location",
            "--max-time",
            "600",
            "--silent",
            "--show-error",
            "--output",
            str(partial),
            spec["url"],
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=630,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"curl failed for {spec['package']}: {completed.stderr}"
        )
    actual_hash = sha256(partial)
    if actual_hash != spec["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch for {spec['package']}")
    partial.rename(wheel)
    with zipfile.ZipFile(wheel) as archive:
        matches = sorted(
            member
            for member in archive.namelist()
            if Path(member).name == spec["soname"]
        )
    if len(matches) != 1:
        raise RuntimeError(
            f"{spec['package']} did not uniquely provide {spec['soname']}"
        )
    return {
        **spec,
        "wheel_path": str(wheel),
        "wheel_size": wheel.stat().st_size,
        "actual_sha256": actual_hash,
        "soname_wheel_member": matches[0],
    }


def validate_lock_and_metadata(
    specs: Sequence[dict[str, str]],
    lock: dict[str, Any],
    metadata: str,
) -> None:
    packages = lock["package"]
    toolkit = [
        package
        for package in packages
        if package.get("name") == "cuda-toolkit"
        and package.get("version") == "13.0.2"
    ]
    if len(toolkit) != 1:
        raise RuntimeError("cuda-toolkit==13.0.2 lock identity is not unique")
    optional = toolkit[0].get("optional-dependencies", {})
    if (
        "cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,"
        "cusparse,nvjitlink,nvrtc,nvtx]==13.0.2" not in metadata
    ):
        raise RuntimeError("Torch METADATA does not authorize toolkit extras")
    toolkit_providers = {
        "nvidia-cusolver": "cusolver",
        "nvidia-cuda-nvrtc": "nvrtc",
        "nvidia-nvjitlink": "nvjitlink",
    }
    for spec in specs:
        if spec["package"] in toolkit_providers:
            extra = toolkit_providers[spec["package"]]
            if optional.get(extra) != [{"name": spec["package"]}]:
                raise RuntimeError(
                    f"cuda-toolkit {extra} extra changed"
                )
        elif spec["package"] == "nvidia-nvshmem-cu13":
            if "nvidia-nvshmem-cu13==3.4.5" not in metadata:
                raise RuntimeError("Torch METADATA does not authorize NVSHMEM")
        elif spec["package"] == "nvidia-nccl-cu13":
            if "nvidia-nccl-cu13==2.28.9" not in metadata:
                raise RuntimeError("Torch METADATA does not authorize NCCL")
        else:
            raise RuntimeError(
                f"no metadata authorization rule for {spec['package']}"
            )
        matches = [
            package
            for package in packages
            if package.get("name") == spec["package"]
            and package.get("version") == spec["version"]
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"lock identity is not unique for {spec['package']}"
            )
        wheels = [
            wheel
            for wheel in matches[0].get("wheels", [])
            if wheel["url"] == spec["url"]
            and wheel["hash"] == f"sha256:{spec['sha256']}"
        ]
        if len(wheels) != 1:
            raise RuntimeError(
                f"wheel identity differs from uv.lock for {spec['package']}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-dir", type=Path, required=True)
    parser.add_argument(
        "--batch",
        choices=sorted(BATCHES),
        default="batch01",
    )
    args = parser.parse_args(argv)
    batch = BATCHES[args.batch]
    specs: tuple[dict[str, str], ...] = batch["specs"]
    expected_missing: set[str] = batch["expected_missing"]
    scratch = SCRATCH_ROOT / batch["scratch"]
    attempt = args.attempt_dir.resolve()
    run_root = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
    ).resolve()
    if run_root not in attempt.parents:
        raise RuntimeError("attempt is outside Eagle3 run root")
    output = attempt / batch["output"]
    if output.exists():
        raise RuntimeError(f"refusing to overwrite: {output}")
    closure_dir = attempt / batch["source_closure"]
    closure = json.loads(
        (closure_dir / "summary.json").read_text(encoding="utf-8")
    )
    observed = set(closure.get("missing_sonames", []))
    if observed != expected_missing or closure.get("cuda_context_count") != 0:
        raise RuntimeError("observed ELF closure differs from authorized batch")
    trigger_evidence: dict[str, Any] | None = None
    if "required_import_evidence" in batch:
        import_path = attempt / batch["required_import_evidence"]
        trigger_evidence = json.loads(import_path.read_text(encoding="utf-8"))
        if (
            trigger_evidence.get("status") != "TORCH_IMPORT_FAILED"
            or batch["required_import_error"]
            not in trigger_evidence.get("stderr", "")
        ):
            raise RuntimeError("runtime-symbol trigger evidence differs")
        ldd_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in closure_dir.glob("*.ldd.txt")
        )
        if batch["required_ldd_resolution"] not in ldd_text:
            raise RuntimeError("runtime-symbol provider resolution differs")
    metadata_path = closure_dir / "torch.METADATA"
    metadata = metadata_path.read_text(encoding="utf-8")
    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    validate_lock_and_metadata(specs, lock, metadata)
    contexts_before = cuda_context_count()
    if contexts_before != 0:
        raise RuntimeError("closure installation requires zero CUDA contexts")
    scratch.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(specs)
    ) as executor:
        futures = [
            executor.submit(download, spec, scratch)
            for spec in specs
        ]
        downloaded = [future.result() for future in futures]
    downloaded.sort(key=lambda record: record["package"])

    UV_CACHE.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(UV_CACHE)
    if environment["UV_CACHE_DIR"] != str(UV_CACHE):
        raise RuntimeError("refusing non-lane uv cache")
    installs: list[dict[str, Any]] = []
    for record in downloaded:
        stdout_path = attempt / f"{record['package']}_closure_uv.stdout.txt"
        stderr_path = attempt / f"{record['package']}_closure_uv.stderr.txt"
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            completed = subprocess.run(
                (
                    str(UV),
                    "pip",
                    "install",
                    "--python",
                    str(ENV / "bin/python"),
                    "--no-deps",
                    record["wheel_path"],
                ),
                check=False,
                stdout=stdout,
                stderr=stderr,
                text=True,
                env=environment,
                timeout=300,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"uv local install failed for {record['package']}"
            )
        installed_version = subprocess.run(
            (
                str(ENV / "bin/python"),
                "-c",
                (
                    "import importlib.metadata, sys; "
                    "sys.stdout.write(importlib.metadata.version(sys.argv[1]))"
                ),
                record["package"],
            ),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        ).stdout
        if installed_version != record["version"]:
            raise RuntimeError(
                f"installed version mismatch for {record['package']}"
            )
        installs.append(
            {
                "package": record["package"],
                "version": installed_version,
                "returncode": completed.returncode,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }
        )
    contexts_after = cuda_context_count()
    if contexts_after != 0:
        raise RuntimeError("closure installation unexpectedly created contexts")
    payload = {
        "schema_version": 1,
        "status": "OBSERVED_ELF_CLOSURE_PROVIDERS_INSTALLED",
        "worker_id": "4099544",
        "source_closure_summary": str(closure_dir / "summary.json"),
        "observed_missing_sonames": sorted(observed),
        "lock_path": str(REPO / "uv.lock"),
        "torch_metadata_path": str(metadata_path),
        "parallel_download_count": len(downloaded),
        "downloads": downloaded,
        "installs": installs,
        "runtime_trigger_evidence": trigger_evidence,
        "uv_cache_dir": str(UV_CACHE),
        "uv_local_no_deps": True,
        "cuda_context_count_before": contexts_before,
        "cuda_context_count_after": contexts_after,
        "cuda_operation_performed": False,
        "next_required_action": "rerun complete Torch ELF closure",
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"ELF_CLOSURE_{args.batch.upper()}_INSTALLED evidence={output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as error:
        print(f"ELF closure install error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
