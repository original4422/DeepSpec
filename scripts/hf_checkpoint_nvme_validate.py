#!/usr/bin/env python3
"""Validate a completed Hugging Face snapshot without hashing large files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


SHARD_PATTERN = re.compile(r"model-(\d{5})-of-00048\.safetensors")
CORE_FILES = (
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--nvme-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()

    snapshot = args.nvme_root / "snapshot"
    metadata_path = args.nvme_root / "metadata" / "hf_metadata.json"
    metadata = read_json(metadata_path)

    expected_sizes = {item["path"]: int(item["size"]) for item in metadata["files"]}
    expected_paths = set(expected_sizes)
    actual_paths: set[str] = set()
    symlinks: list[str] = []
    for path in snapshot.rglob("*"):
        relative = path.relative_to(snapshot)
        if relative.parts and relative.parts[0] == ".cache":
            continue
        relative_text = relative.as_posix()
        if path.is_symlink():
            symlinks.append(relative_text)
        elif path.is_file():
            actual_paths.add(relative_text)

    missing_paths = sorted(expected_paths - actual_paths)
    extra_paths = sorted(actual_paths - expected_paths)
    size_mismatches = []
    actual_total_bytes = 0
    for relative in sorted(expected_paths & actual_paths):
        actual_size = (snapshot / relative).stat().st_size
        actual_total_bytes += actual_size
        if actual_size != expected_sizes[relative]:
            size_mismatches.append(
                {
                    "path": relative,
                    "expected": expected_sizes[relative],
                    "actual": actual_size,
                }
            )

    shard_paths = sorted(
        path for path in actual_paths if SHARD_PATTERN.fullmatch(path)
    )
    expected_shards = [
        f"model-{index:05d}-of-00048.safetensors" for index in range(1, 49)
    ]
    missing_core_files = sorted(set(CORE_FILES) - actual_paths)

    checks = {
        "provider_is_huggingface": metadata.get("provider") == "huggingface",
        "repo_id_matches": metadata.get("repo_id") == args.repo_id,
        "requested_revision_matches": (
            metadata.get("requested_revision") == args.revision
        ),
        "resolved_revision_matches": (
            metadata.get("resolved_revision") == args.revision
        ),
        "metadata_file_count_is_74": metadata.get("file_count") == 74,
        "metadata_shard_count_is_48": metadata.get("shard_count") == 48,
        "metadata_total_bytes_matches": (
            metadata.get("expected_total_bytes") == sum(expected_sizes.values())
        ),
        "path_set_matches": not missing_paths and not extra_paths,
        "all_sizes_match": not size_mismatches,
        "total_bytes_match": (
            actual_total_bytes == metadata.get("expected_total_bytes")
        ),
        "shard_set_matches": shard_paths == expected_shards,
        "core_files_present": not missing_core_files,
        "no_symlinks": not symlinks,
    }
    passed = all(checks.values())
    payload = {
        "schema_version": 1,
        "timestamp": utc_timestamp(),
        "attempt_id": args.attempt_id,
        "status": "PASS" if passed else "FAIL",
        "scope": (
            "fixed revision, exact provider path set and sizes, 48 shards, "
            "core files, and no provider symlinks; no content hashes"
        ),
        "provider": metadata.get("provider"),
        "repo_id": metadata.get("repo_id"),
        "requested_revision": metadata.get("requested_revision"),
        "resolved_revision": metadata.get("resolved_revision"),
        "snapshot_path": str(snapshot),
        "expected_file_count": len(expected_paths),
        "actual_file_count": len(actual_paths),
        "expected_total_bytes": metadata.get("expected_total_bytes"),
        "actual_total_bytes": actual_total_bytes,
        "expected_shard_count": 48,
        "actual_shard_count": len(shard_paths),
        "core_files": list(CORE_FILES),
        "missing_core_files": missing_core_files,
        "missing_paths": missing_paths,
        "extra_paths": extra_paths,
        "size_mismatches": size_mismatches,
        "symlinks": sorted(symlinks),
        "checks": checks,
        "content_hashes_computed": False,
        "hdfs_copy_performed": False,
        "published": False,
        "publication_marker_written": False,
    }
    write_json(args.nvme_root / "metadata" / "nvme_minimal_validation.json", payload)
    write_json(args.run_dir / "nvme_minimal_validation.json", payload)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
