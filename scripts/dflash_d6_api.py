#!/usr/bin/env python3
"""Run one protocol DFlash formal arm and build reproducible metrics."""

from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dflash_d1c_harness import PROMPT_SUFFIX, run_cohort  # noqa: E402


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROPOSAL_WIDTH = 7


class HardStop(BaseException):
    """Escape request retries at the immutable operational deadline."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def request_json(url: str, timeout: float = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with OPENER.open(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise ValueError(f"{url} did not return an object")
    return value


def hedge_snapshot(server_info: Mapping[str, Any]) -> dict[str, Any]:
    states = server_info.get("internal_states")
    if not isinstance(states, list) or len(states) != 1:
        raise ValueError("expected exactly one DP internal state")
    state = states[0]
    if not isinstance(state, dict):
        raise ValueError("server internal state is not an object")
    record = state.get("dflash_info_record")
    if not isinstance(record, dict) or not isinstance(record.get("hedge"), dict):
        raise ValueError("DFlash HEDGE snapshot is missing")
    return dict(record["hedge"])


def install_deadline(hard_stop_utc: str) -> None:
    deadline = datetime.fromisoformat(hard_stop_utc.replace("Z", "+00:00"))
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise HardStop("D6 hard stop already reached")

    def stop(_signum: int, _frame: Any) -> None:
        raise HardStop("D6 absolute hard stop reached")

    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, remaining)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} is not an object")
        rows.append(row)
    return rows


def validate_protocol_inputs(
    calibration: Sequence[Mapping[str, Any]],
    warmup: Sequence[Mapping[str, Any]],
    formal: Sequence[Mapping[str, Any]],
) -> None:
    if len(calibration) != 32:
        raise ValueError("calibration cohort must contain exactly 32 rows")
    if len(warmup) != 10:
        raise ValueError("warmup cohort must contain exactly 10 rows")
    if len(formal) != 500:
        raise ValueError("formal cohort must contain exactly 500 rows")
    if list(warmup) != list(calibration[:10]):
        raise ValueError("warmup is not the exact first 10 calibration rows")
    calibration_indices = [int(row["dataset_index"]) for row in calibration]
    formal_indices = [int(row["dataset_index"]) for row in formal]
    if set(calibration_indices) & set(formal_indices):
        raise ValueError("calibration and formal cohorts overlap")
    for cohort_name, rows in (("calibration", calibration), ("formal", formal)):
        for position, row in enumerate(rows):
            if row.get("cohort") != cohort_name:
                raise ValueError(f"{cohort_name} row {position} has wrong cohort")
            if int(row.get("cohort_position", -1)) != position:
                raise ValueError(f"{cohort_name} row {position} is out of order")
            prompt = row.get("prompt")
            if (
                not isinstance(prompt, str)
                or not prompt.endswith("\n" + PROMPT_SUFFIX)
            ):
                raise ValueError(f"{cohort_name} row {position} prompt is not pinned")


def response_speculative_metrics(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if row.get("terminal_state") != "success":
        return None
    response = row.get("full_response")
    if not isinstance(response, dict):
        raise ValueError("successful row is missing full_response")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("successful row does not have exactly one choice")
    meta = choices[0].get("meta_info")
    if not isinstance(meta, dict):
        raise ValueError("successful row is missing meta_info")
    histogram = meta.get("spec_correct_drafts_histogram")
    if (
        not isinstance(histogram, list)
        or not histogram
        or len(histogram) > PROPOSAL_WIDTH + 1
        or not all(isinstance(item, int) and item >= 0 for item in histogram)
    ):
        raise ValueError("invalid per-request speculative acceptance histogram")
    histogram = list(histogram) + [0] * (PROPOSAL_WIDTH + 1 - len(histogram))
    proposals = sum(histogram)
    accepted = sum(length * count for length, count in enumerate(histogram))
    verify_count = int(meta.get("spec_verify_ct", -1))
    reported_accepted = int(meta.get("spec_num_correct_drafts", -1))
    reported_proposed = int(meta.get("spec_num_proposed_drafts", -1))
    if proposals <= 0 or verify_count != proposals:
        raise ValueError("speculative histogram and verify count differ")
    if reported_accepted != accepted:
        raise ValueError("speculative histogram and accepted count differ")
    if reported_proposed != proposals * PROPOSAL_WIDTH:
        raise ValueError("proposed draft count does not equal proposals times seven")
    completion_tokens = int(row["usage"]["completion_tokens"])
    reported_length = float(meta.get("spec_accept_length", math.nan))
    expected_length = completion_tokens / proposals
    if not math.isclose(reported_length, expected_length, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("reported speculative accept length is not reproducible")
    return {
        "proposals": proposals,
        "accepted_draft_tokens": accepted,
        "proposed_draft_tokens": reported_proposed,
        "accepted_drafts_per_proposal": accepted / proposals,
        "accept_length_including_current": reported_length,
        "acceptance_length_histogram_0_to_7": histogram,
    }


def enrich_and_summarize(
    rows: Sequence[dict[str, Any]],
    *,
    cohort_summary: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(rows) != 500:
        raise ValueError("formal output must contain exactly 500 rows")
    aggregate_histogram = [0] * (PROPOSAL_WIDTH + 1)
    proposals = 0
    accepted = 0
    successful_completion_tokens = 0
    successful_with_metrics = 0
    enriched = []
    for expected_index, raw in enumerate(rows):
        row = dict(raw)
        if int(row.get("request_index", -1)) != expected_index:
            raise ValueError("formal output request order is not contiguous")
        metrics = response_speculative_metrics(row)
        row["speculative_metrics"] = metrics
        enriched.append(row)
        if metrics is None:
            continue
        successful_with_metrics += 1
        proposals += int(metrics["proposals"])
        accepted += int(metrics["accepted_draft_tokens"])
        successful_completion_tokens += int(row["usage"]["completion_tokens"])
        for index, count in enumerate(
            metrics["acceptance_length_histogram_0_to_7"]
        ):
            aggregate_histogram[index] += int(count)
    if proposals != sum(aggregate_histogram):
        raise ValueError("aggregate proposal count is inconsistent")
    if accepted != sum(
        length * count for length, count in enumerate(aggregate_histogram)
    ):
        raise ValueError("aggregate accepted count is inconsistent")
    accepted_by_position = [
        sum(aggregate_histogram[length] for length in range(position, 8))
        for position in range(1, 8)
    ]
    summary = {
        "schema_version": 1,
        "proposal_width": PROPOSAL_WIDTH,
        "successful_requests_with_speculative_metrics": successful_with_metrics,
        "proposals": proposals,
        "proposed_draft_tokens": proposals * PROPOSAL_WIDTH,
        "accepted_draft_tokens": accepted,
        "mean_accepted_drafts_per_proposal": (
            accepted / proposals if proposals else None
        ),
        "mean_accept_length_including_current": (
            successful_completion_tokens / proposals if proposals else None
        ),
        "acceptance_length_histogram_0_to_7": aggregate_histogram,
        "accepted_draft_tokens_by_position_1_to_7": accepted_by_position,
        "acceptance_rate_by_position_1_to_7": [
            count / proposals if proposals else None for count in accepted_by_position
        ],
        "completion_tokens": int(cohort_summary["completion_tokens"]),
        "timed_wall_seconds": float(cohort_summary["wall_time_seconds"]),
        "e2e_output_tps": float(cohort_summary["e2e_output_tps"]),
        "terminal_counts": dict(cohort_summary["terminal_counts"]),
        "retry_count": int(cohort_summary["retry_count"]),
    }
    return enriched, summary


def validate_native_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("mode") != "disabled":
        raise ValueError(f"native formal HEDGE mode is not disabled: {snapshot.get('mode')}")
    if snapshot.get("config") is not None:
        raise ValueError("native formal unexpectedly has a HEDGE config")
    switches = snapshot.get("experiment_switches")
    if not isinstance(switches, dict):
        raise ValueError("experiment switches are missing")
    if int(switches.get("HEDGE_ENABLED", -1)) != 0:
        raise ValueError("native formal HEDGE_ENABLED is not zero")
    if int(switches.get("SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE", -1)) != 0:
        raise ValueError("native formal calibration trace is enabled")
    if int(snapshot.get("proposal_width", -1)) != PROPOSAL_WIDTH:
        raise ValueError("native formal proposal width is not seven")
    # The adapter deliberately bypasses and never binds HEDGE request state in
    # disabled mode. Cohort terminality is proven by the 510 durable client
    # records; the disabled adapter must therefore remain entirely zeroed.
    for field in (
        "requests_initialized",
        "requests_finished",
        "slot_reuse_resets",
        "requests_non_natural",
        "proposals",
        "draft_tokens_verifiable",
        "strict_accepted_draft_tokens",
        "hedge_accepted_draft_tokens",
        "relaxed_mismatches",
        "budget_exhaustion_events",
    ):
        if int(snapshot.get(field, -1)) != 0:
            raise ValueError(f"disabled native HEDGE counter is nonzero: {field}")
    if int(snapshot.get("active_request_states", -1)) != 0:
        raise ValueError("active request state remains after formal arm")
    if int(snapshot.get("state_leaks", -1)) != 0:
        raise ValueError("request state leak was observed")
    if snapshot.get("request_state", []) != []:
        raise ValueError("request_state was not cleared")


def run_native(args: argparse.Namespace) -> int:
    scratch: Path = args.scratch
    result: dict[str, Any] = {
        "schema_version": 1,
        "phase": "D6",
        "arm": "native",
        "status": "FAIL",
        "arm_pass": False,
        "started_at_utc": utc_now(),
        "hard_stop_utc": args.hard_stop_utc,
    }
    install_deadline(args.hard_stop_utc)
    warmup_marker = scratch / "warmup.active"
    formal_marker = scratch / "formal.active"
    try:
        calibration = load_jsonl(args.calibration)
        warmup = load_jsonl(args.warmup)
        formal = load_jsonl(args.formal)
        validate_protocol_inputs(calibration, warmup, formal)
        server_info_before = request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )
        warmup_marker.write_text(utc_now() + "\n")
        try:
            warmup_summary = run_cohort(
                warmup,
                cohort_kind="warmup",
                base_url=args.base_url,
                model=args.model,
                output_path=scratch / "warmup_outputs.jsonl",
                summary_path=scratch / "warmup_summary.json",
                max_attempts=3,
                request_timeout_seconds=args.timeout,
                retry_backoff_seconds=1,
            )
        finally:
            warmup_marker.unlink(missing_ok=True)
        if not warmup_summary["all_terminal"]:
            raise ValueError("not all 10 warmup requests reached a terminal state")
        server_info_after_warmup = request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )
        formal_dispatched_after = utc_now()
        formal_marker.write_text(formal_dispatched_after + "\n")
        try:
            formal_summary = run_cohort(
                formal,
                cohort_kind="formal",
                base_url=args.base_url,
                model=args.model,
                output_path=scratch / "formal_outputs.raw.jsonl",
                summary_path=scratch / "formal_timing.json",
                max_attempts=3,
                request_timeout_seconds=args.timeout,
                retry_backoff_seconds=1,
            )
        finally:
            formal_marker.unlink(missing_ok=True)
        if not formal_summary["all_terminal"]:
            raise ValueError("not all 500 formal requests reached a terminal state")
        raw_rows = load_jsonl(scratch / "formal_outputs.raw.jsonl")
        enriched_rows, acceptance = enrich_and_summarize(
            raw_rows, cohort_summary=formal_summary
        )
        with (scratch / "formal_outputs.jsonl").open("w") as output:
            for row in enriched_rows:
                output.write(canonical(row) + "\n")
        (scratch / "requests.jsonl").write_bytes(
            (scratch / "formal_outputs.jsonl").read_bytes()
        )
        write_json(scratch / "acceptance_summary.json", acceptance)
        server_info_after = request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )
        snapshot = hedge_snapshot(server_info_after)
        validate_native_snapshot(snapshot)
        write_json(
            scratch / "hedge_counters.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "arm": "native",
                "status": "PASS",
                "before_warmup": hedge_snapshot(server_info_before),
                "after_warmup": hedge_snapshot(server_info_after_warmup),
                "after_formal": snapshot,
                "formal_response_metrics": acceptance,
            },
        )
        result.update(
            status="PASS",
            arm_pass=True,
            warmup_count=10,
            warmup_summary=warmup_summary,
            formal_count=500,
            formal_dispatched_after_utc=formal_dispatched_after,
            formal_summary=formal_summary,
            acceptance_summary=acceptance,
            server_info_after=server_info_after,
        )
    except BaseException as error:
        result.update(
            status="FAIL",
            arm_pass=False,
            error_type=type(error).__name__,
            error=str(error),
        )
        write_json(
            scratch / "hedge_counters.json",
            {"schema_version": 1, "phase": "D6", "status": "FAIL", "error": repr(error)},
        )
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        warmup_marker.unlink(missing_ok=True)
        formal_marker.unlink(missing_ok=True)
        result["finished_at_utc"] = utc_now()
        write_json(scratch / "api_smoke.json", result)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    run = root.add_subparsers(dest="command", required=True).add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--calibration", type=Path, required=True)
    run.add_argument("--warmup", type=Path, required=True)
    run.add_argument("--formal", type=Path, required=True)
    run.add_argument("--scratch", type=Path, required=True)
    run.add_argument("--hard-stop-utc", required=True)
    run.add_argument("--timeout", type=float, default=300)
    run.set_defaults(handler=run_native)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
