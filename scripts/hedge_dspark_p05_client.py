#!/usr/bin/env python3
"""Run one exact 32-request P05 calibration arm and seal its live snapshot."""

from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.config import DEFAULT_MODEL  # noqa: E402
from deepspec.hedge_protocol.io import (  # noqa: E402
    load_jsonl,
    sha256_file,
    write_json,
    write_jsonl,
)
from deepspec.hedge_protocol.runner import ProtocolRunner  # noqa: E402
from deepspec.hedge_protocol.summary import recompute_summary  # noqa: E402
from hedge_dspark_p04_client import (  # noqa: E402
    B0_CONFIG,
    SERVER_FIELDS,
    _NoProxyJsonGet,
    wait_ready,
)
from hedge_dspark_p05_prepare import (  # noqa: E402
    CALIBRATION_SHA256,
    TRACE_CAPACITY,
    validate_calibration_dataset,
)


ARMS = ("native-trace", "b0")
JsonGet = Callable[[str, float], Mapping[str, Any]]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _trace_row(
    row: Mapping[str, Any], *, snapshot_index: int
) -> dict[str, Any]:
    required = {
        "proposal_ordinal",
        "request_serial",
        "rid",
        "request_pool_slot",
        "forward_ct",
        "barrier_position",
        "regret",
        "value",
        "regret_per_value",
    }
    if set(row) != required:
        raise ValueError(
            "strict rejection trace fields mismatch: "
            f"expected={sorted(required)} observed={sorted(row)}"
        )
    normalized = {
        "snapshot_index": snapshot_index,
        "proposal_ordinal": _nonnegative_int(
            row["proposal_ordinal"], field="proposal_ordinal"
        ),
        "request_serial": _nonnegative_int(
            row["request_serial"], field="request_serial"
        ),
        "rid": row["rid"],
        "request_pool_slot": _nonnegative_int(
            row["request_pool_slot"], field="request_pool_slot"
        ),
        "forward_ct": _nonnegative_int(
            row["forward_ct"], field="forward_ct"
        ),
        "barrier_position": _nonnegative_int(
            row["barrier_position"], field="barrier_position"
        ),
    }
    if normalized["request_serial"] <= 0:
        raise ValueError("trace request_serial must be positive")
    if not isinstance(normalized["rid"], str) or not normalized["rid"]:
        raise ValueError("trace rid must be a non-empty string")
    if normalized["barrier_position"] >= 5:
        raise ValueError("trace barrier_position must be in DSpark width 5")
    regret = row["regret"]
    value = row["value"]
    ratio = row["regret_per_value"]
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in (regret, value, ratio)
    ):
        raise ValueError("trace regret/value/ratio must be numeric")
    regret_float = float(regret)
    value_float = float(value)
    ratio_float = float(ratio)
    expected_value = (5 - normalized["barrier_position"]) / 5
    if (
        not math.isfinite(regret_float)
        or not math.isfinite(value_float)
        or not math.isfinite(ratio_float)
        or regret_float <= 0
        or value_float <= 0
        or ratio_float <= 0
        or not math.isclose(value_float, expected_value, rel_tol=0, abs_tol=1e-6)
        or not math.isclose(
            ratio_float,
            regret_float / value_float,
            rel_tol=1e-6,
            abs_tol=1e-7,
        )
    ):
        raise ValueError("trace regret/value/ratio is not a positive finite ratio")
    normalized.update(
        regret=regret_float,
        value=value_float,
        regret_per_value=ratio_float,
    )
    return normalized


