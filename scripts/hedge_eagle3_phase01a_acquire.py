#!/usr/bin/env python3
"""Acquire and atomically publish the pinned Eagle3 target and draft.

Large downloads and mutable Hugging Face state stay on the assigned worker's
NVMe.  HDFS receives only verified entity files through unique staging
directories.  Large LFS payloads are verified by provider OID plus exact size;
they are deliberately not reread to compute a second content digest.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Iterable, Mapping, Sequence

from huggingface_hub import (
    HfApi,
    __version__ as huggingface_hub_version,
    snapshot_download,
)
from huggingface_hub._local_folder import read_download_metadata


WORKER_ID = "4099544"
SESSION = "hedge-v4-eagle3"
EXPECTED_GPU_COUNT = 8
EXPECTED_GPU_INDICES = list(range(EXPECTED_GPU_COUNT))
SCRATCH_ROOT = Path("/tmp/deepspec-hedge-v4-eagle3")
ACQUISITION_ROOT = SCRATCH_ROOT / "phase-01a-acquisition"
RUN_ROOT = Path("/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs")
COORDINATION_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4"
)
TARGET_MARKER = (
    COORDINATION_ROOT
    / (
        "target-deepseek-v4-flash-"
        "60d8d70770c6776ff598c94bb586a859a38244f1.complete.json"
    )
)
KEEPALIVE_CONTROLLER = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3/scripts/hedge_eagle3_keepalive.sh"
)


@dataclasses.dataclass(frozen=True)
class RepoSpec:
    label: str
    repo_id: str
    revision: str
    snapshot_path: Path
    staging_path: Path
    final_path: Path
    require_tokenizer: bool
    require_index: bool


TARGET = RepoSpec(
    label="target",
    repo_id="deepseek-ai/DeepSeek-V4-Flash",
    revision="60d8d70770c6776ff598c94bb586a859a38244f1",
    snapshot_path=ACQUISITION_ROOT / "target" / "snapshot",
    staging_path=(
        Path(
            "/mnt/hdfs/pengzegang/DeepSpec/models/"
            "deepseek-ai__DeepSeek-V4-Flash/snapshots"
        )
        / (
            ".staging-huggingface-"
            "60d8d70770c6776ff598c94bb586a859a38244f1-"
            "eagle3-phase01a-01"
        )
    ),
    final_path=(
        Path(
            "/mnt/hdfs/pengzegang/DeepSpec/models/"
            "deepseek-ai__DeepSeek-V4-Flash/snapshots"
        )
        / (
            "huggingface-"
            "60d8d70770c6776ff598c94bb586a859a38244f1"
        )
    ),
    require_tokenizer=True,
    require_index=True,
)

DRAFT = RepoSpec(
    label="draft",
    repo_id="SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1",
    revision="4c68aa4689d59cb1064f20abec7708174ee4613d",
    snapshot_path=ACQUISITION_ROOT / "draft" / "snapshot",
    staging_path=(
        Path(
            "/mnt/hdfs/pengzegang/DeepSpec/models/"
            "SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/snapshots"
        )
        / (
            ".staging-huggingface-"
            "4c68aa4689d59cb1064f20abec7708174ee4613d-"
            "eagle3-phase01a-01"
        )
    ),
    final_path=(
        Path(
            "/mnt/hdfs/pengzegang/DeepSpec/models/"
            "SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/snapshots"
        )
        / (
            "huggingface-"
            "4c68aa4689d59cb1064f20abec7708174ee4613d"
        )
    ),
    require_tokenizer=False,
    require_index=False,
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def write_exclusive_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to replace immutable marker: {path}")
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    with temporary.open("xb") as handle:
        handle.write(canonical_json_bytes(value))
        handle.flush()
    if path.exists():
        raise FileExistsError(f"immutable marker appeared during write: {path}")
    os.rename(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    size = path.stat().st_size
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def process_identity() -> dict[str, Any]:
    pid = os.getpid()
    return {
        "schema_version": 1,
        "session": SESSION,
        "worker_id": WORKER_ID,
        "hostname": socket.gethostname(),
        "pid": pid,
        "ppid": os.getppid(),
        "pgid": os.getpgid(pid),
        "sid": os.getsid(pid),
        "uid": os.getuid(),
        "command_line": sys.argv,
        "python": sys.executable,
        "started_at": utc_now(),
    }


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def recursive_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            if item_key == key:
                found.append(item_value)
            found.extend(recursive_values(item_value, key))
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            found.extend(recursive_values(item, key))
    return found


def validate_keepalive_marker(path: Path) -> dict[str, Any]:
    marker = read_json(path)
    if not isinstance(marker, Mapping):
        raise ValueError("keepalive coordination marker is not an object")

    worker_values = [
        str(value)
        for key in ("worker_id", "worker")
        for value in recursive_values(marker, key)
    ]
    if WORKER_ID not in worker_values:
        raise ValueError("keepalive marker does not pin worker 4099544")

    gpu_counts = [
        value
        for key in ("expected_gpu_count", "gpu_count")
        for value in recursive_values(marker, key)
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    if EXPECTED_GPU_COUNT not in gpu_counts:
        raise ValueError("keepalive marker does not prove exact eight GPUs")

    sample_counts = [
        value
        for value in recursive_values(marker, "sample_count")
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    if 10 not in sample_counts:
        raise ValueError("keepalive marker does not prove a 10-sample gate")

    means = [
        float(value)
        for value in recursive_values(marker, "mean_utilization")
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if len(means) < EXPECTED_GPU_COUNT or min(means) < 40.0:
        raise ValueError(
            "keepalive marker lacks eight per-GPU means at or above 40%"
        )

    statuses = {
        str(value).lower()
        for value in recursive_values(marker, "status")
        + recursive_values(marker, "health")
    }
    healthy_values = recursive_values(marker, "healthy")
    if not (
        statuses.intersection({"healthy", "pass", "active", "complete"})
        or True in healthy_values
    ):
        raise ValueError("keepalive marker does not report healthy status")

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "validated_at": utc_now(),
        "worker_id": WORKER_ID,
        "gpu_count": EXPECTED_GPU_COUNT,
        "sample_count": 10,
        "minimum_observed_mean": min(means),
    }


def require_worker_inventory() -> dict[str, Any]:
    gpu_query = command_output(
        (
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total",
            "--format=csv,noheader,nounits",
        )
    )
    if gpu_query["returncode"] != 0:
        raise RuntimeError(f"nvidia-smi failed: {gpu_query['stderr']}")
    rows = [
        [field.strip() for field in line.split(",")]
        for line in gpu_query["stdout"].splitlines()
        if line.strip()
    ]
    if len(rows) != EXPECTED_GPU_COUNT:
        raise RuntimeError(f"expected 8 GPUs, observed {len(rows)}")
    if [int(row[0]) for row in rows] != EXPECTED_GPU_INDICES:
        raise RuntimeError("GPU indices are not the exact set 0..7")
    if any(row[2] not in {"NVIDIA H20", "NVIDIA-H20"} for row in rows):
        raise RuntimeError("assigned worker contains a non-H20 GPU")

    compute = command_output(
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name",
            "--format=csv,noheader,nounits",
        )
    )
    capacity_tmp = command_output(("df", "-B1", "/tmp"))
    capacity_hdfs = command_output(
        ("df", "-B1", "/mnt/hdfs/pengzegang/DeepSpec")
    )
    return {
        "checked_at": utc_now(),
        "worker_id": WORKER_ID,
        "hostname": socket.gethostname(),
        "gpu_count": len(rows),
        "gpus": [
            {
                "index": int(row[0]),
                "uuid": row[1],
                "name": row[2],
                "memory_total_mib": int(row[3]),
            }
            for row in rows
        ],
        "compute_contexts": compute,
        "capacity_tmp": capacity_tmp,
        "capacity_hdfs": capacity_hdfs,
    }


def require_live_keepalive(run_dir: Path, label: str) -> dict[str, Any]:
    completed = subprocess.run(
        (
            "bash",
            str(KEEPALIVE_CONTROLLER),
            "status",
            WORKER_ID,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = {
        "checked_at": utc_now(),
        "label": label,
        "command": [
            "bash",
            str(KEEPALIVE_CONTROLLER),
            "status",
            WORKER_ID,
        ],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    atomic_write_json(run_dir / f"keepalive_{label}.json", payload)
    if completed.returncode != 0 or not completed.stdout.startswith(
        f"HEALTHY on {socket.gethostname()} worker={WORKER_ID} "
    ):
        raise RuntimeError(f"keepalive is not healthy at {label}")
    return payload


def sibling_record(sibling: Any) -> dict[str, Any]:
    lfs = getattr(sibling, "lfs", None)
    lfs_record = None
    if lfs is not None:
        lfs_record = {
            "oid": getattr(lfs, "sha256", None),
            "size": getattr(lfs, "size", None),
            "pointer_size": getattr(lfs, "pointer_size", None),
        }
    return {
        "path": sibling.rfilename,
        "size": sibling.size,
        "blob_id": sibling.blob_id,
        "lfs": lfs_record,
    }


def fetch_provider_identity(
    api: HfApi,
    spec: RepoSpec,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    info = api.model_info(
        spec.repo_id,
        revision=spec.revision,
        files_metadata=True,
    )
    if info.sha != spec.revision:
        raise ValueError(
            f"{spec.label} provider commit mismatch: "
            f"expected {spec.revision}, observed {info.sha}"
        )
    files = sorted(
        (sibling_record(item) for item in info.siblings),
        key=lambda item: item["path"],
    )
    if not files:
        raise ValueError(f"{spec.label} provider returned no files")
    missing_sizes = [item["path"] for item in files if item["size"] is None]
    if missing_sizes:
        raise ValueError(
            f"{spec.label} provider omitted sizes: {missing_sizes[:5]}"
        )
    identity = {
        "schema_version": 1,
        "provider": "huggingface",
        "repo_type": "model",
        "repo_id": spec.repo_id,
        "requested_revision": spec.revision,
        "resolved_commit": info.sha,
        "queried_at": utc_now(),
        "huggingface_hub_version": huggingface_hub_version,
        "file_count": len(files),
        "total_bytes": sum(int(item["size"]) for item in files),
        "lfs_file_count": sum(item["lfs"] is not None for item in files),
        "lfs_identity_source": "Hugging Face files_metadata",
        "files": files,
    }
    return identity, {item["path"]: item for item in files}


def list_entity_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".cache":
            continue
        if path.is_symlink():
            raise ValueError(f"symlink is not an entity file: {path}")
        if path.is_file():
            files[relative.as_posix()] = path
        elif not path.is_dir():
            raise ValueError(f"unsupported filesystem entry: {path}")
    return files


def inspect_checkpoint_contract(
    spec: RepoSpec,
    root: Path,
    provider: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    config_path = root / "config.json"
    if not config_path.is_file():
        raise ValueError(f"{spec.label} has no config.json")
    config = read_json(config_path)
    if not isinstance(config, Mapping):
        raise ValueError(f"{spec.label} config.json is not an object")
    if not config.get("model_type"):
        raise ValueError(f"{spec.label} config has no model_type")
    architectures = config.get("architectures")
    if not isinstance(architectures, list) or not architectures:
        raise ValueError(f"{spec.label} config has no architectures")

    tokenizer_paths = sorted(
        path
        for path in provider
        if path in {"tokenizer.json", "tokenizer.model"}
        or path.startswith("tokenizer.")
        or path.startswith("tokenizer_")
    )
    if spec.require_tokenizer and not tokenizer_paths:
        raise ValueError(f"{spec.label} provider has no tokenizer files")

    indexes = sorted(
        path for path in provider if path.endswith(".index.json")
    )
    if spec.require_index and not indexes:
        raise ValueError(f"{spec.label} provider has no weight index")

    index_referents: set[str] = set()
    index_tensor_count = 0
    for relative in indexes:
        payload = read_json(root / relative)
        weight_map = payload.get("weight_map")
        if not isinstance(weight_map, Mapping) or not weight_map:
            raise ValueError(f"invalid weight_map in {relative}")
        index_tensor_count += len(weight_map)
        for referent in weight_map.values():
            if not isinstance(referent, str):
                raise ValueError(f"non-string index referent in {relative}")
            index_referents.add(referent)
    missing_referents = sorted(
        referent
        for referent in index_referents
        if referent not in provider or not (root / referent).is_file()
    )
    if missing_referents:
        raise ValueError(
            f"{spec.label} index referents are missing: "
            f"{missing_referents[:5]}"
        )

    provider_weights = sorted(
        path
        for path in provider
        if path.endswith((".safetensors", ".bin", ".pt"))
    )
    if not provider_weights:
        raise ValueError(f"{spec.label} provider has no weight payload")
    if index_referents and set(provider_weights) != index_referents:
        raise ValueError(
            f"{spec.label} provider weight set differs from index referents"
        )

    return {
        "config": {
            "model_type": config.get("model_type"),
            "architectures": architectures,
            "torch_dtype": config.get("torch_dtype"),
            "hidden_size": config.get("hidden_size"),
            "num_hidden_layers": config.get("num_hidden_layers"),
            "quantization_config": config.get("quantization_config"),
            "eagle_aux_hidden_state_layer_ids": config.get(
                "eagle_aux_hidden_state_layer_ids"
            ),
        },
        "tokenizer": {
            "required": spec.require_tokenizer,
            "paths": tokenizer_paths,
            "status": (
                "present"
                if tokenizer_paths
                else "absent_by_provider_draft_uses_target_tokenizer"
            ),
        },
        "index": {
            "required": spec.require_index,
            "paths": indexes,
            "tensor_count": index_tensor_count,
            "referent_count": len(index_referents),
            "referents": sorted(index_referents),
            "status": (
                "present"
                if indexes
                else "not_applicable_single_weight_file"
            ),
        },
        "weight_shard_count": len(provider_weights),
        "weight_paths": provider_weights,
    }


def validate_local_download_metadata(
    spec: RepoSpec,
    provider: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Match local-dir metadata to the pinned commit and provider object IDs."""

    records: list[dict[str, Any]] = []
    for relative in sorted(provider):
        expected = provider[relative]
        metadata = read_download_metadata(spec.snapshot_path, relative)
        if metadata is None:
            raise ValueError(
                f"{spec.label} lacks Hugging Face metadata for {relative}"
            )
        lfs = expected.get("lfs")
        expected_etag = (
            lfs.get("oid") if lfs is not None else expected.get("blob_id")
        )
        observed_etag = metadata.etag.strip('"')
        allowed_etags = {expected_etag}
        if lfs is not None:
            allowed_etags.add(f"sha256:{expected_etag}")
        if metadata.commit_hash != spec.revision:
            raise ValueError(
                f"{spec.label} local metadata commit mismatch for {relative}"
            )
        if observed_etag not in allowed_etags:
            raise ValueError(
                f"{spec.label} local metadata ETag mismatch for {relative}"
            )
        records.append(
            {
                "path": relative,
                "commit_hash": metadata.commit_hash,
                "etag": observed_etag,
                "provider_object_id": expected_etag,
                "provider_object_kind": "lfs_sha256" if lfs else "git_blob",
                "matches": True,
            }
        )
    return {
        "schema_version": 1,
        "status": "PASS",
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "validated_at": utc_now(),
        "file_count": len(records),
        "all_commits_match": True,
        "all_provider_object_ids_match": True,
        "large_payload_content_hashes_computed": False,
        "files": records,
    }


