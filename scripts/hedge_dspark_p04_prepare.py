#!/usr/bin/env python3
"""Resolve and validate one fixed HEDGE-on-V4 DSpark P04 attempt."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


EXPECTED_WORKER = "4106666"
EXPECTED_GPUS = 8
EXPECTED_GPU_NAME = "NVIDIA H20"
FIXED_PORT = 31066
REPO_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
)
VENV = Path("/home/tiger/venvs/hedge-v4-dspark")
PYTHON = VENV / "bin/python"
CUDA_HOME = (
    VENV / "lib/python3.11/site-packages/nvidia/cu13"
)
CUDA_COMPAT = Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
    "usr/local/cuda-13.0/compat"
)
SGLANG_SOURCE = Path(
    "/home/tiger/src/"
    "hedge-v4-dspark-sglang-"
    "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
)
MODEL_PATH = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/models/"
    "deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/"
    "modelscope-"
    "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
RUN_ROOT = Path("/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark")
SERVED_MODEL = "deepseek-v4-flash-dspark"
ATTEMPT_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z-p04-(native|b0)"
    r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
)

B0_CONFIG: dict[str, int | float | str] = {
    "B": 0,
    "g": 1e30,
    "m": 5,
    "value_scheme": "normalized_suffix",
    "block_size": 5,
}
B0_CONFIG_BYTES = (
    b'{"B":0,"g":1e30,"m":5,'
    b'"value_scheme":"normalized_suffix","block_size":5}\n'
)
SGLANG_BASE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PURE_CORE_COMMIT = "4d96f44065c07030ede67484a262006ec149626a"
INTEGRATION_COMMIT = "3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc"
PATCHED_TREE_SHA256 = (
    "996fbfd6d83c0f001d44d75a7aaf097"
    "25d338418d76087efa2ea2f8ea02b94bb"
)
FINAL_WHEEL_SHA256 = (
    "f2054c32025182ea8b4e57731ffa9d015"
    "0a40d5ac296f34e93c9b124181c7262"
)
EXPECTED_DISTRIBUTIONS = {
    "torch": "2.11.0+cu130",
    "sglang": "0.5.16",
    "sglang-kernel": "0.4.5+cu130",
    "flashinfer-python": "0.6.14",
    "triton": "3.6.0",
    "nvidia-cuda-nvcc": "13.0.88",
    "nvidia-cuda-runtime": "13.0.96",
    "nvidia-cuda-nvrtc": "13.0.88",
    "nvidia-nccl-cu13": "2.28.9",
}
WHEEL_MANIFEST = (
    REPO_ROOT / "integrations/sglang_dspark_hedge/wheel_manifest.json"
)
P03_ENGINE_IDENTITY = (
    REPO_ROOT / "integrations/sglang_dspark_hedge/engine_identity.json"
)
CANONICAL_CHECKPOINT_IDENTITY = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/"
    "20260728T205441Z-p00-bootstrap/checkpoint_identity.json"
)
CHECKPOINT_SNAPSHOT = (
    "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
SHARD_PATTERN = re.compile(r"^model-(\d{5})-of-00048\.safetensors$")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("xb") as output:
        output.write(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ).encode("ascii")
        )
        output.write(b"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_engine_identity(
    *, decode_config_fingerprint: str
) -> dict[str, Any]:
    """Validate installed bytes against the accepted P03 wheel manifest."""

    if not decode_config_fingerprint:
        raise ValueError("decode config fingerprint must be non-empty")
    manifest = json.loads(WHEEL_MANIFEST.read_text(encoding="utf-8"))
    p03_identity = json.loads(
        P03_ENGINE_IDENTITY.read_text(encoding="utf-8")
    )
    distribution = importlib.metadata.distribution("sglang")
    distribution_root = Path(distribution.locate_file("")).resolve()
    installed_records: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    content_checks: list[bool] = []
    for expected in manifest["wheel_content"]:
        relative = Path(str(expected["path"]))
        installed = (distribution_root / relative).resolve()
        source = (SGLANG_SOURCE / "python" / relative).resolve()
        installed_sha = _sha256_file(installed) if installed.is_file() else None
        source_sha = _sha256_file(source) if source.is_file() else None
        expected_sha = str(expected["sha256"])
        installed_records.append(
            {
                "path": str(installed),
                "relative_path": relative.as_posix(),
                "sha256": installed_sha,
                "expected_sha256": expected_sha,
                "matches": installed_sha == expected_sha,
            }
        )
        source_records.append(
            {
                "path": str(source),
                "relative_path": relative.as_posix(),
                "sha256": source_sha,
                "expected_sha256": expected_sha,
                "matches": source_sha == expected_sha,
            }
        )
        content_checks.extend(
            (installed_sha == expected_sha, source_sha == expected_sha)
        )

    source_head = _git("rev-parse", "HEAD", cwd=SGLANG_SOURCE)
    repo_head = _git("rev-parse", "HEAD")
    core_is_ancestor = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", PURE_CORE_COMMIT, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    integration_is_ancestor = (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                INTEGRATION_COMMIT,
                "HEAD",
            ],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    record_path = (
        distribution_root / "sglang-0.5.16.dist-info/RECORD"
    ).resolve()
    installed_record_sha = (
        _sha256_file(record_path) if record_path.is_file() else None
    )
    distribution_versions = {
        name: importlib.metadata.version(name)
        for name in EXPECTED_DISTRIBUTIONS
    }
    nvcc_path = CUDA_HOME / "bin/nvcc"
    cudart_link = CUDA_HOME / "lib64/libcudart.so"
    nvrtc_link = CUDA_HOME / "lib64/libnvrtc.so"
    compat_libcuda = CUDA_COMPAT / "libcuda.so.1"
    manifest_wheel = manifest["formal_wheel"]
    manifest_installation = manifest["installation"]
    formal_wheel_path = Path(str(manifest_wheel["path"]))
    formal_wheel_size = (
        formal_wheel_path.stat().st_size
        if formal_wheel_path.is_file()
        else None
    )
    formal_wheel_sha = (
        _sha256_file(formal_wheel_path)
        if formal_wheel_path.is_file()
        else None
    )
    replay_identity = manifest["verification"][
        "artifact_only_patch_replay"
    ]
    import_paths = {
        "sglang": distribution_root / "sglang/__init__.py",
        "adapter": (
            distribution_root
            / "sglang/srt/speculative/dspark_components/hedge_dspark.py"
        ),
        "core": (
            distribution_root
            / "sglang/srt/speculative/hedge_spec/__init__.py"
        ),
    }
    p03_import_paths = p03_identity["installation"]["import_paths"]
    checks = {
        "formal_python": Path(sys.executable).resolve() == PYTHON.resolve(),
        "distribution_version": distribution.version == "0.5.16",
        "fixed_distribution_versions": distribution_versions
        == EXPECTED_DISTRIBUTIONS,
        "cuda_13_nvcc": nvcc_path.is_file(),
        "cuda_13_runtime": cudart_link.is_file(),
        "cuda_13_nvrtc": nvrtc_link.is_file(),
        "driver_forward_compatibility": compat_libcuda.is_file(),
        "wheel_manifest_status": manifest.get("status") == "PASS",
        "wheel_sha256": manifest_wheel.get("sha256")
        == FINAL_WHEEL_SHA256,
        "formal_wheel_exists": formal_wheel_path.is_file(),
        "formal_wheel_size": formal_wheel_size
        == manifest_wheel.get("size_bytes")
        == 14646094,
        "formal_wheel_actual_sha256": formal_wheel_sha
        == FINAL_WHEEL_SHA256,
        "wheel_content": all(content_checks),
        "installed_record_sha256": installed_record_sha
        == manifest_installation.get("record_sha256"),
        "source_head": source_head == SGLANG_BASE_SHA,
        "patched_tree_identity": (
            replay_identity.get("patched_tree_sha256")
            == p03_identity["sglang"].get("patched_tree_sha256")
            == PATCHED_TREE_SHA256
        ),
        "installed_import_paths": all(
            path.is_file()
            and str(path) == p03_import_paths.get(name)
            for name, path in import_paths.items()
        ),
        "pure_core_ancestor": core_is_ancestor,
        "integration_ancestor": integration_is_ancestor,
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "deepspec": {
            "worktree": str(REPO_ROOT),
            "head": repo_head,
            "branch": _git("branch", "--show-current"),
        },
        "source": {
            "path": str(SGLANG_SOURCE),
            "upstream_base_sha": SGLANG_BASE_SHA,
            "actual_head": source_head,
            "patched_tree_sha256": PATCHED_TREE_SHA256,
            "content": source_records,
        },
        "hedge_core": {
            "deepspec_commit": PURE_CORE_COMMIT,
            "source_commit": (
                "9fb903d676254ea5f5d171051fb15c54f331111c"
            ),
        },
        "dspark_integration": {
            "deepspec_commit": INTEGRATION_COMMIT,
            "patch_sha256": (
                "8e8cc840f4656391a792ac3312e7ee11"
                "c0738f80cbf9989392edfc0364d74170"
            ),
        },
        "wheel": {
            "filename": manifest_wheel["filename"],
            "sha256": FINAL_WHEEL_SHA256,
            "formal_path": str(formal_wheel_path),
            "formal_size_bytes": formal_wheel_size,
            "formal_actual_sha256": formal_wheel_sha,
            "manifest": str(WHEEL_MANIFEST),
            "manifest_sha256": _sha256_file(WHEEL_MANIFEST),
            "installed_distribution_root": str(distribution_root),
            "installed_record_path": str(record_path),
            "installed_record_sha256": installed_record_sha,
            "installed_import_paths": {
                name: str(path) for name, path in import_paths.items()
            },
            "installed_content": installed_records,
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version,
        },
        "toolchain": {
            "distributions": distribution_versions,
            "expected_distributions": dict(EXPECTED_DISTRIBUTIONS),
            "cuda_home": str(CUDA_HOME),
            "nvcc": str(nvcc_path),
            "cudart": str(cudart_link),
            "cudart_resolved": str(cudart_link.resolve()),
            "nvrtc": str(nvrtc_link),
            "nvrtc_resolved": str(nvrtc_link.resolve()),
            "driver_compat_libcuda": str(compat_libcuda),
            "driver_compat_libcuda_resolved": str(
                compat_libcuda.resolve()
            ),
        },
        "decode_config_fingerprint": decode_config_fingerprint,
    }


def build_checkpoint_identity() -> dict[str, Any]:
    """Revalidate the pinned snapshot via metadata and file sizes only."""

    canonical = json.loads(
        CANONICAL_CHECKPOINT_IDENTITY.read_text(encoding="utf-8")
    )
    complete_path = MODEL_PATH / ".complete"
    config_path = MODEL_PATH / "config.json"
    index_path = MODEL_PATH / "model.safetensors.index.json"
    complete = json.loads(complete_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    payload_files = sorted(
        path
        for path in MODEL_PATH.rglob("*")
        if path.is_file() and path != complete_path
    )
    shards = [
        path
        for path in payload_files
        if SHARD_PATTERN.fullmatch(path.name)
        and path.parent == MODEL_PATH
    ]
    expected_shards = {
        f"model-{number:05d}-of-00048.safetensors"
        for number in range(1, 49)
    }
    actual_shards = {path.name for path in shards}
    index_referents = set(index.get("weight_map", {}).values())
    total_bytes = sum(path.stat().st_size for path in payload_files)
    symlinks = [
        str(path.relative_to(MODEL_PATH))
        for path in MODEL_PATH.rglob("*")
        if path.is_symlink()
    ]
    small_hashes = {
        path.name: _sha256_file(path)
        for path in (complete_path, config_path, index_path)
    }
    checks = {
        "canonical_identity_status": canonical.get("status") == "PASS",
        "canonical_model_path": canonical.get("model_path") == str(MODEL_PATH),
        "complete_status": complete.get("status") == "complete",
        "snapshot_identity": complete.get("provider_payload_snapshot_id")
        == CHECKPOINT_SNAPSHOT,
        "provider": complete.get("provider") == "modelscope",
        "repository": complete.get("repository")
        == "deepseek-ai/DeepSeek-V4-Flash-DSpark",
        "file_count": len(payload_files)
        == complete.get("provider_payload_file_count")
        == 75,
        "payload_bytes": total_bytes
        == complete.get("provider_payload_bytes")
        == 166898666759,
        "exact_48_shards": len(shards) == 48
        and actual_shards == expected_shards,
        "index_referents": index_referents == expected_shards,
        "index_total_size": index.get("metadata", {}).get("total_size")
        == 166878536440,
        "no_symlinks": not symlinks,
        "architecture": config.get("architectures")
        == ["DeepseekV4ForCausalLM"],
        "model_type": config.get("model_type") == "deepseek_v4",
        "packed_fp4": config.get("expert_dtype") == "fp4",
        "dspark_block_size": config.get("dspark_block_size") == 5,
        "small_file_hashes_match_canonical": small_hashes
        == canonical.get("small_file_sha256"),
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "model_path": str(MODEL_PATH),
        "provider": complete.get("provider"),
        "repository": complete.get("repository"),
        "snapshot_identity": complete.get("provider_payload_snapshot_id"),
        "hf_reference_revision": (
            "62af8fffb2f7030cac4de2f0169f5b8d1101b646"
        ),
        "file_count": len(payload_files),
        "total_bytes": total_bytes,
        "shard_count": len(shards),
        "index_referent_count": len(index_referents),
        "critical_config": {
            key: config.get(key)
            for key in (
                "architectures",
                "model_type",
                "expert_dtype",
                "quantization_config",
                "dspark_block_size",
                "dspark_markov_rank",
                "dspark_target_layer_ids",
            )
        },
        "small_file_sha256": small_hashes,
        "canonical_identity_path": str(CANONICAL_CHECKPOINT_IDENTITY),
        "canonical_identity_sha256": _sha256_file(
            CANONICAL_CHECKPOINT_IDENTITY
        ),
        "symlinks": symlinks,
        "full_checkpoint_hash_performed": False,
    }


def parse_gpu_inventory(payload: str) -> list[dict[str, Any]]:
    """Parse and enforce the dedicated lane's exact eight-H20 inventory."""

    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        fields = [field.strip() for field in raw_line.split(",")]
        if len(fields) != 4:
            raise ValueError(f"unexpected nvidia-smi GPU row: {raw_line!r}")
        index_raw, uuid, name, memory_raw = fields
        try:
            index = int(index_raw)
            memory_total_mib = int(memory_raw)
        except ValueError as error:
            raise ValueError(
                f"non-numeric nvidia-smi GPU row: {raw_line!r}"
            ) from error
        rows.append(
            {
                "index": index,
                "uuid": uuid,
                "name": name,
                "memory_total_mib": memory_total_mib,
            }
        )

    if [row["index"] for row in rows] != list(range(EXPECTED_GPUS)):
        raise ValueError("GPU indices must be exactly 0 through 7 in order")
    uuids = [str(row["uuid"]) for row in rows]
    if len(set(uuids)) != EXPECTED_GPUS or any(
        not uuid.startswith("GPU-") for uuid in uuids
    ):
        raise ValueError("GPU UUIDs must be eight unique NVIDIA UUIDs")
    if any(row["name"] != EXPECTED_GPU_NAME for row in rows):
        raise ValueError(f"all GPUs must be {EXPECTED_GPU_NAME}")
    if any(int(row["memory_total_mib"]) <= 0 for row in rows):
        raise ValueError("GPU memory totals must be positive")
    return rows


