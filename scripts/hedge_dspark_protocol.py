#!/usr/bin/env python3
"""CLI for the frozen HEDGE × DSpark GSM8K protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from deepspec.hedge_protocol.config import fingerprint_document
from deepspec.hedge_protocol.dataset import (
    acquire_and_materialize,
    verify_materialized_dataset,
)
from deepspec.hedge_protocol.io import load_jsonl, sha256_file, write_json
from deepspec.hedge_protocol.runner import ProtocolRunner, run_formal_from_files
from deepspec.hedge_protocol.summary import recompute_summary


def _runner(args: argparse.Namespace) -> ProtocolRunner:
    return ProtocolRunner(
        base_url=args.base_url,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        max_total_attempts=args.max_total_attempts,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )


def prepare_dataset(args: argparse.Namespace) -> None:
    manifest = acquire_and_materialize(
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        generator_path=Path(__file__).resolve(),
        repository_root=REPOSITORY_ROOT,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


def verify_dataset(args: argparse.Namespace) -> None:
    result = verify_materialized_dataset(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def run_calibration(args: argparse.Namespace) -> None:
    samples = load_jsonl(args.samples)
    runner = _runner(args)
    records = runner.run_cohort(
        samples,
        cohort="calibration",
        output_path=args.output,
        expected_count=32,
    )
    summary = recompute_summary(
        records, expected_count=32, expected_cohort="calibration"
    )
    summary["source_artifacts"] = {
        "outputs_sha256": sha256_file(args.output)
    }
    summary["fingerprint_sha256"] = fingerprint_document(summary)
    write_json(args.summary, summary)


def run_formal(args: argparse.Namespace) -> None:
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    run_formal_from_files(
        _runner(args),
        calibration_path=args.calibration,
        formal_path=args.formal,
        artifact_dir=args.artifact_dir,
    )


def summarize(args: argparse.Namespace) -> None:
    records = load_jsonl(args.outputs)
    timing = (
        None
        if args.timing is None
        else json.loads(args.timing.read_text(encoding="utf-8"))
    )
    summary = recompute_summary(
        records,
        timing=timing,
        expected_count=args.expected_count,
        expected_cohort=args.expected_cohort,
    )
    if args.timing is None:
        summary["source_artifacts"] = {
            "outputs_sha256": sha256_file(args.outputs)
        }
    else:
        summary["source_artifacts"] = {
            "formal_outputs_sha256": sha256_file(args.outputs),
            "formal_timing_sha256": sha256_file(args.timing),
        }
    summary["fingerprint_sha256"] = fingerprint_document(summary)
    if args.assert_matches is not None:
        existing = json.loads(args.assert_matches.read_text(encoding="utf-8"))
        if existing != summary:
            raise SystemExit(
                "offline recomputation does not match existing summary"
            )
    if args.output is not None:
        write_json(args.output, summary)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def add_runner_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:30000"
    )
    parser.add_argument("--model", default="deepseek-v4-flash-dspark")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--max-total-attempts", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare-dataset",
        help="acquire the pinned HF revision and create immutable 32/500 cohorts",
    )
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--cache-dir", type=Path, required=True)
    prepare.set_defaults(function=prepare_dataset)

    verify = subparsers.add_parser(
        "verify-dataset",
        help="recompute immutable cohort hashes, indices, prompt, and references",
    )
    verify.add_argument("--output-dir", type=Path, required=True)
    verify.set_defaults(function=verify_dataset)

    calibration = subparsers.add_parser(
        "run-calibration", help="run exactly 32 calibration requests"
    )
    calibration.add_argument("--samples", type=Path, required=True)
    calibration.add_argument("--output", type=Path, required=True)
    calibration.add_argument("--summary", type=Path, required=True)
    add_runner_arguments(calibration)
    calibration.set_defaults(function=run_calibration)

    formal = subparsers.add_parser(
        "run-formal",
        help="run 10 excluded warmups followed by one timed 500-request cohort",
    )
    formal.add_argument("--calibration", type=Path, required=True)
    formal.add_argument("--formal", type=Path, required=True)
    formal.add_argument("--artifact-dir", type=Path, required=True)
    add_runner_arguments(formal)
    formal.set_defaults(function=run_formal)

    summary = subparsers.add_parser(
        "summarize", help="recompute a summary solely from raw JSONL/timing"
    )
    summary.add_argument("--outputs", type=Path, required=True)
    summary.add_argument("--timing", type=Path)
    summary.add_argument("--expected-count", type=int)
    summary.add_argument("--expected-cohort")
    summary.add_argument("--output", type=Path)
    summary.add_argument("--assert-matches", type=Path)
    summary.set_defaults(function=summarize)

    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
