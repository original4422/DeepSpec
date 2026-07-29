#!/usr/bin/env python3
"""Reduce P05 native/B0 artifacts into equivalence and one frozen HEDGE config."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.io import (  # noqa: E402
    load_jsonl,
    sha256_file,
    write_json,
    write_jsonl,
)
from deepspec.hedge_spec import HedgeConfig  # noqa: E402
from hedge_dspark_p05_client import _trace_row  # noqa: E402
from hedge_dspark_p05_prepare import (  # noqa: E402
    TRACE_CAPACITY,
    validate_calibration_dataset,
)


def linear_q25(sorted_values: Sequence[float]) -> float:
    """Return the plan §4.4 linear 25th percentile of sorted positive values."""

    if not sorted_values:
        raise ValueError("positive first-rejection ratio distribution is empty")
    previous = -math.inf
    for index, value in enumerate(sorted_values):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0
            or float(value) < previous
        ):
            raise ValueError(
                f"q25 input at position {index} is not sorted positive finite"
            )
        previous = float(value)
    h = (len(sorted_values) - 1) * 0.25
    lower = math.floor(h)
    upper = math.ceil(h)
    if lower == upper:
        return float(sorted_values[lower])
    return (
        float(sorted_values[lower]) * (upper - h)
        + float(sorted_values[upper]) * (h - lower)
    )


def _validate_outputs(
    path: Path, *, expected_indices: Sequence[int], arm: str
) -> list[dict[str, Any]]:
    records = load_jsonl(path)
    if len(records) != 32:
        raise ValueError(f"{arm} output must contain exactly 32 records")
    for position, (record, dataset_index) in enumerate(
        zip(records, expected_indices)
    ):
        token_ids = record.get("output_token_ids")
        if (
            record.get("cohort") != "calibration"
            or record.get("cohort_position") != position
            or record.get("dataset_index") != dataset_index
            or record.get("terminal_status") != "succeeded"
            or not isinstance(token_ids, list)
            or not token_ids
            or any(
                isinstance(token, bool)
                or not isinstance(token, int)
                or token < 0
                for token in token_ids
            )
        ):
            raise ValueError(
                f"{arm} output record {position} lacks frozen identity/full token IDs"
            )
    return records


def _compare_token_ids(
    native: Sequence[Mapping[str, Any]],
    b0: Sequence[Mapping[str, Any]],
    *,
    native_sha256: str,
    b0_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    mismatches: list[int] = []
    first_counterexample: dict[str, Any] | None = None
    for position, (native_record, b0_record) in enumerate(zip(native, b0)):
        native_ids = list(native_record["output_token_ids"])
        b0_ids = list(b0_record["output_token_ids"])
        if native_ids == b0_ids:
            continue
        mismatches.append(position)
        if first_counterexample is None:
            first_difference = next(
                (
                    index
                    for index, (native_token, b0_token) in enumerate(
                        zip(native_ids, b0_ids)
                    )
                    if native_token != b0_token
                ),
                min(len(native_ids), len(b0_ids)),
            )
            first_counterexample = {
                "schema_version": 1,
                "authorized_phase": "P05",
                "cohort_position": position,
                "dataset_index": native_record["dataset_index"],
                "first_differing_token_position": first_difference,
                "native_token_id": (
                    native_ids[first_difference]
                    if first_difference < len(native_ids)
                    else None
                ),
                "b0_token_id": (
                    b0_ids[first_difference]
                    if first_difference < len(b0_ids)
                    else None
                ),
                "native_output_token_ids": native_ids,
                "b0_output_token_ids": b0_ids,
            }
    equivalent = len(native) - len(mismatches)
    return (
        {
            "schema_version": 1,
            "authorized_phase": "P05",
            "status": "PASS" if not mismatches else "FAILED",
            "b0_status": "PASS" if not mismatches else "FAILED",
            "comparison": "complete output_token_ids lists, no re-tokenization",
            "sample_count": len(native),
            "full_token_id_lists_equal": equivalent,
            "mismatch_count": len(mismatches),
            "mismatch_cohort_positions": mismatches,
            "first_mismatch_cohort_position": (
                None if not mismatches else mismatches[0]
            ),
            "native_outputs_sha256": native_sha256,
            "b0_outputs_sha256": b0_sha256,
        },
        first_counterexample,
    )


def _positive_trace_values(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("trace record must be an object")
        snapshot_index = record.get("snapshot_index")
        if (
            isinstance(snapshot_index, bool)
            or not isinstance(snapshot_index, int)
            or snapshot_index < 0
        ):
            raise ValueError("trace snapshot_index must be non-negative")
        candidate = dict(record)
        candidate.pop("snapshot_index")
        ratio = candidate.get("regret_per_value")
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(float(ratio))
            or float(ratio) <= 0
        ):
            continue
        normalized = _trace_row(
            candidate, snapshot_index=snapshot_index
        )
        selected.append(normalized)
    selected.sort(
        key=lambda row: (
            row["regret_per_value"],
            row["snapshot_index"],
            row["proposal_ordinal"],
        )
    )
    return [
        {"sorted_ordinal": ordinal, **record}
        for ordinal, record in enumerate(selected)
    ]


def reduce_calibration(
    *,
    native_outputs: Path,
    b0_outputs: Path,
    native_trace: Path,
    native_counters: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create all deterministic P05 reducer outputs without model access."""

    dataset = validate_calibration_dataset()
    expected_indices = dataset["dataset_indices"]
    native_sha256 = sha256_file(native_outputs)
    b0_sha256 = sha256_file(b0_outputs)
    native = _validate_outputs(
        native_outputs, expected_indices=expected_indices, arm="native"
    )
    b0 = _validate_outputs(
        b0_outputs, expected_indices=expected_indices, arm="b0"
    )
    equivalence, counterexample = _compare_token_ids(
        native,
        b0,
        native_sha256=native_sha256,
        b0_sha256=b0_sha256,
    )

    counters = json.loads(native_counters.read_text(encoding="utf-8"))
    trace_records = load_jsonl(native_trace)
    if (
        not isinstance(counters, Mapping)
        or counters.get("status") != "PASS"
        or counters.get("arm") != "native-trace"
        or counters.get("trace_capacity") != TRACE_CAPACITY
        or counters.get("trace_rows_dropped") != 0
        or counters.get("native_acceptance_preserved") is not True
        or counters.get("trace_rows_stored") != len(trace_records)
        or not isinstance(counters.get("trace_rows_seen"), int)
        or not 0 < counters["trace_rows_seen"] <= TRACE_CAPACITY
    ):
        raise ValueError("native trace counters do not prove capacity/dropped=0")
    values = _positive_trace_values(trace_records)
    if not values:
        raise ValueError("positive first-rejection ratio distribution is empty")
    ratios = [record["regret_per_value"] for record in values]
    q25 = linear_q25(ratios)
    config = HedgeConfig(
        risk_budget=q25,
        max_regret_per_value=q25,
        max_relaxed_mismatches_per_block=1,
        value_scheme="normalized_suffix",
        block_size=5,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    equivalence_path = output_dir / "b0_equivalence.json"
    values_path = output_dir / "calibration_values.jsonl"
    config_path = output_dir / "hedge_config.json"
    write_json(equivalence_path, equivalence, immutable=True)
    if counterexample is not None:
        write_json(
            output_dir / "first_minimal_counterexample.json",
            counterexample,
            immutable=True,
        )
    write_jsonl(values_path, values, immutable=True)
    write_json(config_path, config.to_mapping(), immutable=True)
    summary = {
        "schema_version": 1,
        "authorized_phase": "P05",
        "status": "PASS",
        "b0_status": equivalence["b0_status"],
        "positive_value_count": len(values),
        "q25_method": "linear interpolation with h=(n-1)*0.25",
        "q25": q25,
        "g": q25,
        "B": q25,
        "m": 1,
        "value_scheme": "normalized_suffix",
        "block_size": 5,
        "config": config.to_mapping(),
        "config_fingerprint": config.fingerprint(),
        "trace_capacity": TRACE_CAPACITY,
        "trace_rows_seen": counters["trace_rows_seen"],
        "trace_rows_stored": len(trace_records),
        "trace_rows_dropped": 0,
        "native_acceptance_preserved": True,
        "source_artifacts": {
            "native_outputs_sha256": native_sha256,
            "b0_outputs_sha256": b0_sha256,
            "native_trace_sha256": sha256_file(native_trace),
            "native_counters_sha256": sha256_file(native_counters),
            "b0_equivalence_sha256": sha256_file(equivalence_path),
            "calibration_values_sha256": sha256_file(values_path),
            "hedge_config_sha256": sha256_file(config_path),
        },
    }
    write_json(
        output_dir / "calibration_summary.json",
        summary,
        immutable=True,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-outputs", type=Path, required=True)
    parser.add_argument("--b0-outputs", type=Path, required=True)
    parser.add_argument("--native-trace", type=Path, required=True)
    parser.add_argument("--native-counters", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = reduce_calibration(
        native_outputs=args.native_outputs,
        b0_outputs=args.b0_outputs,
        native_trace=args.native_trace,
        native_counters=args.native_counters,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
