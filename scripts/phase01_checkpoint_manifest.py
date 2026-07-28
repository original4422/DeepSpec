#!/usr/bin/env python3
"""Freeze and verify the read-only ModelScope checkpoint source.

The local tree is hashed in full.  ModelScope ``master`` metadata is the
provider identity, while the fixed Hugging Face revision is retained only as a
cross-provider comparison.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from typing import Any


SHARD_PATTERN = re.compile(r"model-(\d{5})-of-00048\.safetensors")
MODEL_CRITICAL_PATHS = {
    "config.json",
    "configuration.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
}
PROGRESS_LOCK = threading.Lock()
PROGRESS_BYTES = 0
PROGRESS_FILES = 0
WORKER_CHECKS: list[dict[str, Any]] = []


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    global PROGRESS_BYTES, PROGRESS_FILES
    digest = hashlib.sha256()
    bytes_read = 0
    with path.open("rb", buffering=16 * 1024 * 1024) as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            bytes_read += len(chunk)
    with PROGRESS_LOCK:
        PROGRESS_BYTES += bytes_read
        PROGRESS_FILES += 1
    return digest.hexdigest()


def git_blob_sha1(path: pathlib.Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode())
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        file_stat = path.lstat()
        kind = (
            "symlink"
            if stat.S_ISLNK(file_stat.st_mode)
            else "file"
            if stat.S_ISREG(file_stat.st_mode)
            else "directory"
            if stat.S_ISDIR(file_stat.st_mode)
            else "other"
        )
        result[relative] = {
            "kind": kind,
            "size_bytes": file_stat.st_size,
            "mtime_ns": file_stat.st_mtime_ns,
            "inode": file_stat.st_ino,
            "device": file_stat.st_dev,
            "link_count": file_stat.st_nlink,
        }
    return result


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DeepSpec-Phase01-Preflight/1"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def fetch_hf_metadata(
    repository: str,
    revision: str,
) -> tuple[str, dict[str, Any]]:
    url = (
        f"https://huggingface.co/api/models/{repository}/revision/"
        f"{revision}?blobs=true"
    )
    return url, fetch_json(url)


def fetch_modelscope_metadata(
    repository: str,
    revision: str,
) -> tuple[
    dict[str, str],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
]:
    api_root = f"https://www.modelscope.cn/api/v1/models/{repository}"
    urls = {
        "repository": api_root,
        "revisions": f"{api_root}/revisions",
        "files": f"{api_root}/repo/files",
    }
    repository_payload = fetch_json(urls["repository"])
    revisions_payload = fetch_json(urls["revisions"])
    pending_roots = [""]
    visited_roots: set[str] = set()
    files: list[dict[str, Any]] = []
    raw_queries: list[dict[str, Any]] = []
    while pending_roots:
        root = pending_roots.pop(0)
        if root in visited_roots:
            continue
        visited_roots.add(root)
        query_url = urls["files"] + "?" + urllib.parse.urlencode(
            {"Revision": revision, "Root": root}
        )
        payload = fetch_json(query_url)
        raw_queries.append(
            {
                "root": root,
                "url": query_url,
                "payload": payload,
            }
        )
        if payload.get("Code") != 200 or not payload.get("Success"):
            raise RuntimeError(f"ModelScope file query failed: {query_url}")
        for entry in payload["Data"]["Files"]:
            if entry.get("Type") == "tree":
                pending_roots.append(entry["Path"])
            elif entry.get("Type") == "blob":
                files.append(dict(entry))
            else:
                raise RuntimeError(
                    f"unexpected ModelScope entry type: {entry!r}"
                )
    raw_file_payload = {
        "schema_version": 1,
        "provider": "modelscope",
        "repository": repository,
        "requested_revision": revision,
        "queries": raw_queries,
    }
    return (
        urls,
        repository_payload,
        revisions_payload,
        files,
        raw_file_payload,
    )


def worker_check(worker_id: str) -> dict[str, Any]:
    observed_at = utc_now()
    try:
        completed = subprocess.run(
            ["mlx", "worker", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        matching_lines = [
            line
            for line in completed.stdout.splitlines()
            if line.split(maxsplit=1)[0:1] == [worker_id]
        ]
        return {
            "observed_at_utc": observed_at,
            "returncode": completed.returncode,
            "worker_id": worker_id,
            "present": completed.returncode == 0 and len(matching_lines) == 1,
            "matching_lines": matching_lines,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "observed_at_utc": observed_at,
            "returncode": None,
            "worker_id": worker_id,
            "present": False,
            "error_type": type(error).__name__,
            "error": str(error),
        }


def categorize_hf_path(path: str) -> str:
    if SHARD_PATTERN.fullmatch(path):
        return "weight_shard"
    if path in MODEL_CRITICAL_PATHS:
        return "model_config_tokenizer_index"
    return "ancillary"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--modelscope-revision", default="master")
    parser.add_argument("--hf-reference-revision", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--hash-workers", type=int, default=4)
    args = parser.parse_args()

    source = pathlib.Path(args.source).resolve()
    artifact_dir = pathlib.Path(args.artifact_dir)
    if not source.is_dir():
        raise SystemExit(f"source is not a directory: {source}")
    if args.hash_workers < 1 or args.hash_workers > 8:
        raise SystemExit("hash worker count must be between 1 and 8")

    started_at = utc_now()
    print(
        f"{started_at} checkpoint manifest start source={source}",
        flush=True,
    )
    before = file_snapshot(source)
    local_files = {
        relative: metadata
        for relative, metadata in before.items()
        if metadata["kind"] == "file"
    }
    symlinks = sorted(
        relative
        for relative, metadata in before.items()
        if metadata["kind"] == "symlink"
    )

    (
        modelscope_urls,
        modelscope_repository,
        modelscope_revisions,
        modelscope_entries,
        modelscope_file_payload,
    ) = fetch_modelscope_metadata(
        args.repository,
        args.modelscope_revision,
    )
    write_json(
        artifact_dir / "modelscope_repository_metadata.json",
        {
            "schema_version": 1,
            "provider": "modelscope",
            "repository": args.repository,
            "requested_revision": args.modelscope_revision,
            "urls": modelscope_urls,
            "repository_response": modelscope_repository,
            "revisions_response": modelscope_revisions,
        },
    )
    write_json(
        artifact_dir / "modelscope_file_metadata.json",
        modelscope_file_payload,
    )
    modelscope_files = {
        entry["Path"]: entry for entry in modelscope_entries
    }
    if len(modelscope_files) != len(modelscope_entries):
        raise SystemExit("duplicate paths in ModelScope file metadata")

    hf_url, hf = fetch_hf_metadata(
        args.repository,
        args.hf_reference_revision,
    )
    write_json(artifact_dir / "hf_revision_metadata.json", hf)
    if hf.get("sha") != args.hf_reference_revision:
        raise SystemExit(
            "Hugging Face API did not resolve to the requested revision"
        )
    hf_files = {item["rfilename"]: item for item in hf.get("siblings", [])}

    print(
        f"{utc_now()} hashing all {len(local_files)} local files with "
        f"{args.hash_workers} workers",
        flush=True,
    )
    stop_heartbeat = threading.Event()
    WORKER_CHECKS.append(worker_check(args.worker_id))

    def heartbeat() -> None:
        while not stop_heartbeat.wait(30.0):
            check = worker_check(args.worker_id)
            with PROGRESS_LOCK:
                WORKER_CHECKS.append(check)
                completed_bytes = PROGRESS_BYTES
                completed_files = PROGRESS_FILES
            print(
                f"{utc_now()} hash heartbeat completed_files="
                f"{completed_files}/{len(local_files)} "
                f"completed_bytes={completed_bytes} "
                f"worker_present={check['present']}",
                flush=True,
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    local_hashes: dict[str, str] = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.hash_workers
        ) as executor:
            futures = {
                executor.submit(sha256_file, source / relative): relative
                for relative in local_files
            }
            for future in concurrent.futures.as_completed(futures):
                relative = futures[future]
                local_hashes[relative] = future.result()
                print(f"{utc_now()} hashed {relative}", flush=True)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1.0)
    WORKER_CHECKS.append(worker_check(args.worker_id))

    after = file_snapshot(source)
    source_unchanged = before == after
    provider_missing = sorted(set(modelscope_files) - set(local_files))
    provider_extras = sorted(set(local_files) - set(modelscope_files))
    provider_results: list[dict[str, Any]] = []
    provider_mismatches: list[dict[str, Any]] = []
    for relative, expected in sorted(modelscope_files.items()):
        result = {
            "path": relative,
            "expected_size_bytes": expected.get("Size"),
            "expected_sha256": expected.get("Sha256"),
            "provider_file_revision": expected.get("Revision"),
            "provider_is_lfs": expected.get("IsLFS"),
            "exists": relative in local_files,
        }
        if relative in local_files:
            result["actual_size_bytes"] = local_files[relative]["size_bytes"]
            result["actual_sha256"] = local_hashes[relative]
            result["size_match"] = (
                local_files[relative]["size_bytes"] == expected.get("Size")
            )
            result["content_match"] = (
                local_hashes[relative] == expected.get("Sha256")
            )
        else:
            result["size_match"] = False
            result["content_match"] = False
        if not result["size_match"] or not result["content_match"]:
            provider_mismatches.append(result)
        provider_results.append(result)

    local_manifest = [
        {
            "path": relative,
            "size_bytes": local_files[relative]["size_bytes"],
            "sha256": local_hashes[relative],
        }
        for relative in sorted(local_files)
    ]
    provider_payload_manifest = [
        {
            "path": relative,
            "size_bytes": local_files[relative]["size_bytes"],
            "sha256": local_hashes[relative],
        }
        for relative in sorted(modelscope_files)
        if relative in local_files
    ]
    local_tree_snapshot_id = canonical_sha256(local_manifest)
    provider_payload_snapshot_id = canonical_sha256(
        provider_payload_manifest
    )

    hf_results: list[dict[str, Any]] = []
    hf_mismatches_by_category = {
        "weight_shard": [],
        "model_config_tokenizer_index": [],
        "ancillary": [],
    }
    hf_matches_by_category = {
        "weight_shard": 0,
        "model_config_tokenizer_index": 0,
        "ancillary": 0,
    }
    for relative, expected in sorted(hf_files.items()):
        category = categorize_hf_path(relative)
        result: dict[str, Any] = {
            "path": relative,
            "category": category,
            "exists": relative in local_files,
            "expected_size_bytes": expected.get("size"),
            "official_blob_id": expected.get("blobId"),
            "official_lfs": expected.get("lfs"),
        }
        if relative not in local_files:
            result["content_match"] = False
        elif expected.get("lfs") is not None:
            result["verification_method"] = "sha256_vs_hf_lfs_oid"
            result["actual_sha256"] = local_hashes[relative]
            result["expected_sha256"] = expected["lfs"].get("sha256")
            result["content_match"] = (
                result["actual_sha256"] == result["expected_sha256"]
                and local_files[relative]["size_bytes"]
                == expected.get("size")
            )
        else:
            actual_blob = git_blob_sha1(source / relative)
            result["verification_method"] = "git_blob_sha1"
            result["actual_git_blob_id"] = actual_blob
            result["actual_sha256"] = local_hashes[relative]
            result["content_match"] = (
                actual_blob == expected.get("blobId")
                and local_files[relative]["size_bytes"]
                == expected.get("size")
            )
        if result["content_match"]:
            hf_matches_by_category[category] += 1
        else:
            hf_mismatches_by_category[category].append(result)
        hf_results.append(result)

    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    index = json.loads(
        (source / "model.safetensors.index.json").read_text(encoding="utf-8")
    )
    index_shards = sorted(set(index.get("weight_map", {}).values()))
    actual_shards = sorted(
        relative
        for relative in local_files
        if SHARD_PATTERN.fullmatch(relative)
    )
    expected_shards = [
        f"model-{ordinal:05d}-of-00048.safetensors"
        for ordinal in range(1, 49)
    ]
    complete_path = source / ".complete"
    complete_payload = (
        complete_path.read_text(encoding="utf-8")
        if complete_path.is_file()
        else None
    )
    provider_exact = (
        not provider_missing
        and provider_extras == [".complete"]
        and not provider_mismatches
        and not symlinks
    )
    worker_seen_all_checks = bool(WORKER_CHECKS) and all(
        check["present"] for check in WORKER_CHECKS
    )

    hedge_fetch_script = pathlib.Path(
        "/mlx_devbox/users/pengzegang/playground/github/HEDGE/"
        "scripts/fetch_v4flash.sh"
    )
    acquisition_script = None
    if hedge_fetch_script.is_file():
        acquisition_script = {
            "path": str(hedge_fetch_script),
            "sha256": sha256_file(hedge_fetch_script),
            "contents": hedge_fetch_script.read_text(encoding="utf-8"),
        }

    payload = {
        "schema_version": 2,
        "authorized_phase": "Phase 01",
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "source_path": str(source),
        "source_was_read_only_observation": True,
        "source_snapshot_unchanged_during_verification": source_unchanged,
        "provider_identity": {
            "provider": "modelscope",
            "repository": args.repository,
            "requested_revision": args.modelscope_revision,
            "repository_api_success": modelscope_repository.get("Success"),
            "repository_api_model_id": (
                modelscope_repository.get("Data") or {}
            ).get("Id"),
            "repository_api_name": (
                modelscope_repository.get("Data") or {}
            ).get("Name"),
            "repository_api_revision": (
                modelscope_repository.get("Data") or {}
            ).get("Revision"),
            "repository_namespace": args.repository.split("/", 1)[0],
            "provider_file_revisions": sorted(
                {
                    entry.get("Revision")
                    for entry in modelscope_entries
                    if entry.get("Revision")
                }
            ),
            "provider_snapshot_commit_available": False,
            "immutable_local_payload_snapshot_id": {
                "algorithm": "sha256_canonical_json_path_size_sha256",
                "value": provider_payload_snapshot_id,
                "scope": (
                    f"{len(modelscope_files)} ModelScope repository files; "
                    "excludes .complete"
                ),
            },
            "immutable_local_tree_snapshot_id": {
                "algorithm": "sha256_canonical_json_path_size_sha256",
                "value": local_tree_snapshot_id,
                "scope": (
                    f"all {len(local_files)} local regular files; "
                    "includes .complete"
                ),
            },
            "local_complete_contents": complete_payload,
            "acquisition_script": acquisition_script,
        },
        "counts": {
            "local_regular_files_including_marker": len(local_files),
            "modelscope_repository_files": len(modelscope_files),
            "provider_missing_files": len(provider_missing),
            "provider_extra_files": len(provider_extras),
            "actual_weight_shards": len(actual_shards),
            "index_weight_shards": len(index_shards),
            "hf_reference_files": len(hf_files),
        },
        "bytes": {
            "modelscope_repository_total_bytes": sum(
                int(item.get("Size") or 0)
                for item in modelscope_files.values()
            ),
            "local_provider_paths_total_bytes": sum(
                int(local_files[path]["size_bytes"])
                for path in modelscope_files
                if path in local_files
            ),
            "local_all_regular_files_total_bytes": sum(
                int(item["size_bytes"]) for item in local_files.values()
            ),
        },
        "checkpoint_config": {
            "architectures": config.get("architectures"),
            "model_type": config.get("model_type"),
            "expert_dtype": config.get("expert_dtype"),
            "quantization_config": config.get("quantization_config"),
            "dspark_block_size": config.get("dspark_block_size"),
            "dspark_noise_token_id": config.get("dspark_noise_token_id"),
            "dspark_target_layer_ids": config.get(
                "dspark_target_layer_ids"
            ),
            "dspark_markov_rank": config.get("dspark_markov_rank"),
            "num_nextn_predict_layers": config.get(
                "num_nextn_predict_layers"
            ),
        },
        "checkpoint_structure": {
            "required_tokenizer_files_present": all(
                name in local_files
                for name in ("tokenizer.json", "tokenizer_config.json")
            ),
            "config_present": "config.json" in local_files,
            "configuration_present": "configuration.json" in local_files,
            "weight_index_present": (
                "model.safetensors.index.json" in local_files
            ),
            "complete_marker_present": ".complete" in local_files,
            "actual_shards": actual_shards,
            "index_shards": index_shards,
            "expected_shards": expected_shards,
            "actual_shards_exact": actual_shards == expected_shards,
            "index_shards_exact": index_shards == expected_shards,
        },
        "modelscope_verification": {
            "all_provider_files_match": provider_exact,
            "source_snapshot_unchanged": source_unchanged,
            "missing": provider_missing,
            "extras": provider_extras,
            "symlinks": symlinks,
            "content_or_size_mismatches": provider_mismatches,
            "files": provider_results,
        },
        "hf_fixed_revision_reference": {
            "metadata_url": hf_url,
            "requested_revision": args.hf_reference_revision,
            "resolved_revision": hf.get("sha"),
            "role": "cross-provider reference only; not acquisition gate",
            "matches_by_category": hf_matches_by_category,
            "mismatches_by_category": hf_mismatches_by_category,
            "files": hf_results,
        },
        "full_local_manifest": local_manifest,
        "worker_watchdog": {
            "worker_id": args.worker_id,
            "seen_on_every_check": worker_seen_all_checks,
            "checks": WORKER_CHECKS,
        },
    }
    write_json(artifact_dir / "source_checkpoint_manifest.json", payload)
    print(
        json.dumps(
            {
                "modelscope_all_provider_files_match": provider_exact,
                "source_snapshot_unchanged": source_unchanged,
                "modelscope_repository_files": len(modelscope_files),
                "actual_weight_shards": len(actual_shards),
                "provider_mismatches": provider_mismatches,
                "provider_missing": provider_missing,
                "provider_extras": provider_extras,
                "immutable_local_payload_snapshot_id": (
                    provider_payload_snapshot_id
                ),
                "hf_matches_by_category": hf_matches_by_category,
                "hf_mismatch_counts_by_category": {
                    category: len(items)
                    for category, items in hf_mismatches_by_category.items()
                },
                "worker_seen_on_every_check": worker_seen_all_checks,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
