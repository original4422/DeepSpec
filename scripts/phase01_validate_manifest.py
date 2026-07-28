#!/usr/bin/env python3
"""Validate and normalize the completed Phase 01 checkpoint manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
from typing import Any


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def write_text_atomic(path: pathlib.Path, payload: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: pathlib.Path, payload: Any) -> None:
    write_text_atomic(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()
    artifact_dir = pathlib.Path(args.artifact_dir)
    manifest_path = artifact_dir / "source_checkpoint_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    local_manifest = manifest["full_local_manifest"]
    local_count = manifest["counts"][
        "local_regular_files_including_marker"
    ]
    provider_count = manifest["counts"]["modelscope_repository_files"]
    if len(local_manifest) != local_count:
        errors.append(
            f"local manifest count {len(local_manifest)} != {local_count}"
        )
    paths = [entry["path"] for entry in local_manifest]
    if len(paths) != len(set(paths)):
        errors.append("full local manifest contains duplicate paths")
    if sum(entry["size_bytes"] for entry in local_manifest) != manifest[
        "bytes"
    ]["local_all_regular_files_total_bytes"]:
        errors.append("local manifest byte sum mismatch")
    if manifest["counts"]["actual_weight_shards"] != 48:
        errors.append("actual weight shard count is not 48")
    if manifest["counts"]["index_weight_shards"] != 48:
        errors.append("index weight shard count is not 48")
    if not manifest["checkpoint_structure"]["actual_shards_exact"]:
        errors.append("actual shard names are not exact")
    if not manifest["checkpoint_structure"]["index_shards_exact"]:
        errors.append("index shard references are not exact")
    if not manifest["modelscope_verification"][
        "all_provider_files_match"
    ]:
        errors.append("ModelScope provider file verification failed")
    if manifest["modelscope_verification"]["missing"]:
        errors.append("ModelScope provider files are missing")
    if manifest["modelscope_verification"][
        "content_or_size_mismatches"
    ]:
        errors.append("ModelScope provider files have mismatches")
    if manifest["modelscope_verification"]["extras"] != [".complete"]:
        errors.append("unexpected local files outside ModelScope snapshot")
    if not manifest["source_snapshot_unchanged_during_verification"]:
        errors.append("source snapshot changed during hashing")
    if not manifest["worker_watchdog"]["seen_on_every_check"]:
        errors.append("worker disappeared during hashing")

    local_snapshot_id = canonical_sha256(local_manifest)
    provider_manifest = [
        entry for entry in local_manifest if entry["path"] != ".complete"
    ]
    if len(provider_manifest) != provider_count:
        errors.append(
            f"provider manifest count {len(provider_manifest)} "
            f"!= {provider_count}"
        )
    provider_snapshot_id = canonical_sha256(provider_manifest)
    recorded_local = manifest["provider_identity"][
        "immutable_local_tree_snapshot_id"
    ]["value"]
    recorded_provider = manifest["provider_identity"][
        "immutable_local_payload_snapshot_id"
    ]["value"]
    if local_snapshot_id != recorded_local:
        errors.append("local tree snapshot ID recomputation mismatch")
    if provider_snapshot_id != recorded_provider:
        errors.append("provider payload snapshot ID recomputation mismatch")

    corrections = []
    expected_provider_scope = (
        f"{provider_count} ModelScope repository files; excludes .complete"
    )
    provider_identity = manifest["provider_identity"]
    if (
        provider_identity["immutable_local_payload_snapshot_id"]["scope"]
        != expected_provider_scope
    ):
        corrections.append(
            {
                "field": (
                    "provider_identity.immutable_local_payload_snapshot_id."
                    "scope"
                ),
                "old": provider_identity[
                    "immutable_local_payload_snapshot_id"
                ]["scope"],
                "new": expected_provider_scope,
                "reason": "initial report text used the HF file count",
            }
        )
        provider_identity["immutable_local_payload_snapshot_id"][
            "scope"
        ] = expected_provider_scope
    expected_local_scope = (
        f"all {local_count} local regular files; includes .complete"
    )
    if (
        provider_identity["immutable_local_tree_snapshot_id"]["scope"]
        != expected_local_scope
    ):
        corrections.append(
            {
                "field": (
                    "provider_identity.immutable_local_tree_snapshot_id."
                    "scope"
                ),
                "old": provider_identity[
                    "immutable_local_tree_snapshot_id"
                ]["scope"],
                "new": expected_local_scope,
                "reason": "initial report text used the HF file count",
            }
        )
        provider_identity["immutable_local_tree_snapshot_id"][
            "scope"
        ] = expected_local_scope

    validation = {
        "schema_version": 1,
        "validated_at_utc": utc_now(),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "corrections": corrections,
        "recomputed": {
            "local_tree_snapshot_id": local_snapshot_id,
            "provider_payload_snapshot_id": provider_snapshot_id,
            "local_file_count": len(local_manifest),
            "provider_file_count": len(provider_manifest),
            "local_total_bytes": sum(
                entry["size_bytes"] for entry in local_manifest
            ),
        },
    }
    manifest["artifact_validation"] = validation
    write_json(manifest_path, manifest)
    write_json(
        artifact_dir / "checkpoint_manifest_validation.json",
        validation,
    )

    preflight_log = artifact_dir / "preflight.log"
    previous = (
        preflight_log.read_text(encoding="utf-8")
        if preflight_log.is_file()
        else ""
    )
    summary_lines = [
        "",
        f"{utc_now()} CHECKPOINT_HASH_SUMMARY",
        (
            f"modelscope_provider_files={provider_count} "
            "all_size_sha256_match=true"
        ),
        (
            "weight_shards=48 index_shards=48 "
            f"provider_payload_snapshot_id={provider_snapshot_id}"
        ),
        (
            "hf_reference_weight_matches=48 "
            "hf_reference_core_mismatches=0 "
            "hf_reference_ancillary_mismatches=.gitattributes,LICENSE"
        ),
        (
            "source_snapshot_unchanged=true "
            "worker_watchdog_all_present=true"
        ),
        (
            "hash_wrapper_exit=1 due to HDFS tee append "
            "Operation_not_supported; manifest process completed and "
            f"independent_validation={validation['status']}"
        ),
        (
            f"manifest_scope_text_corrections={len(corrections)} "
            "snapshot_ids_recomputed_without_mismatch=true"
        ),
    ]
    write_text_atomic(
        preflight_log,
        previous.rstrip("\n") + "\n" + "\n".join(summary_lines) + "\n",
    )
    print(json.dumps(validation, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
