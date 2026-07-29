#!/usr/bin/env python3
"""Run one fail-closed P06 native warmup plus formal-500 arm."""

from __future__ import annotations

import argparse
import datetime as dt
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

from deepspec.hedge_protocol.config import (  # noqa: E402
    DEFAULT_MODEL,
    FORMAL_COUNT,
    WARMUP_COUNT,
    fingerprint_document,
)
from deepspec.hedge_protocol.io import (  # noqa: E402
    load_jsonl,
    sha256_file,
    write_json,
)
from deepspec.hedge_protocol.runner import ProtocolRunner  # noqa: E402
from deepspec.hedge_protocol.schema import (  # noqa: E402
    validate_acceptance_counters,
)
from deepspec.hedge_protocol.summary import recompute_summary  # noqa: E402
from hedge_dspark_p04_client import (  # noqa: E402
    SERVER_FIELDS,
    _NoProxyJsonGet,
    wait_ready,
)
from hedge_dspark_p05_client import _NoProxyJsonPost  # noqa: E402
from hedge_dspark_p06_prepare import (  # noqa: E402
    CALIBRATION,
    FORMAL,
    validate_formal_datasets,
)


JsonGet = Callable[[str, float], Mapping[str, Any]]
JsonPost = Callable[[str, Mapping[str, Any], float], Any]
CounterClear = Callable[[], Mapping[str, Any]]
SnapshotValidator = Callable[
    [Mapping[str, Any], bool, bool], Mapping[str, Any]
]
CONTROL_HTTP_TIMEOUT_SECONDS = 10.0
CLEAR_TIMEOUT_SECONDS = 120.0
CLEAR_POLL_SECONDS = 1.0
OUTPUT_NAMES = (
    "warmup_outputs.jsonl",
    "formal_outputs.jsonl",
    "pre_formal_clear.json",
    "formal_timing.json",
    "acceptance_summary.json",
    "answer_summary.json",
    "hedge_counters.json",
)
ZERO_SCALAR_FIELDS = (
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
SPEC_FIELDS = (
    "spec_verify_ct",
    "spec_num_proposed_drafts",
    "spec_proposed_drafts",
    "spec_num_correct_drafts",
    "spec_accepted_drafts",
    "spec_correct_drafts_histogram",
    "spec_accept_histogram",
    "spec_accept_rate",
    "spec_accept_length",
    "completion_tokens",
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _nonnegative_number(value: Any, *, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{field} must be a finite non-negative number")
    return float(value)


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def normalize_spec_acceptance(
    meta_info: Mapping[str, Any],
    *,
    explicit_acceptance: Mapping[str, Any] | None = None,
    completion_tokens: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize SGLang spec_* metadata without mutating the raw response."""

    if not isinstance(meta_info, Mapping):
        raise ValueError("SGLang meta_info must be an object")
    missing = [field for field in SPEC_FIELDS if field not in meta_info]
    if missing:
        raise ValueError(
            "SGLang speculative metadata is incomplete: " + ", ".join(missing)
        )
    proposals = _nonnegative_int(
        meta_info["spec_verify_ct"], field="spec_verify_ct"
    )
    proposed = _nonnegative_int(
        meta_info["spec_num_proposed_drafts"],
        field="spec_num_proposed_drafts",
    )
    proposed_alias = _nonnegative_int(
        meta_info["spec_proposed_drafts"],
        field="spec_proposed_drafts",
    )
    accepted_reported = _nonnegative_int(
        meta_info["spec_num_correct_drafts"],
        field="spec_num_correct_drafts",
    )
    accepted_alias = _nonnegative_int(
        meta_info["spec_accepted_drafts"],
        field="spec_accepted_drafts",
    )
    histogram_raw = meta_info["spec_correct_drafts_histogram"]
    accept_histogram_raw = meta_info["spec_accept_histogram"]
    if not isinstance(histogram_raw, list) or len(histogram_raw) != 6:
        raise ValueError(
            "spec_correct_drafts_histogram must contain lengths 0 through 5"
        )
    if not isinstance(accept_histogram_raw, list):
        raise ValueError("spec_accept_histogram must be an array")
    histogram = [
        _nonnegative_int(value, field=f"spec_correct_drafts_histogram[{index}]")
        for index, value in enumerate(histogram_raw)
    ]
    accept_histogram = [
        _nonnegative_int(value, field=f"spec_accept_histogram[{index}]")
        for index, value in enumerate(accept_histogram_raw)
    ]
    derived_proposed = proposals * 5
    derived_accepted = sum(
        accepted_length * count
        for accepted_length, count in enumerate(histogram)
    )
    by_position = [
        sum(histogram[position + 1 :]) for position in range(5)
    ]
    metadata_completion = _nonnegative_int(
        meta_info["completion_tokens"], field="meta_info.completion_tokens"
    )
    if completion_tokens is not None:
        completion_tokens = _nonnegative_int(
            completion_tokens, field="completion_tokens"
        )
        if completion_tokens != metadata_completion:
            raise ValueError(
                "meta_info.completion_tokens disagrees with response usage"
            )
    bonus_tokens = metadata_completion - derived_accepted
    if bonus_tokens < 0:
        raise ValueError(
            "accepted draft tokens exceed response completion tokens"
        )
    including_bonus = metadata_completion
    rate = _nonnegative_number(
        meta_info["spec_accept_rate"], field="spec_accept_rate"
    )
    length = _nonnegative_number(
        meta_info["spec_accept_length"], field="spec_accept_length"
    )
    expected_rate = (
        derived_accepted / derived_proposed if derived_proposed else 0.0
    )
    expected_length = metadata_completion / proposals if proposals else 0.0
    checks = {
        "histogram_count_equals_proposal_count": sum(histogram) == proposals,
        "proposed_equals_width_times_proposals": proposed == derived_proposed,
        "proposed_alias_matches": proposed_alias == proposed,
        "accepted_equals_histogram_weighted_sum": (
            accepted_reported == derived_accepted
        ),
        "accepted_alias_matches": accepted_alias == derived_accepted,
        "accept_histogram_matches_correct_histogram": (
            accept_histogram == histogram
        ),
        "accept_rate_matches": math.isclose(
            rate, expected_rate, rel_tol=1e-12, abs_tol=1e-12
        ),
        "accept_length_including_bonus_matches": math.isclose(
            length, expected_length, rel_tol=1e-12, abs_tol=1e-12
        ),
        "completion_tokens_cover_accepted_drafts": (
            metadata_completion >= derived_accepted
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        details = {
            "spec_verify_ct": proposals,
            "spec_num_proposed_drafts": proposed,
            "derived_proposed": derived_proposed,
            "spec_num_correct_drafts": accepted_reported,
            "derived_accepted": derived_accepted,
            "histogram": histogram,
            "failed_checks": failed,
        }
        raise ValueError(f"SGLang spec_* cross-check failed: {details}")
    normalized = validate_acceptance_counters(
        {
            "schema_version": 1,
            "proposal_count": proposals,
            "draft_tokens_proposed": proposed,
            "accepted_draft_tokens": derived_accepted,
            "accepted_draft_tokens_by_position": by_position,
            "acceptance_length_including_bonus_sum": including_bonus,
            "acceptance_length_including_bonus_count": proposals,
        }
    )
    if explicit_acceptance is not None:
        explicit = validate_acceptance_counters(explicit_acceptance)
        if explicit != normalized:
            raise ValueError(
                "explicit acceptance_counters disagree with normalized spec_*"
            )
        checks["explicit_acceptance_counters_match"] = True
    evidence = {
        "schema_version": 1,
        "source": "choices[0].meta_info.spec_*",
        "proposal_width": 5,
        "proposal_count": proposals,
        "draft_tokens_proposed": proposed,
        "accepted_draft_tokens": derived_accepted,
        "accepted_draft_tokens_by_position": by_position,
        "bonus_tokens": bonus_tokens,
        "bonus_minus_proposals": bonus_tokens - proposals,
        "accepted_tokens_including_bonus": including_bonus,
        "acceptance_length_including_bonus_sum": including_bonus,
        "acceptance_length_including_bonus_count": proposals,
        "accepted_draft_tokens_formula": (
            "sum(i * histogram[i] for i in 0..5)"
        ),
        "accepted_by_position_formula": (
            "position[j] = sum(histogram[j+1:]) for j in 0..4"
        ),
        "bonus_formula": "completion_tokens - accepted_draft_tokens",
        "histogram": histogram,
        "raw_spec_fields": {
            field: meta_info[field] for field in SPEC_FIELDS
        },
        "cross_checks": checks,
    }
    return normalized, evidence


class P06ProtocolRunner(ProtocolRunner):
    """Protocol runner that normalizes the actual SGLang speculative seam."""

    def run_one(
        self,
        sample: Mapping[str, Any],
        *,
        cohort: str,
        cohort_position: int,
    ) -> dict[str, Any]:
        record = super().run_one(
            sample, cohort=cohort, cohort_position=cohort_position
        )
        if record["terminal_status"] != "succeeded":
            record["spec_acceptance"] = None
            return record
        successful = [
            attempt
            for attempt in record["attempts"]
            if attempt.get("status") == "success"
        ]
        if len(successful) != 1:
            raise ValueError(
                "successful request must retain exactly one successful attempt"
            )
        raw_response = successful[0].get("raw_response")
        choices = (
            raw_response.get("choices")
            if isinstance(raw_response, Mapping)
            else None
        )
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        meta_info = (
            choice.get("meta_info") if isinstance(choice, Mapping) else None
        )
        normalized, evidence = normalize_spec_acceptance(
            meta_info,
            explicit_acceptance=record.get("acceptance_counters"),
            completion_tokens=record.get("completion_tokens"),
        )
        record["acceptance_counters"] = normalized
        record["spec_acceptance"] = evidence
        return record


def validate_native_server_snapshot(
    server_info: Mapping[str, Any],
    *,
    require_exact_zero: bool,
    allow_active: bool = False,
) -> dict[str, Any]:
    """Validate the native-off DSpark server seam and optional exact zero."""

    if not isinstance(server_info, Mapping):
        raise ValueError("/server_info response must be an object")
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
    dirty_snapshots: list[dict[str, Any]] = []
    active_request_states = 0
    state_leaks = 0
    proposals = 0
    for snapshot_index, state in enumerate(internal_states):
        if not isinstance(state, Mapping):
            raise ValueError(
                f"internal_states[{snapshot_index}] must be an object"
            )
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
            normalized.get("mode") != "disabled"
            or normalized.get("experiment_switches")
            != {
                "HEDGE_ENABLED": 0,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
            }
            or normalized.get("config") is not None
            or normalized.get("gamma") != 5
            or normalized.get("verify_num_draft_tokens") != 6
        ):
            raise ValueError(
                f"native HEDGE snapshot {snapshot_index} identity mismatch"
            )
        dirty: dict[str, Any] = {}
        for field in ZERO_SCALAR_FIELDS:
            numeric = _nonnegative_number(
                normalized.get(field), field=field
            )
            if numeric != 0.0:
                dirty[field] = normalized[field]
        positions = normalized.get(
            "hedge_accepted_draft_tokens_by_position"
        )
        if (
            not isinstance(positions, list)
            or len(positions) != 5
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                for value in positions
            )
        ):
            raise ValueError(
                f"native HEDGE snapshot {snapshot_index} positions malformed"
            )
        if positions != [0] * 5:
            dirty["hedge_accepted_draft_tokens_by_position"] = positions
        remaining = normalized.get("remaining_budget_by_request")
        trace = normalized.get("strict_rejection_trace")
        if not isinstance(remaining, list) or not isinstance(trace, list):
            raise ValueError(
                f"native HEDGE snapshot {snapshot_index} list fields malformed"
            )
        if remaining:
            dirty["remaining_budget_by_request"] = remaining
        if trace:
            dirty["strict_rejection_trace_count"] = len(trace)
        if dirty:
            dirty_snapshots.append(
                {"snapshot_index": snapshot_index, "fields": dirty}
            )
        active_request_states += int(normalized["active_request_states"])
        state_leaks += int(normalized["state_leaks"])
        proposals += int(normalized["proposals"])
        snapshots.append(normalized)
    if not allow_active and (active_request_states != 0 or state_leaks != 0):
        raise ValueError("native formal snapshot leaks request state")
    if require_exact_zero and dirty_snapshots:
        raise ValueError(
            "native formal snapshot is not exact zero: "
            f"{dirty_snapshots}"
        )
    return {
        "schema_version": 1,
        "authorized_phase": "P06",
        "status": "PASS",
        "arm": "native",
        "source_endpoint": "/server_info",
        "server_config": {
            key: server_info[key] for key in SERVER_FIELDS
        },
        "hedge_mode": "disabled",
        "hedge_enabled": False,
        "hedge_config": None,
        "snapshot_count": len(snapshots),
        "hedge_snapshots": snapshots,
        "proposal_count": proposals,
        "active_request_states": active_request_states,
        "state_leaks": state_leaks,
        "quiescent": active_request_states == 0 and state_leaks == 0,
        "exact_zero": not dirty_snapshots,
        "dirty_snapshots": dirty_snapshots,
    }


def clear_formal_evidence(
    *,
    authorized_phase: str,
    arm: str,
    snapshot_validator: SnapshotValidator,
    base_url: str,
    server_info_get: JsonGet | None = None,
    internal_state_post: JsonPost | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    timeout_seconds: float = CLEAR_TIMEOUT_SECONDS,
    poll_seconds: float = CLEAR_POLL_SECONDS,
) -> dict[str, Any]:
    """Wait for quiescence, clear counters once, and prove exact zero."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or not 0 < float(timeout_seconds) <= 300
    ):
        raise ValueError("clear timeout must be in (0, 300] seconds")
    if (
        isinstance(poll_seconds, bool)
        or not isinstance(poll_seconds, (int, float))
        or not math.isfinite(float(poll_seconds))
        or not 0 < float(poll_seconds) <= float(timeout_seconds)
    ):
        raise ValueError("clear poll must be in (0, timeout] seconds")
    getter = server_info_get or _NoProxyJsonGet()
    poster = internal_state_post or _NoProxyJsonPost()
    started_ns = monotonic_ns()
    if (
        isinstance(started_ns, bool)
        or not isinstance(started_ns, int)
        or started_ns < 0
    ):
        raise ValueError("monotonic_ns must return a non-negative integer")
    deadline_ns = started_ns + int(float(timeout_seconds) * 1_000_000_000)
    server_info_url = base_url.rstrip("/") + "/server_info"
    clear_url = base_url.rstrip("/") + "/set_internal_state"
    request_body = {"server_args": {"dspark_clear_info_records": 1}}
    polls: list[dict[str, Any]] = []
    clear_attempts: list[dict[str, Any]] = []

    def remaining_seconds() -> float:
        now = monotonic_ns()
        if isinstance(now, bool) or not isinstance(now, int) or now < started_ns:
            raise ValueError("monotonic_ns returned an invalid value")
        return (deadline_ns - now) / 1_000_000_000

    def poll(stage: str) -> dict[str, Any]:
        remaining = remaining_seconds()
        if remaining <= 0:
            raise TimeoutError("pre-formal clear handshake timed out")
        raw = getter(
            server_info_url,
            min(CONTROL_HTTP_TIMEOUT_SECONDS, remaining),
        )
        observation = dict(snapshot_validator(raw, False, True))
        polls.append(
            {
                "poll_ordinal": len(polls) + 1,
                "stage": stage,
                "active_request_states": observation[
                    "active_request_states"
                ],
                "state_leaks": observation["state_leaks"],
                "quiescent": observation["quiescent"],
                "exact_zero": observation["exact_zero"],
                "dirty_snapshots": observation["dirty_snapshots"],
            }
        )
        return observation

    try:
        while True:
            observation = poll("wait_quiescent")
            if observation["quiescent"]:
                break
            remaining = remaining_seconds()
            if remaining <= 0:
                raise TimeoutError("pre-formal quiescence timed out")
            sleeper(min(float(poll_seconds), remaining))

        remaining = remaining_seconds()
        if remaining <= 0:
            raise TimeoutError("pre-formal clear timed out before POST")
        response = poster(
            clear_url,
            request_body,
            min(CONTROL_HTTP_TIMEOUT_SECONDS, remaining),
        )
        clear_attempts.append(
            {
                "clear_ordinal": 1,
                "request_body": request_body,
                "response": response,
            }
        )
        if response != [True]:
            raise ValueError(
                "/set_internal_state must return exact DP=1 success list [true]"
            )
        while True:
            observation = poll("verify_clear")
            if observation["exact_zero"]:
                finished_ns = monotonic_ns()
                return {
                    "schema_version": 1,
                    "authorized_phase": authorized_phase,
                    "status": "PASS",
                    "arm": arm,
                    "started_monotonic_ns": started_ns,
                    "finished_monotonic_ns": finished_ns,
                    "timeout_seconds": float(timeout_seconds),
                    "poll_seconds": float(poll_seconds),
                    "http_timeout_seconds": CONTROL_HTTP_TIMEOUT_SECONDS,
                    "poll_count": len(polls),
                    "clear_attempt_count": len(clear_attempts),
                    "verified_snapshot_count": observation["snapshot_count"],
                    "quiescent": observation["quiescent"],
                    "exact_zero": observation["exact_zero"],
                    "polls": polls,
                    "clear_attempts": clear_attempts,
                }
            remaining = remaining_seconds()
            if remaining <= 0:
                raise TimeoutError("pre-formal exact-zero proof timed out")
            sleeper(min(float(poll_seconds), remaining))
    except BaseException as error:
        evidence = {
            "schema_version": 1,
            "authorized_phase": authorized_phase,
            "status": "FAIL",
            "arm": arm,
            "started_monotonic_ns": started_ns,
            "finished_monotonic_ns": monotonic_ns(),
            "timeout_seconds": float(timeout_seconds),
            "poll_seconds": float(poll_seconds),
            "http_timeout_seconds": CONTROL_HTTP_TIMEOUT_SECONDS,
            "poll_count": len(polls),
            "clear_attempt_count": len(clear_attempts),
            "exact_zero": False,
            "polls": polls,
            "clear_attempts": clear_attempts,
            "error_type": type(error).__name__,
            "error": str(error),
        }
        error.pre_formal_clear_evidence = evidence
        raise


def clear_native_formal_evidence(
    *,
    base_url: str,
    server_info_get: JsonGet | None = None,
    internal_state_post: JsonPost | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    timeout_seconds: float = CLEAR_TIMEOUT_SECONDS,
    poll_seconds: float = CLEAR_POLL_SECONDS,
) -> dict[str, Any]:
    """Preserve the strict P06 native-off clear seam."""

    return clear_formal_evidence(
        authorized_phase="P06",
        arm="native",
        snapshot_validator=lambda payload, exact, active: (
            validate_native_server_snapshot(
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


def _seconds(start_ns: int, end_ns: int) -> float:
    if end_ns <= start_ns:
        raise ValueError("formal monotonic boundary must have positive duration")
    return (end_ns - start_ns) / 1_000_000_000


def _ensure_outputs_absent(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        name for name in OUTPUT_NAMES if (artifact_dir / name).exists()
    ]
    if existing:
        raise FileExistsError(
            "refusing formal resume/overwrite; existing artifacts: "
            + ", ".join(existing)
        )


def aggregate_spec_acceptance(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Independently aggregate normalized per-response spec evidence."""

    proposal_count = 0
    proposed = 0
    accepted = 0
    bonus = 0
    including_bonus = 0
    by_position = [0] * 5
    successful_records = 0
    for position, record in enumerate(records):
        if record.get("terminal_status") != "succeeded":
            _require(
                record.get("spec_acceptance") is None,
                f"failed record {position} has speculative acceptance evidence",
            )
            continue
        evidence = record.get("spec_acceptance")
        if not isinstance(evidence, Mapping):
            raise ValueError(
                f"successful record {position} lacks spec_* normalization"
            )
        checks = evidence.get("cross_checks")
        _require(
            isinstance(checks, Mapping)
            and bool(checks)
            and all(value is True for value in checks.values()),
            f"record {position} has a failed spec_* cross-check",
        )
        positions = evidence.get("accepted_draft_tokens_by_position")
        _require(
            isinstance(positions, list) and len(positions) == 5,
            f"record {position} has invalid per-position acceptance",
        )
        successful_records += 1
        proposal_count += _nonnegative_int(
            evidence.get("proposal_count"), field="proposal_count"
        )
        proposed += _nonnegative_int(
            evidence.get("draft_tokens_proposed"),
            field="draft_tokens_proposed",
        )
        accepted += _nonnegative_int(
            evidence.get("accepted_draft_tokens"),
            field="accepted_draft_tokens",
        )
        bonus += _nonnegative_int(
            evidence.get("bonus_tokens"), field="bonus_tokens"
        )
        including_bonus += _nonnegative_int(
            evidence.get("accepted_tokens_including_bonus"),
            field="accepted_tokens_including_bonus",
        )
        for index, value in enumerate(positions):
            by_position[index] += _nonnegative_int(
                value,
                field=f"accepted_draft_tokens_by_position[{index}]",
            )
    _require(
        proposed == proposal_count * 5,
        "aggregate proposed drafts do not equal width * proposal count",
    )
    _require(
        sum(by_position) == accepted,
        "aggregate per-position accepted drafts do not equal accepted total",
    )
    _require(
        including_bonus == accepted + bonus,
        "aggregate including-bonus total is inconsistent",
    )
    return {
        "schema_version": 1,
        "source": "per-response choices[0].meta_info.spec_*",
        "records_with_spec_metadata": successful_records,
        "proposal_width": 5,
        "proposal_count": proposal_count,
        "draft_tokens_proposed": proposed,
        "accepted_draft_tokens": accepted,
        "accepted_draft_tokens_by_position": by_position,
        "bonus_tokens": bonus,
        "bonus_minus_proposals": bonus - proposal_count,
        "accepted_tokens_including_bonus": including_bonus,
        "acceptance_length_including_bonus_sum": including_bonus,
        "acceptance_length_including_bonus_count": proposal_count,
        "mean_accepted_draft_tokens_per_proposal": (
            accepted / proposal_count if proposal_count else None
        ),
        "mean_acceptance_length_including_bonus": (
            including_bonus / proposal_count if proposal_count else None
        ),
        "formulas": {
            "proposed": "5 * spec_verify_ct",
            "accepted": "sum(i * histogram[i] for i in 0..5)",
            "by_position": (
                "position[j] = sum(histogram[j+1:]) for j in 0..4"
            ),
            "bonus": "completion_tokens - accepted_draft_tokens",
        },
    }


def run_formal_arm(
    *,
    authorized_phase: str,
    arm: str,
    final_snapshot_validator: Callable[
        [Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
    ],
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
    """Run one frozen 10-warmup plus formal-500 protocol."""

    _require(
        (authorized_phase, arm) in {("P06", "native"), ("P07", "hedge")},
        "formal arm identity must be P06/native or P07/hedge",
    )
    _ensure_outputs_absent(artifact_dir)
    if len(warmup_samples) != WARMUP_COUNT:
        raise ValueError(
            f"{authorized_phase} requires exactly {WARMUP_COUNT} warmups"
        )
    if len(formal_samples) != FORMAL_COUNT:
        raise ValueError(
            f"{authorized_phase} requires exactly {FORMAL_COUNT} formal samples"
        )
    runner = P06ProtocolRunner(
        base_url=base_url,
        model=DEFAULT_MODEL,
        transport=transport,
        sleeper=sleeper,
        clock_ns=clock_ns,
    )
    warmup_path = artifact_dir / "warmup_outputs.jsonl"
    formal_path = artifact_dir / "formal_outputs.jsonl"
    timing_path = artifact_dir / "formal_timing.json"
    answer_path = artifact_dir / "answer_summary.json"
    acceptance_path = artifact_dir / "acceptance_summary.json"
    clear_path = artifact_dir / "pre_formal_clear.json"
    counters_path = artifact_dir / "hedge_counters.json"

    started_at_utc = _utc_now()
    warmup_records = runner.run_cohort(
        warmup_samples,
        cohort="warmup",
        output_path=warmup_path,
        expected_count=WARMUP_COUNT,
    )
    warmup_summary = recompute_summary(
        warmup_records,
        expected_count=WARMUP_COUNT,
        expected_cohort="warmup",
    )
    _require(
        authorized_phase == "P06" or counter_clear is not None,
        "P07 must provide the HEDGE-on clear validator",
    )
    clear_operation = counter_clear or (
        lambda: clear_native_formal_evidence(
            base_url=base_url,
            server_info_get=server_info_get,
            internal_state_post=internal_state_post,
            sleeper=sleeper,
            monotonic_ns=clock_ns,
        )
    )
    try:
        clear_evidence = dict(clear_operation())
    except BaseException as error:
        evidence = getattr(error, "pre_formal_clear_evidence", None)
        if isinstance(evidence, Mapping):
            write_json(clear_path, dict(evidence), immutable=True)
        raise
    write_json(clear_path, clear_evidence, immutable=True)
    if (
        clear_evidence.get("status") != "PASS"
        or clear_evidence.get("exact_zero") is not True
    ):
        raise ValueError("pre-formal counter clear is not exact PASS")

    formal_records = runner.run_cohort(
        formal_samples,
        cohort="formal",
        output_path=formal_path,
        expected_count=FORMAL_COUNT,
    )
    formal_start = formal_records[0].get("request_started_monotonic_ns")
    formal_end = formal_records[-1].get("terminal_monotonic_ns")
    if (
        isinstance(formal_start, bool)
        or isinstance(formal_end, bool)
        or not isinstance(formal_start, int)
        or not isinstance(formal_end, int)
    ):
        raise ValueError("formal records lack integer monotonic boundaries")
    clear_finished = clear_evidence.get("finished_monotonic_ns")
    if (
        isinstance(clear_finished, bool)
        or not isinstance(clear_finished, int)
        or clear_finished > formal_start
    ):
        raise ValueError("formal timing starts before counter clear completed")
    timing = {
        "schema_version": 1,
        "authorized_phase": authorized_phase,
        "arm": arm,
        "clock": "time.monotonic_ns",
        "warmup_record_count": WARMUP_COUNT,
        "warmup_terminal_requests": warmup_summary["terminal_requests"],
        "warmup_included": False,
        "formal_record_count": FORMAL_COUNT,
        "formal_start_monotonic_ns": formal_start,
        "formal_end_monotonic_ns": formal_end,
        "timed_wall_seconds": _seconds(formal_start, formal_end),
        "start_boundary": "immediately before formal request 1 is issued",
        "end_boundary": "immediately after formal request 500 is terminal",
        "retry_time_included": True,
        "single_sequential_pass": True,
        "warmup_output_sha256": sha256_file(warmup_path),
        "formal_output_sha256": sha256_file(formal_path),
        "pre_formal_clear_sha256": sha256_file(clear_path),
    }
    write_json(timing_path, timing, immutable=True)
    summary = recompute_summary(
        formal_records,
        timing=timing,
        expected_count=FORMAL_COUNT,
        expected_cohort="formal",
    )
    summary.update(
        authorized_phase=authorized_phase,
        arm=arm,
        source_artifacts={
            "formal_outputs_sha256": sha256_file(formal_path),
            "formal_timing_sha256": sha256_file(timing_path),
            "pre_formal_clear_sha256": sha256_file(clear_path),
        },
    )
    summary["fingerprint_sha256"] = fingerprint_document(summary)
    write_json(answer_path, summary, immutable=True)
    spec_summary = aggregate_spec_acceptance(formal_records)
    _require(
        spec_summary["proposal_count"]
        == summary["acceptance"]["proposal_count"]
        and spec_summary["draft_tokens_proposed"]
        == summary["acceptance"]["draft_tokens_proposed"]
        and spec_summary["accepted_draft_tokens"]
        == summary["acceptance"]["accepted_draft_tokens"]
        and spec_summary["accepted_draft_tokens_by_position"]
        == summary["acceptance"]["accepted_draft_tokens_by_position"]
        and spec_summary["acceptance_length_including_bonus_sum"]
        == summary["acceptance"]["acceptance_length_including_bonus_sum"]
        and spec_summary["acceptance_length_including_bonus_count"]
        == summary["acceptance"]["acceptance_length_including_bonus_count"],
        "spec_* aggregation disagrees with protocol acceptance summary",
    )
    acceptance_summary = {
        "schema_version": 1,
        "authorized_phase": authorized_phase,
        "arm": arm,
        "acceptance": summary["acceptance"],
        "sglang_spec_normalization": spec_summary,
        "hedge": summary["hedge"],
        "source_artifacts": summary["source_artifacts"],
    }
    acceptance_summary["fingerprint_sha256"] = fingerprint_document(
        acceptance_summary
    )
    write_json(acceptance_path, acceptance_summary, immutable=True)

    getter = server_info_get or _NoProxyJsonGet()
    server_info = getter(
        base_url.rstrip("/") + "/server_info",
        300.0,
    )
    counters = dict(final_snapshot_validator(server_info, summary))
    counters["fetched_at_utc"] = _utc_now()
    counters["formal_request_interval_monotonic_ns"] = {
        "start": formal_start,
        "end": formal_end,
    }
    write_json(counters_path, counters, immutable=True)
    return {
        "schema_version": 1,
        "authorized_phase": authorized_phase,
        "status": "PASS",
        "arm": arm,
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "warmup_count": WARMUP_COUNT,
        "formal_count": FORMAL_COUNT,
        "terminal_requests": summary["terminal_requests"],
        "success_requests": summary["success_requests"],
        "failed_requests": summary["failed_requests"],
        "retry_attempts": summary["retry_attempts"],
        "completion_tokens": summary["completion_tokens"],
        "timed_wall_seconds": timing["timed_wall_seconds"],
        "end_to_end_output_tps": summary["timing"][
            "end_to_end_output_tps"
        ],
    }


def run_native_formal(
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
    """Preserve the strict native-only P06 public interface."""

    return run_formal_arm(
        authorized_phase="P06",
        arm="native",
        final_snapshot_validator=lambda payload, _summary: (
            validate_native_server_snapshot(
                payload, require_exact_zero=False
            )
        ),
        base_url=base_url,
        warmup_samples=warmup_samples,
        formal_samples=formal_samples,
        artifact_dir=artifact_dir,
        transport=transport,
        server_info_get=server_info_get,
        internal_state_post=internal_state_post,
        sleeper=sleeper,
        clock_ns=clock_ns,
        counter_clear=counter_clear,
    )


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
    if args.command == "run":
        dataset = validate_formal_datasets()
        if (
            args.calibration.resolve()
            != Path(dataset["calibration_jsonl"]).resolve()
            or args.formal.resolve()
            != Path(dataset["formal_jsonl"]).resolve()
        ):
            parser.error("P06 must use the immutable P01 calibration/formal JSONL")
        try:
            result = run_native_formal(
                base_url=args.base_url,
                warmup_samples=load_jsonl(CALIBRATION)[:WARMUP_COUNT],
                formal_samples=load_jsonl(FORMAL),
                artifact_dir=args.artifact_dir,
            )
        except BaseException as error:
            failure = {
                "schema_version": 1,
                "authorized_phase": "P06",
                "status": "FAIL",
                "arm": "native",
                "error_type": type(error).__name__,
                "error": repr(error),
            }
            failure_path = args.artifact_dir / "formal_client_failure.json"
            if not failure_path.exists():
                write_json(failure_path, failure, immutable=True)
            raise
        print(json.dumps(result, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