def validate_server_snapshot(
    server_info: Mapping[str, Any], *, arm: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate the post-cohort DSpark snapshot and extract trace rows."""

    if arm not in ARMS:
        raise ValueError("arm must be exactly native-trace or b0")
    mismatches = {
        key: {"expected": expected, "observed": server_info.get(key)}
        for key, expected in SERVER_FIELDS.items()
        if server_info.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"/server_info decode config mismatch: {mismatches}")
    internal_states = server_info.get("internal_states")
    if not isinstance(internal_states, list) or not internal_states:
        raise ValueError("/server_info internal_states must be non-empty")
    snapshots: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    trace_seen = 0
    trace_dropped = 0
    proposals = 0
    expected_mode = "calibration" if arm == "native-trace" else "enabled"
    expected_switches = {
        "HEDGE_ENABLED": 0 if arm == "native-trace" else 1,
        "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": (
            1 if arm == "native-trace" else 0
        ),
    }
    expected_config = None if arm == "native-trace" else dict(B0_CONFIG)
    for snapshot_index, state in enumerate(internal_states):
        if not isinstance(state, Mapping):
            raise ValueError(f"internal_states[{snapshot_index}] is not an object")
        info_record = state.get("dspark_info_record")
        snapshot = (
            info_record.get("hedge")
            if isinstance(info_record, Mapping)
            else None
        )
        if not isinstance(snapshot, Mapping):
            raise ValueError(
                f"internal_states[{snapshot_index}] has no HEDGE snapshot"
            )
        normalized = dict(snapshot)
        if (
            normalized.get("mode") != expected_mode
            or normalized.get("experiment_switches") != expected_switches
            or normalized.get("config") != expected_config
            or normalized.get("gamma") != 5
            or normalized.get("verify_num_draft_tokens") != 6
        ):
            raise ValueError(f"HEDGE snapshot {snapshot_index} identity mismatch")
        if (
            normalized.get("state_leaks") != 0
            or normalized.get("active_request_states") != 0
        ):
            raise ValueError(f"HEDGE snapshot {snapshot_index} leaks request state")
        snapshot_proposals = _nonnegative_int(
            normalized.get("proposals"), field="proposals"
        )
        snapshot_seen = _nonnegative_int(
            normalized.get("trace_rows_seen"), field="trace_rows_seen"
        )
        snapshot_dropped = _nonnegative_int(
            normalized.get("trace_rows_dropped"), field="trace_rows_dropped"
        )
        raw_trace = normalized.get("strict_rejection_trace")
        if not isinstance(raw_trace, list):
            raise ValueError("strict_rejection_trace must be an array")
        if len(raw_trace) > snapshot_seen:
            raise ValueError("stored trace rows exceed trace_rows_seen")
        proposals += snapshot_proposals
        trace_seen += snapshot_seen
        trace_dropped += snapshot_dropped
        trace_rows.extend(
            _trace_row(row, snapshot_index=snapshot_index)
            for row in raw_trace
            if isinstance(row, Mapping)
        )
        if len(trace_rows) < sum(
            len(item.get("strict_rejection_trace", []))
            for item in snapshots
        ) + len(raw_trace):
            raise ValueError("strict_rejection_trace contains a non-object row")
        if arm == "b0":
            if (
                normalized.get("relaxed_mismatches") != 0
                or float(normalized.get("regret_charged", -1)) != 0.0
                or normalized.get("hedge_accepted_draft_tokens")
                != normalized.get("strict_accepted_draft_tokens")
                or snapshot_dropped != 0
                or snapshot_seen != 0
                or raw_trace
            ):
                raise ValueError("B0 snapshot does not prove strict zero-budget behavior")
        snapshots.append(normalized)
    if arm == "native-trace":
        if trace_dropped != 0:
            raise ValueError("native calibration trace dropped rows")
        if trace_seen <= 0 or trace_seen > TRACE_CAPACITY:
            raise ValueError("native calibration trace capacity/coverage is invalid")
        if not trace_rows:
            raise ValueError("native calibration has no positive strict rejection")
    elif proposals <= 0:
        raise ValueError("B0 snapshot does not prove HEDGE verifier execution")
    counters = {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "arm": arm,
        "source_endpoint": "/server_info",
        "server_config": {key: server_info[key] for key in SERVER_FIELDS},
        "hedge_snapshots": snapshots,
        "proposal_count": proposals,
        "trace_capacity": TRACE_CAPACITY if arm == "native-trace" else None,
        "trace_rows_seen": trace_seen,
        "trace_rows_stored": len(trace_rows),
        "trace_rows_dropped": trace_dropped,
        "native_acceptance_preserved": arm == "native-trace",
    }
    return counters, trace_rows


def run_calibration_arm(
    *,
    arm: str,
    base_url: str,
    dataset: Path,
    outputs_path: Path,
    summary_path: Path,
    counters_path: Path,
    trace_path: Path,
    transport: Callable[[str, dict[str, Any], float], Mapping[str, Any]]
    | None = None,
    server_info_get: JsonGet | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run the frozen cohort once, then seal the arm-level server snapshot."""

    if arm not in ARMS:
        raise ValueError("arm must be exactly native-trace or b0")
    dataset_identity = validate_calibration_dataset()
    if dataset.resolve() != Path(dataset_identity["calibration_jsonl"]).resolve():
        raise ValueError("P05 must use the immutable P01 calibration JSONL")
    if sha256_file(dataset) != CALIBRATION_SHA256:
        raise ValueError("P05 calibration dataset bytes changed")
    samples = load_jsonl(dataset)
    runner = ProtocolRunner(
        base_url=base_url,
        model=DEFAULT_MODEL,
        transport=transport,
        sleeper=sleeper,
    )
    started_at = _utc_now()
    records = runner.run_cohort(
        samples,
        cohort="calibration",
        output_path=outputs_path,
        expected_count=32,
    )
    summary = recompute_summary(
        records,
        expected_count=32,
        expected_cohort="calibration",
    )
    terminal_counts = {
        "succeeded": summary["success_requests"],
        "failed": summary["failed_requests"],
    }
    if terminal_counts != {"succeeded": 32, "failed": 0}:
        raise ValueError(
            "P05 requires all 32 requests to preserve complete output token IDs"
        )
    getter = server_info_get or _NoProxyJsonGet()
    server_info = getter(
        base_url.rstrip("/") + "/server_info",
        300.0,
    )
    counters, trace_rows = validate_server_snapshot(server_info, arm=arm)
    write_jsonl(trace_path, trace_rows, immutable=True)
    counters["fetched_at_utc"] = _utc_now()
    write_json(counters_path, counters, immutable=True)
    result = {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "arm": arm,
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "sample_count": 32,
        "terminal_counts": terminal_counts,
        "attempts_total": summary["attempts_total"],
        "retry_attempts": summary["retry_attempts"],
        "completion_tokens": summary["completion_tokens"],
        "dataset_indices": [record["dataset_index"] for record in records],
        "outputs_sha256": sha256_file(outputs_path),
        "trace_sha256": sha256_file(trace_path),
        "trace_rows_seen": counters["trace_rows_seen"],
        "trace_rows_stored": counters["trace_rows_stored"],
        "trace_rows_dropped": counters["trace_rows_dropped"],
    }
    write_json(summary_path, result, immutable=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    ready = subparsers.add_parser("wait-ready")
    ready.add_argument("--base-url", required=True)
    ready.add_argument("--server-pid", type=int, required=True)
    ready.add_argument("--server-start-ticks", required=True)
    ready.add_argument("--timeout", type=float, default=3600)
    ready.add_argument("--output", type=Path, required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--outputs", type=Path, required=True)
    run.add_argument("--summary", type=Path, required=True)
    run.add_argument("--counters", type=Path, required=True)
    run.add_argument("--trace", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "wait-ready":
        result = wait_ready(
            base_url=args.base_url,
            server_pid=args.server_pid,
            server_start_ticks=args.server_start_ticks,
            timeout_seconds=args.timeout,
        )
        write_json(args.output, result, immutable=True)
        return 0 if result["status"] == "ready" else 1
    if args.command == "run":
        try:
            result = run_calibration_arm(
                arm=args.arm,
                base_url=args.base_url,
                dataset=args.dataset,
                outputs_path=args.outputs,
                summary_path=args.summary,
                counters_path=args.counters,
                trace_path=args.trace,
            )
        except BaseException as error:
            failure = {
                "schema_version": 1,
                "authorized_phase": "P05",
                "status": "FAIL",
                "arm": args.arm,
                "error_type": type(error).__name__,
                "error": str(error),
            }
            if not args.summary.exists():
                write_json(args.summary, failure, immutable=True)
            raise
        return 0 if result["status"] == "PASS" else 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
