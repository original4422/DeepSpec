#!/usr/bin/env python3
"""Validate, finalize, and immutably archive one P06 native formal attempt."""

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

from deepspec.hedge_protocol.config import fingerprint_document  # noqa: E402
from deepspec.hedge_protocol.io import (  # noqa: E402
    load_jsonl,
    sha256_file,
)
from deepspec.hedge_protocol.summary import recompute_summary  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
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
    validate_gpu_sampler_status,
)
from hedge_dspark_p06_client import (  # noqa: E402
    aggregate_spec_acceptance,
    normalize_spec_acceptance,
    validate_native_server_snapshot,
)
from hedge_dspark_p06_prepare import (  # noqa: E402
    ATTEMPT_PATTERN,
    DATASET_MANIFEST_SHA256,
    FROZEN_CONFIG_FINGERPRINT,
    FROZEN_CONFIG_SHA256,
    FORMAL_SHA256,
    P05_FREEZE_COMMIT,
    validate_formal_datasets,
    validate_p05_freeze,
)


REQUIRED_ARTIFACTS = (
    "resolved_config.json",
    "engine_identity.json",
    "checkpoint_identity.json",
    "dataset_manifest.json",
    "p05_frozen_hedge_config.json",
    "startup.json",
    "server.log",
    "gpu_samples.csv",
    "gpu_sampler_status.json",
    "warmup_outputs.jsonl",
    "formal_outputs.jsonl",
    "pre_formal_clear.json",
    "formal_timing.json",
    "hedge_counters.json",
    "acceptance_summary.json",
    "answer_summary.json",
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _atomic_json(
    path: Path, value: Any, *, exclusive: bool = False
) -> None:
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


def validate_resolved_contract(
    resolved: Mapping[str, Any],
    *,
    attempt_id: str,
    scratch: Path,
) -> dict[str, Any]:
    """Validate fixed native identity, HEDGE-off state, and exact 8xH20."""

    _require(
        ATTEMPT_PATTERN.fullmatch(attempt_id) is not None,
        "invalid P06 native formal attempt-id",
    )
    _require(resolved.get("authorized_phase") == "P06", "wrong phase")
    _require(resolved.get("worker_id") == EXPECTED_WORKER, "wrong worker")
    _require(resolved.get("arm") == "native", "wrong P06 arm")
    _require(resolved.get("attempt_id") == attempt_id, "attempt-id mismatch")
    _require(
        resolved.get("scratch") == str(scratch.resolve()),
        "scratch identity mismatch",
    )
    _require(
        resolved.get("hdfs_run") == str(RUN_ROOT / attempt_id),
        "HDFS run identity mismatch",
    )
    expected_dataset = validate_formal_datasets()
    _require(
        resolved.get("dataset") == expected_dataset,
        "resolved frozen formal dataset identity mismatch",
    )
    _require(
        resolved.get("p05_freeze") == validate_p05_freeze(),
        "resolved P05 freeze identity mismatch",
    )
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
        _require(
            command.count(switch) == 1,
            f"resolved server switch missing: {switch}",
        )
    environment = server.get("environment")
    _require(isinstance(environment, Mapping), "server environment is missing")
    fixed_environment = {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "HEDGE_ENABLED": "0",
        "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": "0",
    }
    for key, expected in fixed_environment.items():
        _require(
            environment.get(key) == expected,
            f"environment mismatch: {key}",
        )
    _require(
        "SGLANG_DSPARK_HEDGE_CONFIG_PATH" not in environment
        and "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY" not in environment
        and resolved.get("hedge")
        == {
            "mode": "disabled",
            "enabled": False,
            "calibration_trace": False,
            "config": None,
            "config_path": None,
        }
        and not (scratch / "hedge_config.json").exists(),
        "native formal arm must prove HEDGE off with no runtime config",
    )
    protocol = resolved.get("formal_protocol")
    _require(
        isinstance(protocol, Mapping)
        and protocol.get("clock") == "time.monotonic_ns"
        and protocol.get("warmup_count") == 10
        and protocol.get("warmup_included") is False
        and protocol.get("formal_count") == 500
        and protocol.get("max_total_attempts_per_request") == 3
        and protocol.get("retry_time_included") is True
        and protocol.get("single_sequential_pass") is True
        and protocol.get("resume_or_append_allowed") is False
        and protocol.get("rerun_for_tps_allowed") is False,
        "formal protocol contract mismatch",
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
        and all(isinstance(uuid, str) and uuid.startswith("GPU-") for uuid in uuids),
        "GPU UUID inventory is invalid",
    )
    return {
        "status": "PASS",
        "decode_config_fingerprint": fingerprint,
        "gpu_uuids": uuids,
        "p05_freeze_commit": P05_FREEZE_COMMIT,
        "p05_config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
        "formal_sha256": FORMAL_SHA256,
    }


def _validate_intervals(
    records: Sequence[Mapping[str, Any]], *, cohort: str
) -> tuple[int, int]:
    starts: list[int] = []
    ends: list[int] = []
    for position, record in enumerate(records):
        start = record.get("request_started_monotonic_ns")
        end = record.get("terminal_monotonic_ns")
        _require(
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and start <= end,
            f"{cohort} record {position} has invalid request interval",
        )
        attempts = record.get("attempts")
        _require(
            isinstance(attempts, list) and 1 <= len(attempts) <= 3,
            f"{cohort} record {position} has invalid attempts",
        )
        previous_end = start
        for attempt_index, attempt in enumerate(attempts):
            attempt_start = attempt.get("started_monotonic_ns")
            attempt_end = attempt.get("finished_monotonic_ns")
            _require(
                isinstance(attempt_start, int)
                and isinstance(attempt_end, int)
                and previous_end <= attempt_start <= attempt_end <= end,
                f"{cohort} record {position} attempt {attempt_index} interval invalid",
            )
            previous_end = attempt_end
        starts.append(start)
        ends.append(end)
    _require(
        all(
            earlier_end <= later_start
            for earlier_end, later_start in zip(ends, starts[1:])
        ),
        f"{cohort} request intervals are not sequential",
    )
    return starts[0], ends[-1]


def _replay_spec_records(records: Sequence[Mapping[str, Any]]) -> None:
    for position, record in enumerate(records):
        if record.get("terminal_status") != "succeeded":
            _require(
                record.get("spec_acceptance") is None,
                f"failed formal record {position} has spec evidence",
            )
            continue
        attempts = record.get("attempts")
        successful = [
            attempt
            for attempt in attempts
            if isinstance(attempt, Mapping)
            and attempt.get("status") == "success"
        ]
        _require(
            len(successful) == 1,
            f"formal record {position} must contain one successful attempt",
        )
        raw = successful[0].get("raw_response")
        choices = raw.get("choices") if isinstance(raw, Mapping) else None
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        meta = choice.get("meta_info") if isinstance(choice, Mapping) else None
        normalized, evidence = normalize_spec_acceptance(
            meta,
            explicit_acceptance=(
                meta.get("acceptance_counters")
                if isinstance(meta, Mapping)
                else None
            ),
            completion_tokens=record.get("completion_tokens"),
        )
        _require(
            record.get("acceptance_counters") == normalized
            and record.get("spec_acceptance") == evidence,
            f"formal record {position} spec_* normalization does not replay",
        )


def _validate_record_identity(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_indices: Sequence[int],
    cohort: str,
    manifest_cohort: str,
) -> None:
    _require(
        [record.get("dataset_index") for record in records]
        == list(expected_indices),
        f"{cohort} dataset index order mismatch",
    )
    for position, record in enumerate(records):
        _require(
            record.get("cohort") == cohort
            and record.get("cohort_position") == position
            and record.get("manifest_cohort") == manifest_cohort
            and record.get("manifest_cohort_position") == position,
            f"{cohort} record {position} cohort identity mismatch",
        )


def validate_formal_client_artifacts(
    *,
    scratch: Path,
    expected_warmup_indices: Sequence[int],
    expected_formal_indices: Sequence[int],
    authorized_phase: str,
    arm: str,
    snapshot_validator: Any,
) -> dict[str, Any]:
    """Recompute all formal artifacts from raw response-bearing JSONL."""

    warmups = load_jsonl(scratch / "warmup_outputs.jsonl")
    formal = load_jsonl(scratch / "formal_outputs.jsonl")
    _require(len(warmups) == 10, "warmup outputs must contain exactly 10 rows")
    _require(len(formal) == 500, "formal outputs must contain exactly 500 rows")
    _validate_record_identity(
        warmups,
        expected_indices=expected_warmup_indices,
        cohort="warmup",
        manifest_cohort="calibration",
    )
    _validate_record_identity(
        formal,
        expected_indices=expected_formal_indices,
        cohort="formal",
        manifest_cohort="formal",
    )
    warmup_start, warmup_end = _validate_intervals(warmups, cohort="warmup")
    formal_start, formal_end = _validate_intervals(formal, cohort="formal")
    _replay_spec_records(warmups)
    _replay_spec_records(formal)
    warmup_summary = recompute_summary(
        warmups, expected_count=10, expected_cohort="warmup"
    )
    clear = _load_json(scratch / "pre_formal_clear.json")
    clear_start = clear.get("started_monotonic_ns")
    clear_end = clear.get("finished_monotonic_ns")
    _require(
        clear.get("authorized_phase") == authorized_phase
        and clear.get("status") == "PASS"
        and clear.get("exact_zero") is True
        and clear.get("verified_snapshot_count", 0) > 0
        and clear.get("clear_attempt_count", 0) == 1
        and isinstance(clear_start, int)
        and isinstance(clear_end, int)
        and warmup_end <= clear_start <= clear_end <= formal_start,
        "pre-formal clear does not separate warmup from formal timing",
    )
    timing = _load_json(scratch / "formal_timing.json")
    _require(
        timing.get("authorized_phase") == authorized_phase
        and timing.get("arm") == arm
        and timing.get("clock") == "time.monotonic_ns"
        and timing.get("warmup_record_count") == 10
        and timing.get("warmup_terminal_requests")
        == warmup_summary["terminal_requests"]
        and timing.get("warmup_included") is False
        and timing.get("formal_record_count") == 500
        and timing.get("formal_start_monotonic_ns") == formal_start
        and timing.get("formal_end_monotonic_ns") == formal_end
        and timing.get("retry_time_included") is True
        and timing.get("single_sequential_pass") is True
        and timing.get("warmup_output_sha256")
        == sha256_file(scratch / "warmup_outputs.jsonl")
        and timing.get("formal_output_sha256")
        == sha256_file(scratch / "formal_outputs.jsonl")
        and timing.get("pre_formal_clear_sha256")
        == sha256_file(scratch / "pre_formal_clear.json"),
        "formal timing identity/boundaries are invalid",
    )
    expected_summary = recompute_summary(
        formal,
        timing=timing,
        expected_count=500,
        expected_cohort="formal",
    )
    expected_summary.update(
        authorized_phase=authorized_phase,
        arm=arm,
        source_artifacts={
            "formal_outputs_sha256": sha256_file(
                scratch / "formal_outputs.jsonl"
            ),
            "formal_timing_sha256": sha256_file(
                scratch / "formal_timing.json"
            ),
            "pre_formal_clear_sha256": sha256_file(
                scratch / "pre_formal_clear.json"
            ),
        },
    )
    expected_summary["fingerprint_sha256"] = fingerprint_document(
        expected_summary
    )
    stored_summary = _load_json(scratch / "answer_summary.json")
    _require(
        stored_summary == expected_summary,
        "answer summary differs from independent formal recomputation",
    )
    spec = aggregate_spec_acceptance(formal)
    expected_acceptance = {
        "schema_version": 1,
        "authorized_phase": authorized_phase,
        "arm": arm,
        "acceptance": expected_summary["acceptance"],
        "sglang_spec_normalization": spec,
        "hedge": expected_summary["hedge"],
        "source_artifacts": expected_summary["source_artifacts"],
    }
    expected_acceptance["fingerprint_sha256"] = fingerprint_document(
        expected_acceptance
    )
    _require(
        _load_json(scratch / "acceptance_summary.json")
        == expected_acceptance,
        "acceptance summary differs from spec_* recomputation",
    )
    stored_counters = _load_json(scratch / "hedge_counters.json")
    reconstructed = {
        **stored_counters.get("server_config", {}),
        "internal_states": [
            {"dspark_info_record": {"hedge": snapshot}}
            for snapshot in stored_counters.get("hedge_snapshots", [])
        ],
    }
    replayed = snapshot_validator(reconstructed, expected_summary)
    for key in (
        "status",
        "arm",
        "hedge_mode",
        "hedge_enabled",
        "hedge_config",
        "snapshot_count",
        "proposal_count",
        "active_request_states",
        "state_leaks",
    ):
        _require(
            stored_counters.get(key) == replayed.get(key),
            f"formal server counter mismatch: {key}",
        )
    _require(
        stored_counters.get("formal_request_interval_monotonic_ns")
        == {"start": formal_start, "end": formal_end},
        "formal server counter interval mismatch",
    )
    return {
        "status": "PASS",
        "warmup_count": 10,
        "formal_count": 500,
        "terminal_requests": expected_summary["terminal_requests"],
        "success_requests": expected_summary["success_requests"],
        "failed_requests": expected_summary["failed_requests"],
        "retry_attempts": expected_summary["retry_attempts"],
        "completion_tokens": expected_summary["completion_tokens"],
        "timed_wall_seconds": expected_summary["timing"][
            "timed_wall_seconds"
        ],
        "end_to_end_output_tps": expected_summary["timing"][
            "end_to_end_output_tps"
        ],
        "warmup_start_monotonic_ns": warmup_start,
        "warmup_end_monotonic_ns": warmup_end,
        "formal_start_monotonic_ns": formal_start,
        "formal_end_monotonic_ns": formal_end,
        "gpu_request_window": {"start": formal_start, "end": formal_end},
        "formal_outputs_sha256": sha256_file(
            scratch / "formal_outputs.jsonl"
        ),
    }


def validate_client_artifacts(
    *,
    scratch: Path,
    expected_warmup_indices: Sequence[int],
    expected_formal_indices: Sequence[int],
) -> dict[str, Any]:
    """Preserve the strict native P06 artifact validator."""

    return validate_formal_client_artifacts(
        scratch=scratch,
        expected_warmup_indices=expected_warmup_indices,
        expected_formal_indices=expected_formal_indices,
        authorized_phase="P06",
        arm="native",
        snapshot_validator=lambda payload, _summary: (
            validate_native_server_snapshot(
                payload, require_exact_zero=False
            )
        ),
    )


def validate_formal_gpu_window(
    path: Path,
    *,
    expected_uuids: Sequence[str],
    formal_start: int,
    formal_end: int,
) -> dict[str, Any]:
    """Validate GPU participation only inside the exact formal request window."""

    return _validate_gpu_samples(
        path,
        expected_uuids=expected_uuids,
        request_start=formal_start,
        request_end=formal_end,
    )


def validate_live(*, scratch: Path, attempt_id: str) -> dict[str, Any]:
    resolved = _load_json(scratch / "resolved_config.json")
    resolved_audit = validate_resolved_contract(
        resolved, attempt_id=attempt_id, scratch=scratch
    )
    _require(
        sha256_file(scratch / "dataset_manifest.json")
        == DATASET_MANIFEST_SHA256,
        "copied dataset manifest hash mismatch",
    )
    _require(
        sha256_file(scratch / "p05_frozen_hedge_config.json")
        == FROZEN_CONFIG_SHA256,
        "copied P05 config hash mismatch",
    )
    identity = _validate_identity_artifacts(
        engine=_load_json(scratch / "engine_identity.json"),
        checkpoint=_load_json(scratch / "checkpoint_identity.json"),
        decode_config_fingerprint=resolved_audit[
            "decode_config_fingerprint"
        ],
    )
    startup = _load_json(scratch / "startup.json")
    _require(startup.get("status") == "ready", "server startup is not ready")
    dataset = resolved["dataset"]
    client = validate_client_artifacts(
        scratch=scratch,
        expected_warmup_indices=dataset["warmup_indices"],
        expected_formal_indices=dataset["formal_indices"],
    )
    gpu = validate_formal_gpu_window(
        scratch / "gpu_samples.csv",
        expected_uuids=resolved_audit["gpu_uuids"],
        formal_start=client["formal_start_monotonic_ns"],
        formal_end=client["formal_end_monotonic_ns"],
    )
    return {
        "schema_version": 1,
        "authorized_phase": "P06",
        "status": "PASS",
        "arm": "native",
        "attempt_id": attempt_id,
        "resolved_config": resolved_audit,
        "identities": identity,
        "client": client,
        "gpu_evidence": gpu,
        "server_log": _validate_server_log(scratch / "server.log"),
    }


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
    process_results: dict[str, Any] = {}
    for role in ("server", "sampler"):
        path = scratch / f"{role}_shutdown.json"
        process_results[role] = (
            _load_json(path)
            if path.is_file()
            else {"status": "NOT_STARTED_OR_UNPROVEN"}
        )
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
        "authorized_phase": "P06",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "arm": "native",
        "attempt_id": attempt_id,
        "original_returncode": original_returncode,
        "cleanup_returncode": cleanup_returncode,
        "signal_name": signal_name or None,
        "checks": checks,
        "process_results": process_results,
    }
    _atomic_json(scratch / "shutdown.json", result, exclusive=True)
    return result