def verify_snapshot(
    spec: RepoSpec,
    root: Path,
    provider: Mapping[str, Mapping[str, Any]],
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    actual = list_entity_files(root)
    expected_paths = set(provider)
    actual_paths = set(actual)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise ValueError(
            f"{spec.label} file set mismatch: missing={missing[:5]} "
            f"extra={extra[:5]}"
        )

    manifest_records: list[dict[str, Any]] = []
    for relative in sorted(provider):
        expected = provider[relative]
        path = actual[relative]
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{spec.label} is not regular: {relative}")
        if metadata.st_size != expected["size"]:
            raise ValueError(
                f"{spec.label} size mismatch for {relative}: "
                f"{metadata.st_size} != {expected['size']}"
            )

        lfs = expected.get("lfs")
        record = {
            "path": relative,
            "size": metadata.st_size,
            "provider_blob_id": expected.get("blob_id"),
            "provider_lfs_oid": lfs.get("oid") if lfs else None,
            "provider_lfs_size": lfs.get("size") if lfs else None,
            "entity_regular_file": True,
            "symlink": False,
            "verification": (
                "exact_size_plus_provider_lfs_oid"
                if lfs
                else "git_blob_sha1_plus_sha256"
            ),
            "git_blob_sha1": None,
            "sha256": None,
        }
        if lfs:
            if lfs.get("size") != metadata.st_size or not lfs.get("oid"):
                raise ValueError(
                    f"{spec.label} invalid provider LFS identity: {relative}"
                )
        else:
            record["git_blob_sha1"] = git_blob_sha1(path)
            record["sha256"] = sha256_file(path)
            if record["git_blob_sha1"] != expected.get("blob_id"):
                raise ValueError(
                    f"{spec.label} Git blob mismatch for {relative}"
                )
        manifest_records.append(record)

    manifest_payload = b"".join(
        json.dumps(record, sort_keys=True).encode("utf-8") + b"\n"
        for record in manifest_records
    )
    atomic_write_bytes(manifest_path, manifest_payload)
    contract = inspect_checkpoint_contract(spec, root, provider)
    return {
        "schema_version": 1,
        "label": spec.label,
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "snapshot_path": str(root),
        "validated_at": utc_now(),
        "file_count": len(manifest_records),
        "total_bytes": sum(item["size"] for item in manifest_records),
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "large_payload_content_hashes_computed": False,
        "identity_policy": (
            "provider LFS OID plus exact size for LFS payloads; "
            "Git blob SHA-1 plus SHA-256 for non-LFS files"
        ),
        **contract,
    }


def ensure_capacity(
    identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    required_payload = sum(int(item["total_bytes"]) for item in identities)
    scratch_usage = shutil.disk_usage(SCRATCH_ROOT)
    hdfs_usage = shutil.disk_usage("/mnt/hdfs/pengzegang/DeepSpec")
    # Allow one full local snapshot, one full HDFS entity copy, and generous
    # Xet/cache overhead.  HDFS and NVMe are evaluated independently.
    required_nvme = required_payload * 2
    required_hdfs = required_payload
    if scratch_usage.free < required_nvme:
        raise RuntimeError(
            f"insufficient NVMe: {scratch_usage.free} < {required_nvme}"
        )
    if hdfs_usage.free < required_hdfs:
        raise RuntimeError(
            f"insufficient HDFS: {hdfs_usage.free} < {required_hdfs}"
        )
    return {
        "checked_at": utc_now(),
        "provider_payload_bytes": required_payload,
        "required_nvme_bytes": required_nvme,
        "nvme_free_bytes": scratch_usage.free,
        "required_hdfs_bytes": required_hdfs,
        "hdfs_free_bytes": hdfs_usage.free,
    }


def copy_file_exclusive(source: Path, destination: Path, token: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and destination.stat().st_size == source.stat().st_size:
            return
        raise FileExistsError(f"unexpected existing destination: {destination}")
    temporary = destination.with_name(f".{destination.name}.{token}.partial")
    if temporary.exists():
        raise FileExistsError(
            f"owned staging has an incomplete prior copy: {temporary}"
        )
    with source.open("rb") as source_handle:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o444,
        )
        with os.fdopen(fd, "wb", buffering=0) as destination_handle:
            shutil.copyfileobj(
                source_handle,
                destination_handle,
                length=32 * 1024 * 1024,
            )
    if temporary.stat().st_size != source.stat().st_size:
        raise IOError(f"staging copy size mismatch: {temporary}")
    os.rename(temporary, destination)
    print(
        f"{utc_now()} copied {source.name} bytes={source.stat().st_size}",
        flush=True,
    )


def publish_snapshot(
    spec: RepoSpec,
    provider: Mapping[str, Mapping[str, Any]],
    validation: Mapping[str, Any],
    *,
    run_dir: Path,
    copy_workers: int,
) -> dict[str, Any]:
    if spec.final_path.exists():
        raise FileExistsError(
            f"refusing to replace published snapshot: {spec.final_path}"
        )
    if spec.staging_path.exists():
        raise FileExistsError(
            f"refusing ambiguous existing staging: {spec.staging_path}"
        )
    spec.staging_path.parent.mkdir(parents=True, exist_ok=True)
    spec.staging_path.mkdir()

    token = f"{spec.label}-{os.getpid()}"
    jobs = [
        (
            spec.snapshot_path / relative,
            spec.staging_path / relative,
            token,
        )
        for relative in sorted(provider)
    ]
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=copy_workers
    ) as executor:
        futures = [
            executor.submit(copy_file_exclusive, *job) for job in jobs
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    staging_manifest = (
        ACQUISITION_ROOT / spec.label / "staging_manifest.jsonl"
    )
    staging_validation = verify_snapshot(
        spec,
        spec.staging_path,
        provider,
        manifest_path=staging_manifest,
    )
    if (
        staging_validation["file_count"] != validation["file_count"]
        or staging_validation["total_bytes"] != validation["total_bytes"]
        or staging_validation["manifest_sha256"]
        != validation["manifest_sha256"]
    ):
        raise ValueError(
            f"{spec.label} staging differs from validated NVMe snapshot"
        )

    source_device = spec.snapshot_path.stat().st_dev
    staging_device = spec.staging_path.stat().st_dev
    if source_device == staging_device:
        raise ValueError(
            f"{spec.label} HDFS staging is not an independent filesystem"
        )

    require_live_keepalive(run_dir, f"{spec.label}_before_atomic_publish")
    os.rename(spec.staging_path, spec.final_path)
    if not spec.final_path.is_dir():
        raise RuntimeError(f"{spec.label} atomic directory publish failed")

    final_files = list_entity_files(spec.final_path)
    hardlink_violations = [
        relative
        for relative, path in final_files.items()
        if path.stat().st_nlink != 1
    ]
    if hardlink_violations:
        raise ValueError(
            f"{spec.label} published hardlinks: {hardlink_violations[:5]}"
        )
    return {
        "schema_version": 1,
        "status": "complete",
        "owner_session": "eagle3",
        "provider": "huggingface",
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "source_nvme_snapshot": str(spec.snapshot_path),
        "staging_path": str(spec.staging_path),
        "snapshot_path": str(spec.final_path),
        "file_count": validation["file_count"],
        "weight_shard_count": validation["weight_shard_count"],
        "total_bytes": validation["total_bytes"],
        "manifest_sha256": validation["manifest_sha256"],
        "source_device": source_device,
        "destination_device": staging_device,
        "entity_regular_files": True,
        "symlink_count": 0,
        "hardlink_count": 0,
        "copy_workers": copy_workers,
        "published_at": utc_now(),
        "immutable": True,
    }


class State:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.scratch_path = ACQUISITION_ROOT / "acquisition_state.json"
        self.run_path = run_dir / "acquisition_state.json"
        self.heartbeat_path = ACQUISITION_ROOT / "heartbeat.json"
        self.phase = "initializing"
        self.status = "running"
        self.error: str | None = None
        self.started_at = utc_now()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
        )

    @staticmethod
    def _snapshot_progress(root: Path) -> dict[str, int]:
        complete_files = 0
        complete_bytes = 0
        partial_files = 0
        partial_bytes = 0
        if root.is_dir():
            for candidate in root.rglob("*"):
                try:
                    is_file = candidate.is_file()
                    is_symlink = candidate.is_symlink()
                    size = candidate.stat().st_size
                except FileNotFoundError:
                    continue
                if not is_file or is_symlink:
                    continue
                relative = candidate.relative_to(root)
                if relative.parts and relative.parts[0] == ".cache":
                    if ".incomplete" in candidate.name:
                        partial_files += 1
                        partial_bytes += size
                    continue
                complete_files += 1
                complete_bytes += size
        return {
            "complete_files": complete_files,
            "complete_bytes": complete_bytes,
            "partial_files": partial_files,
            "partial_bytes": partial_bytes,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session": SESSION,
            "worker_id": WORKER_ID,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "pgid": os.getpgid(0),
            "sid": os.getsid(0),
            "status": self.status,
            "phase": self.phase,
            "error": self.error,
            "started_at": self.started_at,
            "updated_at": utc_now(),
            "run_dir": str(self.run_dir),
            "scratch_root": str(ACQUISITION_ROOT),
            "target_revision": TARGET.revision,
            "draft_revision": DRAFT.revision,
            "download_progress": {
                "target": self._snapshot_progress(TARGET.snapshot_path),
                "draft": self._snapshot_progress(DRAFT.snapshot_path),
            },
        }

    def update(
        self,
        phase: str,
        *,
        status: str = "running",
        error: str | None = None,
    ) -> None:
        self.phase = phase
        self.status = status
        self.error = error
        payload = self.snapshot()
        atomic_write_json(self.scratch_path, payload)
        atomic_write_json(self.run_path, payload)
        print(
            f"{payload['updated_at']} phase={phase} status={status}",
            flush=True,
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(60):
            atomic_write_json(self.heartbeat_path, self.snapshot())

    def start(self) -> None:
        atomic_write_json(self.heartbeat_path, self.snapshot())
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        atomic_write_json(self.heartbeat_path, self.snapshot())


def create_owner(run_dir: Path) -> dict[str, Any]:
    owner_path = ACQUISITION_ROOT / "owner.json"
    expected = {
        "schema_version": 1,
        "kind": "phase01a_acquisition_owner",
        "session": SESSION,
        "worker_id": WORKER_ID,
        "scratch_root": str(ACQUISITION_ROOT),
        "run_dir": str(run_dir),
        "target_repo_id": TARGET.repo_id,
        "target_revision": TARGET.revision,
        "draft_repo_id": DRAFT.repo_id,
        "draft_revision": DRAFT.revision,
    }
    if owner_path.exists():
        observed = read_json(owner_path)
        for key, value in expected.items():
            if observed.get(key) != value:
                raise ValueError(
                    f"acquisition owner conflict for {key}: "
                    f"{observed.get(key)!r} != {value!r}"
                )
        return observed
    ACQUISITION_ROOT.mkdir(parents=True, exist_ok=True)
    owner = {**expected, "created_at": utc_now()}
    write_exclusive_json(owner_path, owner)
    return owner


def artifact_paths(run_dir: Path, label: str) -> dict[str, Path]:
    return {
        "provider": run_dir / f"{label}_provider_identity.json",
        "manifest": run_dir / f"{label}_manifest.jsonl",
        "manifest_sha": run_dir / f"{label}_manifest.sha256",
        "validation": run_dir / f"{label}_validation.json",
        "publish": run_dir / f"{label}_publish.json",
    }


def copy_small_artifact(source: Path, destination: Path) -> None:
    atomic_write_bytes(destination, source.read_bytes())


def download_and_validate(
    spec: RepoSpec,
    identity: Mapping[str, Any],
    provider: Mapping[str, Mapping[str, Any]],
    run_dir: Path,
    state: State,
    *,
    download_workers: int,
) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = artifact_paths(run_dir, spec.label)
    atomic_write_json(paths["provider"], identity)
    spec.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    resolved: str | None = None
    attempts_path = (
        ACQUISITION_ROOT / spec.label / "download_attempts.jsonl"
    )
    for attempt_number in range(1, 4):
        state.update(f"{spec.label}_download_attempt_{attempt_number}")
        started_at = utc_now()
        try:
            resolved = snapshot_download(
                repo_id=spec.repo_id,
                repo_type="model",
                revision=spec.revision,
                local_dir=str(spec.snapshot_path),
                cache_dir=str(ACQUISITION_ROOT / "hf-cache"),
                max_workers=download_workers,
                token=os.environ.get("HF_TOKEN"),
            )
            attempt = {
                "attempt": attempt_number,
                "started_at": started_at,
                "finished_at": utc_now(),
                "status": "complete",
                "error": None,
            }
        except BaseException as error:
            attempt = {
                "attempt": attempt_number,
                "started_at": started_at,
                "finished_at": utc_now(),
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
            attempts_path.parent.mkdir(parents=True, exist_ok=True)
            with attempts_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(attempt, sort_keys=True, ensure_ascii=False)
                    + "\n"
                )
                handle.flush()
            if attempt_number == 3:
                raise
            print(
                f"{utc_now()} retaining pinned partial state; "
                f"retrying {spec.label} in 30 seconds",
                flush=True,
            )
            time.sleep(30)
            continue
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(attempt, sort_keys=True, ensure_ascii=False) + "\n"
            )
            handle.flush()
        break
    if resolved is None:
        raise RuntimeError(f"{spec.label} download produced no snapshot")
    if Path(resolved).resolve() != spec.snapshot_path.resolve():
        raise ValueError(
            f"{spec.label} downloader returned unexpected path: {resolved}"
        )

    state.update(f"{spec.label}_nvme_validation")
    download_metadata = validate_local_download_metadata(spec, provider)
    atomic_write_json(
        run_dir / f"{spec.label}_download_metadata_identity.json",
        download_metadata,
    )
    local_manifest = (
        ACQUISITION_ROOT / spec.label / f"{spec.label}_manifest.jsonl"
    )
    validation = verify_snapshot(
        spec,
        spec.snapshot_path,
        provider,
        manifest_path=local_manifest,
    )
    copy_small_artifact(local_manifest, paths["manifest"])
    atomic_write_bytes(
        paths["manifest_sha"],
        f"{validation['manifest_sha256']}  {paths['manifest'].name}\n".encode(
            "ascii"
        ),
    )
    atomic_write_json(paths["validation"], validation)
    return validation, paths


def validate_existing_publish(
    spec: RepoSpec,
    provider: Mapping[str, Mapping[str, Any]],
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    """Resume after an earlier atomic publish without rewriting the entity."""

    if not spec.final_path.is_dir():
        raise FileNotFoundError(
            f"{spec.label} resume requested but snapshot is absent"
        )
    paths = artifact_paths(run_dir, spec.label)
    local_manifest = (
        ACQUISITION_ROOT
        / spec.label
        / f"{spec.label}_published_resume_manifest.jsonl"
    )
    validation = verify_snapshot(
        spec,
        spec.final_path,
        provider,
        manifest_path=local_manifest,
    )
    copy_small_artifact(local_manifest, paths["manifest"])
    atomic_write_bytes(
        paths["manifest_sha"],
        f"{validation['manifest_sha256']}  {paths['manifest'].name}\n".encode(
            "ascii"
        ),
    )
    atomic_write_json(paths["validation"], validation)

    if paths["publish"].is_file():
        publish = read_json(paths["publish"])
        if (
            publish.get("repo_id") != spec.repo_id
            or publish.get("revision") != spec.revision
            or publish.get("snapshot_path") != str(spec.final_path)
            or publish.get("manifest_sha256")
            != validation["manifest_sha256"]
        ):
            raise ValueError(
                f"{spec.label} existing publish artifact conflicts"
            )
    else:
        publish = {
            "schema_version": 1,
            "status": "complete",
            "owner_session": "eagle3",
            "provider": "huggingface",
            "repo_id": spec.repo_id,
            "revision": spec.revision,
            "source_nvme_snapshot": str(spec.snapshot_path),
            "staging_path": str(spec.staging_path),
            "snapshot_path": str(spec.final_path),
            "file_count": validation["file_count"],
            "weight_shard_count": validation["weight_shard_count"],
            "total_bytes": validation["total_bytes"],
            "manifest_path": str(paths["manifest"]),
            "manifest_sha256": validation["manifest_sha256"],
            "entity_regular_files": True,
            "symlink_count": 0,
            "hardlink_count": 0,
            "published_at": utc_now(),
            "immutable": True,
            "resume_reconstructed": True,
        }
        atomic_write_json(paths["publish"], publish)
    return validation, paths, publish


def publish_target_marker(
    run_dir: Path,
    validation: Mapping[str, Any],
    publish: Mapping[str, Any],
) -> dict[str, Any]:
    marker = {
        "schema_version": 1,
        "status": "complete",
        "owner_session": "eagle3",
        "provider": "huggingface",
        "repo_id": TARGET.repo_id,
        "revision": TARGET.revision,
        "snapshot_path": str(TARGET.final_path),
        "manifest_path": str(run_dir / "target_manifest.jsonl"),
        "manifest_sha256": validation["manifest_sha256"],
        "file_count": validation["file_count"],
        "weight_shard_count": validation["weight_shard_count"],
        "total_bytes": validation["total_bytes"],
        "published_at": publish["published_at"],
        "immutable": True,
    }
    write_exclusive_json(TARGET_MARKER, marker)
    return marker


def handoff_text(
    *,
    status: str,
    run_dir: Path,
    keepalive_evidence: Mapping[str, Any],
    target_publish: Mapping[str, Any] | None,
    draft_publish: Mapping[str, Any] | None,
    error: str | None = None,
) -> str:
    target_status = "PASS" if target_publish else "INCOMPLETE"
    draft_status = "PASS" if draft_publish else "INCOMPLETE"
    lines = [
        "# Phase 01A handoff",
        "",
        f"Status: **{status}**.",
        "",
        f"- Worker: `{WORKER_ID}`; no model load was performed",
        (
            "- Keepalive gate: exact 8 GPUs, 10×1 second samples, "
            f"minimum per-GPU mean "
            f"`{keepalive_evidence['minimum_observed_mean']}`%"
        ),
        f"- Target acquisition/publish: **{target_status}**",
        f"- Draft acquisition/publish: **{draft_status}**",
        f"- Persistent artifact: `{run_dir}`",
        f"- NVMe resume root: `{ACQUISITION_ROOT}`",
        f"- Acquisition PID/PGID/SID: `{os.getpid()}`/"
        f"`{os.getpgid(0)}`/`{os.getsid(0)}`",
    ]
    if target_publish:
        lines.extend(
            [
                f"- Target snapshot: `{target_publish['snapshot_path']}`",
                f"- Shared target marker: `{TARGET_MARKER}`",
            ]
        )
    if draft_publish:
        lines.append(
            f"- Draft snapshot: `{draft_publish['snapshot_path']}`"
        )
    if error:
        lines.extend(["", "## Blocker", "", f"```text\n{error}\n```"])
    lines.extend(
        [
            "",
            "## Exit gates",
            "",
            f"- {target_status}: target provider commit/repo fixed",
            f"- {draft_status}: draft provider commit/repo fixed",
            f"- {target_status}: target manifest/size/index/config/tokenizer",
            f"- {draft_status}: draft manifest/size/config/single weight file",
            f"- {target_status}: target marker written after atomic publish",
            (
                "- PASS: no symlink/hardlink/cache reference was used for "
                "a published snapshot"
                if target_publish and draft_publish
                else "- INCOMPLETE: both entity publishes are not complete"
            ),
            "",
            "Phase 02 was not entered. This executor did not commit or push.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--keepalive-marker", type=Path, required=True)
    parser.add_argument("--keepalive-status-evidence", type=Path, required=True)
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument("--copy-workers", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.worker_id != WORKER_ID:
        raise ValueError(f"refusing unassigned worker: {args.worker_id}")
    run_dir = args.run_dir.resolve()
    if run_dir.parent != RUN_ROOT:
        raise ValueError(f"run directory is outside Eagle3 root: {run_dir}")
    if not 1 <= args.download_workers <= 16:
        raise ValueError("download worker count must be 1..16")
    if not 1 <= args.copy_workers <= 8:
        raise ValueError("copy worker count must be 1..8")
    run_dir_preexisting = run_dir.exists()
    if run_dir_preexisting and not run_dir.is_dir():
        raise ValueError(f"Phase 01A run path is not a directory: {run_dir}")
    if run_dir_preexisting and not (
        ACQUISITION_ROOT / "owner.json"
    ).is_file():
        raise FileExistsError(
            "refusing pre-existing run directory without the pinned "
            "Phase 01A NVMe owner"
        )
    ACQUISITION_ROOT.mkdir(parents=True, exist_ok=True)
    owner = create_owner(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    keepalive_evidence = validate_keepalive_marker(args.keepalive_marker)
    keepalive_status_text = args.keepalive_status_evidence.read_text(
        encoding="utf-8"
    )
    if "HEALTHY" not in keepalive_status_text:
        raise ValueError("independent keepalive status evidence is not healthy")
    atomic_write_json(run_dir / "keepalive_marker_validation.json", keepalive_evidence)
    copy_small_artifact(
        args.keepalive_status_evidence,
        run_dir / "keepalive_status_before.txt",
    )
    atomic_write_json(run_dir / "owner.json", owner)
    atomic_write_json(run_dir / "process_identity.json", process_identity())

    state = State(run_dir)
    state.start()
    target_publish: dict[str, Any] | None = None
    draft_publish: dict[str, Any] | None = None
    try:
        state.update("worker_preflight")
        inventory = require_worker_inventory()
        atomic_write_json(run_dir / "worker_preflight.json", inventory)

        state.update("provider_identity")
        api = HfApi()
        target_identity, target_provider = fetch_provider_identity(api, TARGET)
        draft_identity, draft_provider = fetch_provider_identity(api, DRAFT)
        atomic_write_json(
            run_dir / "target_provider_identity.json",
            target_identity,
        )
        atomic_write_json(
            run_dir / "draft_provider_identity.json",
            draft_identity,
        )
        capacity = ensure_capacity((target_identity, draft_identity))
        atomic_write_json(run_dir / "capacity.json", capacity)

        if TARGET_MARKER.exists():
            state.update("target_existing_publish_validation")
            marker = read_json(TARGET_MARKER)
            required_marker_values = {
                "status": "complete",
                "owner_session": "eagle3",
                "provider": "huggingface",
                "repo_id": TARGET.repo_id,
                "revision": TARGET.revision,
                "snapshot_path": str(TARGET.final_path),
                "manifest_path": str(
                    run_dir / "target_manifest.jsonl"
                ),
                "immutable": True,
            }
            conflicts = {
                key: {
                    "expected": expected,
                    "observed": marker.get(key),
                }
                for key, expected in required_marker_values.items()
                if marker.get(key) != expected
            }
            if conflicts:
                raise ValueError(
                    f"existing target marker conflicts: {conflicts}"
                )
            (
                target_validation,
                target_paths,
                target_publish,
            ) = validate_existing_publish(
                TARGET,
                target_provider,
                run_dir,
            )
            if (
                marker.get("manifest_sha256")
                != target_validation["manifest_sha256"]
            ):
                raise ValueError(
                    "existing target marker manifest hash conflicts"
                )
            atomic_write_json(
                run_dir / "target_complete_marker.json",
                marker,
            )
        else:
            if TARGET.final_path.exists():
                raise FileExistsError(
                    "target snapshot exists without its immutable marker"
                )
            target_validation, target_paths = download_and_validate(
                TARGET,
                target_identity,
                target_provider,
                run_dir,
                state,
                download_workers=args.download_workers,
            )
            state.update("target_hdfs_publish")
            target_publish = publish_snapshot(
                TARGET,
                target_provider,
                target_validation,
                run_dir=run_dir,
                copy_workers=args.copy_workers,
            )
            target_publish = {
                **target_publish,
                "manifest_path": str(target_paths["manifest"]),
            }
            atomic_write_json(target_paths["publish"], target_publish)

            state.update("target_complete_marker")
            marker = publish_target_marker(
                run_dir,
                target_validation,
                target_publish,
            )
            atomic_write_json(
                run_dir / "target_complete_marker.json",
                marker,
            )

        if DRAFT.final_path.exists():
            state.update("draft_existing_publish_validation")
            (
                draft_validation,
                draft_paths,
                draft_publish,
            ) = validate_existing_publish(
                DRAFT,
                draft_provider,
                run_dir,
            )
        else:
            draft_validation, draft_paths = download_and_validate(
                DRAFT,
                draft_identity,
                draft_provider,
                run_dir,
                state,
                download_workers=args.download_workers,
            )
            state.update("draft_hdfs_publish")
            draft_publish = publish_snapshot(
                DRAFT,
                draft_provider,
                draft_validation,
                run_dir=run_dir,
                copy_workers=args.copy_workers,
            )
            draft_publish = {
                **draft_publish,
                "manifest_path": str(draft_paths["manifest"]),
            }
            atomic_write_json(draft_paths["publish"], draft_publish)

        handoff = handoff_text(
            status="PASS — ready for main Agent acceptance",
            run_dir=run_dir,
            keepalive_evidence=keepalive_evidence,
            target_publish=target_publish,
            draft_publish=draft_publish,
        )
        atomic_write_bytes(
            run_dir / "phase-01a-handoff.md",
            handoff.encode("utf-8"),
        )
        state.update("complete", status="complete")
        return 0
    except BaseException as error:
        rendered = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        atomic_write_bytes(
            run_dir / "failure.txt",
            rendered.encode("utf-8"),
        )
        handoff = handoff_text(
            status="INCOMPLETE — blocker retained",
            run_dir=run_dir,
            keepalive_evidence=keepalive_evidence,
            target_publish=target_publish,
            draft_publish=draft_publish,
            error=str(error),
        )
        atomic_write_bytes(
            run_dir / "phase-01a-handoff.md",
            handoff.encode("utf-8"),
        )
        state.update(
            "failed",
            status="failed",
            error=f"{type(error).__name__}: {error}",
        )
        raise
    finally:
        state.stop()


if __name__ == "__main__":
    raise SystemExit(main())