def parse_keepalive_status(payload: str) -> dict[str, Any]:
    """Validate one dedicated 8-GPU, 10x1-second keepalive status report."""

    lines = payload.splitlines()
    if not lines:
        raise ValueError("keepalive status output is empty")
    match = re.fullmatch(
        r"HEALTHY on (\S+) worker=4106666 "
        r"pid=([1-9][0-9]*) pgid=([1-9][0-9]*) sid=([1-9][0-9]*)",
        lines[0],
    )
    if match is None:
        raise ValueError("keepalive status line is not exact HEALTHY identity")
    pid, pgid, sid = (int(value) for value in match.groups()[1:])
    if pid != pgid or pid != sid:
        raise ValueError("keepalive PID, PGID and SID must be identical")
    health = None
    for line in lines[1:]:
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "per_gpu" in candidate:
            health = candidate
            break
    if health is None:
        raise ValueError("keepalive status has no per-GPU health JSON")
    errors: list[str] = []
    if health.get("healthy") is not True:
        errors.append("health.healthy is not true")
    if health.get("expected_gpus") != EXPECTED_GPUS:
        errors.append("health.expected_gpus is not 8")
    if health.get("sample_count") != 10:
        errors.append("health.sample_count is not 10")
    if health.get("underutilized_gpus") != []:
        errors.append("health.underutilized_gpus is not empty")
    per_gpu = health.get("per_gpu")
    if not isinstance(per_gpu, dict) or set(per_gpu) != {
        str(index) for index in range(EXPECTED_GPUS)
    }:
        errors.append("health.per_gpu is not exact indices 0 through 7")
    else:
        for index in range(EXPECTED_GPUS):
            record = per_gpu[str(index)]
            if not isinstance(record, dict):
                errors.append(f"GPU {index} health is not an object")
                continue
            if record.get("sample_count") != 10:
                errors.append(f"GPU {index} sample count is not 10")
            try:
                mean = float(record.get("mean_utilization"))
            except (TypeError, ValueError):
                errors.append(f"GPU {index} mean is not numeric")
            else:
                if mean < 40.0:
                    errors.append(f"GPU {index} mean is below 40")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS",
        "worker_id": EXPECTED_WORKER,
        "hostname": match.group(1),
        "supervisor_pid": pid,
        "supervisor_pgid": pgid,
        "supervisor_sid": sid,
        "health": health,
    }


