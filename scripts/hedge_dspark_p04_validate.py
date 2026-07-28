#!/usr/bin/env python3
"""Validate and atomically archive one HEDGE-on-V4 DSpark P04 attempt."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from hedge_dspark_p04_prepare import (
    B0_CONFIG,
    B0_CONFIG_BYTES,
    EXPECTED_GPU_NAME,
    EXPECTED_GPUS,
    EXPECTED_WORKER,
    FIXED_PORT,
    MODEL_PATH,
    RUN_ROOT,
    _fingerprint,
)


REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "resolved_config.json",
    "engine_identity.json",
    "checkpoint_identity.json",
    "server.log",
    "gpu_samples.csv",
    "api_smoke.json",
    "hedge_counters.json",
    "shutdown.json",
    "cuda_contexts_after.txt",
    "keepalive_before.json",
    "keepalive_after.json",
)
JSON_ARTIFACTS = {
    name for name in REQUIRED_ARTIFACTS if name.endswith(".json")
}
EXPECTED_CLEANUP_ORDER: tuple[str, ...] = (
    "terminate_registered_server",
    "prove_cuda_contexts_none",
    "terminate_registered_sampler",
    "resume_keepalive_if_cleanup_proven",
    "validate_keepalive_8x10_mean_ge_40",
    "validate_required_artifacts",
    "archive_without_overwrite",
)
ATTEMPT_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z-p04-(native|b0)"
    r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
)
SERVER_ARG_VALUES = {
    "--model-path": str(MODEL_PATH),
    "--served-model-name": "deepseek-v4-flash-dspark",
    "--host": "127.0.0.1",
    "--port": str(FIXED_PORT),
    "--tp-size": "8",
    "--speculative-algorithm": "DSPARK",
    "--speculative-dspark-block-size": "5",
    "--moe-runner-backend": "flashinfer_mxfp4",
    "--speculative-moe-runner-backend": "flashinfer_mxfp4",
    "--context-length": "4096",
    "--max-running-requests": "1",
    "--mem-fraction-static": "0.80",
}
SERVER_SWITCHES = (
    "--disable-cuda-graph",
    "--disable-overlap-schedule",
    "--disable-radix-cache",
)
EXPECTED_ENVIRONMENT = {
    "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
    "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": "0",
    "SGLANG_DSV4_FP4_EXPERTS": "1",
    "SGLANG_RAGGED_VERIFY_MODE": "static",
    "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
FORBIDDEN_ENVIRONMENT = {
    "HEDGE_CONFIG",
    "SGLANG_DSPARK_HEDGE_CONFIG_JSON",
    "SGLANG_DSPARK_HEDGE_MODE",
    "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY",
    "SGLANG_DSV4_FP4_DEQUANT",
}
CRASH_PATTERNS = {
    "python_traceback": re.compile(r"Traceback \(most recent call last\)"),
    "cuda_error": re.compile(r"\bCUDA (?:error|Error)\b"),
    "nccl_error": re.compile(r"\bNCCL (?:WARN|ERROR)\b"),
    "worker_crash": re.compile(
        r"\bworker\b.{0,80}\b(?:died|crashed|aborted)\b", re.IGNORECASE
    ),
    "segmentation_fault": re.compile(r"\bSegmentation fault\b"),
}


def _atomic_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    mode = "xb" if exclusive else "wb"
    try:
        with temporary.open(mode) as output:
            output.write(
                json.dumps(
                    value,
                    allow_nan=False,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
            )
            output.write(b"\n")
            output.flush()
            os.fsync(output.fileno())
        if exclusive and path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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
    _require(arm in {"native", "b0"}, "arm must be native or b0")
    match = ATTEMPT_PATTERN.fullmatch(attempt_id)
    _require(
        match is not None and match.group(1) == arm,
        "attempt-id does not encode the selected P04 arm",
    )
    _require(
        resolved.get("authorized_phase") == "P04",
        "resolved config is not authorized for P04",
    )
    _require(
        resolved.get("worker_id") == EXPECTED_WORKER,
        "resolved worker is not the dedicated DSpark lane",
    )
    _require(
        isinstance(resolved.get("hostname"), str)
        and bool(resolved.get("hostname")),
        "resolved worker hostname is missing",
    )
    _require(resolved.get("arm") == arm, "resolved arm mismatch")
    _require(
        resolved.get("attempt_id") == attempt_id,
        "resolved attempt-id mismatch",
    )
    _require(
        resolved.get("scratch") == str(scratch.resolve()),
        "resolved scratch path mismatch",
    )
    _require(
        resolved.get("hdfs_run") == str(RUN_ROOT / attempt_id),
        "resolved HDFS run path mismatch",
    )
    api = resolved.get("api")
    _require(isinstance(api, Mapping), "resolved API config is missing")
    _require(
        api.get("host") == "127.0.0.1"
        and api.get("port") == FIXED_PORT
        and api.get("base_url") == f"http://127.0.0.1:{FIXED_PORT}",
        "resolved API endpoint is not the fixed loopback port",
    )

    server = resolved.get("server")
    _require(isinstance(server, Mapping), "resolved server config is missing")
    command = server.get("command")
    _require(
        isinstance(command, list)
        and command[:3]
        == [
            "/home/tiger/venvs/hedge-v4-dspark/bin/python",
            "-m",
            "sglang.launch_server",
        ],
        "resolved launcher command is not the fixed formal Python",
    )
    for flag, expected in SERVER_ARG_VALUES.items():
        _require(
            command.count(flag) == 1,
            f"server command must contain {flag} exactly once",
        )
        position = command.index(flag)
        _require(
            position + 1 < len(command)
            and command[position + 1] == expected,
            f"server command has the wrong value for {flag}",
        )
    for switch in SERVER_SWITCHES:
        _require(
            command.count(switch) == 1,
            f"server command must contain {switch} exactly once",
        )

    environment = server.get("environment")
    _require(
        isinstance(environment, Mapping),
        "resolved server environment is missing",
    )
    for key, expected in EXPECTED_ENVIRONMENT.items():
        _require(
            environment.get(key) == expected,
            f"resolved environment mismatch for {key}",
        )
    _require(
        environment.get("HEDGE_ENABLED")
        == ("1" if arm == "b0" else "0"),
        "HEDGE_ENABLED does not match the arm",
    )
    _require(
        not (FORBIDDEN_ENVIRONMENT & set(environment)),
        "forbidden inherited decode environment was resolved",
    )
    unset_environment = server.get("unset_environment")
    _require(
        isinstance(unset_environment, list)
        and FORBIDDEN_ENVIRONMENT.issubset(set(unset_environment)),
        "resolved unset-environment list is incomplete",
    )

    hedge = resolved.get("hedge")
    _require(isinstance(hedge, Mapping), "resolved HEDGE config is missing")
    expected_config = dict(B0_CONFIG) if arm == "b0" else None
    _require(
        hedge.get("mode") == ("enabled" if arm == "b0" else "disabled"),
        "resolved HEDGE mode does not match the arm",
    )
    _require(
        hedge.get("config") == expected_config,
        "resolved HEDGE config does not match the arm",
    )
    config_path = scratch / "hedge_config.json"
    if arm == "b0":
        _require(
            hedge.get("config_path") == str(config_path.resolve()),
            "B0 config path is not attempt-local",
        )
        _require(
            environment.get("SGLANG_DSPARK_HEDGE_CONFIG_PATH")
            == str(config_path.resolve()),
            "B0 environment does not point at the attempt-local config",
        )
        _require(
            config_path.read_bytes() == B0_CONFIG_BYTES,
            "B0 config bytes are not the frozen configuration",
        )
    else:
        _require(
            hedge.get("config_path") is None,
            "native arm unexpectedly resolved a HEDGE config path",
        )
        _require(
            "SGLANG_DSPARK_HEDGE_CONFIG_PATH" not in environment,
            "native arm unexpectedly exported a HEDGE config path",
        )
        _require(
            not config_path.exists(),
            "native attempt unexpectedly contains hedge_config.json",
        )

    decode_affecting = resolved.get("decode_affecting")
    _require(
        isinstance(decode_affecting, Mapping),
        "decode-affecting config is missing",
    )
    fingerprint = resolved.get("decode_config_fingerprint")
    _require(
        isinstance(fingerprint, str)
        and fingerprint == _fingerprint(decode_affecting),
        "decode config fingerprint mismatch",
    )

    inventory = resolved.get("gpu_inventory")
    _require(
        isinstance(inventory, list) and len(inventory) == EXPECTED_GPUS,
        "resolved inventory must contain exactly 8 GPUs",
    )
    _require(
        [item.get("index") for item in inventory] == list(range(EXPECTED_GPUS)),
        "resolved GPU indices must be exactly 0 through 7",
    )
    uuids = [item.get("uuid") for item in inventory]
    _require(
        len(set(uuids)) == EXPECTED_GPUS
        and all(
            isinstance(uuid, str) and uuid.startswith("GPU-")
            for uuid in uuids
        ),
        "resolved inventory must contain eight unique GPU UUIDs",
    )
    _require(
        all(item.get("name") == EXPECTED_GPU_NAME for item in inventory),
        "resolved inventory contains a non-H20 GPU",
    )
    return {
        "status": "PASS",
        "decode_config_fingerprint": fingerprint,
        "gpu_uuids": uuids,
    }


def _validate_identity_artifacts(
    *,
    engine: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    decode_config_fingerprint: str,
) -> dict[str, Any]:
    _require(engine.get("status") == "PASS", "engine identity is not PASS")
    _require(
        engine.get("decode_config_fingerprint")
        == decode_config_fingerprint,
        "engine identity has a different decode config fingerprint",
    )
    engine_checks = engine.get("checks")
    if engine_checks is not None:
        _require(
            isinstance(engine_checks, Mapping)
            and bool(engine_checks)
            and all(value is True for value in engine_checks.values()),
            "one or more engine identity checks failed",
        )
    _require(
        checkpoint.get("status") == "PASS",
        "checkpoint identity is not PASS",
    )
    checkpoint_checks = checkpoint.get("checks")
    if checkpoint_checks is not None:
        _require(
            isinstance(checkpoint_checks, Mapping)
            and bool(checkpoint_checks)
            and all(value is True for value in checkpoint_checks.values()),
            "one or more checkpoint identity checks failed",
        )
    return {"status": "PASS"}


def _validate_api(
    api: Mapping[str, Any], *, arm: str
) -> dict[str, Any]:
    _require(api.get("status") == "PASS", "API smoke is not PASS")
    _require(api.get("arm") == arm, "API smoke arm mismatch")
    raw_response = api.get("raw_response")
    _require(
        isinstance(raw_response, Mapping) and bool(raw_response),
        "API raw response is missing or empty",
    )
    token_ids = api.get("output_token_ids")
    _require(
        isinstance(token_ids, list)
        and bool(token_ids)
        and all(
            isinstance(token, int) and not isinstance(token, bool)
            for token in token_ids
        ),
        "API output token IDs must be a non-empty integer list",
    )
    completion_tokens = api.get("completion_tokens")
    _require(
        isinstance(completion_tokens, int)
        and not isinstance(completion_tokens, bool)
        and completion_tokens == len(token_ids),
        "completion token count does not match output token IDs",
    )
    start = api.get("request_started_monotonic_ns")
    end = api.get("request_finished_monotonic_ns")
    _require(
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start <= end,
        "API monotonic request interval is invalid",
    )
    return {
        "status": "PASS",
        "completion_tokens": completion_tokens,
        "request_start_monotonic_ns": start,
        "request_end_monotonic_ns": end,
    }


def _validate_counters(
    counters: Mapping[str, Any],
    *,
    arm: str,
    request_start: int,
    request_end: int,
) -> dict[str, Any]:
    _require(counters.get("status") == "PASS", "HEDGE counters are not PASS")
    _require(counters.get("arm") == arm, "HEDGE counter arm mismatch")
    snapshots = counters.get("hedge_snapshots")
    _require(
        isinstance(snapshots, list) and bool(snapshots),
        "HEDGE counter snapshots are missing",
    )
    expected_mode = "enabled" if arm == "b0" else "disabled"
    expected_enabled = 1 if arm == "b0" else 0
    total_proposals = 0
    for index, snapshot in enumerate(snapshots):
        _require(
            isinstance(snapshot, Mapping),
            f"HEDGE snapshot {index} is not an object",
        )
        _require(
            snapshot.get("mode") == expected_mode,
            f"HEDGE snapshot {index} mode mismatch",
        )
        _require(
            snapshot.get("experiment_switches")
            == {
                "HEDGE_ENABLED": expected_enabled,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
            },
            f"HEDGE snapshot {index} switches mismatch",
        )
        _require(
            snapshot.get("config")
            == (dict(B0_CONFIG) if arm == "b0" else None),
            f"HEDGE snapshot {index} config mismatch",
        )
        _require(
            snapshot.get("gamma") == 5
            and snapshot.get("verify_num_draft_tokens") == 6,
            f"HEDGE snapshot {index} DSpark width mismatch",
        )
        proposals = snapshot.get("proposals")
        _require(
            isinstance(proposals, int)
            and not isinstance(proposals, bool)
            and proposals >= 0,
            f"HEDGE snapshot {index} proposal count is invalid",
        )
        total_proposals += proposals
    _require(
        counters.get("proposal_count") == total_proposals,
        "aggregate HEDGE proposal count mismatch",
    )
    if arm == "b0":
        _require(
            total_proposals > 0,
            "B0 HEDGE counter does not prove verify was called",
        )
    interval = counters.get("request_interval_monotonic_ns")
    _require(
        interval == {"start": request_start, "end": request_end},
        "counter request interval does not match API evidence",
    )
    return {
        "status": "PASS",
        "proposal_count": total_proposals,
        "snapshot_count": len(snapshots),
    }


def _integer_field(
    row: Mapping[str, str], field: str, *, ordinal: int
) -> int:
    try:
        value = int(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"sample ordinal {ordinal} has invalid {field}"
        ) from error
    return value


def _validate_gpu_samples(
    path: Path,
    *,
    expected_uuids: Sequence[str],
    request_start: int,
    request_end: int,
) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    _require(bool(rows), "GPU sample CSV has no samples")
    grouped: dict[int, list[Mapping[str, str]]] = defaultdict(list)
    for raw in rows:
        ordinal = _integer_field(raw, "sample_ordinal", ordinal=-1)
        grouped[ordinal].append(raw)
    ordinals = sorted(grouped)
    _require(
        ordinals == list(range(len(ordinals))),
        "GPU sample ordinals must be contiguous from zero",
    )

    sample_times: list[int] = []
    request_rows: list[Mapping[str, str]] = []
    expected_uuid_list = list(expected_uuids)
    for ordinal in ordinals:
        sample = grouped[ordinal]
        _require(
            len(sample) == EXPECTED_GPUS,
            f"sample ordinal {ordinal} must contain exactly 8 rows",
        )
        indices = [
            _integer_field(row, "gpu_index", ordinal=ordinal)
            for row in sample
        ]
        _require(
            indices == list(range(EXPECTED_GPUS)),
            f"sample ordinal {ordinal} GPU indices are not exactly 0..7",
        )
        uuids = [row.get("gpu_uuid") for row in sample]
        _require(
            uuids == expected_uuid_list,
            f"sample ordinal {ordinal} GPU UUID inventory changed",
        )
        times = {
            _integer_field(row, "monotonic_ns", ordinal=ordinal)
            for row in sample
        }
        _require(
            len(times) == 1,
            f"sample ordinal {ordinal} has multiple timestamps",
        )
        sample_time = times.pop()
        sample_times.append(sample_time)
        for row in sample:
            utilization = _integer_field(
                row, "utilization_gpu_percent", ordinal=ordinal
            )
            used = _integer_field(row, "memory_used_mib", ordinal=ordinal)
            total = _integer_field(row, "memory_total_mib", ordinal=ordinal)
            _require(
                0 <= utilization <= 100 and 0 <= used <= total and total > 0,
                f"sample ordinal {ordinal} has invalid GPU metrics",
            )
        if request_start <= sample_time <= request_end:
            request_rows.extend(sample)

    _require(
        sample_times == sorted(sample_times)
        and len(set(sample_times)) == len(sample_times),
        "GPU sample monotonic timestamps are not strictly increasing",
    )
    cadence_seconds = [
        (later - earlier) / 1_000_000_000
        for earlier, later in zip(sample_times, sample_times[1:])
    ]
    _require(
        all(0.5 <= delta <= 2.5 for delta in cadence_seconds),
        "GPU sampling cadence departed from the one-second sampler",
    )
    request_bracketed = (
        sample_times[0] <= request_start
        and sample_times[-1] >= request_end
    )
    _require(
        request_bracketed,
        "GPU samples do not bracket the API request interval",
    )
    _require(
        bool(request_rows),
        "GPU samples contain no observation during the API request",
    )
    request_by_uuid: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in request_rows:
        request_by_uuid[str(row["gpu_uuid"])].append(row)
    participation: dict[str, dict[str, int]] = {}
    for uuid in expected_uuid_list:
        samples = request_by_uuid.get(uuid, [])
        _require(
            bool(samples),
            f"GPU {uuid} has no sample during the API request",
        )
        maximum_utilization = max(
            int(row["utilization_gpu_percent"]) for row in samples
        )
        minimum_memory = min(int(row["memory_used_mib"]) for row in samples)
        _require(
            maximum_utilization > 0,
            f"GPU {uuid} shows no request-period utilization",
        )
        _require(
            minimum_memory > 0,
            f"GPU {uuid} shows no request-period model memory",
        )
        participation[uuid] = {
            "request_sample_count": len(samples),
            "max_utilization_percent": maximum_utilization,
            "min_memory_used_mib": minimum_memory,
        }
    return {
        "status": "PASS",
        "sample_count": len(ordinals),
        "row_count": len(rows),
        "gpu_uuids": expected_uuid_list,
        "request_bracketed": request_bracketed,
        "request_sample_ordinals": len(request_rows) // EXPECTED_GPUS,
        "cadence_seconds": cadence_seconds,
        "participation": participation,
    }


def _rank_has(
    text: str, rank: int, required_pattern: str
) -> bool:
    rank_tag = rf"\bTP{rank}\b"
    return any(
        re.search(rank_tag, line)
        and re.search(required_pattern, line, re.IGNORECASE)
        for line in text.splitlines()
    )


def _validate_server_log(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    _require(bool(text.strip()), "server.log is empty")
    tp_ranks = [
        rank
        for rank in range(EXPECTED_GPUS)
        if re.search(rf"\bTP{rank}\b", text)
    ]
    _require(
        tp_ranks == list(range(EXPECTED_GPUS)),
        "server.log does not contain TP rank 0 through 7",
    )
    distributed_ranks = [
        rank
        for rank in range(EXPECTED_GPUS)
        if _rank_has(
            text,
            rank,
            r"(?:Init torch distributed ends|NCCL.*Init COMPLETE)",
        )
    ]
    _require(
        distributed_ranks == list(range(EXPECTED_GPUS)),
        "server.log does not prove all 8 TP ranks initialized",
    )
    draft_ranks = [
        rank
        for rank in range(EXPECTED_GPUS)
        if _rank_has(text, rank, r"DeepseekV4ForCausalLMDSpark")
    ]
    _require(
        draft_ranks == list(range(EXPECTED_GPUS)),
        "server.log does not prove DSpark draft loading on all 8 ranks",
    )
    target_loaded_ranks = [
        rank
        for rank in range(EXPECTED_GPUS)
        if _rank_has(
            text,
            rank,
            r"Load weight end.*type=DeepseekV4ForCausalLM,",
        )
    ]
    _require(
        target_loaded_ranks == list(range(EXPECTED_GPUS)),
        "server.log does not prove target load completion on all 8 ranks",
    )
    draft_loaded_ranks = [
        rank
        for rank in range(EXPECTED_GPUS)
        if _rank_has(
            text,
            rank,
            r"Load weight end.*type=DeepseekV4ForCausalLMDSpark,",
        )
    ]
    _require(
        draft_loaded_ranks == list(range(EXPECTED_GPUS)),
        "server.log does not prove draft load completion on all 8 ranks",
    )
    _require(
        len(re.findall(r"48/48", text)) >= 2,
        "server.log does not prove both target and draft 48/48 loads",
    )
    _require(
        "speculative_algorithm='DSPARK'" in text
        or "speculative_algorithm=DSPARK" in text
        or "speculative_algorithm: DSPARK" in text,
        "server.log does not identify speculative_algorithm DSPARK",
    )
    _require(
        "flashinfer_mxfp4" in text
        and (
            "Mxfp4FlashinferCutlassMoEMethod" in text
            or "MXFP4" in text
        ),
        "server.log does not prove the packed FP4 FlashInfer backend",
    )
    _require(
        re.search(
            r"Initialized DSpark draft runner.{0,160}gamma=5", text
        )
        is not None,
        "server.log does not prove DSpark proposal width 5",
    )
    _require(
        "The server is fired up and ready to roll!" in text,
        "server.log does not contain the ready marker",
    )
    crash_markers = [
        name for name, pattern in CRASH_PATTERNS.items() if pattern.search(text)
    ]
    _require(
        not crash_markers,
        "server.log contains unhandled crash evidence: "
        + ", ".join(crash_markers),
    )
    return {
        "status": "PASS",
        "tp_ranks": tp_ranks,
        "distributed_ranks": distributed_ranks,
        "draft_ranks": draft_ranks,
        "target_loaded_ranks": target_loaded_ranks,
        "draft_loaded_ranks": draft_loaded_ranks,
        "load_48_of_48_markers": len(re.findall(r"48/48", text)),
        "crash_markers": crash_markers,
    }


def validate_live(
    *, scratch: Path, arm: str, attempt_id: str
) -> dict[str, Any]:
    """Validate all evidence available while the registered server is live."""

    scratch = scratch.resolve()
    resolved = _load_json(scratch / "resolved_config.json")
    engine = _load_json(scratch / "engine_identity.json")
    checkpoint = _load_json(scratch / "checkpoint_identity.json")
    api = _load_json(scratch / "api_smoke.json")
    counters = _load_json(scratch / "hedge_counters.json")
    resolved_audit = _validate_resolved(
        resolved,
        arm=arm,
        attempt_id=attempt_id,
        scratch=scratch,
    )
    identity_audit = _validate_identity_artifacts(
        engine=engine,
        checkpoint=checkpoint,
        decode_config_fingerprint=resolved_audit[
            "decode_config_fingerprint"
        ],
    )
    api_audit = _validate_api(api, arm=arm)
    counter_audit = _validate_counters(
        counters,
        arm=arm,
        request_start=api_audit["request_start_monotonic_ns"],
        request_end=api_audit["request_end_monotonic_ns"],
    )
    gpu_audit = _validate_gpu_samples(
        scratch / "gpu_samples.csv",
        expected_uuids=resolved_audit["gpu_uuids"],
        request_start=api_audit["request_start_monotonic_ns"],
        request_end=api_audit["request_end_monotonic_ns"],
    )
    server_log_audit = _validate_server_log(scratch / "server.log")
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS",
        "arm": arm,
        "attempt_id": attempt_id,
        "resolved_config": resolved_audit,
        "identities": identity_audit,
        "api": api_audit,
        "hedge_counters": counter_audit,
        "gpu_evidence": gpu_audit,
        "server_log": server_log_audit,
    }


def _placeholder_json(name: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "MISSING",
        "artifact": name,
        "reason": reason,
    }


def ensure_required_artifacts(
    *, scratch: Path, reason: str
) -> list[str]:
    """Create explicit, non-overwriting placeholders for missing evidence."""

    _require(scratch.is_dir(), f"scratch directory does not exist: {scratch}")
    missing: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        path = scratch / name
        if path.exists():
            continue
        missing.append(name)
        if name in JSON_ARTIFACTS:
            _atomic_json(
                path, _placeholder_json(name, reason), exclusive=True
            )
        elif name == "gpu_samples.csv":
            path.write_text(
                "status,reason\n"
                + "MISSING,"
                + json.dumps(reason, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(
                f"MISSING: {reason}\n",
                encoding="utf-8",
            )
    return missing


def _load_lifecycle_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        _require(
            isinstance(value, dict) and isinstance(value.get("stage"), str),
            f"invalid lifecycle event at line {line_number}",
        )
        events.append(value)
    return events


def validate_lifecycle_events(
    events: Sequence[Mapping[str, Any]],
    *,
    require_archive: bool = True,
) -> dict[str, Any]:
    expected = list(EXPECTED_CLEANUP_ORDER)
    if not require_archive:
        expected.pop()
    observed = [
        str(event.get("stage"))
        for event in events
        if event.get("stage") in EXPECTED_CLEANUP_ORDER
    ]
    _require(
        observed == expected,
        "cleanup stage order/membership mismatch: "
        f"expected={expected!r} observed={observed!r}",
    )
    return {"status": "PASS", "cleanup_order": observed}


def _validate_keepalive(value: Mapping[str, Any], name: str) -> None:
    _require(value.get("status") == "PASS", f"{name} is not PASS")
    _require(
        value.get("worker_id") == EXPECTED_WORKER,
        f"{name} worker mismatch",
    )
    health = value.get("health")
    _require(isinstance(health, Mapping), f"{name} health is missing")
    _require(
        health.get("expected_gpus") == EXPECTED_GPUS
        and health.get("sample_count") == 10
        and health.get("underutilized_gpus") == [],
        f"{name} is not an exact 8x10 healthy gate",
    )
    per_gpu = health.get("per_gpu")
    _require(
        isinstance(per_gpu, Mapping)
        and set(per_gpu) == {str(index) for index in range(EXPECTED_GPUS)},
        f"{name} does not contain exact GPUs 0 through 7",
    )
    for index in range(EXPECTED_GPUS):
        record = per_gpu[str(index)]
        _require(
            isinstance(record, Mapping)
            and record.get("sample_count") == 10
            and float(record.get("mean_utilization", -1)) >= 40.0,
            f"{name} GPU {index} fails the 10-sample mean>=40 gate",
        )


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
    successful_process_cleanup = all(
        value.get("status") in {"terminated", "already_exited"}
        for value in process_results.values()
    )
    checks = {
        "main_returncode_zero": original_returncode == 0,
        "cleanup_returncode_zero": cleanup_returncode == 0,
        "contexts_proven": contexts_proven,
        "keepalive_ready": keepalive_ready,
        "registered_process_groups_stopped": successful_process_cleanup,
        "no_external_signal": signal_name == "",
    }
    result = {
        "schema_version": 1,
        "authorized_phase": "P04",
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


def finalize_attempt(
    *, scratch: Path, arm: str, attempt_id: str
) -> dict[str, Any]:
    missing = ensure_required_artifacts(
        scratch=scratch,
        reason="P04 lifecycle ended before this artifact was produced",
    )
    checks: dict[str, Any] = {}
    errors: list[str] = []

    def capture(name: str, operation: Any) -> None:
        try:
            value = operation()
        except BaseException as error:
            checks[name] = {
                "status": "FAIL",
                "error_type": type(error).__name__,
                "error": str(error),
            }
            errors.append(f"{name}: {type(error).__name__}: {error}")
        else:
            checks[name] = value

    capture(
        "live_evidence",
        lambda: validate_live(
            scratch=scratch, arm=arm, attempt_id=attempt_id
        ),
    )

    def validate_shutdown_artifact() -> dict[str, Any]:
        shutdown = _load_json(scratch / "shutdown.json")
        _require(shutdown.get("status") == "PASS", "shutdown is not PASS")
        _require(
            shutdown.get("arm") == arm
            and shutdown.get("attempt_id") == attempt_id,
            "shutdown identity mismatch",
        )
        _require(
            isinstance(shutdown.get("checks"), Mapping)
            and all(
                value is True for value in shutdown["checks"].values()
            ),
            "shutdown contains a failed cleanup check",
        )
        return {"status": "PASS"}

    capture("shutdown", validate_shutdown_artifact)

    def validate_contexts() -> dict[str, Any]:
        text = (scratch / "cuda_contexts_after.txt").read_text(
            encoding="utf-8"
        )
        _require(
            "contexts=none" in text,
            "post-shutdown CUDA contexts were not proven absent",
        )
        return {"status": "PASS"}

    capture("cuda_contexts_after", validate_contexts)
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
        "lifecycle_order",
        lambda: validate_lifecycle_events(
            _load_lifecycle_events(scratch / "lifecycle_events.jsonl"),
            require_archive=False,
        ),
    )
    if missing:
        errors.append(
            "required artifacts missing at lifecycle end: "
            + ", ".join(missing)
        )
    status = "PASS" if not errors else "FAIL"
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": status,
        "arm": arm,
        "attempt_id": attempt_id,
        "required_artifacts": list(REQUIRED_ARTIFACTS),
        "missing_artifacts_materialized": missing,
        "checks": checks,
        "errors": errors,
    }


def _copy_exclusive(source: Path, destination: Path) -> None:
    with source.open("rb") as input_stream, destination.open(
        "xb"
    ) as output_stream:
        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)


def archive_attempt(*, scratch: Path, hdfs_run: Path) -> dict[str, Any]:
    """Copy immutable small artifacts to an empty HDFS run and re-hash them."""

    scratch = scratch.resolve()
    hdfs_run = hdfs_run.resolve()
    _require(scratch.is_dir(), f"scratch directory does not exist: {scratch}")
    _require(
        hdfs_run.is_dir(),
        f"HDFS run directory does not exist: {hdfs_run}",
    )
    existing = list(hdfs_run.iterdir())
    if existing:
        raise FileExistsError(
            f"archive destination is not empty: {hdfs_run}"
        )
    validate_lifecycle_path = scratch / "lifecycle_events.jsonl"
    if validate_lifecycle_path.is_file():
        validate_lifecycle_events(
            _load_lifecycle_events(validate_lifecycle_path),
            require_archive=True,
        )
    manifest_path = scratch / "archive_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(
            f"refusing to overwrite archive manifest: {manifest_path}"
        )
    sources = sorted(
        (
            path
            for path in scratch.iterdir()
            if path.is_file() and path.name != manifest_path.name
        ),
        key=lambda path: path.name,
    )
    _require(bool(sources), "scratch contains no files to archive")
    source_names = {path.name for path in sources}
    _require(
        set(REQUIRED_ARTIFACTS).issubset(source_names),
        "scratch is missing one or more required P04 artifacts",
    )
    records = [
        {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sources
    ]
    manifest = {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS",
        "source": str(scratch),
        "destination": str(hdfs_run),
        "files": records,
    }
    _atomic_json(manifest_path, manifest, exclusive=True)
    for record in records:
        _copy_exclusive(
            scratch / record["path"], hdfs_run / record["path"]
        )
    _copy_exclusive(
        manifest_path, hdfs_run / manifest_path.name
    )
    for record in records:
        destination = hdfs_run / record["path"]
        _require(
            destination.stat().st_size == record["bytes"]
            and _sha256_file(destination) == record["sha256"],
            f"archived file verification failed: {record['path']}",
        )
    _require(
        _sha256_file(hdfs_run / manifest_path.name)
        == _sha256_file(manifest_path),
        "archived manifest verification failed",
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "file_count": len(records),
        "manifest": str(hdfs_run / manifest_path.name),
    }


def _write_cli_failure(
    path: Path,
    *,
    arm: str | None,
    attempt_id: str | None,
    error: BaseException,
) -> None:
    value = {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "FAIL",
        "arm": arm,
        "attempt_id": attempt_id,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    if not path.exists():
        _atomic_json(path, value, exclusive=True)


def _bool_arg(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise argparse.ArgumentTypeError("boolean flag must be 0 or 1")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    live = subparsers.add_parser("live")
    live.add_argument("--scratch", type=Path, required=True)
    live.add_argument("--arm", choices=("native", "b0"), required=True)
    live.add_argument("--attempt-id", required=True)

    shutdown = subparsers.add_parser("record-shutdown")
    shutdown.add_argument("--scratch", type=Path, required=True)
    shutdown.add_argument("--arm", choices=("native", "b0"), required=True)
    shutdown.add_argument("--attempt-id", required=True)
    shutdown.add_argument("--original-returncode", type=int, required=True)
    shutdown.add_argument("--cleanup-returncode", type=int, required=True)
    shutdown.add_argument("--contexts-proven", type=_bool_arg, required=True)
    shutdown.add_argument("--keepalive-ready", type=_bool_arg, required=True)
    shutdown.add_argument("--signal-name", default="")

    final = subparsers.add_parser("final")
    final.add_argument("--scratch", type=Path, required=True)
    final.add_argument("--arm", choices=("native", "b0"), required=True)
    final.add_argument("--attempt-id", required=True)

    archive = subparsers.add_parser("archive")
    archive.add_argument("--scratch", type=Path, required=True)
    archive.add_argument("--hdfs-run", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "live":
        output = args.scratch / "live_validation.json"
        try:
            result = validate_live(
                scratch=args.scratch,
                arm=args.arm,
                attempt_id=args.attempt_id,
            )
            _atomic_json(output, result, exclusive=True)
        except BaseException as error:
            _write_cli_failure(
                output,
                arm=args.arm,
                attempt_id=args.attempt_id,
                error=error,
            )
            raise
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
        output = args.scratch / "artifact_validation.json"
        result = finalize_attempt(
            scratch=args.scratch,
            arm=args.arm,
            attempt_id=args.attempt_id,
        )
        _atomic_json(output, result, exclusive=True)
        return 0 if result["status"] == "PASS" else 1
    if args.command == "archive":
        result = archive_attempt(
            scratch=args.scratch, hdfs_run=args.hdfs_run
        )
        return 0 if result["status"] == "PASS" else 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
