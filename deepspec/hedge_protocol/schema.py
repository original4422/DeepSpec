"""Validation for response metadata and speculative-decoding counters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .config import (
    COUNTER_SCHEMA_VERSION,
    PROPOSAL_WIDTH,
)


class ResponseSchemaError(ValueError):
    """The server response cannot support an auditable protocol record."""


@dataclass(frozen=True)
class ParsedResponse:
    model_text: str
    output_token_ids: list[int]
    completion_tokens: int
    acceptance_counters: dict[str, Any] | None
    hedge_counters: dict[str, Any] | None


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResponseSchemaError(f"{field} must be a non-negative integer")
    return value


def _optional_nonnegative_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, field=field)


def validate_acceptance_counters(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResponseSchemaError("acceptance_counters must be an object")
    required = {
        "schema_version",
        "proposal_count",
        "draft_tokens_proposed",
        "accepted_draft_tokens",
        "accepted_draft_tokens_by_position",
        "acceptance_length_including_bonus_sum",
        "acceptance_length_including_bonus_count",
    }
    if set(value) != required:
        raise ResponseSchemaError(
            "acceptance_counters fields mismatch: "
            f"expected {sorted(required)}, got {sorted(value)}"
        )
    if value["schema_version"] != COUNTER_SCHEMA_VERSION:
        raise ResponseSchemaError("unsupported acceptance counter schema_version")
    proposal_count = _nonnegative_int(
        value["proposal_count"], field="proposal_count"
    )
    proposed = _nonnegative_int(
        value["draft_tokens_proposed"], field="draft_tokens_proposed"
    )
    accepted = _nonnegative_int(
        value["accepted_draft_tokens"], field="accepted_draft_tokens"
    )
    by_position = value["accepted_draft_tokens_by_position"]
    if (
        not isinstance(by_position, list)
        or len(by_position) != PROPOSAL_WIDTH
    ):
        raise ResponseSchemaError(
            "accepted_draft_tokens_by_position must have proposal width "
            f"{PROPOSAL_WIDTH}"
        )
    normalized_positions = [
        _nonnegative_int(item, field=f"accepted_draft_tokens_by_position[{index}]")
        for index, item in enumerate(by_position)
    ]
    if proposed > proposal_count * PROPOSAL_WIDTH:
        raise ResponseSchemaError(
            "draft_tokens_proposed exceeds proposal_count * proposal width"
        )
    if accepted > proposed:
        raise ResponseSchemaError(
            "accepted_draft_tokens exceeds draft_tokens_proposed"
        )
    if sum(normalized_positions) != accepted:
        raise ResponseSchemaError(
            "accepted_draft_tokens_by_position sum does not match accepted total"
        )
    if any(item > proposal_count for item in normalized_positions):
        raise ResponseSchemaError(
            "accepted count at a position exceeds proposal_count"
        )
    length_sum = _optional_nonnegative_int(
        value["acceptance_length_including_bonus_sum"],
        field="acceptance_length_including_bonus_sum",
    )
    length_count = _optional_nonnegative_int(
        value["acceptance_length_including_bonus_count"],
        field="acceptance_length_including_bonus_count",
    )
    if (length_sum is None) != (length_count is None):
        raise ResponseSchemaError(
            "acceptance length sum/count must both be null or both be integers"
        )
    return {
        "schema_version": COUNTER_SCHEMA_VERSION,
        "proposal_count": proposal_count,
        "draft_tokens_proposed": proposed,
        "accepted_draft_tokens": accepted,
        "accepted_draft_tokens_by_position": normalized_positions,
        "acceptance_length_including_bonus_sum": length_sum,
        "acceptance_length_including_bonus_count": length_count,
    }


def validate_hedge_counters(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResponseSchemaError("hedge_counters must be an object")
    integer_fields = (
        "runtime_calls",
        "relaxed_tokens",
        "budget_hit_requests",
        "cap_bound_blocks",
        "requests_initialized",
        "requests_finalized",
        "requests_aborted",
        "slot_resets",
        "active_request_states",
        "state_leaks",
    )
    required = {"schema_version", "budget_spent", *integer_fields}
    if set(value) != required:
        raise ResponseSchemaError(
            "hedge_counters fields mismatch: "
            f"expected {sorted(required)}, got {sorted(value)}"
        )
    if value["schema_version"] != COUNTER_SCHEMA_VERSION:
        raise ResponseSchemaError("unsupported HEDGE counter schema_version")
    normalized: dict[str, Any] = {"schema_version": COUNTER_SCHEMA_VERSION}
    for field in integer_fields:
        normalized[field] = _nonnegative_int(value[field], field=field)
    if normalized["budget_hit_requests"] not in (0, 1):
        raise ResponseSchemaError("budget_hit_requests must be 0 or 1")
    spent = value["budget_spent"]
    if isinstance(spent, bool) or not isinstance(spent, (int, float)):
        raise ResponseSchemaError("budget_spent must be a finite number")
    spent_float = float(spent)
    if not math.isfinite(spent_float) or spent_float < 0:
        raise ResponseSchemaError("budget_spent must be finite and non-negative")
    normalized["budget_spent"] = spent_float
    return normalized


def parse_chat_response(response: Any) -> ParsedResponse:
    """Validate and extract the canonical OpenAI chat response seam."""

    if not isinstance(response, Mapping):
        raise ResponseSchemaError("response must be an object")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ResponseSchemaError("response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise ResponseSchemaError("choice must be an object")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ResponseSchemaError("choice.message must be an object")
    model_text = message.get("content")
    if not isinstance(model_text, str) or not model_text:
        raise ResponseSchemaError("choice.message.content must be non-empty")
    meta_info = choice.get("meta_info")
    if not isinstance(meta_info, Mapping):
        raise ResponseSchemaError(
            "choices[0].meta_info is required for output token IDs"
        )
    token_ids = meta_info.get("output_token_ids")
    if not isinstance(token_ids, list) or not token_ids:
        raise ResponseSchemaError(
            "choices[0].meta_info.output_token_ids must be a non-empty array"
        )
    normalized_ids: list[int] = []
    for index, token_id in enumerate(token_ids):
        if (
            isinstance(token_id, bool)
            or not isinstance(token_id, int)
            or token_id < 0
        ):
            raise ResponseSchemaError(
                f"output_token_ids[{index}] must be a non-negative integer"
            )
        normalized_ids.append(token_id)
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        raise ResponseSchemaError("response.usage must be an object")
    completion_tokens = _nonnegative_int(
        usage.get("completion_tokens"), field="usage.completion_tokens"
    )
    if completion_tokens != len(normalized_ids):
        raise ResponseSchemaError(
            "usage.completion_tokens does not equal output token ID count"
        )
    acceptance = meta_info.get("acceptance_counters")
    hedge = meta_info.get("hedge_counters")
    return ParsedResponse(
        model_text=model_text,
        output_token_ids=normalized_ids,
        completion_tokens=completion_tokens,
        acceptance_counters=(
            None
            if acceptance is None
            else validate_acceptance_counters(acceptance)
        ),
        hedge_counters=(
            None if hedge is None else validate_hedge_counters(hedge)
        ),
    )