def _server_command() -> list[str]:
    return [
        str(PYTHON),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(MODEL_PATH),
        "--served-model-name",
        SERVED_MODEL,
        "--host",
        "127.0.0.1",
        "--port",
        str(FIXED_PORT),
        "--tp-size",
        "8",
        "--speculative-algorithm",
        "DSPARK",
        "--speculative-dspark-block-size",
        "5",
        "--moe-runner-backend",
        "flashinfer_mxfp4",
        "--speculative-moe-runner-backend",
        "flashinfer_mxfp4",
        "--context-length",
        "4096",
        "--max-running-requests",
        "1",
        "--mem-fraction-static",
        "0.80",
        "--disable-cuda-graph",
        "--disable-overlap-schedule",
        "--disable-radix-cache",
    ]


def _base_environment(scratch: Path) -> dict[str, str]:
    return {
        "CUDA_HOME": str(CUDA_HOME),
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "FLASHINFER_WORKSPACE_BASE": str(scratch / "flashinfer"),
        "LD_LIBRARY_PATH": (
            f"{CUDA_COMPAT}:{CUDA_HOME / 'lib64'}:{CUDA_HOME / 'lib'}"
        ),
        "PATH": (
            f"{VENV / 'bin'}:{CUDA_HOME / 'bin'}:"
            "/usr/local/bin:/usr/bin:/bin"
        ),
        "PYTHONUNBUFFERED": "1",
        "SGLANG_CACHE_DIR": str(scratch / "sglang-cache"),
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": "0",
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "TOKENIZERS_PARALLELISM": "false",
        "TORCH_EXTENSIONS_DIR": str(scratch / "torch-extensions"),
        "TRITON_CACHE_DIR": str(scratch / "triton-cache"),
    }


