#!/usr/bin/env python3
"""Perform the P00 metadata-only checkpoint identity check."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
from typing import Any


MODEL_PATH = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/models/"
    "deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/"
    "modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
EXPECTED_SNAPSHOT = (
    "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
EXPECTED_REPOSITORY = "deepseek-ai/DeepSeek-V4-Flash-DSpark"
SHARD_PATTERN = re.compile(r"model-(\d{5})-of-00048\.safetensors")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.worker_id != "4106666":
        raise SystemExit("only worker 4106666 is authorized")

    complete_path = MODEL_PATH / ".complete"
    config_path = MODEL_PATH / "config.json"
    index_path = MODEL_PATH / "model.safetensors.index.json"
    required_paths = [
        complete_path,
        config_path,
        index_path,
        MODEL_PATH / "tokenizer.json",
        MODEL_PATH / "tokenizer_config.json",
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    complete = (
        json.loads(complete_path.read_text(encoding="utf-8"))
        if complete_path.is_file()
        else {}
    )
    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.is_file()
        else {}
    )
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.is_file()
        else {}
    )

    top_level_files = sorted(
        path for path in MODEL_PATH.iterdir() if path.is_file()
    )
    payload_files = sorted(
        path
        for path in MODEL_PATH.rglob("*")
        if path.is_file() and path != complete_path
    )
    shards = [
        path for path in top_level_files if SHARD_PATTERN.fullmatch(path.name)
    ]
    expected_shard_names = {
        f"model-{number:05d}-of-00048.safetensors"
        for number in range(1, 49)
    }
    actual_shard_names = {path.name for path in shards}
    index_referents = set(index.get("weight_map", {}).values())
    payload_bytes = sum(path.stat().st_size for path in payload_files)
    shard_bytes = sum(path.stat().st_size for path in shards)
    symlinks = [
        str(path.relative_to(MODEL_PATH))
        for path in MODEL_PATH.rglob("*")
        if path.is_symlink()
    ]

    checks = {
        "model_path_exact": str(MODEL_PATH).endswith(EXPECTED_SNAPSHOT),
        "complete_status": complete.get("status") == "complete",
        "snapshot_identity": (
            complete.get("provider_payload_snapshot_id") == EXPECTED_SNAPSHOT
        ),
        "repository": complete.get("repository") == EXPECTED_REPOSITORY,
        "provider": complete.get("provider") == "modelscope",
        "file_count": (
            len(payload_files) == complete.get("provider_payload_file_count")
            == 75
        ),
        "payload_bytes": (
            payload_bytes == complete.get("provider_payload_bytes")
            == 166898666759
        ),
        "exact_48_shards": (
            len(shards) == 48 and actual_shard_names == expected_shard_names
        ),
        "index_referents": index_referents == expected_shard_names,
        "index_total_size": (
            index.get("metadata", {}).get("total_size") == 166878536440
        ),
        "no_symlinks": not symlinks,
        "required_files": not missing,
        "architecture": config.get("architectures")
        == ["DeepseekV4ForCausalLM"],
        "model_type": config.get("model_type") == "deepseek_v4",
        "packed_fp4": config.get("expert_dtype") == "fp4",
        "dspark_block_size": config.get("dspark_block_size") == 5,
        "dspark_markov_rank": config.get("dspark_markov_rank") == 256,
        "dspark_target_layer_ids": config.get("dspark_target_layer_ids")
        == [40, 41, 42],
    }
    payload = {
        "schema_version": 1,
        "authorized_phase": "P00",
        "observed_at_utc": dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "worker_id": args.worker_id,
        "hostname": platform.node(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "model_path": str(MODEL_PATH),
        "provider": complete.get("provider"),
        "repository": complete.get("repository"),
        "snapshot_identity": complete.get("provider_payload_snapshot_id"),
        "hf_reference_revision": (
            "62af8fffb2f7030cac4de2f0169f5b8d1101b646"
        ),
        "complete_marker": complete,
        "file_count": len(payload_files),
        "top_level_file_count_including_complete": len(top_level_files),
        "total_bytes": payload_bytes,
        "shard_count": len(shards),
        "shard_file_bytes_including_safetensors_headers": shard_bytes,
        "index_logical_tensor_bytes": index.get("metadata", {}).get(
            "total_size"
        ),
        "index_referent_count": len(index_referents),
        "critical_config": {
            key: config.get(key)
            for key in (
                "architectures",
                "model_type",
                "expert_dtype",
                "quantization_config",
                "dspark_block_size",
                "dspark_noise_token_id",
                "dspark_target_layer_ids",
                "dspark_markov_rank",
            )
        },
        "small_file_sha256": {
            path.name: sha256(path)
            for path in (complete_path, config_path, index_path)
            if path.is_file()
        },
        "checks": checks,
        "missing": missing,
        "symlinks": symlinks,
        "full_checkpoint_hash_performed": False,
        "note": (
            "P00 reused the published minimal identity and read only metadata, "
            "file sizes, the index, and critical config; it did not read all "
            "weight bytes."
        ),
    }
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.artifact_dir / "checkpoint_identity.json", payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "snapshot_identity": payload["snapshot_identity"],
                "file_count": payload["file_count"],
                "shard_count": payload["shard_count"],
                "total_bytes": payload["total_bytes"],
                "full_checkpoint_hash_performed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
