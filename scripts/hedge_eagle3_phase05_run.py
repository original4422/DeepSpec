#!/usr/bin/env python3
"""Run and persist the one allowed Phase 05 native formal cohort."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from deepspec.hedge_eagle3_phase01b.tools import (
    DRAFT_REVISION,
    TARGET_REVISION,
    Eagle3TraceControl,
    SequentialOpenAIRunner,
    formal_timing_bounds,
    summarize_run,
)


DATASET_MANIFEST = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12/"
    "gsm8k_split_manifest.json"
)
EXPECTED_DATASET_SHA256 = (
    "5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5"
)
CALIBRATION = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T052000Z-phase-04-calibration-01/calibration.json"
)
EXPECTED_CALIBRATION_SHA256 = (
    "9af2cff0cc176ef16c7552c54817b2cfb66f5224463ac15730e6eae04a837474"
)
SOURCE_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
ACCEPTED_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-native-formal.complete.json"
)
OUTPUT_NAMES = (
    "warmup_outputs.jsonl",
    "request_outputs.jsonl",
    "acceptance_trace.jsonl",
    "summary.json",
    "formal_result.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_available(output_dir: Path, accepted_marker: Path) -> None:
    if accepted_marker.exists():
        raise RuntimeError("an accepted native formal result already exists")
    collisions = [name for name in OUTPUT_NAMES if (output_dir / name).exists()]
    if collisions:
        raise RuntimeError(f"refusing to overwrite formal output: {collisions}")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    calibration = manifest.get("calibration")
    formal = manifest.get("formal")
    if not isinstance(calibration, list) or len(calibration) != 32:
        raise RuntimeError("calibration cohort is not exactly 32")
    if not isinstance(formal, list) or len(formal) != 500:
        raise RuntimeError("formal cohort is not exactly 500")
    calibration_ids = [row.get("source_index") for row in calibration]
    formal_ids = [row.get("source_index") for row in formal]
    if (
        len(set(calibration_ids)) != 32
        or len(set(formal_ids)) != 500
        or set(calibration_ids) & set(formal_ids)
    ):
        raise RuntimeError("fixed calibration/formal cohorts are not disjoint")


def write_jsonl_exclusive(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_json_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def acceptance_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    proposals = [
        proposal
        for record in records
        for proposal in record.get("proposal_trace", [])
    ]
    accepted = [int(row["hedge_accepted_drafts"]) for row in proposals]
    lengths = [int(row["commit_length"]) for row in proposals]
    if any(not 0 <= value <= 3 for value in accepted):
        raise RuntimeError("native proposal accepted-draft count is invalid")
    if any(length != value + 1 for length, value in zip(lengths, accepted)):
        raise RuntimeError("native proposal commit length is inconsistent")
    count = len(proposals)
    return {
        "proposal_count": count,
        "accepted_draft_tokens": sum(accepted),
        "accepted_draft_tokens_per_proposal": (
            sum(accepted) / count if count else None
        ),
        "mean_accept_length": sum(lengths) / count if count else None,
        "accepted_draft_distribution": {
            str(key): value for key, value in sorted(Counter(accepted).items())
        },
        "acceptance_length_distribution": {
            str(key): value for key, value in sorted(Counter(lengths).items())
        },
        "accepted_by_position": [
            {
                "position": position,
                "accepted": sum(value > position for value in accepted),
                "rate": (
                    sum(value > position for value in accepted) / count
                    if count
                    else None
                ),
            }
            for position in range(3)
        ],
    }


def run_and_write(
    *,
    manifest: Mapping[str, Any],
    runner: Any,
    output_dir: Path,
    dataset_sha256: str,
    accepted_marker: Path = ACCEPTED_MARKER,
) -> dict[str, Any]:
    assert_available(output_dir, accepted_marker)
    validate_manifest(manifest)
    protocol_run = runner.run(manifest, warmup_count=10)
    warmup = protocol_run.get("warmup")
    formal = protocol_run.get("formal")
    if not isinstance(warmup, list) or len(warmup) != 10:
        raise RuntimeError("native formal run did not preserve 10 warmups")
    if not isinstance(formal, list) or len(formal) != 500:
        raise RuntimeError("native formal run did not reach 500 terminal rows")
    if protocol_run.get("maximum_in_flight") != 1:
        raise RuntimeError("native formal run was not strictly sequential")
    for position, (sample, row) in enumerate(zip(manifest["formal"], formal)):
        if (
            row.get("position") != position
            or row.get("timed") is not True
            or row.get("source_index") != sample.get("source_index")
            or row.get("terminal_status") not in {"success", "failure"}
        ):
            raise RuntimeError("formal row order/timing/terminal identity differs")
    started, finished = formal_timing_bounds(formal)
    wall = finished - started
    if not math.isclose(
        wall,
        float(protocol_run.get("formal_wall_seconds")),
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("formal wall time is not recomputable from boundaries")
    base = summarize_run({**protocol_run, "formal_wall_seconds": wall})
    traces = [
        {
            "formal_position": position,
            "source_index": row.get("source_index"),
            **proposal,
        }
        for position, row in enumerate(formal)
        for proposal in row.get("proposal_trace", [])
    ]
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    summary = {
        "schema_version": 1,
        "status": "PASS",
        "mode": "native",
        "source_sha": SOURCE_SHA,
        "target_revision": TARGET_REVISION,
        "draft_revision": DRAFT_REVISION,
        "worker_id": "4099544",
        "gpu_count": 8,
        "tp_size": 8,
        "proposal_tokens": 3,
        "internal_verify_width": 4,
        "hedge_B": None,
        "hedge_m": None,
        "b0_status": calibration["b0_status"].removeprefix("B0_"),
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": dataset_sha256,
        "calibration_artifact": str(CALIBRATION),
        "calibration_artifact_sha256": EXPECTED_CALIBRATION_SHA256,
        "warmup": len(warmup),
        "total": len(formal),
        "success": base["successes"],
        "failed": base["failures"],
        "retries": base["retries"],
        "trace_retries": base["trace_retries"],
        "parse_failures": base["parse_failures"],
        "matches": base["matches"],
        "match_rate": base["match_rate"],
        "completion_tokens": base["completion_tokens"],
        "formal_monotonic_started": started,
        "formal_monotonic_finished": finished,
        "timed_seconds": wall,
        "output_tps": base["end_to_end_output_tps"],
        "maximum_in_flight": protocol_run["maximum_in_flight"],
        **acceptance_summary(formal),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl_exclusive(output_dir / "warmup_outputs.jsonl", warmup)
    write_jsonl_exclusive(output_dir / "request_outputs.jsonl", formal)
    write_jsonl_exclusive(output_dir / "acceptance_trace.jsonl", traces)
    write_json_exclusive(output_dir / "summary.json", summary)
    write_json_exclusive(
        output_dir / "formal_result.json",
        {
            "schema_version": 1,
            "status": "PASS",
            "mode": "native",
            "formal_terminal": 500,
            "summary_sha256": sha256(output_dir / "summary.json"),
        },
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if sha256(DATASET_MANIFEST) != EXPECTED_DATASET_SHA256:
        raise RuntimeError("fixed dataset manifest hash differs")
    if sha256(CALIBRATION) != EXPECTED_CALIBRATION_SHA256:
        raise RuntimeError("frozen Phase 04 calibration hash differs")
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    control = Eagle3TraceControl(
        base_url=args.base_url,
        expected_mode="disabled",
        timeout_seconds=args.timeout,
    )
    runner = SequentialOpenAIRunner(
        endpoint=f"{args.base_url.rstrip('/')}/v1/chat/completions",
        model=args.model,
        timeout_seconds=args.timeout,
        trace_control=control,
        require_proposal_trace=True,
    )
    run_and_write(
        manifest=manifest,
        runner=runner,
        output_dir=args.output_dir,
        dataset_sha256=EXPECTED_DATASET_SHA256,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
