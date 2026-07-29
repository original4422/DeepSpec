#!/usr/bin/env python3
"""Resolve the frozen runtime contract for one P05 calibration arm."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
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
    PROMPT_SUFFIX,
)
from deepspec.hedge_protocol.io import load_jsonl, sha256_file  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
    B0_CONFIG,
    B0_CONFIG_BYTES,
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


CALIBRATION = (
    REPO_ROOT
    / "artifacts/hedge-dspark/p01-protocol/gsm8k_calibration_32.jsonl"
)
DATASET_MANIFEST = (
    REPO_ROOT / "artifacts/hedge-dspark/p01-protocol/dataset_manifest.json"
)
CALIBRATION_SHA256 = (
    "28a7080565cde90b8cf1db79c88bb463861515fabe3fa7409481802104a6e47d"
)
DATASET_FINGERPRINT = "59ec1b7f9357c7a2"
TRACE_CAPACITY = 65536
ARMS = ("native-trace", "b0")
ATTEMPT_PATTERNS = {
    "native-trace": re.compile(
        r"^[0-9]{8}T[0-9]{6}Z-p05-native-calibration"
        r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
    ),
    "b0": re.compile(
        r"^[0-9]{8}T[0-9]{6}Z-p05-b0-calibration"
        r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
    ),
}


def validate_calibration_dataset() -> dict[str, Any]:
    """Validate immutable bytes, manifest identity, order, and prompt text."""

    if sha256_file(CALIBRATION) != CALIBRATION_SHA256:
        raise ValueError("calibration JSONL bytes differ from the frozen P01 artifact")
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest.get("artifacts", {}).get(
        "gsm8k_calibration_32.jsonl"
    )
    if artifact != {"row_count": 32, "sha256": CALIBRATION_SHA256}:
        raise ValueError("dataset manifest calibration identity mismatch")
    selection = manifest.get("selection")
    source = manifest.get("source")
    if not isinstance(selection, Mapping) or not isinstance(source, Mapping):
        raise ValueError("dataset manifest selection/source is missing")
    expected_indices = selection.get("calibration_indices")
    if (
        not isinstance(expected_indices, list)
        or len(expected_indices) != 32
        or len(set(expected_indices)) != 32
    ):
        raise ValueError("dataset manifest must contain 32 unique indices")
    if source.get("revision") != DATASET_REVISION:
        raise ValueError("dataset manifest revision is not the pinned revision")

    samples = load_jsonl(CALIBRATION)
    if len(samples) != 32:
        raise ValueError("calibration JSONL must contain exactly 32 rows")
    observed_indices: list[int] = []
    prompt_records: list[dict[str, Any]] = []
    for position, sample in enumerate(samples):
        question = sample.get("question")
        expected_user_content = (
            question + "\n" + PROMPT_SUFFIX
            if isinstance(question, str)
            else None
        )
        if (
            sample.get("cohort") != "calibration"
            or sample.get("cohort_position") != position
            or sample.get("dataset_revision") != DATASET_REVISION
            or sample.get("dataset_fingerprint") != DATASET_FINGERPRINT
            or not isinstance(question, str)
            or not question
            or sample.get("user_content") != expected_user_content
        ):
            raise ValueError(
                f"calibration row {position} identity/prompt is not frozen"
            )
        dataset_index = sample.get("dataset_index")
        if isinstance(dataset_index, bool) or not isinstance(dataset_index, int):
            raise ValueError(f"calibration row {position} index is invalid")
        observed_indices.append(dataset_index)
        prompt_records.append(
            {
                "cohort_position": position,
                "dataset_index": dataset_index,
                "user_content": expected_user_content,
            }
        )
    if observed_indices != expected_indices:
        raise ValueError("calibration JSONL index order differs from its manifest")
    return {
        "calibration_jsonl": str(CALIBRATION),
        "calibration_jsonl_sha256": CALIBRATION_SHA256,
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": sha256_file(DATASET_MANIFEST),
        "dataset_revision": DATASET_REVISION,
        "dataset_fingerprint": DATASET_FINGERPRINT,
        "sample_count": 32,
        "dataset_indices": observed_indices,
        "prompt_records_sha256": _fingerprint(prompt_records),
    }


def resolve_attempt(
    *, arm: str, attempt_id: str, scratch: Path
) -> dict[str, Any]:
    """Return and materialize one immutable P05 arm contract."""

    if arm not in ARMS:
        raise ValueError("arm must be exactly native-trace or b0")
    if ATTEMPT_PATTERNS[arm].fullmatch(attempt_id) is None:
        raise ValueError("attempt-id does not match the selected P05 arm")
    scratch = scratch.resolve()
    if not scratch.is_dir():
        raise ValueError(f"scratch directory does not exist: {scratch}")
    dataset = validate_calibration_dataset()
    config_path = scratch / "hedge_config.json"
    environment = _base_environment(scratch)
    if arm == "native-trace":
        environment["HEDGE_ENABLED"] = "0"
        environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"] = "1"
        environment["SGLANG_DSPARK_HEDGE_TRACE_CAPACITY"] = str(TRACE_CAPACITY)
        hedge_config = None
        hedge_mode = "calibration"
    else:
        environment["HEDGE_ENABLED"] = "1"
        environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"] = "0"
        environment.pop("SGLANG_DSPARK_HEDGE_TRACE_CAPACITY", None)
        with config_path.open("xb") as output:
            output.write(B0_CONFIG_BYTES)
        environment["SGLANG_DSPARK_HEDGE_CONFIG_PATH"] = str(config_path)
        hedge_config = dict(B0_CONFIG)
        hedge_mode = "enabled"

    command = _server_command()
    decode_affecting = {
        "server_command": command,
        "hedge_enabled": arm == "b0",
        "hedge_calibration_trace": arm == "native-trace",
        "hedge_trace_capacity": TRACE_CAPACITY if arm == "native-trace" else None,
        "hedge_config": hedge_config,
        "ragged_verify_mode": environment["SGLANG_RAGGED_VERIFY_MODE"],
        "fp4_experts": environment["SGLANG_DSV4_FP4_EXPERTS"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P05",
        "worker_id": EXPECTED_WORKER,
        "hostname": socket.gethostname(),
        "arm": arm,
        "attempt_id": attempt_id,
        "scratch": str(scratch),
        "hdfs_run": str(RUN_ROOT / attempt_id),
        "dataset": dataset,
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
            "mode": hedge_mode,
            "native_acceptance_preserved": arm == "native-trace",
            "config": hedge_config,
            "config_path": (
                None if arm == "native-trace" else str(config_path)
            ),
        },
        "decode_affecting": decode_affecting,
        "decode_config_fingerprint": _fingerprint(decode_affecting),
    }


def prepare_attempt(
    *, arm: str, attempt_id: str, scratch: Path, inventory_payload: str
) -> dict[str, Any]:
    resolved = resolve_attempt(
        arm=arm, attempt_id=attempt_id, scratch=scratch
    )
    resolved["gpu_inventory"] = parse_gpu_inventory(inventory_payload)
    engine = build_engine_identity(
        decode_config_fingerprint=resolved["decode_config_fingerprint"]
    )
    checkpoint = build_checkpoint_identity()
    engine["authorized_phase"] = "P05"
    checkpoint["authorized_phase"] = "P05"
    _atomic_json(scratch / "resolved_config.json", resolved)
    _atomic_json(scratch / "engine_identity.json", engine)
    _atomic_json(scratch / "checkpoint_identity.json", checkpoint)
    with (scratch / "dataset_manifest.json").open("xb") as output:
        with DATASET_MANIFEST.open("rb") as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
    statuses = {
        "engine_identity": engine["status"],
        "checkpoint_identity": checkpoint["status"],
    }
    return {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": (
            "PASS" if all(value == "PASS" for value in statuses.values()) else "FAIL"
        ),
        "arm": arm,
        "attempt_id": attempt_id,
        "identity_statuses": statuses,
    }


def _write_resolved(path: Path, value: Any) -> None:
    _atomic_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--arm", choices=ARMS, required=True)
    resolve.add_argument("--attempt-id", required=True)
    resolve.add_argument("--scratch", type=Path, required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--worker-id", required=True)
    prepare.add_argument("--arm", choices=ARMS, required=True)
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
            arm=args.arm,
            attempt_id=args.attempt_id,
            scratch=args.scratch,
        )
        _write_resolved(args.scratch / "resolved_config.json", result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "prepare":
        inventory = _gpu_inventory_query()
        result = prepare_attempt(
            arm=args.arm,
            attempt_id=args.attempt_id,
            scratch=args.scratch,
            inventory_payload=inventory,
        )
        _atomic_json(
            args.scratch / "gpu_inventory.json",
            {
                "schema_version": 1,
                "authorized_phase": "P05",
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
        record["authorized_phase"] = "P05"
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
