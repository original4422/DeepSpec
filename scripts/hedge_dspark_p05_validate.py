#!/usr/bin/env python3
"""Validate, finalize, and immutably archive one P05 calibration attempt."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.io import load_jsonl, sha256_file  # noqa: E402
from deepspec.hedge_protocol.summary import recompute_summary  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
    B0_CONFIG_BYTES,
    EXPECTED_GPUS,
    EXPECTED_GPU_NAME,
    EXPECTED_WORKER,
    FIXED_PORT,
    RUN_ROOT,
    _fingerprint,
)
from hedge_dspark_p04_validate import (  # noqa: E402
    SERVER_ARG_VALUES,
    SERVER_SWITCHES,
    _load_lifecycle_events,
    _validate_gpu_samples,
    _validate_identity_artifacts,
    _validate_keepalive,
    _validate_server_log,
)
from hedge_dspark_p05_client import (  # noqa: E402
    SERVER_FIELDS,
    validate_server_snapshot,
)
from hedge_dspark_p05_prepare import (  # noqa: E402
    ARMS,
    ATTEMPT_PATTERNS,
    CALIBRATION_SHA256,
    TRACE_CAPACITY,
    validate_calibration_dataset,
)
from hedge_dspark_p05_reduce import _validate_outputs  # noqa: E402


COMMON_REQUIRED = (
    "resolved_config.json",
    "engine_identity.json",
    "checkpoint_identity.json",
    "dataset_manifest.json",
    "server.log",
    "gpu_samples.csv",
    "calibration_request_summary.json",
    "hedge_counters.json",
    "strict_rejection_trace.jsonl",
    "shutdown.json",
    "cuda_contexts_after.txt",
    "keepalive_before.json",
    "keepalive_after.json",
)
EXPECTED_CLEANUP_ORDER = (
    "terminate_registered_server",
    "prove_cuda_contexts_none",
    "terminate_registered_sampler",
    "resume_keepalive_if_cleanup_proven",
    "validate_keepalive_8x10_mean_ge_40",
    "validate_required_artifacts",
    "archive_without_overwrite",
)


def output_name(arm: str) -> str:
    if arm == "native-trace":
        return "native_calibration_outputs.jsonl"
    if arm == "b0":
        return "b0_calibration_outputs.jsonl"
    raise ValueError("arm must be exactly native-trace or b0")


def required_artifacts(arm: str) -> tuple[str, ...]:
    return (*COMMON_REQUIRED, output_name(arm))


def _atomic_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as output:
            output.write(
                (
                    json.dumps(
                        value,
                        allow_nan=False,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            )
            output.flush()
            os.fsync(output.fileno())
        if exclusive and path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_resolved(
    resolved: Mapping[str, Any],
    *,
    arm: str,
    attempt_id: str,
    scratch: Path,
) -> dict[str, Any]:
    _require(arm in ARMS, "invalid P05 arm")
    _require(
        ATTEMPT_PATTERNS[arm].fullmatch(attempt_id) is not None,
        "attempt-id does not encode the selected P05 arm",
    )
    _require(resolved.get("authorized_phase") == "P05", "wrong phase")
    _require(resolved.get("worker_id") == EXPECTED_WORKER, "wrong worker")
    _require(resolved.get("arm") == arm, "resolved arm mismatch")
    _require(resolved.get("attempt_id") == attempt_id, "attempt-id mismatch")
    _require(
        resolved.get("scratch") == str(scratch.resolve()),
        "scratch identity mismatch",
    )
    _require(
        resolved.get("hdfs_run") == str(RUN_ROOT / attempt_id),
        "HDFS run identity mismatch",
    )
    dataset = resolved.get("dataset")
    expected_dataset = validate_calibration_dataset()
    _require(dataset == expected_dataset, "resolved frozen dataset identity mismatch")

    api = resolved.get("api")
    _require(
        isinstance(api, Mapping)
        and api.get("base_url") == f"http://127.0.0.1:{FIXED_PORT}"
        and api.get("port") == FIXED_PORT,
        "resolved fixed API endpoint mismatch",
    )
    server = resolved.get("server")
    _require(isinstance(server, Mapping), "resolved server is missing")
    command = server.get("command")
    _require(
        isinstance(command, list)
        and command[:3]
        == [
            "/home/tiger/venvs/hedge-v4-dspark/bin/python",
            "-m",
            "sglang.launch_server",
        ],
        "resolved server launcher mismatch",
    )
    for flag, expected in SERVER_ARG_VALUES.items():
        _require(
            command.count(flag) == 1
            and command[command.index(flag) + 1] == expected,
            f"resolved server argument mismatch for {flag}",
        )
    for switch in SERVER_SWITCHES:
        _require(command.count(switch) == 1, f"missing server switch {switch}")
    environment = server.get("environment")
    _require(isinstance(environment, Mapping), "resolved environment is missing")
    fixed_environment = {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }
    for key, expected in fixed_environment.items():
        _require(environment.get(key) == expected, f"environment mismatch: {key}")
    config_path = scratch / "hedge_config.json"
    if arm == "native-trace":
        _require(
            environment.get("HEDGE_ENABLED") == "0"
            and environment.get("SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE") == "1"
            and environment.get("SGLANG_DSPARK_HEDGE_TRACE_CAPACITY")
            == str(TRACE_CAPACITY)
            and "SGLANG_DSPARK_HEDGE_CONFIG_PATH" not in environment
            and not config_path.exists(),
            "native trace switches/config are not exact",
        )
    else:
        _require(
            environment.get("HEDGE_ENABLED") == "1"
            and environment.get("SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE") == "0"
            and "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY" not in environment
            and environment.get("SGLANG_DSPARK_HEDGE_CONFIG_PATH")
            == str(config_path.resolve())
            and config_path.read_bytes() == B0_CONFIG_BYTES,
            "B0 switches/config bytes are not exact",
        )
    decode = resolved.get("decode_affecting")
    fingerprint = resolved.get("decode_config_fingerprint")
    _require(
        isinstance(decode, Mapping)
        and isinstance(fingerprint, str)
        and fingerprint == _fingerprint(decode),
        "decode config fingerprint mismatch",
    )
    inventory = resolved.get("gpu_inventory")
    _require(
        isinstance(inventory, list)
        and len(inventory) == EXPECTED_GPUS
        and [item.get("index") for item in inventory]
        == list(range(EXPECTED_GPUS))
        and all(item.get("name") == EXPECTED_GPU_NAME for item in inventory),
        "GPU inventory is not exact 8xH20",
    )
    uuids = [item.get("uuid") for item in inventory]
    _require(
        len(set(uuids)) == EXPECTED_GPUS
        and all(isinstance(item, str) and item.startswith("GPU-") for item in uuids),
        "GPU UUID inventory is invalid",
    )
    return {
        "status": "PASS",
        "decode_config_fingerprint": fingerprint,
        "gpu_uuids": uuids,
        "calibration_sha256": CALIBRATION_SHA256,
    }


def _validate_client(
    scratch: Path,
    *,
    arm: str,
    expected_indices: Sequence[int],
) -> dict[str, Any]:
    outputs_path = scratch / output_name(arm)
    records = _validate_outputs(
        outputs_path, expected_indices=expected_indices, arm=arm
    )
    summary = _load_json(scratch / "calibration_request_summary.json")
    recomputed = recompute_summary(
        records, expected_count=32, expected_cohort="calibration"
    )
    expected_summary = {
        "status": "PASS",
        "arm": arm,
        "sample_count": 32,
        "terminal_counts": {"succeeded": 32, "failed": 0},
        "attempts_total": recomputed["attempts_total"],
        "retry_attempts": recomputed["retry_attempts"],
        "completion_tokens": recomputed["completion_tokens"],
        "dataset_indices": list(expected_indices),
        "outputs_sha256": sha256_file(outputs_path),
    }
    for key, expected in expected_summary.items():
        _require(summary.get(key) == expected, f"client summary mismatch: {key}")

    counters = _load_json(scratch / "hedge_counters.json")
    snapshots = counters.get("hedge_snapshots")
    server_config = counters.get("server_config")
    _require(
        isinstance(snapshots, list) and isinstance(server_config, Mapping),
        "sealed server counters are incomplete",
    )
    reconstructed = {
        **dict(server_config),
        "internal_states": [
            {"dspark_info_record": {"hedge": snapshot}}
            for snapshot in snapshots
        ],
    }
    validated_counters, validated_trace = validate_server_snapshot(
        reconstructed, arm=arm
    )
    trace = load_jsonl(scratch / "strict_rejection_trace.jsonl")
    _require(trace == validated_trace, "sealed strict trace does not replay")
    for key in (
        "proposal_count",
        "trace_capacity",
        "trace_rows_seen",
        "trace_rows_stored",
        "trace_rows_dropped",
        "native_acceptance_preserved",
    ):
        _require(
            counters.get(key) == validated_counters.get(key),
            f"sealed HEDGE counter mismatch: {key}",
        )
    _require(
        summary.get("trace_sha256")
        == sha256_file(scratch / "strict_rejection_trace.jsonl"),
        "client summary trace hash mismatch",
    )
    starts = [record.get("request_started_monotonic_ns") for record in records]
    ends = [record.get("terminal_monotonic_ns") for record in records]
    _require(
        all(isinstance(item, int) and not isinstance(item, bool) for item in starts + ends)
        and all(start <= end for start, end in zip(starts, ends))
        and all(
            earlier_end <= later_start
            for earlier_end, later_start in zip(ends, starts[1:])
        ),
        "calibration request intervals are not sequential monotonic intervals",
    )
    return {
        "status": "PASS",
        "request_count": 32,
        "success_requests": 32,
        "failed_requests": 0,
        "retry_attempts": recomputed["retry_attempts"],
        "completion_tokens": recomputed["completion_tokens"],
        "request_start_monotonic_ns": starts[0],
        "request_end_monotonic_ns": ends[-1],
        "outputs_sha256": sha256_file(outputs_path),
        "trace_sha256": sha256_file(
            scratch / "strict_rejection_trace.jsonl"
        ),
    }


def validate_live(
    *, scratch: Path, arm: str, attempt_id: str
) -> dict[str, Any]:
    resolved = _load_json(scratch / "resolved_config.json")
    engine = _load_json(scratch / "engine_identity.json")
    checkpoint = _load_json(scratch / "checkpoint_identity.json")
    resolved_audit = _validate_resolved(
        resolved, arm=arm, attempt_id=attempt_id, scratch=scratch
    )
    identity_audit = _validate_identity_artifacts(
        engine=engine,
        checkpoint=checkpoint,
        decode_config_fingerprint=resolved_audit[
            "decode_config_fingerprint"
        ],
    )
    expected_indices = resolved["dataset"]["dataset_indices"]
    client = _validate_client(
        scratch, arm=arm, expected_indices=expected_indices
    )
    gpu = _validate_gpu_samples(
        scratch / "gpu_samples.csv",
        expected_uuids=resolved_audit["gpu_uuids"],
        request_start=client["request_start_monotonic_ns"],
        request_end=client["request_end_monotonic_ns"],
    )
    server_log = _validate_server_log(scratch / "server.log")
    return {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "arm": arm,
        "attempt_id": attempt_id,
        "resolved_config": resolved_audit,
        "identities": identity_audit,
        "client": client,
        "gpu_evidence": gpu,
        "server_log": server_log,
    }


def record_shutdown(
    *,
    scratch: Path,
    arm: str,
    attempt_id: str,
    original_returncode: int,
    cleanup_returncode: int,
    contexts_proven: bool,
    keepalive_ready: bool,
    signal_name: str,
) -> dict[str, Any]:
    process_results: dict[str, Any] = {}
    for role in ("server", "sampler"):
        path = scratch / f"{role}_shutdown.json"
        process_results[role] = (
            _load_json(path)
            if path.is_file()
            else {"status": "NOT_STARTED_OR_UNPROVEN"}
        )
    groups_stopped = all(
        value.get("status") in {"terminated", "already_exited"}
        for value in process_results.values()
    )
    checks = {
        "main_returncode_zero": original_returncode == 0,
        "cleanup_returncode_zero": cleanup_returncode == 0,
        "contexts_proven": contexts_proven,
        "keepalive_ready": keepalive_ready,
        "registered_process_groups_stopped": groups_stopped,
        "no_external_signal": signal_name == "",
    }
    result = {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "arm": arm,
        "attempt_id": attempt_id,
        "original_returncode": original_returncode,
        "cleanup_returncode": cleanup_returncode,
        "signal_name": signal_name or None,
        "checks": checks,
        "process_results": process_results,
    }
    _atomic_json(scratch / "shutdown.json", result, exclusive=True)
    return result


def _validate_lifecycle(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        event.get("stage")
        for event in events
        if event.get("stage") in EXPECTED_CLEANUP_ORDER
    ]
    _require(
        observed == list(EXPECTED_CLEANUP_ORDER[:-1]),
        "cleanup lifecycle order/membership mismatch before archive",
    )
    return {"status": "PASS", "cleanup_order": observed}


def ensure_required_artifacts(
    *, scratch: Path, arm: str, reason: str
) -> list[str]:
    missing: list[str] = []
    for name in required_artifacts(arm):
        path = scratch / name
        if path.exists():
            continue
        missing.append(name)
        if name.endswith(".json"):
            _atomic_json(
                path,
                {
                    "schema_version": 1,
                    "authorized_phase": "P05",
                    "status": "MISSING",
                    "artifact": name,
                    "reason": reason,
                },
                exclusive=True,
            )
        elif name.endswith(".jsonl"):
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "authorized_phase": "P05",
                        "status": "MISSING",
                        "artifact": name,
                        "reason": reason,
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
        elif name == "gpu_samples.csv":
            path.write_text("status,reason\nMISSING," + reason + "\n", encoding="utf-8")
        else:
            path.write_text(f"MISSING: {reason}\n", encoding="utf-8")
    return missing


def finalize_attempt(
    *, scratch: Path, arm: str, attempt_id: str
) -> dict[str, Any]:
    missing = ensure_required_artifacts(
        scratch=scratch,
        arm=arm,
        reason="P05 lifecycle ended before this artifact was produced",
    )
    checks: dict[str, Any] = {}
    errors: list[str] = []

    def capture(name: str, operation: Any) -> None:
        try:
            checks[name] = operation()
        except BaseException as error:
            checks[name] = {
                "status": "FAIL",
                "error_type": type(error).__name__,
                "error": str(error),
            }
            errors.append(f"{name}: {type(error).__name__}: {error}")

    capture(
        "live_evidence",
        lambda: validate_live(
            scratch=scratch, arm=arm, attempt_id=attempt_id
        ),
    )

    def validate_shutdown() -> dict[str, Any]:
        shutdown = _load_json(scratch / "shutdown.json")
        _require(
            shutdown.get("status") == "PASS"
            and shutdown.get("arm") == arm
            and shutdown.get("attempt_id") == attempt_id
            and all(
                value is True
                for value in shutdown.get("checks", {}).values()
            ),
            "shutdown is not an exact PASS",
        )
        return {"status": "PASS"}

    capture("shutdown", validate_shutdown)
    capture(
        "contexts",
        lambda: (
            _require(
                "contexts=none"
                in (scratch / "cuda_contexts_after.txt").read_text(
                    encoding="utf-8"
                ),
                "post-shutdown CUDA contexts are not none",
            )
            or {"status": "PASS"}
        ),
    )
    capture(
        "keepalive_before",
        lambda: (
            _validate_keepalive(
                _load_json(scratch / "keepalive_before.json"),
                "keepalive_before",
            )
            or {"status": "PASS"}
        ),
    )
    capture(
        "keepalive_after",
        lambda: (
            _validate_keepalive(
                _load_json(scratch / "keepalive_after.json"),
                "keepalive_after",
            )
            or {"status": "PASS"}
        ),
    )
    capture(
        "lifecycle",
        lambda: _validate_lifecycle(
            _load_lifecycle_events(scratch / "lifecycle_events.jsonl")
        ),
    )
    if missing:
        errors.append("required artifacts were missing: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS" if not errors else "FAIL",
        "arm": arm,
        "attempt_id": attempt_id,
        "required_artifacts": list(required_artifacts(arm)),
        "missing_artifacts_materialized": missing,
        "checks": checks,
        "errors": errors,
    }


def _copy_exclusive(source: Path, destination: Path) -> None:
    with source.open("rb") as input_stream, destination.open("xb") as output:
        shutil.copyfileobj(input_stream, output, 1024 * 1024)


def archive_attempt(*, scratch: Path, hdfs_run: Path, arm: str) -> dict[str, Any]:
    _require(scratch.is_dir(), "scratch directory is absent")
    _require(hdfs_run.is_dir(), "HDFS run directory is absent")
    _require(not list(hdfs_run.iterdir()), "HDFS run directory is not empty")
    names = {path.name for path in scratch.iterdir() if path.is_file()}
    _require(
        set(required_artifacts(arm)).issubset(names),
        "scratch is missing required artifacts",
    )
    events = _load_lifecycle_events(scratch / "lifecycle_events.jsonl")
    observed = [
        event.get("stage")
        for event in events
        if event.get("stage") in EXPECTED_CLEANUP_ORDER
    ]
    _require(
        observed == list(EXPECTED_CLEANUP_ORDER),
        "archive lifecycle event is missing/out of order",
    )
    manifest_path = scratch / "archive_manifest.json"
    _require(not manifest_path.exists(), "archive manifest already exists")
    sources = sorted(
        (
            path
            for path in scratch.iterdir()
            if path.is_file() and path.name != manifest_path.name
        ),
        key=lambda path: path.name,
    )
    records = [
        {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sources
    ]
    manifest = {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "arm": arm,
        "source": str(scratch),
        "destination": str(hdfs_run),
        "files": records,
    }
    _atomic_json(manifest_path, manifest, exclusive=True)
    for record in records:
        _copy_exclusive(
            scratch / record["path"], hdfs_run / record["path"]
        )
    _copy_exclusive(manifest_path, hdfs_run / manifest_path.name)
    for record in records:
        destination = hdfs_run / record["path"]
        _require(
            destination.stat().st_size == record["bytes"]
            and sha256_file(destination) == record["sha256"],
            f"archived file hash mismatch: {record['path']}",
        )
    _require(
        sha256_file(hdfs_run / manifest_path.name) == sha256_file(manifest_path),
        "archived manifest hash mismatch",
    )
    return {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "file_count": len(records),
        "manifest": str(hdfs_run / manifest_path.name),
    }


def _bool(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise argparse.ArgumentTypeError("boolean must be 0 or 1")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    live = subparsers.add_parser("live")
    live.add_argument("--scratch", type=Path, required=True)
    live.add_argument("--arm", choices=ARMS, required=True)
    live.add_argument("--attempt-id", required=True)

    shutdown = subparsers.add_parser("record-shutdown")
    shutdown.add_argument("--scratch", type=Path, required=True)
    shutdown.add_argument("--arm", choices=ARMS, required=True)
    shutdown.add_argument("--attempt-id", required=True)
    shutdown.add_argument("--original-returncode", type=int, required=True)
    shutdown.add_argument("--cleanup-returncode", type=int, required=True)
    shutdown.add_argument("--contexts-proven", type=_bool, required=True)
    shutdown.add_argument("--keepalive-ready", type=_bool, required=True)
    shutdown.add_argument("--signal-name", default="")

    final = subparsers.add_parser("final")
    final.add_argument("--scratch", type=Path, required=True)
    final.add_argument("--arm", choices=ARMS, required=True)
    final.add_argument("--attempt-id", required=True)

    archive = subparsers.add_parser("archive")
    archive.add_argument("--scratch", type=Path, required=True)
    archive.add_argument("--hdfs-run", type=Path, required=True)
    archive.add_argument("--arm", choices=ARMS, required=True)

    args = parser.parse_args()
    if args.command == "live":
        output = args.scratch / "live_validation.json"
        try:
            result = validate_live(
                scratch=args.scratch,
                arm=args.arm,
                attempt_id=args.attempt_id,
            )
        except BaseException as error:
            _atomic_json(
                output,
                {
                    "schema_version": 1,
                    "authorized_phase": "P05",
                    "status": "FAIL",
                    "arm": args.arm,
                    "attempt_id": args.attempt_id,
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                exclusive=True,
            )
            raise
        _atomic_json(output, result, exclusive=True)
        return 0
    if args.command == "record-shutdown":
        result = record_shutdown(
            scratch=args.scratch,
            arm=args.arm,
            attempt_id=args.attempt_id,
            original_returncode=args.original_returncode,
            cleanup_returncode=args.cleanup_returncode,
            contexts_proven=args.contexts_proven,
            keepalive_ready=args.keepalive_ready,
            signal_name=args.signal_name,
        )
        return 0 if result["status"] == "PASS" else 1
    if args.command == "final":
        result = finalize_attempt(
            scratch=args.scratch, arm=args.arm, attempt_id=args.attempt_id
        )
        _atomic_json(
            args.scratch / "artifact_validation.json",
            result,
            exclusive=True,
        )
        return 0 if result["status"] == "PASS" else 1
    if args.command == "archive":
        result = archive_attempt(
            scratch=args.scratch, hdfs_run=args.hdfs_run, arm=args.arm
        )
        return 0 if result["status"] == "PASS" else 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
