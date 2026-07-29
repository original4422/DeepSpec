#!/usr/bin/env python3
"""Run the sole frozen DFlash HEDGE B+ formal arm."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import signal
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dflash_d6_api as native_api  # noqa: E402
from dflash_d6_bplus_lifecycle import (  # noqa: E402
    C1_ACCEPTANCE,
    C2_ACCEPTANCE,
    load_protocol_identity,
)


PROPOSAL_WIDTH = native_api.PROPOSAL_WIDTH
FORMAL_TIMING_FIELDS = (
    "completion_tokens",
    "wall_time_seconds",
    "e2e_output_tps",
    "terminal_counts",
    "retry_count",
)

# These are deliberately aliases to the committed native public seams so the
# two formal arms cannot drift in cohort, acceptance, or timing semantics.
validate_protocol_inputs = native_api.validate_protocol_inputs
response_speculative_metrics = native_api.response_speculative_metrics
enrich_and_summarize = native_api.enrich_and_summarize


def formal_hedge_counter_delta(
    after_warmup: Mapping[str, Any],
    after_formal: Mapping[str, Any],
    expected_config: Mapping[str, Any],
    *,
    formal_request_count: int,
) -> dict[str, Any]:
    """Subtract the warmup snapshot and validate formal-only HEDGE counters."""

    integer_fields = (
        "proposals",
        "draft_tokens_verifiable",
        "strict_accepted_draft_tokens",
        "hedge_accepted_draft_tokens",
        "relaxed_mismatches",
        "budget_exhaustion_events",
        "requests_initialized",
        "requests_finished",
        "slot_reuse_resets",
        "requests_non_natural",
    )
    delta: dict[str, Any] = {"schema_version": 1}
    for field in integer_fields:
        before = int(after_warmup.get(field, -1))
        after = int(after_formal.get(field, -1))
        if before < 0 or after < before:
            raise ValueError(f"B+ HEDGE counter is not monotonic: {field}")
        delta[field] = after - before
    for field, width in (
        ("accepted_draft_tokens_by_position", PROPOSAL_WIDTH),
        ("accept_length_histogram", PROPOSAL_WIDTH + 1),
    ):
        before_values = after_warmup.get(field)
        after_values = after_formal.get(field)
        if (
            not isinstance(before_values, list)
            or not isinstance(after_values, list)
            or len(before_values) != width
            or len(after_values) != width
        ):
            raise ValueError(f"B+ HEDGE counter array is invalid: {field}")
        values = [
            int(after) - int(before)
            for before, after in zip(before_values, after_values)
        ]
        if any(value < 0 for value in values):
            raise ValueError(f"B+ HEDGE counter is not monotonic: {field}")
        delta[field] = values
    before_charged = float(after_warmup.get("regret_charged", math.nan))
    after_charged = float(after_formal.get("regret_charged", math.nan))
    if (
        not math.isfinite(before_charged)
        or not math.isfinite(after_charged)
        or after_charged < before_charged
    ):
        raise ValueError("B+ HEDGE counter is not monotonic: regret_charged")
    delta["regret_charged"] = after_charged - before_charged

    proposals = int(delta["proposals"])
    verifiable = int(delta["draft_tokens_verifiable"])
    strict = int(delta["strict_accepted_draft_tokens"])
    accepted = int(delta["hedge_accepted_draft_tokens"])
    relaxed = int(delta["relaxed_mismatches"])
    if proposals <= 0 or verifiable != proposals * PROPOSAL_WIDTH:
        raise ValueError("formal-only proposal counters are inconsistent")
    if not 0 <= strict <= accepted <= verifiable:
        raise ValueError("formal-only acceptance counters are inconsistent")
    if not 0 <= relaxed <= proposals * int(expected_config["m"]):
        raise ValueError("formal-only relaxed mismatches exceed the block cap")
    positions = delta["accepted_draft_tokens_by_position"]
    histogram = delta["accept_length_histogram"]
    if (
        any(left < right for left, right in zip(positions, positions[1:]))
        or sum(positions) != accepted
        or sum(histogram) != proposals
        or sum(index * count for index, count in enumerate(histogram)) != accepted
    ):
        raise ValueError("formal-only acceptance distributions are inconsistent")
    initialized = int(delta["requests_initialized"])
    terminal = int(delta["requests_finished"]) + int(
        delta["slot_reuse_resets"]
    )
    if initialized != formal_request_count or terminal != formal_request_count:
        raise ValueError("formal-only request lifecycle is not exactly terminal")
    if int(delta["requests_non_natural"]) < int(delta["slot_reuse_resets"]):
        raise ValueError("formal-only non-natural lifecycle counter is inconsistent")
    risk_upper_bound = float(expected_config["B"]) * formal_request_count
    if delta["regret_charged"] > risk_upper_bound + 1e-9:
        raise ValueError("formal-only regret exceeds the aggregate risk budget")
    if not 0 <= int(delta["budget_exhaustion_events"]) <= formal_request_count:
        raise ValueError("formal-only budget exhaustion counter is inconsistent")
    delta.update(
        {
            "formal_request_count": formal_request_count,
            "risk_budget_per_request": float(expected_config["B"]),
            "risk_budget_upper_bound": risk_upper_bound,
            "relaxed_draft_gain": accepted - strict,
            "pass": True,
        }
    )
    return delta


def validate_formal_counter_alignment(
    formal_delta: Mapping[str, Any],
    response_metrics: Mapping[str, Any],
) -> None:
    """Require server HEDGE counters to match the 500 response records."""

    expected = {
        "proposals": int(response_metrics["proposals"]),
        "hedge_accepted_draft_tokens": int(
            response_metrics["accepted_draft_tokens"]
        ),
        "accept_length_histogram": list(
            response_metrics["acceptance_length_histogram_0_to_7"]
        ),
        "accepted_draft_tokens_by_position": list(
            response_metrics["accepted_draft_tokens_by_position_1_to_7"]
        ),
    }
    observed = {key: formal_delta.get(key) for key in expected}
    if observed != expected:
        raise ValueError(
            "formal HEDGE counters differ from response metrics: "
            f"observed={observed!r} expected={expected!r}"
        )


def validate_bplus_snapshot(
    snapshot: Mapping[str, Any],
    expected_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate frozen config, risk accounting, and terminal request state."""

    if snapshot.get("mode") != "enabled":
        raise ValueError("B+ HEDGE mode is not enabled")
    if snapshot.get("config") != dict(expected_config):
        raise ValueError("B+ runtime config differs from sealed C1 config")
    expected_fingerprint = hashlib.sha256(
        native_api.canonical(dict(expected_config)).encode()
    ).hexdigest()
    if snapshot.get("config_fingerprint") != expected_fingerprint:
        raise ValueError("B+ runtime config fingerprint differs from sealed C1 SHA")
    switches = snapshot.get("experiment_switches")
    if not isinstance(switches, Mapping):
        raise ValueError("B+ experiment switches are missing")
    if int(switches.get("HEDGE_ENABLED", -1)) != 1:
        raise ValueError("B+ HEDGE_ENABLED is not one")
    if int(switches.get("SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE", -1)) != 0:
        raise ValueError("B+ calibration trace is enabled")
    if int(snapshot.get("proposal_width", -1)) != PROPOSAL_WIDTH:
        raise ValueError("B+ proposal width is not seven")

    proposals = int(snapshot.get("proposals", -1))
    verifiable = int(snapshot.get("draft_tokens_verifiable", -1))
    strict = int(snapshot.get("strict_accepted_draft_tokens", -1))
    accepted = int(snapshot.get("hedge_accepted_draft_tokens", -1))
    relaxed = int(snapshot.get("relaxed_mismatches", -1))
    if proposals <= 0 or verifiable != proposals * PROPOSAL_WIDTH:
        raise ValueError("B+ proposal/verifiable draft counters are inconsistent")
    if not 0 <= strict <= accepted <= verifiable:
        raise ValueError("B+ strict/HEDGE accepted counters are inconsistent")
    if not 0 <= relaxed <= proposals * int(expected_config["m"]):
        raise ValueError("B+ relaxed mismatches exceed the per-block cap")

    positions = snapshot.get("accepted_draft_tokens_by_position")
    if (
        not isinstance(positions, list)
        or len(positions) != PROPOSAL_WIDTH
        or any(not isinstance(value, int) or value < 0 for value in positions)
        or any(left < right for left, right in zip(positions, positions[1:]))
        or sum(positions) != accepted
    ):
        raise ValueError("B+ accepted-by-position counters are inconsistent")
    histogram = snapshot.get("accept_length_histogram")
    if (
        not isinstance(histogram, list)
        or len(histogram) != PROPOSAL_WIDTH + 1
        or any(not isinstance(value, int) or value < 0 for value in histogram)
        or sum(histogram) != proposals
        or sum(index * count for index, count in enumerate(histogram)) != accepted
    ):
        raise ValueError("B+ acceptance histogram is inconsistent")

    initialized = int(snapshot.get("requests_initialized", -1))
    finished = int(snapshot.get("requests_finished", -1))
    resets = int(snapshot.get("slot_reuse_resets", -1))
    non_natural = int(snapshot.get("requests_non_natural", -1))
    terminal = finished + resets
    if (
        initialized < 510
        or finished < 0
        or resets < 0
        or terminal != initialized
        or non_natural < resets
    ):
        raise ValueError("B+ request lifecycle counters are inconsistent")
    if int(snapshot.get("active_request_states", -1)) != 0:
        raise ValueError("B+ active request state remains")
    if int(snapshot.get("state_leaks", -1)) != 0:
        raise ValueError("B+ request state leak was observed")
    if snapshot.get("request_state", []) != []:
        raise ValueError("B+ request_state was not cleared")

    charged = float(snapshot.get("regret_charged", math.nan))
    budget_upper_bound = float(expected_config["B"]) * terminal
    if (
        not math.isfinite(charged)
        or charged < 0
        or charged > budget_upper_bound + 1e-9
    ):
        raise ValueError("B+ charged regret exceeds the aggregate risk budget")
    exhaustion = int(snapshot.get("budget_exhaustion_events", -1))
    if not 0 <= exhaustion <= terminal:
        raise ValueError("B+ budget exhaustion counter is inconsistent")
    return {
        "schema_version": 1,
        "risk_budget_per_request": float(expected_config["B"]),
        "risk_budget_upper_bound": budget_upper_bound,
        "regret_charged": charged,
        "relaxed_mismatches": relaxed,
        "relaxed_draft_gain": accepted - strict,
        "lifecycle_terminal_count": terminal,
        "requests_initialized": initialized,
        "requests_finished": finished,
        "slot_reuse_resets": resets,
        "active_request_states": 0,
        "state_leaks": 0,
        "pass": True,
    }


