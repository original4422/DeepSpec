#!/usr/bin/env python3
"""Run and persist the one allowed Phase 06 HEDGE B+ formal cohort."""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_eagle3_phase01b.tools import (
    DRAFT_REVISION,
    TARGET_REVISION,
    Eagle3TraceControl,
    SequentialOpenAIRunner,
    formal_timing_bounds,
    summarize_run,
)


PHASE05_PATH = REPO_ROOT / "scripts/hedge_eagle3_phase05_run.py"
SPEC = importlib.util.spec_from_file_location(
    "hedge_eagle3_phase05_run", PHASE05_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen Phase 05 formal runner")
phase05 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase05)

DATASET_MANIFEST = phase05.DATASET_MANIFEST
EXPECTED_DATASET_SHA256 = phase05.EXPECTED_DATASET_SHA256
CALIBRATION = phase05.CALIBRATION
EXPECTED_CALIBRATION_SHA256 = phase05.EXPECTED_CALIBRATION_SHA256
EXPECTED_FROZEN_CALIBRATION_SHA256 = (
    "836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60"
)
EXPECTED_BPLUS_CONFIG_SHA256 = (
    "87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a"
)
SOURCE_SHA = phase05.SOURCE_SHA
GATE = 6.75
RISK_BUDGET = 6.75
MAX_RELAXED_MISMATCHES = 1
VALUE_SCHEME = "normalized_suffix"
ACCEPTED_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-bplus-formal.complete.json"
)
OUTPUT_NAMES = phase05.OUTPUT_NAMES


