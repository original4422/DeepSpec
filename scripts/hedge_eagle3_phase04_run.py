#!/usr/bin/env python3
"""Run a bounded sequential Phase 04 calibration or B+ smoke arm."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_eagle3_phase01b.tools import (
    Eagle3TraceControl,
    SequentialOpenAIRunner,
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


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, value: object) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        )
        stream.flush()


def trace_mode(mode: str) -> str:
    return {"native": "disabled", "B0": "b0", "B+": "enabled"}[mode]


def output_name(mode: str) -> str:
    return {
        "native": "native_calibration_outputs.jsonl",
        "B0": "b0_calibration_outputs.jsonl",
        "B+": "bplus_smoke_outputs.jsonl",
    }[mode]


def build_summary(
    *,
    mode: str,
    records: Sequence[Mapping[str, Any]],
    runner: SequentialOpenAIRunner,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    run = {
        "formal": list(records),
        "formal_wall_seconds": 0.0,
    }
    base = summarize_run(run)
    expected_count = 3 if mode == "B+" else 32
    all_proposal_identity_complete = all(
        row.get("trace_status") == "success"
        and row.get("trace_metadata", {}).get("sample_id")
        for row in records
    )
    return {
        "schema_version": 1,
        "status": (
            "PASS"
            if len(records) == expected_count
            and all(row.get("terminal_status") == "success" for row in records)
            and all_proposal_identity_complete
            and runner.maximum_in_flight == 1
            else "FAIL"
        ),
        "mode": mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": EXPECTED_DATASET_SHA256,
        "sample_count": len(records),
        "maximum_in_flight": runner.maximum_in_flight,
        **{
            key: value
            for key, value in base.items()
            if key
            not in {
                "schema_version",
                "formal_wall_seconds",
                "end_to_end_output_tps",
            }
        },
        "proposal_rows": sum(
            len(row.get("proposal_trace", [])) for row in records
        ),
        "strict_rejection_barriers": sum(
            len(row.get("strict_rejection_barriers", []))
            for row in records
        ),
        "all_proposal_identity_complete": all_proposal_identity_complete,
    }


def build_api_smoke(
    *,
    mode: str,
    model: str,
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    all_nonempty = all(
        isinstance(row.get("response_text"), str)
        and bool(row["response_text"].strip())
        for row in records
    )
    all_ids = all(
        isinstance(row.get("output_token_ids"), list)
        and len(row["output_token_ids"]) == row.get("completion_tokens")
        for row in records
    )
    proposal_complete = summary["all_proposal_identity_complete"] is True
    return {
        "schema_version": 1,
        "status": (
            "PASS"
            if summary["status"] == "PASS"
            and all_nonempty
            and all_ids
            and proposal_complete
            else "FAIL"
        ),
        "mode": mode,
        "model": model,
        "request_count": summary["sample_count"],
        "generation_successes": summary["generation_successes"],
        "trace_successes": summary["trace_successes"],
        "all_nonempty_responses": all_nonempty,
        "all_complete_output_token_ids": all_ids,
        "all_proposal_identity_complete": proposal_complete,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", choices=("native", "B0", "B+"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if sha256(DATASET_MANIFEST) != EXPECTED_DATASET_SHA256:
        raise RuntimeError("fixed dataset manifest hash differs")
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    calibration = manifest.get("calibration")
    if not isinstance(calibration, list) or len(calibration) != 32:
        raise RuntimeError("fixed calibration partition is not exactly 32")
    count = 3 if args.mode == "B+" else 32
    output = args.output_dir / output_name(args.mode)
    common_output = args.output_dir / "request_outputs.jsonl"
    acceptance_output = args.output_dir / "acceptance_trace.jsonl"
    if output.exists() or common_output.exists() or acceptance_output.exists():
        raise RuntimeError("refusing to overwrite Phase 04 arm outputs")
    control = Eagle3TraceControl(
        base_url=args.base_url,
        expected_mode=trace_mode(args.mode),
        timeout_seconds=args.timeout,
    )
    runner = SequentialOpenAIRunner(
        endpoint=f"{args.base_url.rstrip('/')}/v1/chat/completions",
        model=args.model,
        timeout_seconds=args.timeout,
        trace_control=control,
        require_proposal_trace=True,
    )
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    records = []
    for position, sample in enumerate(calibration[:count]):
        record = runner._execute(
            sample,
            phase="calibration" if args.mode != "B+" else "bplus_smoke",
            position=position,
            timed=False,
        )
        records.append(record)
        append_jsonl(output, record)
        append_jsonl(common_output, record)
        for row in record["proposal_trace"]:
            append_jsonl(
                acceptance_output,
                {
                    "mode": args.mode,
                    "position": position,
                    "source_index": record["source_index"],
                    **row,
                },
            )
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
    summary = build_summary(
        mode=args.mode,
        records=records,
        runner=runner,
        started_at=started_at,
        finished_at=finished_at,
    )
    write_json(args.output_dir / "summary.json", summary)
    api_smoke = build_api_smoke(
        mode=args.mode,
        model=args.model,
        records=records,
        summary=summary,
    )
    write_json(args.output_dir / "api_smoke.json", api_smoke)
    if summary["status"] != "PASS" or api_smoke["status"] != "PASS":
        return 1
    if runner.maximum_in_flight != 1:
        raise RuntimeError("Phase 04 runner violated sequentiality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