def resolve_attempt(
    *,
    arm: str,
    attempt_id: str,
    scratch: Path,
) -> dict[str, Any]:
    """Return the complete immutable runtime contract for one attempt."""

    if arm not in {"native", "b0"}:
        raise ValueError("arm must be exactly native or b0")
    match = ATTEMPT_PATTERN.fullmatch(attempt_id)
    if match is None or match.group(1) != arm:
        raise ValueError(
            "attempt-id must be timestamped P04 ID containing the selected arm"
        )
    scratch = scratch.resolve()
    config_path = scratch / "hedge_config.json"
    environment = _base_environment(scratch)
    environment["HEDGE_ENABLED"] = "0" if arm == "native" else "1"
    hedge_config = None if arm == "native" else dict(B0_CONFIG)
    if arm == "b0":
        with config_path.open("xb") as output:
            output.write(B0_CONFIG_BYTES)
        environment["SGLANG_DSPARK_HEDGE_CONFIG_PATH"] = str(
            config_path
        )
    elif config_path.exists():
        raise ValueError("native arm must not have a HEDGE config file")

    command = _server_command()
    decode_affecting = {
        "server_command": command,
        "hedge_enabled": arm == "b0",
        "hedge_config": hedge_config,
        "ragged_verify_mode": environment["SGLANG_RAGGED_VERIFY_MODE"],
        "fp4_experts": environment["SGLANG_DSV4_FP4_EXPERTS"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "worker_id": EXPECTED_WORKER,
        "hostname": socket.gethostname(),
        "arm": arm,
        "attempt_id": attempt_id,
        "scratch": str(scratch),
        "hdfs_run": str(RUN_ROOT / attempt_id),
        "api": {
            "base_url": f"http://127.0.0.1:{FIXED_PORT}",
            "host": "127.0.0.1",
            "port": FIXED_PORT,
            "startup_timeout_seconds": 3600,
        },
        "server": {
            "command": command,
            "environment": environment,
            "unset_environment": [
                "HEDGE_CONFIG",
                "SGLANG_DSPARK_HEDGE_CONFIG_JSON",
                "SGLANG_DSPARK_HEDGE_CONFIG_PATH",
                "SGLANG_DSPARK_HEDGE_MODE",
                "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY",
                "SGLANG_DSV4_FP4_DEQUANT",
            ],
        },
        "hedge": {
            "mode": "disabled" if arm == "native" else "enabled",
            "config": hedge_config,
            "config_path": (
                None
                if arm == "native"
                else str(config_path)
            ),
        },
        "decode_affecting": decode_affecting,
        "decode_config_fingerprint": _fingerprint(decode_affecting),
    }


def prepare_attempt(
    *,
    arm: str,
    attempt_id: str,
    scratch: Path,
    gpu_inventory_payload: str,
) -> dict[str, Any]:
    """Materialize all identity artifacts before keepalive is paused."""

    scratch = scratch.resolve()
    if not scratch.is_dir():
        raise ValueError(f"scratch directory does not exist: {scratch}")
    resolved = resolve_attempt(
        arm=arm,
        attempt_id=attempt_id,
        scratch=scratch,
    )
    resolved["gpu_inventory"] = parse_gpu_inventory(gpu_inventory_payload)
    engine = build_engine_identity(
        decode_config_fingerprint=resolved["decode_config_fingerprint"]
    )
    checkpoint = build_checkpoint_identity()
    _atomic_json(scratch / "resolved_config.json", resolved)
    _atomic_json(scratch / "engine_identity.json", engine)
    _atomic_json(scratch / "checkpoint_identity.json", checkpoint)
    statuses = {
        "engine_identity": engine["status"],
        "checkpoint_identity": checkpoint["status"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": (
            "PASS"
            if all(value == "PASS" for value in statuses.values())
            else "FAIL"
        ),
        "arm": arm,
        "attempt_id": attempt_id,
        "identity_statuses": statuses,
    }


def _gpu_inventory_query() -> str:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "nvidia-smi GPU inventory failed: " + completed.stderr.strip()
        )
    return completed.stdout