def budget_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate per-request persistent budgets and return recomputable totals."""
    violations: list[dict[str, Any]] = []
    request_rows: list[dict[str, Any]] = []
    unchecked_failures: list[int] = []
    proposal_count = 0
    relaxed_proposals = 0
    relaxed_mismatches = 0
    extra_accepted_drafts = 0
    for position, record in enumerate(records):
        if record.get("terminal_status") != "success":
            unchecked_failures.append(position)
            continue
        proposals = record.get("proposal_trace")
        if not isinstance(proposals, list) or not proposals:
            violations.append(
                {"formal_position": position, "reason": "missing proposal trace"}
            )
            continue
        total_spent = 0.0
        previous_after = RISK_BUDGET
        request_relaxed = 0
        request_extra = 0
        for proposal_position, row in enumerate(proposals):
            proposal_count += 1
            context = {
                "formal_position": position,
                "proposal_position": proposal_position,
                "proposal_id": row.get("proposal_id"),
            }
            try:
                before = float(row["remaining_before"])
                after = float(row["remaining_after"])
                spent = float(row["spent"])
                relaxed = int(row["relaxed_mismatches"])
                strict = int(row["strict_accepted_drafts"])
                accepted = int(row["hedge_accepted_drafts"])
            except (KeyError, TypeError, ValueError) as error:
                violations.append(
                    {**context, "reason": f"invalid budget fields: {error}"}
                )
                continue
            if (
                row.get("mode") != "enabled"
                or not all(math.isfinite(value) for value in (before, after, spent))
            ):
                violations.append(
                    {**context, "reason": "mode or finite-number invariant"}
                )
            if before < -1e-9 or after < -1e-9 or spent < -1e-9:
                violations.append(
                    {**context, "reason": "negative budget accounting"}
                )
            if not math.isclose(before, previous_after, rel_tol=0, abs_tol=1e-9):
                violations.append(
                    {
                        **context,
                        "reason": "budget continuity",
                        "expected_before": previous_after,
                        "observed_before": before,
                    }
                )
            if not math.isclose(after, before - spent, rel_tol=0, abs_tol=1e-9):
                violations.append(
                    {
                        **context,
                        "reason": "budget accounting",
                        "before": before,
                        "spent": spent,
                        "after": after,
                    }
                )
            if relaxed not in range(MAX_RELAXED_MISMATCHES + 1):
                violations.append(
                    {**context, "reason": "m exceeds one", "observed": relaxed}
                )
            if accepted < strict or accepted > 3 or strict < 0:
                violations.append(
                    {**context, "reason": "accepted/strict ordering"}
                )
            if relaxed == 0 and not math.isclose(spent, 0.0, abs_tol=1e-9):
                violations.append(
                    {**context, "reason": "strict proposal spent budget"}
                )
            previous_after = after
            total_spent += spent
            request_relaxed += relaxed
            request_extra += accepted - strict
            relaxed_proposals += int(relaxed > 0)
            relaxed_mismatches += relaxed
            extra_accepted_drafts += accepted - strict
        if not math.isclose(
            previous_after,
            RISK_BUDGET - total_spent,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            violations.append(
                {
                    "formal_position": position,
                    "reason": "request total accounting",
                    "total_spent": total_spent,
                    "remaining": previous_after,
                }
            )
        request_rows.append(
            {
                "formal_position": position,
                "source_index": record.get("source_index"),
                "proposal_count": len(proposals),
                "spent": total_spent,
                "remaining": previous_after,
                "relaxed_mismatches": request_relaxed,
                "extra_accepted_drafts": request_extra,
            }
        )
    return {
        "budget_invariants_status": "PASS" if not violations else "FAIL",
        "budget_invariant_violations": violations,
        "budget_requests_checked": len(request_rows),
        "budget_requests_unchecked_due_failure": len(unchecked_failures),
        "budget_unchecked_formal_positions": unchecked_failures,
        "budget_request_rows": request_rows,
        "budget_total_spent": sum(row["spent"] for row in request_rows),
        "budget_request_spent_distribution": {
            str(key): value
            for key, value in sorted(
                Counter(row["spent"] for row in request_rows).items()
            )
        },
        "budget_final_remaining_distribution": {
            str(key): value
            for key, value in sorted(
                Counter(row["remaining"] for row in request_rows).items()
            )
        },
        "relaxed_proposal_count": relaxed_proposals,
        "relaxed_mismatch_count": relaxed_mismatches,
        "extra_accepted_draft_tokens": extra_accepted_drafts,
        "proposal_count_checked": proposal_count,
    }


def run_and_write(
    *,
    manifest: Mapping[str, Any],
    runner: Any,
    output_dir: Path,
    dataset_sha256: str,
    accepted_marker: Path = ACCEPTED_MARKER,
) -> dict[str, Any]:
    phase05.assert_available(output_dir, accepted_marker)
    phase05.validate_manifest(manifest)
    protocol_run = runner.run(manifest, warmup_count=10)
    warmup = protocol_run.get("warmup")
    formal = protocol_run.get("formal")
    if not isinstance(warmup, list) or len(warmup) != 10:
        raise RuntimeError("B+ formal run did not preserve 10 warmups")
    if not isinstance(formal, list) or len(formal) != 500:
        raise RuntimeError("B+ formal run did not reach 500 terminal rows")
    if protocol_run.get("maximum_in_flight") != 1:
        raise RuntimeError("B+ formal run was not strictly sequential")
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
    budget = budget_summary(formal)
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
    if (
        calibration.get("frozen_calibration_sha256")
        != EXPECTED_FROZEN_CALIBRATION_SHA256
        or calibration.get("formal_bplus_config_sha256")
        != EXPECTED_BPLUS_CONFIG_SHA256
    ):
        raise RuntimeError("calibration or B+ config identity differs")
    status = (
        "PASS"
        if budget["budget_invariants_status"] == "PASS"
        and budget["budget_requests_checked"] == base["successes"]
        and len(formal) == 500
        else "FAIL"
    )
    summary = {
        "schema_version": 1,
        "status": status,
        "mode": "B+",
        "source_sha": SOURCE_SHA,
        "target_revision": TARGET_REVISION,
        "draft_revision": DRAFT_REVISION,
        "worker_id": "4099544",
        "gpu_count": 8,
        "tp_size": 8,
        "proposal_tokens": 3,
        "internal_verify_width": 4,
        "hedge_B": RISK_BUDGET,
        "hedge_g": GATE,
        "hedge_m": MAX_RELAXED_MISMATCHES,
        "value_scheme": VALUE_SCHEME,
        "b0_status": calibration["b0_status"].removeprefix("B0_"),
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": dataset_sha256,
        "calibration_artifact": str(CALIBRATION),
        "calibration_artifact_sha256": EXPECTED_CALIBRATION_SHA256,
        "frozen_calibration_sha256": EXPECTED_FROZEN_CALIBRATION_SHA256,
        "formal_bplus_config_sha256": EXPECTED_BPLUS_CONFIG_SHA256,
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
        **phase05.acceptance_summary(formal),
        **budget,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    phase05.write_jsonl_exclusive(output_dir / "warmup_outputs.jsonl", warmup)
    phase05.write_jsonl_exclusive(output_dir / "request_outputs.jsonl", formal)
    phase05.write_jsonl_exclusive(output_dir / "acceptance_trace.jsonl", traces)
    phase05.write_json_exclusive(output_dir / "summary.json", summary)
    phase05.write_json_exclusive(
        output_dir / "formal_result.json",
        {
            "schema_version": 1,
            "status": status,
            "mode": "B+",
            "formal_terminal": 500,
            "summary_sha256": phase05.sha256(output_dir / "summary.json"),
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
    if phase05.sha256(DATASET_MANIFEST) != EXPECTED_DATASET_SHA256:
        raise RuntimeError("fixed dataset manifest hash differs")
    if phase05.sha256(CALIBRATION) != EXPECTED_CALIBRATION_SHA256:
        raise RuntimeError("frozen Phase 04 calibration hash differs")
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    control = Eagle3TraceControl(
        base_url=args.base_url,
        expected_mode="enabled",
        timeout_seconds=args.timeout,
    )
    runner = SequentialOpenAIRunner(
        endpoint=f"{args.base_url.rstrip('/')}/v1/chat/completions",
        model=args.model,
        timeout_seconds=args.timeout,
        trace_control=control,
        require_proposal_trace=True,
    )
    summary = run_and_write(
        manifest=manifest,
        runner=runner,
        output_dir=args.output_dir,
        dataset_sha256=EXPECTED_DATASET_SHA256,
    )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
