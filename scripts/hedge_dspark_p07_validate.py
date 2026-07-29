#!/usr/bin/env python3
"""Validate and archive one P07 positive-budget formal attempt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.io import load_jsonl, sha256_file  # noqa: E402
from deepspec.hedge_protocol.summary import recompute_summary  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
    EXPECTED_GPUS,
    EXPECTED_GPU_NAME,
)
from hedge_dspark_p04_validate import (  # noqa: E402
    _load_lifecycle_events,
    _validate_identity_artifacts,
    _validate_keepalive,
    _validate_server_log,
    validate_gpu_sampler_status,
)
from hedge_dspark_p06_validate import (  # noqa: E402
    REQUIRED_ARTIFACTS as P06_REQUIRED_ARTIFACTS,
    _atomic_json,
    _load_json,
    archive_formal_attempt,
    validate_formal_client_artifacts,
    validate_formal_gpu_window,
    validate_lifecycle_events,
)
from hedge_dspark_p07_client import validate_hedge_server_snapshot  # noqa: E402
from hedge_dspark_p07_prepare import (  # noqa: E402
    ATTEMPT_PATTERN,
    DATASET_MANIFEST,
    FROZEN_CONFIG_FINGERPRINT,
    FROZEN_CONFIG_SHA256,
    resolve_attempt,
    validate_runtime_identity_parity,
)


REQUIRED_ARTIFACTS = tuple(
    "hedge_config.json"
    if name == "p05_frozen_hedge_config.json"
    else name
    for name in P06_REQUIRED_ARTIFACTS
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_resolved_contract(
    resolved: Mapping[str, Any], *, attempt_id: str, scratch: Path
) -> dict[str, Any]:
    _require(
        ATTEMPT_PATTERN.fullmatch(attempt_id) is not None,
        "invalid P07 HEDGE formal attempt-id",
    )
    expected = resolve_attempt(attempt_id=attempt_id, scratch=scratch)
    allowed_fields = set(expected) | {
        "gpu_inventory",
        "p06_runtime_identity_parity",
    }
    _require(
        set(resolved) == allowed_fields,
        "resolved P07 contract fields mismatch",
    )
    for key, value in expected.items():
        _require(
            resolved.get(key) == value,
            f"resolved P07 contract mismatch: {key}",
        )
    runtime_parity = resolved.get("p06_runtime_identity_parity")
    _require(
        isinstance(runtime_parity, Mapping)
        and set(runtime_parity) == {"status", "checks"}
        and runtime_parity.get("status") == "PASS"
        and isinstance(runtime_parity.get("checks"), Mapping)
        and set(runtime_parity["checks"])
        == {
            "source",
            "wheel",
            "dspark_integration",
            "hedge_core",
            "checkpoint_identity",
        }
        and all(value is True for value in runtime_parity["checks"].values()),
        "P06 runtime source/wheel/model parity is absent",
    )
    config_path = Path(resolved["hedge"]["config_path"])
    _require(
        config_path == scratch / "hedge_config.json"
        and config_path.is_file()
        and sha256_file(config_path) == FROZEN_CONFIG_SHA256,
        "runtime HEDGE config path/bytes mismatch",
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
        and all(isinstance(value, str) and value.startswith("GPU-") for value in uuids),
        "GPU UUID inventory is invalid",
    )
    _require(
        resolved["hedge"]["config_fingerprint"]
        == FROZEN_CONFIG_FINGERPRINT,
        "P07 config fingerprint mismatch",
    )
    return {
        "status": "PASS",
        "decode_config_fingerprint": resolved["decode_config_fingerprint"],
        "gpu_uuids": uuids,
        "p06_identity_parity": resolved["p06_identity_parity"],
        "p06_runtime_identity_parity": resolved[
            "p06_runtime_identity_parity"
        ],
    }


def validate_live(*, scratch: Path, attempt_id: str) -> dict[str, Any]:
    resolved = _load_json(scratch / "resolved_config.json")
    audit = validate_resolved_contract(
        resolved, attempt_id=attempt_id, scratch=scratch
    )
    _require(
        sha256_file(scratch / "dataset_manifest.json")
        == sha256_file(DATASET_MANIFEST),
        "copied dataset manifest hash mismatch",
    )
    _require(
        sha256_file(scratch / "hedge_config.json") == FROZEN_CONFIG_SHA256,
        "runtime HEDGE config bytes changed",
    )
    engine = _load_json(scratch / "engine_identity.json")
    checkpoint = _load_json(scratch / "checkpoint_identity.json")
    identity = _validate_identity_artifacts(
        engine=engine,
        checkpoint=checkpoint,
        decode_config_fingerprint=audit["decode_config_fingerprint"],
    )
    _require(
        validate_runtime_identity_parity(
            engine=engine,
            checkpoint=checkpoint,
        )
        == resolved["p06_runtime_identity_parity"],
        "P06 runtime identity parity does not independently replay",
    )
    _require(
        _load_json(scratch / "startup.json").get("status") == "ready",
        "server startup is not ready",
    )
    dataset = resolved["dataset"]
    client = validate_client_artifacts(
        scratch=scratch,
        expected_warmup_indices=dataset["warmup_indices"],
        expected_formal_indices=dataset["formal_indices"],
    )
    gpu = validate_formal_gpu_window(
        scratch / "gpu_samples.csv",
        expected_uuids=audit["gpu_uuids"],
        formal_start=client["formal_start_monotonic_ns"],
        formal_end=client["formal_end_monotonic_ns"],
    )
    return {
        "schema_version": 1,
        "authorized_phase": "P07",
        "status": "PASS",
        "arm": "hedge",
        "attempt_id": attempt_id,
        "resolved_config": audit,
        "identities": identity,
        "client": client,
        "gpu_evidence": gpu,
        "server_log": _validate_server_log(scratch / "server.log"),
    }


def validate_client_artifacts(
    *,
    scratch: Path,
    expected_warmup_indices: list[int],
    expected_formal_indices: list[int],
) -> dict[str, Any]:
    """Recompute P07 outputs through the shared accepted formal seam."""

    result = validate_formal_client_artifacts(
        scratch=scratch,
        expected_warmup_indices=expected_warmup_indices,
        expected_formal_indices=expected_formal_indices,
        authorized_phase="P07",
        arm="hedge",
        snapshot_validator=lambda payload, summary: (
            validate_hedge_server_snapshot(
                payload,
                require_exact_zero=False,
                formal_summary=summary,
            )
        ),
    )
    formal_summary = recompute_summary(
        load_jsonl(scratch / "formal_outputs.jsonl"),
        expected_count=500,
        expected_cohort="formal",
    )
    stored = _load_json(scratch / "hedge_counters.json")
    reconstructed = {
        **stored.get("server_config", {}),
        "internal_states": [
            {"dspark_info_record": {"hedge": snapshot}}
            for snapshot in stored.get("hedge_snapshots", [])
        ],
    }
    replayed = validate_hedge_server_snapshot(
        reconstructed,
        require_exact_zero=False,
        formal_summary=formal_summary,
    )
    _require(
        set(stored)
        == set(replayed)
        | {
            "fetched_at_utc",
            "formal_request_interval_monotonic_ns",
        }
        and isinstance(stored.get("fetched_at_utc"), str)
        and bool(stored["fetched_at_utc"]),
        "P07 HEDGE counter artifact fields mismatch",
    )
    mismatches = {
        key: {"stored": stored.get(key), "replayed": value}
        for key, value in replayed.items()
        if stored.get(key) != value
    }
    _require(
        not mismatches,
        f"P07 HEDGE counter replay mismatch: {mismatches}",
    )
    result["hedge_counters"] = {
        "status": "PASS",
        "runtime_calls": replayed["runtime_calls"],
        "requests_initialized": replayed["requests_initialized"],
        "requests_finished": replayed["requests_finished"],
        "active_request_states": replayed["active_request_states"],
        "state_leaks": replayed["state_leaks"],
        "relaxed_mismatches": replayed["relaxed_mismatches"],
        "regret_charged": replayed["regret_charged"],
        "remaining_budget_total": replayed["remaining_budget_total"],
        "cap_trim_lens": replayed["cap_trim_lens"],
        "budget_exhaustion_events": replayed[
            "budget_exhaustion_events"
        ],
        "sha256": sha256_file(scratch / "hedge_counters.json"),
    }
    return result


def record_shutdown(
    *,
    scratch: Path,
    attempt_id: str,
    original_returncode: int,
    cleanup_returncode: int,
    contexts_proven: bool,
    keepalive_ready: bool,
    signal_name: str,
) -> dict[str, Any]:
    process_results = {
        role: (
            _load_json(scratch / f"{role}_shutdown.json")
            if (scratch / f"{role}_shutdown.json").is_file()
            else {"status": "NOT_STARTED_OR_UNPROVEN"}
        )
        for role in ("server", "sampler")
    }
    checks = {
        "main_returncode_zero": original_returncode == 0,
        "cleanup_returncode_zero": cleanup_returncode == 0,
        "contexts_proven": contexts_proven,
        "keepalive_ready": keepalive_ready,
        "registered_process_groups_stopped": all(
            value.get("status") in {"terminated", "already_exited"}
            for value in process_results.values()
        ),
        "no_external_signal": signal_name == "",
    }
    result = {
        "schema_version": 1,
        "authorized_phase": "P07",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "arm": "hedge",
        "attempt_id": attempt_id,
        "original_returncode": original_returncode,
        "cleanup_returncode": cleanup_returncode,
        "signal_name": signal_name or None,
        "checks": checks,
        "process_results": process_results,
    }
    _atomic_json(scratch / "shutdown.json", result, exclusive=True)
    return result


def validate_shutdown_artifact(
    *, scratch: Path, attempt_id: str
) -> dict[str, Any]:
    shutdown = _load_json(scratch / "shutdown.json")
    _require(
        shutdown.get("status") == "PASS"
        and shutdown.get("authorized_phase") == "P07"
        and shutdown.get("arm") == "hedge"
        and shutdown.get("attempt_id") == attempt_id
        and isinstance(shutdown.get("checks"), Mapping)
        and bool(shutdown["checks"])
        and all(value is True for value in shutdown["checks"].values()),
        "shutdown is not exact P07 PASS",
    )
    return {"status": "PASS"}


def _materialize_missing(scratch: Path, reason: str) -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        path = scratch / name
        if path.exists():
            continue
        missing.append(name)
        if name.endswith(".json"):
            _atomic_json(
                path,
                {
                    "schema_version": 1,
                    "authorized_phase": "P07",
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
                        "authorized_phase": "P07",
                        "status": "MISSING",
                        "artifact": name,
                        "reason": reason,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        elif name == "gpu_samples.csv":
            path.write_text(f"status,reason\nMISSING,{reason}\n", encoding="utf-8")
        else:
            path.write_text(f"MISSING: {reason}\n", encoding="utf-8")
    return missing


def finalize_attempt(*, scratch: Path, attempt_id: str) -> dict[str, Any]:
    missing = _materialize_missing(
        scratch, "P07 lifecycle ended before this artifact was produced"
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
        lambda: validate_live(scratch=scratch, attempt_id=attempt_id),
    )
    capture(
        "gpu_sampler_status",
        lambda: validate_gpu_sampler_status(
            scratch / "gpu_sampler_status.json",
            scratch / "gpu_samples.csv",
        ),
    )
    capture(
        "shutdown",
        lambda: validate_shutdown_artifact(
            scratch=scratch,
            attempt_id=attempt_id,
        ),
    )
    capture(
        "contexts",
        lambda: (
            _require(
                "contexts=none"
                in (scratch / "cuda_contexts_after.txt").read_text(encoding="utf-8"),
                "post-shutdown CUDA contexts are not none",
            )
            or {"status": "PASS"}
        ),
    )
    for name in ("keepalive_before", "keepalive_after"):
        capture(
            name,
            lambda name=name: (
                _validate_keepalive(_load_json(scratch / f"{name}.json"), name)
                or {"status": "PASS"}
            ),
        )
    capture(
        "lifecycle",
        lambda: validate_lifecycle_events(
            _load_lifecycle_events(scratch / "lifecycle_events.jsonl"),
            require_archive=False,
        ),
    )
    if missing:
        errors.append("required artifacts missing: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "authorized_phase": "P07",
        "status": "PASS" if not errors else "FAIL",
        "arm": "hedge",
        "attempt_id": attempt_id,
        "required_artifacts": list(REQUIRED_ARTIFACTS),
        "missing_artifacts_materialized": missing,
        "checks": checks,
        "errors": errors,
    }


def archive_attempt(*, scratch: Path, hdfs_run: Path) -> dict[str, Any]:
    """Archive with P07/HEDGE identity and the P07 runtime config artifact."""

    return archive_formal_attempt(
        scratch=scratch,
        hdfs_run=hdfs_run,
        authorized_phase="P07",
        arm="hedge",
        required_artifacts=REQUIRED_ARTIFACTS,
    )


def _bool(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise argparse.ArgumentTypeError("boolean must be 0 or 1")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("live", "final"):
        command = commands.add_parser(name)
        command.add_argument("--scratch", type=Path, required=True)
        command.add_argument("--attempt-id", required=True)
    shutdown = commands.add_parser("record-shutdown")
    shutdown.add_argument("--scratch", type=Path, required=True)
    shutdown.add_argument("--attempt-id", required=True)
    shutdown.add_argument("--original-returncode", type=int, required=True)
    shutdown.add_argument("--cleanup-returncode", type=int, required=True)
    shutdown.add_argument("--contexts-proven", type=_bool, required=True)
    shutdown.add_argument("--keepalive-ready", type=_bool, required=True)
    shutdown.add_argument("--signal-name", default="")
    archive = commands.add_parser("archive")
    archive.add_argument("--scratch", type=Path, required=True)
    archive.add_argument("--hdfs-run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "live":
        output = args.scratch / "live_validation.json"
        try:
            result = validate_live(scratch=args.scratch, attempt_id=args.attempt_id)
        except BaseException as error:
            _atomic_json(
                output,
                {
                    "schema_version": 1,
                    "authorized_phase": "P07",
                    "status": "FAIL",
                    "arm": "hedge",
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
            attempt_id=args.attempt_id,
            original_returncode=args.original_returncode,
            cleanup_returncode=args.cleanup_returncode,
            contexts_proven=args.contexts_proven,
            keepalive_ready=args.keepalive_ready,
            signal_name=args.signal_name,
        )
        return 0 if result["status"] == "PASS" else 1
    if args.command == "final":
        result = finalize_attempt(scratch=args.scratch, attempt_id=args.attempt_id)
        _atomic_json(
            args.scratch / "artifact_validation.json",
            result,
            exclusive=True,
        )
        return 0 if result["status"] == "PASS" else 1
    result = archive_attempt(
        scratch=args.scratch,
        hdfs_run=args.hdfs_run,
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