def _wait_no_cuda_contexts(*, output: Path, timeout: int) -> None:
    if timeout <= 0:
        raise ValueError("CUDA context timeout must be positive")
    deadline = time.monotonic() + timeout
    observations: list[str] = []
    while True:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        if completed.returncode != 0:
            observations.append(
                f"{now} query_failed={completed.stderr.strip()!r}"
            )
            output.write_text("\n".join(observations) + "\n", encoding="utf-8")
            raise RuntimeError("cannot prove CUDA context state")
        rows = completed.stdout.strip()
        observations.append(f"{now} contexts={rows or 'none'}")
        output.write_text("\n".join(observations) + "\n", encoding="utf-8")
        if not rows:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("CUDA compute contexts remain after timeout")
        time.sleep(1)


def _check_fixed_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        probe.bind(("127.0.0.1", FIXED_PORT))


def _emit_nul(values: list[str]) -> None:
    for value in values:
        sys.stdout.buffer.write(value.encode("utf-8") + b"\0")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--worker-id", required=True)
    prepare_parser.add_argument(
        "--arm", choices=("native", "b0"), required=True
    )
    prepare_parser.add_argument("--attempt-id", required=True)
    prepare_parser.add_argument("--scratch", type=Path, required=True)

    emit_command = subparsers.add_parser("emit-command")
    emit_command.add_argument("--resolved", type=Path, required=True)

    emit_environment = subparsers.add_parser("emit-environment")
    emit_environment.add_argument("--resolved", type=Path, required=True)

    keepalive = subparsers.add_parser("parse-keepalive")
    keepalive.add_argument("--worker-id", required=True)
    keepalive.add_argument("--input", type=Path, required=True)
    keepalive.add_argument("--output", type=Path, required=True)

    contexts = subparsers.add_parser("wait-no-contexts")
    contexts.add_argument("--worker-id", required=True)
    contexts.add_argument("--output", type=Path, required=True)
    contexts.add_argument("--timeout", type=int, default=120)

    port = subparsers.add_parser("check-port")
    port.add_argument("--worker-id", required=True)

    args = parser.parse_args()
    if getattr(args, "worker_id", EXPECTED_WORKER) != EXPECTED_WORKER:
        parser.error(f"only worker {EXPECTED_WORKER} is authorized")

    if args.command == "prepare":
        inventory_payload = _gpu_inventory_query()
        result = prepare_attempt(
            arm=args.arm,
            attempt_id=args.attempt_id,
            scratch=args.scratch,
            gpu_inventory_payload=inventory_payload,
        )
        _atomic_json(
            args.scratch / "gpu_inventory.json",
            {
                "schema_version": 1,
                "worker_id": EXPECTED_WORKER,
                "status": "PASS",
                "gpus": parse_gpu_inventory(inventory_payload),
            },
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "emit-command":
        resolved = json.loads(args.resolved.read_text(encoding="utf-8"))
        _emit_nul([str(item) for item in resolved["server"]["command"]])
        return 0
    if args.command == "emit-environment":
        resolved = json.loads(args.resolved.read_text(encoding="utf-8"))
        _emit_nul(
            [
                f"{key}={value}"
                for key, value in sorted(
                    resolved["server"]["environment"].items()
                )
            ]
        )
        return 0
    if args.command == "parse-keepalive":
        record = parse_keepalive_status(
            args.input.read_text(encoding="utf-8")
        )
        _atomic_json(args.output, record)
        print(json.dumps(record, sort_keys=True))
        return 0
    if args.command == "wait-no-contexts":
        _wait_no_cuda_contexts(output=args.output, timeout=args.timeout)
        return 0
    if args.command == "check-port":
        _check_fixed_port()
        print(f"fixed_port_available={FIXED_PORT}")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