def run_bplus(args: argparse.Namespace) -> int:
    scratch: Path = args.scratch
    identity = load_protocol_identity(args.c1_acceptance, args.c2_acceptance)
    config = identity["config"]
    result: dict[str, Any] = {
        "schema_version": 1,
        "phase": "D6",
        "arm": "B+",
        "status": "FAIL",
        "arm_pass": False,
        "started_at_utc": native_api.utc_now(),
        "hard_stop_utc": args.hard_stop_utc,
        "hedge_config": config,
        "hedge_config_sha256": identity["sha256"],
        "b0_status": identity["b0_status"],
    }
    native_api.install_deadline(args.hard_stop_utc)
    warmup_marker = scratch / "warmup.active"
    formal_marker = scratch / "formal.active"
    try:
        calibration = native_api.load_jsonl(args.calibration)
        warmup = native_api.load_jsonl(args.warmup)
        formal = native_api.load_jsonl(args.formal)
        validate_protocol_inputs(calibration, warmup, formal)
        before = native_api.request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )

        warmup_marker.write_text(native_api.utc_now() + "\n")
        try:
            warmup_summary = native_api.run_cohort(
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
            raise ValueError("not all 10 B+ warmup requests reached terminal state")
        after_warmup = native_api.request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )

        formal_dispatched_after = native_api.utc_now()
        formal_marker.write_text(formal_dispatched_after + "\n")
        try:
            formal_summary = native_api.run_cohort(
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
            raise ValueError("not all 500 B+ formal requests reached terminal state")
        raw_rows = native_api.load_jsonl(
            scratch / "formal_outputs.raw.jsonl"
        )
        enriched_rows, acceptance = enrich_and_summarize(
            raw_rows, cohort_summary=formal_summary
        )
        with (scratch / "formal_outputs.jsonl").open("w") as output:
            for row in enriched_rows:
                output.write(native_api.canonical(row) + "\n")
        (scratch / "requests.jsonl").write_bytes(
            (scratch / "formal_outputs.jsonl").read_bytes()
        )
        native_api.write_json(
            scratch / "acceptance_summary.json", acceptance
        )

        server_info_after = native_api.request_json(
            args.base_url.rstrip("/") + "/get_server_info"
        )
        snapshot = native_api.hedge_snapshot(server_info_after)
        risk_audit = validate_bplus_snapshot(snapshot, config)
        warmup_snapshot = native_api.hedge_snapshot(after_warmup)
        formal_delta = formal_hedge_counter_delta(
            warmup_snapshot,
            snapshot,
            config,
            formal_request_count=500,
        )
        validate_formal_counter_alignment(formal_delta, acceptance)
        native_api.write_json(
            scratch / "hedge_counters.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "arm": "B+",
                "status": "PASS",
                "hedge_config": config,
                "hedge_config_sha256": identity["sha256"],
                "before_warmup": native_api.hedge_snapshot(before),
                "after_warmup": warmup_snapshot,
                "after_formal": snapshot,
                "risk_lifecycle_audit": risk_audit,
                "formal_hedge_counter_delta": formal_delta,
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
            risk_lifecycle_audit=risk_audit,
            formal_hedge_counter_delta=formal_delta,
            server_info_after=server_info_after,
        )
    except BaseException as error:
        result.update(
            status="FAIL",
            arm_pass=False,
            error_type=type(error).__name__,
            error=str(error),
        )
        native_api.write_json(
            scratch / "hedge_counters.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "arm": "B+",
                "status": "FAIL",
                "error": repr(error),
            },
        )
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        warmup_marker.unlink(missing_ok=True)
        formal_marker.unlink(missing_ok=True)
        result["finished_at_utc"] = native_api.utc_now()
        native_api.write_json(scratch / "api_smoke.json", result)
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
    run.add_argument("--c1-acceptance", type=Path, default=C1_ACCEPTANCE)
    run.add_argument("--c2-acceptance", type=Path, default=C2_ACCEPTANCE)
    run.set_defaults(handler=run_bplus)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
