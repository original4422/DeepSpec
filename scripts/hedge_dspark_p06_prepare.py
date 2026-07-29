#!/usr/bin/env python3
"""Resolve the frozen runtime contract for the P06 native formal arm."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.config import (  # noqa: E402
    DATASET_REVISION,
    FORMAL_COUNT,
    MAX_TOTAL_ATTEMPTS,
    PROMPT_SUFFIX,
    WARMUP_COUNT,
)
from deepspec.hedge_protocol.io import load_jsonl, sha256_file  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
    EXPECTED_GPUS,
    EXPECTED_WORKER,
    FIXED_PORT,
    RUN_ROOT,
    _atomic_json,
    _base_environment,
    _check_fixed_port,
    _emit_nul,
    _fingerprint,
    _gpu_inventory_query,
    _server_command,
    _wait_no_cuda_contexts,
    build_checkpoint_identity,
    build_engine_identity,
    parse_gpu_inventory,
    parse_keepalive_status,
)
from hedge_dspark_p05_prepare import (  # noqa: E402
    CALIBRATION,
    CALIBRATION_SHA256,
    DATASET_FINGERPRINT,
    DATASET_MANIFEST,
    validate_calibration_dataset,
)


FORMAL = (
    REPO_ROOT
    / "artifacts/hedge-dspark/p01-protocol/gsm8k_formal_500.jsonl"
)
FORMAL_SHA256 = (
    "33554b90f751252ced2cfd16333d749f427c84cf025dccef4c7934144e9d5108"
)
DATASET_MANIFEST_SHA256 = (
    "34db2fc76099b2725f51dfd6ceeb1410802ad54c9008b2ab3cc1b8927f02be90"
)
P05_FREEZE_COMMIT = "c2446512713c2db2986cb5c1af88b72073b6be48"
FROZEN_CONFIG = (
    REPO_ROOT / "artifacts/hedge-dspark/p05-calibration/hedge_config.json"
)
FROZEN_CONFIG_SHA256 = (
    "760128b85b8c3dd67e3b4dee512cc302ee59bd2e2a1b3ab3390fd186ade36b71"
)
FROZEN_CONFIG_FINGERPRINT = (
    "6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921"
)
FROZEN_CALIBRATION_SUMMARY = (
    REPO_ROOT
    / "artifacts/hedge-dspark/p05-calibration/calibration_summary.json"
)
ATTEMPT_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z-p06-native-formal"
    r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_formal_datasets() -> dict[str, Any]:
    """Validate immutable warmup/formal bytes, identity, order, and disjointness."""

    calibration = validate_calibration_dataset()
    _require(
        sha256_file(DATASET_MANIFEST) == DATASET_MANIFEST_SHA256,
        "dataset manifest bytes differ from the frozen P01 artifact",
    )
    _require(
        sha256_file(FORMAL) == FORMAL_SHA256,
        "formal JSONL bytes differ from the frozen P01 artifact",
    )
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    selection = manifest.get("selection")
    source_dataset = manifest.get("dataset")
    _require(
        isinstance(artifacts, Mapping)
        and artifacts.get("gsm8k_formal_500.jsonl")
        == {"row_count": FORMAL_COUNT, "sha256": FORMAL_SHA256},
        "dataset manifest formal artifact identity mismatch",
    )
    _require(
        isinstance(selection, Mapping)
        and selection.get("formal_count") == FORMAL_COUNT
        and selection.get("calibration_count") == 32
        and selection.get("cohorts_disjoint") is True,
        "dataset manifest selection is not the frozen 32+500 protocol",
    )
    _require(
        isinstance(source_dataset, Mapping)
        and source_dataset.get("datasets_fingerprint")
        == DATASET_FINGERPRINT,
        "dataset manifest fingerprint mismatch",
    )
    formal_indices = selection.get("formal_indices")
    calibration_indices = selection.get("calibration_indices")
    _require(
        isinstance(formal_indices, list)
        and len(formal_indices) == FORMAL_COUNT
        and len(set(formal_indices)) == FORMAL_COUNT,
        "formal manifest must contain 500 unique indices",
    )
    _require(
        isinstance(calibration_indices, list)
        and len(calibration_indices) == 32
        and len(set(calibration_indices)) == 32,
        "calibration manifest must contain 32 unique indices",
    )
    _require(
        not set(formal_indices) & set(calibration_indices),
        "calibration and formal indices overlap",
    )

    samples = load_jsonl(FORMAL)
    _require(len(samples) == FORMAL_COUNT, "formal JSONL must contain 500 rows")
    observed_indices: list[int] = []
    prompt_records: list[dict[str, Any]] = []
    for position, sample in enumerate(samples):
        question = sample.get("question")
        expected_user_content = (
            question + "\n" + PROMPT_SUFFIX
            if isinstance(question, str)
            else None
        )
        _require(
            sample.get("cohort") == "formal"
            and sample.get("cohort_position") == position
            and sample.get("dataset_revision") == DATASET_REVISION
            and sample.get("dataset_fingerprint") == DATASET_FINGERPRINT
            and isinstance(question, str)
            and bool(question)
            and sample.get("user_content") == expected_user_content,
            f"formal row {position} identity/prompt is not frozen",
        )
        dataset_index = sample.get("dataset_index")
        _require(
            isinstance(dataset_index, int)
            and not isinstance(dataset_index, bool),
            f"formal row {position} dataset index is invalid",
        )
        observed_indices.append(dataset_index)
        prompt_records.append(
            {
                "cohort_position": position,
                "dataset_index": dataset_index,
                "user_content": expected_user_content,
            }
        )
    _require(
        observed_indices == formal_indices,
        "formal JSONL index order differs from its manifest",
    )
    warmup_indices = list(calibration["dataset_indices"][:WARMUP_COUNT])
    _require(
        warmup_indices == calibration_indices[:WARMUP_COUNT],
        "warmup must be calibration[0:10] in frozen order",
    )
    return {
        **calibration,
        "formal_jsonl": str(FORMAL),
        "formal_jsonl_sha256": FORMAL_SHA256,
        "dataset_manifest_sha256": DATASET_MANIFEST_SHA256,
        "warmup_count": WARMUP_COUNT,
        "warmup_indices": warmup_indices,
        "formal_count": FORMAL_COUNT,
        "formal_indices": observed_indices,
        "formal_prompt_records_sha256": _fingerprint(prompt_records),
        "cohorts_disjoint": True,
    }


def validate_p05_freeze() -> dict[str, Any]:
    """Prove the positive-budget configuration was frozen before P06."""

    _require(
        sha256_file(FROZEN_CONFIG) == FROZEN_CONFIG_SHA256,
        "P05 frozen HEDGE config bytes changed",
    )
    summary = json.loads(
        FROZEN_CALIBRATION_SUMMARY.read_text(encoding="utf-8")
    )
    config = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    _require(
        summary.get("status") == "PASS"
        and summary.get("config") == config
        and summary.get("config_fingerprint") == FROZEN_CONFIG_FINGERPRINT
        and summary.get("source_artifacts", {}).get("hedge_config_sha256")
        == FROZEN_CONFIG_SHA256,
        "P05 calibration summary does not bind the frozen config",
    )
    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            P05_FREEZE_COMMIT,
            "HEAD",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    ).returncode
    _require(ancestor == 0, "P05 freeze commit is not an ancestor of HEAD")
    return {
        "commit": P05_FREEZE_COMMIT,
        "hedge_config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
        "hedge_config_sha256": FROZEN_CONFIG_SHA256,
    }


def resolve_attempt(*, attempt_id: str, scratch: Path) -> dict[str, Any]:
    """Return one immutable native-only P06 formal contract."""

    _require(
        ATTEMPT_PATTERN.fullmatch(attempt_id) is not None,
        "attempt-id does not match the P06 native formal pattern",
    )
    scratch = scratch.resolve()
    _require(scratch.is_dir(), f"scratch directory does not exist: {scratch}")
    dataset = validate_formal_datasets()
    p05_freeze = validate_p05_freeze()
    environment = _base_environment(scratch)
    environment["HEDGE_ENABLED"] = "0"
    environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"] = "0"
    environment.pop("SGLANG_DSPARK_HEDGE_TRACE_CAPACITY", None)
    environment.pop("SGLANG_DSPARK_HEDGE_CONFIG_PATH", None)
    command = _server_command()
    decode_affecting = {
        "server_command": command,
        "hedge_enabled": False,
        "hedge_calibration_trace": False,
        "hedge_trace_capacity": None,
        "hedge_config": None,
        "ragged_verify_mode": environment["SGLANG_RAGGED_VERIFY_MODE"],
        "fp4_experts": environment["SGLANG_DSV4_FP4_EXPERTS"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P06",
        "worker_id": EXPECTED_WORKER,
        "hostname": socket.gethostname(),
        "arm": "native",
        "attempt_id": attempt_id,
        "scratch": str(scratch),
        "hdfs_run": str(RUN_ROOT / attempt_id),
        "dataset": dataset,
        "p05_freeze": p05_freeze,
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
            "mode": "disabled",
            "enabled": False,
            "calibration_trace": False,
            "config": None,
            "config_path": None,
        },
        "formal_protocol": {
            "clock": "time.monotonic_ns",
            "warmup_count": WARMUP_COUNT,
            "warmup_included": False,
            "formal_count": FORMAL_COUNT,
            "max_total_attempts_per_request": MAX_TOTAL_ATTEMPTS,
            "retry_time_included": True,
            "single_sequential_pass": True,
            "resume_or_append_allowed": False,
            "rerun_for_tps_allowed": False,
        },
        "decode_affecting": decode_affecting,
        "decode_config_fingerprint": _fingerprint(decode_affecting),
    }


def prepare_attempt(
    *, attempt_id: str, scratch: Path, inventory_payload: str
) -> dict[str, Any]:
    resolved = resolve_attempt(attempt_id=attempt_id, scratch=scratch)
    resolved["gpu_inventory"] = parse_gpu_inventory(inventory_payload)
    engine = build_engine_identity(
        decode_config_fingerprint=resolved["decode_config_fingerprint"]
    )
    checkpoint = build_checkpoint_identity()
    engine["authorized_phase"] = "P06"
    checkpoint["authorized_phase"] = "P06"
    _atomic_json(scratch / "resolved_config.json", resolved)
    _atomic_json(scratch / "engine_identity.json", engine)
    _atomic_json(scratch / "checkpoint_identity.json", checkpoint)
    for source, destination in (
        (DATASET_MANIFEST, scratch / "dataset_manifest.json"),
        (FROZEN_CONFIG, scratch / "p05_frozen_hedge_config.json"),
    ):
        with destination.open("xb") as output:
            with source.open("rb") as input_stream:
                shutil.copyfileobj(input_stream, output, 1024 * 1024)
    statuses = {
        "engine_identity": engine["status"],
        "checkpoint_identity": checkpoint["status"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P06",
        "status": (
            "PASS" if all(value == "PASS" for value in statuses.values()) else "FAIL"
        ),
        "arm": "native",
        "attempt_id": attempt_id,
        "identity_statuses": statuses,
    }


def _write_resolved(path: Path, value: Any) -> None:
    _atomic_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--attempt-id", required=True)
    resolve.add_argument("--scratch", type=Path, required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--worker-id", required=True)
    prepare.add_argument("--attempt-id", required=True)
    prepare.add_argument("--scratch", type=Path, required=True)

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
    worker = getattr(args, "worker_id", EXPECTED_WORKER)
    if worker != EXPECTED_WORKER:
        parser.error(f"only worker {EXPECTED_WORKER} is authorized")
    if args.command == "resolve":
        result = resolve_attempt(
            attempt_id=args.attempt_id, scratch=args.scratch
        )
        _write_resolved(args.scratch / "resolved_config.json", result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "prepare":
        inventory = _gpu_inventory_query()
        result = prepare_attempt(
            attempt_id=args.attempt_id,
            scratch=args.scratch,
            inventory_payload=inventory,
        )
        _atomic_json(
            args.scratch / "gpu_inventory.json",
            {
                "schema_version": 1,
                "authorized_phase": "P06",
                "status": "PASS",
                "worker_id": EXPECTED_WORKER,
                "gpus": parse_gpu_inventory(inventory),
            },
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "emit-command":
        resolved_value = json.loads(
            args.resolved.read_text(encoding="utf-8")
        )
        _emit_nul([str(item) for item in resolved_value["server"]["command"]])
        return 0
    if args.command == "emit-environment":
        resolved_value = json.loads(
            args.resolved.read_text(encoding="utf-8")
        )
        _emit_nul(
            [
                f"{key}={value}"
                for key, value in sorted(
                    resolved_value["server"]["environment"].items()
                )
            ]
        )
        return 0
    if args.command == "parse-keepalive":
        record = parse_keepalive_status(
            args.input.read_text(encoding="utf-8")
        )
        record["authorized_phase"] = "P06"
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
