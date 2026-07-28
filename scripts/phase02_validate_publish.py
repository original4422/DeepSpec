#!/usr/bin/env python3
"""Operational-minimal validation and publication of the Phase 02 staging."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import traceback
from typing import Any


EXPECTED_FILES = 75
EXPECTED_BYTES = 166_898_666_759
EXPECTED_SHARDS = [
    f"model-{number:05d}-of-00048.safetensors"
    for number in range(1, 49)
]
EXPECTED_SNAPSHOT_ID = (
    "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "186d562ff6b1ebda2051cd12725acf5d230ed55a078106de95137630434806e9"
)
CORE_HASH_PATHS = [
    "config.json",
    "configuration.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def write_atomic(path: pathlib.Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(payload)
    os.replace(temporary, path)


def write_json(path: pathlib.Path, payload: Any) -> None:
    write_atomic(path, json_bytes(payload))


def artifact_record(path: pathlib.Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def stat_record(path: pathlib.Path, relative: str) -> dict[str, Any]:
    observed = path.lstat()
    return {
        "path": relative,
        "size_bytes": observed.st_size,
        "mode": stat.S_IMODE(observed.st_mode),
        "mtime_ns": observed.st_mtime_ns,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "is_regular": stat.S_ISREG(observed.st_mode),
        "is_symlink": stat.S_ISLNK(observed.st_mode),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--prior-attempt-id", required=True)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--source-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--staging", type=pathlib.Path, required=True)
    parser.add_argument("--formal", type=pathlib.Path, required=True)
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--prior-run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--scratch", type=pathlib.Path, required=True)
    parser.add_argument("--prior-scratch", type=pathlib.Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--keepalive-script", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = utc_now()
    published = False
    errors: list[str] = []
    args.scratch.mkdir(parents=True, exist_ok=False)
    log_path = args.scratch / "validation.log"

    def log(message: str) -> None:
        line = f"{utc_now()} {message}"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)

    try:
        if args.run_dir.exists():
            raise FileExistsError(f"run dir exists: {args.run_dir}")
        args.run_dir.mkdir(parents=True, exist_ok=False)
        if args.formal.exists():
            raise FileExistsError(f"formal target exists: {args.formal}")
        if not args.staging.is_dir():
            raise FileNotFoundError(f"staging missing: {args.staging}")
        if args.staging.parent != args.formal.parent:
            raise RuntimeError("staging and formal do not share a parent")

        manifest_sha = sha256_file(args.source_manifest)
        if manifest_sha != EXPECTED_SOURCE_MANIFEST_SHA256:
            raise RuntimeError("Phase 01 source manifest hash mismatch")
        manifest = json.loads(args.source_manifest.read_text())
        expected = {
            item["path"]: {
                "size_bytes": item["expected_size_bytes"],
                "sha256": item["expected_sha256"],
            }
            for item in manifest["modelscope_verification"]["files"]
        }
        if (
            len(expected) != EXPECTED_FILES
            or sum(item["size_bytes"] for item in expected.values())
            != EXPECTED_BYTES
            or ".complete" in expected
        ):
            raise RuntimeError("Phase 01 provider manifest structure mismatch")

        prior_pid = 4_170_621
        if pathlib.Path(f"/proc/{prior_pid}").exists():
            raise RuntimeError("prior full-hash coordinator is still running")

        prior_gate_path = args.prior_run_dir / "phase02_gate.json"
        if prior_gate_path.exists():
            raise FileExistsError("prior attempt gate unexpectedly exists")
        prior_gate = {
            "schema_version": 1,
            "authorized_phase": "Phase 02",
            "attempt_id": args.prior_attempt_id,
            "status": "FAIL",
            "failed_at_utc": utc_now(),
            "failure_class": "authorized_gpu_pause_coordination_conflict",
            "error": (
                "Full target SHA256 coordinator was intentionally terminated "
                "after its keepalive watchdog observed the separately "
                "authorized Phase 03 GPU validation pause."
            ),
            "copy_payload_complete": True,
            "copied_file_count": EXPECTED_FILES,
            "copied_bytes": EXPECTED_BYTES,
            "full_target_sha256_completed": False,
            "formal_target_exists": False,
            "staging_preserved": str(args.staging),
            "technical_checkpoint_failure": False,
            "recovery_attempt": args.attempt_id,
        }
        write_json(prior_gate_path, prior_gate)
        for name in [
            "attempt.json",
            "copy.log",
            "progress.json",
            "runner.log",
            "source_stat_before.json",
            "worker_monitor.json",
        ]:
            source_artifact = args.prior_scratch / name
            if source_artifact.exists():
                write_atomic(
                    args.prior_run_dir / name,
                    source_artifact.read_bytes(),
                )

        inventory = subprocess.run(
            ["mlx", "worker", "list"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
        matching = [
            line
            for line in inventory.stdout.splitlines()
            if re.match(rf"^{re.escape(args.worker_id)}\s+", line)
        ]
        fields = matching[0].split() if len(matching) == 1 else []
        if not (
            inventory.returncode == 0
            and len(matching) == 1
            and len(fields) >= 5
            and fields[3] == "4"
            and fields[4] == "NVIDIA-H20"
        ):
            raise RuntimeError("current worker is not the expected 4xH20")
        keepalive = subprocess.run(
            [
                "mlx",
                "worker",
                "login",
                args.worker_id,
                "--",
                "bash",
                args.keepalive_script,
                "status",
                args.worker_id,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        report = None
        for line in keepalive.stdout.splitlines():
            if line.startswith("{") and '"healthy"' in line:
                report = json.loads(line)
        if not (
            keepalive.returncode == 0
            and "HEALTHY on " in keepalive.stdout
            and isinstance(report, dict)
            and report.get("healthy") is True
            and report.get("expected_gpus") == 4
            and not report.get("underutilized_gpus")
        ):
            raise RuntimeError("restored keepalive status failed")
        keepalive_evidence = {
            "checked_at_utc": utc_now(),
            "worker_id": args.worker_id,
            "worker_list_matching_line": matching[0],
            "worker_list_stderr": inventory.stderr,
            "status_stdout": keepalive.stdout,
            "status_stderr": keepalive.stderr,
            "report": report,
            "status": "PASS",
        }
        write_json(args.scratch / "keepalive_validation.json", keepalive_evidence)
        log("WORKER_AND_KEEPALIVE_PASS")

        observed_paths: set[str] = set()
        symlinks: list[str] = []
        for candidate in args.staging.rglob("*"):
            relative = candidate.relative_to(args.staging).as_posix()
            if candidate.is_symlink():
                symlinks.append(relative)
            elif candidate.is_file():
                observed_paths.add(relative)
        expected_paths = set(expected)
        size_records = []
        for relative in sorted(expected):
            target = args.staging / relative
            observed = stat_record(target, relative)
            size_records.append(
                {
                    **observed,
                    "expected_size_bytes": expected[relative]["size_bytes"],
                    "size_match": (
                        observed["size_bytes"]
                        == expected[relative]["size_bytes"]
                    ),
                }
            )
        if observed_paths != expected_paths:
            errors.append("staging file set mismatch")
        if symlinks:
            errors.append("staging contains symlinks")
        if any(
            not item["is_regular"]
            or item["is_symlink"]
            or not item["size_match"]
            for item in size_records
        ):
            errors.append("staging size or file type mismatch")
        actual_bytes = sum(item["size_bytes"] for item in size_records)
        if actual_bytes != EXPECTED_BYTES:
            errors.append("staging total bytes mismatch")

        actual_shards = sorted(
            path
            for path in observed_paths
            if re.fullmatch(r"model-\d{5}-of-00048\.safetensors", path)
        )
        index = json.loads(
            (args.staging / "model.safetensors.index.json").read_text()
        )
        index_shards = sorted(set(index["weight_map"].values()))
        if actual_shards != EXPECTED_SHARDS:
            errors.append("actual shard set is not exactly 48")
        if index_shards != EXPECTED_SHARDS:
            errors.append("index shard set is not exactly 48")

        config = json.loads((args.staging / "config.json").read_text())
        if config.get("dspark_block_size") != 5:
            errors.append("dspark_block_size is not 5")
        if config.get("expert_dtype") != "fp4":
            errors.append("expert_dtype is not fp4")
        if not set(CORE_HASH_PATHS).issubset(observed_paths):
            errors.append("required config/tokenizer/index file missing")
        core_hashes = []
        for relative in CORE_HASH_PATHS:
            actual_sha = sha256_file(args.staging / relative)
            core_hashes.append(
                {
                    "path": relative,
                    "expected_sha256": expected[relative]["sha256"],
                    "actual_sha256": actual_sha,
                    "match": actual_sha == expected[relative]["sha256"],
                }
            )
        if any(not item["match"] for item in core_hashes):
            errors.append("core file SHA256 mismatch")

        prior_source = json.loads(
            (args.prior_scratch / "source_stat_before.json").read_text()
        )["files"]
        source_after = [
            stat_record(args.source / relative, relative)
            for relative in sorted(expected)
        ]
        source_unchanged = prior_source == source_after
        if not source_unchanged:
            errors.append("source stat snapshot changed")
        independence = []
        for relative in sorted(expected):
            source_stat = (args.source / relative).stat()
            target_stat = (args.staging / relative).stat()
            samefile = os.path.samefile(
                args.source / relative, args.staging / relative
            )
            independence.append(
                {
                    "path": relative,
                    "source_device": source_stat.st_dev,
                    "source_inode": source_stat.st_ino,
                    "target_device": target_stat.st_dev,
                    "target_inode": target_stat.st_ino,
                    "samefile": samefile,
                    "same_device_and_inode": (
                        source_stat.st_dev == target_stat.st_dev
                        and source_stat.st_ino == target_stat.st_ino
                    ),
                }
            )
        if any(
            item["samefile"] or item["same_device_and_inode"]
            for item in independence
        ):
            errors.append("source and staging share file identity")
        if errors:
            raise RuntimeError("; ".join(errors))

        target_validation = {
            "schema_version": 1,
            "attempt_id": args.attempt_id,
            "validated_at_utc": utc_now(),
            "validation_level": "operational_minimal_user_authorized",
            "full_target_sha256_performed": False,
            "unverified_target_weight_sha256_count": 48,
            "provider_payload_snapshot_id_inherited_from_phase01": (
                EXPECTED_SNAPSHOT_ID
            ),
            "file_count": len(observed_paths),
            "total_bytes": actual_bytes,
            "missing_paths": sorted(expected_paths - observed_paths),
            "extra_paths": sorted(observed_paths - expected_paths),
            "symlinks": symlinks,
            "actual_weight_shards": actual_shards,
            "index_weight_shards": index_shards,
            "core_file_sha256": core_hashes,
            "config": {
                "architectures": config.get("architectures"),
                "model_type": config.get("model_type"),
                "expert_dtype": config.get("expert_dtype"),
                "dspark_block_size": config.get("dspark_block_size"),
                "dspark_target_layer_ids": config.get(
                    "dspark_target_layer_ids"
                ),
                "num_nextn_predict_layers": config.get(
                    "num_nextn_predict_layers"
                ),
            },
            "independent_entity_copy": {
                "all_file_identities_distinct": True,
                "records": independence,
            },
            "size_records": size_records,
            "status": "PASS",
        }
        source_unchanged_record = {
            "schema_version": 1,
            "attempt_id": args.attempt_id,
            "source": str(args.source),
            "before_attempt": args.prior_attempt_id,
            "before": prior_source,
            "after": source_after,
            "unchanged": True,
            "source_was_read_only": True,
        }
        log(
            "OPERATIONAL_MINIMAL_VALIDATION_PASS "
            f"files={len(observed_paths)} bytes={actual_bytes}"
        )

        os.rename(args.staging, args.formal)
        published = True
        complete = {
            "schema_version": 1,
            "status": "complete",
            "provider": "modelscope",
            "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
            "provider_revision": None,
            "provider_payload_snapshot_id": EXPECTED_SNAPSHOT_ID,
            "provider_payload_file_count": EXPECTED_FILES,
            "provider_payload_bytes": EXPECTED_BYTES,
            "source": str(args.source),
            "source_manifest": str(args.source_manifest),
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "copy_attempt_id": args.prior_attempt_id,
            "publication_attempt_id": args.attempt_id,
            "published_at_utc": utc_now(),
            "validation_level": "operational_minimal_user_authorized",
            "full_target_sha256_performed": False,
            "core_file_sha256_verified": CORE_HASH_PATHS,
        }
        write_json(args.formal / ".complete", complete)
        if json.loads((args.formal / ".complete").read_text()) != complete:
            raise RuntimeError(".complete readback mismatch")
        formal_paths = {
            path.relative_to(args.formal).as_posix()
            for path in args.formal.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        formal_symlinks = [
            path.relative_to(args.formal).as_posix()
            for path in args.formal.rglob("*")
            if path.is_symlink()
        ]
        if formal_paths != expected_paths | {".complete"} or formal_symlinks:
            raise RuntimeError("post-publication formal tree mismatch")

        copy_manifest = {
            "schema_version": 1,
            "copy_attempt_id": args.prior_attempt_id,
            "publication_attempt_id": args.attempt_id,
            "source": str(args.source),
            "formal_target": str(args.formal),
            "copy_method": (
                "4-worker python buffered userspace entity byte copy"
            ),
            "provider_payload_file_count": EXPECTED_FILES,
            "provider_payload_bytes": EXPECTED_BYTES,
            "copy_progress_terminal": json.loads(
                (args.prior_scratch / "progress.json").read_text()
            ),
            "status": "PASS",
        }
        storage = shutil.disk_usage(args.formal.parent)
        storage_after = {
            "schema_version": 1,
            "observed_at_utc": utc_now(),
            "formal_target": str(args.formal),
            "formal_payload_files": EXPECTED_FILES,
            "formal_payload_bytes": EXPECTED_BYTES,
            "staging_exists": args.staging.exists(),
            "hdfs": {
                "total_bytes": storage.total,
                "used_bytes": storage.used,
                "free_bytes": storage.free,
            },
        }
        provenance = {
            "schema_version": 1,
            "provider": "modelscope",
            "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
            "snapshot_identity": {
                "algorithm": "sha256_canonical_json_path_size_sha256",
                "value": EXPECTED_SNAPSHOT_ID,
                "verified_in_phase": "Phase 01 source",
            },
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "validation_level": "operational_minimal_user_authorized",
            "full_target_sha256_performed": False,
        }
        payloads = {
            "copy_manifest.json": copy_manifest,
            "source_unchanged.json": source_unchanged_record,
            "target_validation.json": target_validation,
            "storage_after.json": storage_after,
            "checkpoint_provenance.json": provenance,
            "destination_checkpoint_manifest.json": target_validation,
            "keepalive_validation.json": keepalive_evidence,
        }
        artifacts: dict[str, dict[str, Any]] = {}
        for name, payload in payloads.items():
            path = args.run_dir / name
            write_json(path, payload)
            artifacts[name] = artifact_record(path)
        write_atomic(
            args.run_dir / "source_checkpoint_manifest.json",
            args.source_manifest.read_bytes(),
        )
        artifacts["source_checkpoint_manifest.json"] = artifact_record(
            args.run_dir / "source_checkpoint_manifest.json"
        )
        write_atomic(
            args.run_dir / "copy.log",
            (args.prior_scratch / "copy.log").read_bytes(),
        )
        artifacts["copy.log"] = artifact_record(args.run_dir / "copy.log")
        write_atomic(
            args.run_dir / "validation.log", log_path.read_bytes()
        )
        artifacts["validation.log"] = artifact_record(
            args.run_dir / "validation.log"
        )
        write_atomic(
            args.run_dir / "copy_or_download.log",
            (args.prior_scratch / "copy.log").read_bytes(),
        )
        artifacts["copy_or_download.log"] = artifact_record(
            args.run_dir / "copy_or_download.log"
        )
        gate = {
            "schema_version": 1,
            "authorized_phase": "Phase 02",
            "attempt_id": args.attempt_id,
            "copy_attempt_id": args.prior_attempt_id,
            "audited_at_utc": utc_now(),
            "status": "PASS",
            "errors": [],
            "validation_level": "operational_minimal_user_authorized",
            "full_target_sha256_performed": False,
            "unverified_target_weight_sha256_count": 48,
            "source_phase01_full_manifest_verified": True,
            "copied_file_count": EXPECTED_FILES,
            "copied_bytes": EXPECTED_BYTES,
            "target_file_set_and_sizes_verified": True,
            "target_core_file_sha256_verified": True,
            "target_48_shards_and_index_verified": True,
            "target_config_and_tokenizer_verified": True,
            "target_has_no_symlinks": True,
            "target_independent_entity_copy": True,
            "source_unchanged": True,
            "worker_and_keepalive_status": "PASS",
            "formal_target": str(args.formal),
            "formal_target_exists": args.formal.is_dir(),
            "staging_absent": not args.staging.exists(),
            "complete_marker": artifact_record(args.formal / ".complete"),
            "required_final_artifact_hashes": artifacts,
            "next_eligible_phase": (
                "Phase 04 only after Phase 03 PASS and user confirmation"
            ),
        }
        write_json(args.run_dir / "phase02_gate.json", gate)
        log(f"PHASE02_PASS formal={args.formal}")
        return 0
    except Exception as error:
        if published:
            try:
                marker = args.formal / ".complete"
                if marker.exists():
                    marker.unlink()
                if not args.staging.exists():
                    os.rename(args.formal, args.staging)
                published = False
            except Exception as rollback_error:
                errors.append(
                    f"rollback failed: {type(rollback_error).__name__}: "
                    f"{rollback_error}"
                )
        failure = {
            "schema_version": 1,
            "authorized_phase": "Phase 02",
            "attempt_id": args.attempt_id,
            "status": "FAIL",
            "failed_at_utc": utc_now(),
            "error": f"{type(error).__name__}: {error}",
            "errors": errors,
            "traceback": traceback.format_exc(),
            "formal_target_exists": args.formal.exists(),
            "staging_exists": args.staging.exists(),
        }
        write_json(args.run_dir / "phase02_gate.json", failure)
        log(f"PHASE02_FAIL error={type(error).__name__}:{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