def validate_lifecycle_events(
    events: Sequence[Mapping[str, Any]],
    *,
    require_archive: bool,
) -> dict[str, Any]:
    expected = list(EXPECTED_CLEANUP_ORDER)
    if not require_archive:
        expected.pop()
    observed = [
        event.get("stage")
        for event in events
        if event.get("stage") in EXPECTED_CLEANUP_ORDER
    ]
    _require(
        observed == expected,
        "cleanup lifecycle order/membership mismatch",
    )
    return {"status": "PASS", "cleanup_order": observed}


def ensure_required_artifacts(
    *, scratch: Path, reason: str
) -> list[str]:
    """Materialize explicit placeholders without replacing partial evidence."""

    _require(scratch.is_dir(), f"scratch directory is absent: {scratch}")
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
                    "authorized_phase": "P06",
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
                        "authorized_phase": "P06",
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
            path.write_text(
                "status,reason\nMISSING," + reason + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(f"MISSING: {reason}\n", encoding="utf-8")
    return missing


def finalize_attempt(*, scratch: Path, attempt_id: str) -> dict[str, Any]:
    missing = ensure_required_artifacts(
        scratch=scratch,
        reason="P06 lifecycle ended before this artifact was produced",
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

    def shutdown_check() -> dict[str, Any]:
        shutdown = _load_json(scratch / "shutdown.json")
        _require(
            shutdown.get("status") == "PASS"
            and shutdown.get("attempt_id") == attempt_id
            and all(
                value is True
                for value in shutdown.get("checks", {}).values()
            ),
            "shutdown is not exact PASS",
        )
        return {"status": "PASS"}

    capture("shutdown", shutdown_check)
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
    for name in ("keepalive_before", "keepalive_after"):
        capture(
            name,
            lambda name=name: (
                _validate_keepalive(
                    _load_json(scratch / f"{name}.json"), name
                )
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
        "authorized_phase": "P06",
        "status": "PASS" if not errors else "FAIL",
        "arm": "native",
        "attempt_id": attempt_id,
        "required_artifacts": list(REQUIRED_ARTIFACTS),
        "missing_artifacts_materialized": missing,
        "checks": checks,
        "errors": errors,
    }


def _copy_exclusive(source: Path, destination: Path) -> None:
    with source.open("rb") as input_stream, destination.open("xb") as output:
        shutil.copyfileobj(input_stream, output, 1024 * 1024)


def archive_formal_attempt(
    *,
    scratch: Path,
    hdfs_run: Path,
    authorized_phase: str,
    arm: str,
    required_artifacts: Sequence[str] = REQUIRED_ARTIFACTS,
) -> dict[str, Any]:
    _require(scratch.is_dir(), "scratch directory is absent")
    _require(hdfs_run.is_dir(), "HDFS run directory is absent")
    _require(not list(hdfs_run.iterdir()), "HDFS run directory is not empty")
    names = {path.name for path in scratch.iterdir() if path.is_file()}
    _require(
        set(required_artifacts).issubset(names),
        "scratch is missing required artifacts",
    )
    validate_lifecycle_events(
        _load_lifecycle_events(scratch / "lifecycle_events.jsonl"),
        require_archive=True,
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
        "authorized_phase": authorized_phase,
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
        sha256_file(hdfs_run / manifest_path.name)
        == sha256_file(manifest_path),
        "archived manifest hash mismatch",
    )
    return {
        "schema_version": 1,
        "authorized_phase": authorized_phase,
        "status": "PASS",
        "file_count": len(records),
        "manifest": str(hdfs_run / manifest_path.name),
    }


def archive_attempt(*, scratch: Path, hdfs_run: Path) -> dict[str, Any]:
    """Preserve the native P06 archive interface."""

    return archive_formal_attempt(
        scratch=scratch,
        hdfs_run=hdfs_run,
        authorized_phase="P06",
        arm="native",
    )


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
    live.add_argument("--attempt-id", required=True)

    shutdown = subparsers.add_parser("record-shutdown")
    shutdown.add_argument("--scratch", type=Path, required=True)
    shutdown.add_argument("--attempt-id", required=True)
    shutdown.add_argument("--original-returncode", type=int, required=True)
    shutdown.add_argument("--cleanup-returncode", type=int, required=True)
    shutdown.add_argument("--contexts-proven", type=_bool, required=True)
    shutdown.add_argument("--keepalive-ready", type=_bool, required=True)
    shutdown.add_argument("--signal-name", default="")

    final = subparsers.add_parser("final")
    final.add_argument("--scratch", type=Path, required=True)
    final.add_argument("--attempt-id", required=True)

    archive = subparsers.add_parser("archive")
    archive.add_argument("--scratch", type=Path, required=True)
    archive.add_argument("--hdfs-run", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "live":
        output = args.scratch / "live_validation.json"
        try:
            result = validate_live(
                scratch=args.scratch, attempt_id=args.attempt_id
            )
        except BaseException as error:
            _atomic_json(
                output,
                {
                    "schema_version": 1,
                    "authorized_phase": "P06",
                    "status": "FAIL",
                    "arm": "native",
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
        result = finalize_attempt(
            scratch=args.scratch, attempt_id=args.attempt_id
        )
        _atomic_json(
            args.scratch / "artifact_validation.json",
            result,
            exclusive=True,
        )
        return 0 if result["status"] == "PASS" else 1
    if args.command == "archive":
        result = archive_attempt(
            scratch=args.scratch, hdfs_run=args.hdfs_run
        )
        return 0 if result["status"] == "PASS" else 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
