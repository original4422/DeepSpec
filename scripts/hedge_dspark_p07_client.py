#!/usr/bin/env python3
"""Run the frozen P07 positive-budget formal arm on the P06 protocol seam."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_protocol.config import FORMAL_COUNT, WARMUP_COUNT  # noqa: E402
from deepspec.hedge_protocol.io import load_jsonl, write_json  # noqa: E402
from hedge_dspark_p04_client import (  # noqa: E402
    SERVER_FIELDS,
    _NoProxyJsonGet,
    wait_ready,
)
from hedge_dspark_p06_client import (  # noqa: E402
    CounterClear,
    JsonGet,
    JsonPost,
    clear_formal_evidence,
    run_formal_arm,
)
from hedge_dspark_p06_prepare import CALIBRATION, FORMAL  # noqa: E402
from hedge_dspark_p07_prepare import (  # noqa: E402
    FROZEN_CONFIG,
    FROZEN_CONFIG_FINGERPRINT,
    validate_formal_datasets,
)


CONFIG = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
COUNTER_SCHEMA_VERSION = 1
CANDIDATE_ALIGNMENT = {
    "anchor_index": 0,
    "draft_indices": [1, 6],
    "target_draft_logit_indices": [0, 5],
}
SCORE_SEAM = (
    "native full-vocab next_token_logits after the existing "
    "LogitsProcessor TP all-gather; HEDGE adds no TP collective"
)
COUNTER_FIELDS = (
    "proposals",
    "draft_tokens_verifiable",
    "strict_accepted_draft_tokens",
    "hedge_accepted_draft_tokens",
    "relaxed_mismatches",
    "regret_charged",
    "cap_trim_lens",
    "budget_exhaustion_events",
    "remaining_budget_total",
    "requests_initialized",
    "requests_finished",
    "requests_non_natural",
    "slot_reuse_resets",
    "active_request_states",
    "state_leaks",
    "trace_rows_seen",
    "trace_rows_dropped",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _number(value: Any, *, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{field} must be finite and non-negative")
    return float(value)


def _integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def validate_hedge_server_snapshot(
    server_info: Mapping[str, Any],
    *,
    require_exact_zero: bool,
    formal_summary: Mapping[str, Any] | None = None,
    allow_active: bool = False,
) -> dict[str, Any]:
    """Audit the real HEDGE snapshot schema at clear and formal boundaries."""

    _require(isinstance(server_info, Mapping), "/server_info must be an object")
    mismatches = {
        key: {"expected": expected, "observed": server_info.get(key)}
        for key, expected in SERVER_FIELDS.items()
        if server_info.get(key) != expected
    }
    _require(not mismatches, f"/server_info decode config mismatch: {mismatches}")
    states = server_info.get("internal_states")
    _require(
        isinstance(states, list) and bool(states),
        "/server_info internal_states must be non-empty",
    )
    totals = {field: 0.0 for field in COUNTER_FIELDS}
    positions = [0] * 5
    snapshots: list[dict[str, Any]] = []
    dirty: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        snapshot = (
            state.get("dspark_info_record", {}).get("hedge")
            if isinstance(state, Mapping)
            else None
        )
        _require(
            isinstance(snapshot, Mapping),
            f"internal_states[{index}] has no HEDGE snapshot",
        )
        normalized = dict(snapshot)
        _require(
            _integer(
                normalized.get("counter_schema_version"),
                field="counter_schema_version",
            )
            == COUNTER_SCHEMA_VERSION,
            f"HEDGE snapshot {index} identity mismatch",
        )
        _require(
            normalized.get("mode") == "enabled"
            and normalized.get("experiment_switches")
            == {
                "HEDGE_ENABLED": 1,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
            }
            and normalized.get("config") == CONFIG
            and normalized.get("config_fingerprint")
            == FROZEN_CONFIG_FINGERPRINT
            and normalized.get("gamma") == 5
            and normalized.get("verify_num_draft_tokens") == 6
            and normalized.get("candidate_alignment")
            == CANDIDATE_ALIGNMENT
            and normalized.get("score_seam") == SCORE_SEAM,
            f"HEDGE snapshot {index} identity mismatch",
        )
        current_dirty: dict[str, Any] = {}
        for field in COUNTER_FIELDS:
            value = (
                _number(normalized.get(field), field=field)
                if field in {"regret_charged", "remaining_budget_total"}
                else float(_integer(normalized.get(field), field=field))
            )
            totals[field] += value
            if value != 0.0:
                current_dirty[field] = normalized[field]
        observed_positions = normalized.get(
            "hedge_accepted_draft_tokens_by_position"
        )
        _require(
            isinstance(observed_positions, list)
            and len(observed_positions) == 5
            and all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
                for value in observed_positions
            ),
            f"HEDGE snapshot {index} position counters malformed",
        )
        snapshot_proposals = _integer(
            normalized["proposals"], field="proposals"
        )
        snapshot_verifiable = _integer(
            normalized["draft_tokens_verifiable"],
            field="draft_tokens_verifiable",
        )
        snapshot_strict = _integer(
            normalized["strict_accepted_draft_tokens"],
            field="strict_accepted_draft_tokens",
        )
        snapshot_hedge = _integer(
            normalized["hedge_accepted_draft_tokens"],
            field="hedge_accepted_draft_tokens",
        )
        _require(
            all(value <= snapshot_proposals for value in observed_positions)
            and all(
                left >= right
                for left, right in zip(
                    observed_positions, observed_positions[1:]
                )
            )
            and sum(observed_positions) == snapshot_hedge,
            f"HEDGE snapshot {index} position counters are not physical",
        )
        _require(
            snapshot_verifiable <= snapshot_proposals * 5,
            f"HEDGE snapshot {index} verifiable drafts exceed width",
        )
        _require(
            snapshot_strict <= snapshot_hedge <= snapshot_verifiable,
            f"HEDGE snapshot {index} acceptance counters inconsistent",
        )
        _require(
            _integer(
                normalized["relaxed_mismatches"],
                field="relaxed_mismatches",
            )
            <= snapshot_proposals * int(CONFIG["m"]),
            f"HEDGE snapshot {index} relaxed mismatches exceed block cap",
        )
        _require(
            _integer(normalized["cap_trim_lens"], field="cap_trim_lens")
            <= snapshot_proposals * 5,
            f"HEDGE snapshot {index} cap trim lengths exceed width bound",
        )
        for position, value in enumerate(observed_positions):
            positions[position] += value
        if observed_positions != [0] * 5:
            current_dirty["hedge_accepted_draft_tokens_by_position"] = (
                observed_positions
            )
        remaining = normalized.get("remaining_budget_by_request")
        trace = normalized.get("strict_rejection_trace")
        _require(
            isinstance(remaining, list) and isinstance(trace, list),
            f"HEDGE snapshot {index} request/trace fields malformed",
        )
        snapshot_active = _integer(
            normalized["active_request_states"],
            field="active_request_states",
        )
        snapshot_leaks = _integer(
            normalized["state_leaks"],
            field="state_leaks",
        )
        snapshot_initialized = _integer(
            normalized["requests_initialized"],
            field="requests_initialized",
        )
        snapshot_finished = _integer(
            normalized["requests_finished"],
            field="requests_finished",
        )
        snapshot_non_natural = _integer(
            normalized["requests_non_natural"],
            field="requests_non_natural",
        )
        snapshot_slot_resets = _integer(
            normalized["slot_reuse_resets"],
            field="slot_reuse_resets",
        )
        _require(
            snapshot_active == snapshot_leaks == len(remaining),
            f"HEDGE snapshot {index} request-state gauge/list mismatch",
        )
        _require(
            snapshot_initialized >= snapshot_finished
            and snapshot_initialized - snapshot_finished
            == snapshot_active
            == snapshot_leaks,
            f"HEDGE snapshot {index} request lifecycle invariant failed",
        )
        _require(
            snapshot_non_natural <= snapshot_finished
            and snapshot_slot_resets <= snapshot_initialized,
            f"HEDGE snapshot {index} lifecycle counters exceed requests",
        )
        _require(
            _integer(
                normalized["budget_exhaustion_events"],
                field="budget_exhaustion_events",
            )
            <= snapshot_initialized,
            f"HEDGE snapshot {index} budget exhaustion exceeds requests",
        )
        snapshot_regret = _number(
            normalized["regret_charged"], field="regret_charged"
        )
        snapshot_remaining = _number(
            normalized["remaining_budget_total"],
            field="remaining_budget_total",
        )
        snapshot_initial_budget = (
            snapshot_initialized * float(CONFIG["B"])
        )
        _require(
            snapshot_regret <= snapshot_initial_budget + 1e-9,
            f"HEDGE snapshot {index} charged above initialized budget",
        )
        _require(
            math.isclose(
                snapshot_regret + snapshot_remaining,
                snapshot_initial_budget,
                rel_tol=1e-9,
                abs_tol=1e-6,
            ),
            f"HEDGE snapshot {index} does not conserve request budget",
        )
        for request_index, request_state in enumerate(remaining):
            _require(
                isinstance(request_state, Mapping)
                and isinstance(request_state.get("rid"), str)
                and bool(request_state["rid"])
                and isinstance(request_state.get("slot"), int)
                and not isinstance(request_state["slot"], bool)
                and request_state["slot"] >= 0
                and 0.0
                <= _number(
                    request_state.get("remaining_budget"),
                    field=(
                        "remaining_budget_by_request"
                        f"[{request_index}].remaining_budget"
                    ),
                )
                <= float(CONFIG["B"]),
                f"HEDGE snapshot {index} active request state malformed",
            )
        if remaining:
            current_dirty["remaining_budget_by_request"] = remaining
        if trace:
            current_dirty["strict_rejection_trace"] = len(trace)
        _require(
            normalized["trace_rows_seen"] == 0
            and normalized["trace_rows_dropped"] == 0
            and not trace,
            f"HEDGE snapshot {index} unexpectedly enabled calibration trace",
        )
        if current_dirty:
            dirty.append({"snapshot_index": index, "fields": current_dirty})
        snapshots.append(normalized)
    integer_totals = {
        key: int(value)
        for key, value in totals.items()
        if key not in {"regret_charged", "remaining_budget_total"}
    }
    _require(
        sum(positions) == integer_totals["hedge_accepted_draft_tokens"],
        "HEDGE per-position acceptance does not sum to total",
    )
    active = integer_totals["active_request_states"]
    leaks = integer_totals["state_leaks"]
    _require(
        allow_active or (active == 0 and leaks == 0),
        "HEDGE formal snapshot has request-state leak",
    )
    if formal_summary is not None:
        success_requests = _integer(
            formal_summary.get("success_requests"),
            field="formal_summary.success_requests",
        )
        attempts_total = _integer(
            formal_summary.get("attempts_total"),
            field="formal_summary.attempts_total",
        )
        total_requests = _integer(
            formal_summary.get("total_requests"),
            field="formal_summary.total_requests",
        )
        terminal_requests = _integer(
            formal_summary.get("terminal_requests"),
            field="formal_summary.terminal_requests",
        )
        _require(
            total_requests == FORMAL_COUNT
            and terminal_requests == FORMAL_COUNT
            and formal_summary.get("all_terminal") is True,
            "formal summary is not an exact terminal 500-record cohort",
        )
        initialized = integer_totals["requests_initialized"]
        _require(
            initialized == integer_totals["requests_finished"]
            and active == 0
            and leaks == 0,
            "HEDGE final request lifecycle is not initialized=finished",
        )
        _require(
            success_requests <= initialized <= attempts_total,
            "HEDGE initialized requests fall outside formal attempt bounds",
        )
        _require(
            integer_totals["proposals"] > 0,
            "HEDGE runtime was not called during formal requests",
        )
        _require(
            integer_totals["requests_non_natural"]
            <= integer_totals["requests_finished"]
            and integer_totals["slot_reuse_resets"] <= initialized,
            "HEDGE request lifecycle counters exceed initialized requests",
        )
        _require(
            totals["regret_charged"]
            <= initialized * float(CONFIG["B"]) + 1e-9,
            "HEDGE charged more than the request-wide budget bound",
        )
        _require(
            math.isclose(
                totals["regret_charged"]
                + totals["remaining_budget_total"],
                initialized * float(CONFIG["B"]),
                rel_tol=1e-9,
                abs_tol=1e-6,
            ),
            "HEDGE charged plus completed remaining budget does not conserve B",
        )
        _require(
            integer_totals["relaxed_mismatches"]
            <= integer_totals["proposals"] * int(CONFIG["m"]),
            "HEDGE relaxed mismatches exceed the per-block cap",
        )
    exact_zero = not dirty
    _require(
        not require_exact_zero or exact_zero,
        f"HEDGE clear snapshot is not exact zero: {dirty}",
    )
    return {
        "schema_version": 1,
        "authorized_phase": "P07",
        "status": "PASS",
        "arm": "hedge",
        "source_endpoint": "/server_info",
        "server_config": {key: server_info[key] for key in SERVER_FIELDS},
        "hedge_mode": "enabled",
        "hedge_enabled": True,
        "hedge_config": CONFIG,
        "hedge_config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
        "snapshot_count": len(snapshots),
        "hedge_snapshots": snapshots,
        "runtime_calls": integer_totals["proposals"],
        "proposal_count": integer_totals["proposals"],
        "requests_initialized": integer_totals["requests_initialized"],
        "requests_finished": integer_totals["requests_finished"],
        "active_request_states": active,
        "state_leaks": leaks,
        "relaxed_mismatches": integer_totals["relaxed_mismatches"],
        "regret_charged": totals["regret_charged"],
        "remaining_budget_total": totals["remaining_budget_total"],
        "budget_conservation": {
            "initial_budget_total": (
                integer_totals["requests_initialized"] * float(CONFIG["B"])
            ),
            "charged_plus_remaining": (
                totals["regret_charged"]
                + totals["remaining_budget_total"]
            ),
        },
        "cap_trim_lens": integer_totals["cap_trim_lens"],
        "budget_exhaustion_events": integer_totals[
            "budget_exhaustion_events"
        ],
        "hedge_accepted_draft_tokens": integer_totals[
            "hedge_accepted_draft_tokens"
        ],
        "hedge_accepted_draft_tokens_by_position": positions,
        "quiescent": active == 0 and leaks == 0,
        "exact_zero": exact_zero,
        "dirty_snapshots": dirty,
    }


def run_hedge_formal(
    *,
    base_url: str,
    warmup_samples: Sequence[Mapping[str, Any]],
    formal_samples: Sequence[Mapping[str, Any]],
    artifact_dir: Path,
    transport: Callable[[str, dict[str, Any], float], Mapping[str, Any]]
    | None = None,
    server_info_get: JsonGet | None = None,
    internal_state_post: JsonPost | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    counter_clear: CounterClear | None = None,
) -> dict[str, Any]:
    getter = server_info_get or _NoProxyJsonGet()
    clear = counter_clear or (
        lambda: clear_hedge_formal_evidence(
            base_url=base_url,
            server_info_get=getter,
            internal_state_post=internal_state_post,
            sleeper=sleeper,
            monotonic_ns=clock_ns,
        )
    )
    return run_formal_arm(
        authorized_phase="P07",
        arm="hedge",
        final_snapshot_validator=lambda payload, summary: (
            validate_hedge_server_snapshot(
                payload,
                require_exact_zero=False,
                formal_summary=summary,
            )
        ),
        base_url=base_url,
        warmup_samples=warmup_samples,
        formal_samples=formal_samples,
        artifact_dir=artifact_dir,
        transport=transport,
        server_info_get=getter,
        internal_state_post=internal_state_post,
        sleeper=sleeper,
        clock_ns=clock_ns,
        counter_clear=clear,
    )


def clear_hedge_formal_evidence(
    *,
    base_url: str,
    server_info_get: JsonGet | None = None,
    internal_state_post: JsonPost | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    timeout_seconds: float = 120.0,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    """Clear warmup evidence with the exact P07 HEDGE-on schema."""

    return clear_formal_evidence(
        authorized_phase="P07",
        arm="hedge",
        snapshot_validator=lambda payload, exact, active: (
            validate_hedge_server_snapshot(
                payload,
                require_exact_zero=exact,
                allow_active=active,
            )
        ),
        base_url=base_url,
        server_info_get=server_info_get,
        internal_state_post=internal_state_post,
        sleeper=sleeper,
        monotonic_ns=monotonic_ns,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    ready = commands.add_parser("wait-ready")
    ready.add_argument("--base-url", required=True)
    ready.add_argument("--server-pid", type=int, required=True)
    ready.add_argument("--server-start-ticks", required=True)
    ready.add_argument("--timeout", type=float, default=3600)
    ready.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--calibration", type=Path, required=True)
    run.add_argument("--formal", type=Path, required=True)
    run.add_argument("--artifact-dir", type=Path, required=True)
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
    dataset = validate_formal_datasets()
    if (
        args.calibration.resolve()
        != Path(dataset["calibration_jsonl"]).resolve()
        or args.formal.resolve() != Path(dataset["formal_jsonl"]).resolve()
    ):
        parser.error("P07 must use immutable P01 calibration/formal JSONL")
    try:
        result = run_hedge_formal(
            base_url=args.base_url,
            warmup_samples=load_jsonl(CALIBRATION)[:WARMUP_COUNT],
            formal_samples=load_jsonl(FORMAL),
            artifact_dir=args.artifact_dir,
        )
    except BaseException as error:
        failure_path = args.artifact_dir / "formal_client_failure.json"
        if not failure_path.exists():
            write_json(
                failure_path,
                {
                    "schema_version": 1,
                    "authorized_phase": "P07",
                    "status": "FAIL",
                    "arm": "hedge",
                    "error_type": type(error).__name__,
                    "error": repr(error),
                },
                immutable=True,
            )
        raise
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
