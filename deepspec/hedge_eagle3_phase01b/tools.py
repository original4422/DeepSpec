"""Deterministic runner, calibration, reporting, and process ownership tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.error
import urllib.request


SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
TARGET_REVISION = "60d8d70770c6776ff598c94bb586a859a38244f1"
DRAFT_REVISION = "4c68aa4689d59cb1064f20abec7708174ee4613d"
TARGET_PATH = (
    "/mnt/hdfs/pengzegang/DeepSpec/models/"
    "deepseek-ai__DeepSeek-V4-Flash/snapshots/"
    f"huggingface-{TARGET_REVISION}"
)
DRAFT_PATH = (
    "/mnt/hdfs/pengzegang/DeepSpec/models/"
    "SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/snapshots/"
    f"huggingface-{DRAFT_REVISION}"
)
VENV = "/home/tiger/venvs/deepspec-hedge-v4-eagle3"
SOURCE_ROOT = "/home/tiger/src/sglang-hedge-v4-eagle3"
COMPAT_ROOT = (
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)
GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "max_tokens": 512,
    "chat_template_kwargs": {"enable_thinking": False},
    "return_meta_info": True,
    "logprobs": True,
    "top_logprobs": 0,
}


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_resolved_config(
    mode: str,
    *,
    gate: float | None = None,
) -> dict[str, Any]:
    """Build identical-shape native/B0/B+ resolved configurations."""

    if mode not in {"native", "B0", "B+"}:
        raise ValueError(f"unknown experiment mode: {mode}")
    if mode == "B+":
        if gate is None or not math.isfinite(gate) or gate <= 0:
            raise ValueError("B+ requires one finite positive calibrated gate")
        hedge = {
            "enabled": True,
            "risk_budget": float(gate),
            "gate": float(gate),
            "max_relaxed_mismatches_per_block": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 3,
        }
        hedge_mode = "enabled"
        hedge_config = {
            "B": float(gate),
            "g": float(gate),
            "m": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 3,
        }
    elif mode == "B0":
        hedge = {
            "enabled": True,
            "risk_budget": 0.0,
            "gate": 0.0,
            "max_relaxed_mismatches_per_block": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 3,
        }
        hedge_mode = "b0"
        hedge_config = {
            "B": 0.0,
            "g": 0.0,
            "m": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 3,
        }
    else:
        hedge = {
            "enabled": False,
            "risk_budget": None,
            "gate": None,
            "max_relaxed_mismatches_per_block": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 3,
        }
        hedge_mode = "disabled"
        hedge_config = None
    config: dict[str, Any] = {
        "schema_version": 1,
        "mode": mode,
        "proposal_tokens": 3,
        "internal_verify_width": 4,
        "lane": {
            "worker_id": "4099544",
            "gpu_model": "NVIDIA H20",
            "physical_gpu_indices": list(range(8)),
            "cuda_visible_devices": "0,1,2,3,4,5,6,7",
            "tp_size": 8,
            "http_port": 31001,
        },
        "source": {
            "sglang_base_commit": SGLANG_BASE,
            "sglang_source_root": SOURCE_ROOT,
            "venv": VENV,
            "final_commit": "90c8558721de37ed0dc12802f29253ba52b873bc",
        },
        "models": {
            "target": {
                "repo_id": "deepseek-ai/DeepSeek-V4-Flash",
                "revision": TARGET_REVISION,
                "path": TARGET_PATH,
            },
            "draft": {
                "repo_id": "SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1",
                "revision": DRAFT_REVISION,
                "path": DRAFT_PATH,
            },
        },
        "server": {
            "speculative_algorithm": "EAGLE3",
            "speculative_draft_attention_backend": "flashinfer",
            "speculative_num_steps": 3,
            "speculative_eagle_topk": 1,
            "speculative_num_draft_tokens": 4,
            "moe_runner_backend": "flashinfer_mxfp4",
            "context_length": 4096,
            "max_running_requests": 1,
            "mem_fraction_static": 0.60,
            "disable_cuda_graph": True,
            "disable_prefill_cuda_graph": True,
            "disable_draft_extend_cuda_graph": True,
            "disable_overlap_schedule": True,
            "disable_radix_cache": True,
        },
        "environment": {
            "SGLANG_DSV4_FP4_EXPERTS": "1",
            "SGLANG_DSV4_FP4_DEQUANT": None,
            "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
            "SGLANG_RAGGED_VERIFY_MODE": "static",
            "SGLANG_EAGLE3_V4_AUX_TRACE": "1",
            "SGLANG_EAGLE3_HEDGE_MODE": hedge_mode,
            "SGLANG_EAGLE3_HEDGE_CONFIG_JSON": (
                None
                if hedge_config is None
                else json.dumps(
                    hedge_config,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            ),
            "SGLANG_EAGLE3_HEDGE_TRACE_CAPACITY": "1024",
            "compat_root": COMPAT_ROOT,
            "cuda_home": (
                f"{VENV}/lib/python3.11/site-packages/nvidia/cu13"
            ),
            "library_precedence": [
                COMPAT_ROOT,
                f"{VENV}/lib/python3.11/site-packages/nvidia/*/lib",
                (
                    f"{VENV}/lib/python3.11/site-packages/"
                    "nvidia/cu13/lib64"
                ),
            ],
        },
        "request": {
            "messages": "from_gsm8k_split_manifest",
            "system_prompt": None,
            "generation": GENERATION,
            "sequential": True,
            "max_attempts_total": 3,
            "warmup_count": 10,
            "formal_count": 500,
            "require_proposal_trace": True,
            "trace_control": {
                "clear": "/set_internal_state",
                "drain": "/server_info",
                "dp_size": 1,
            },
        },
        "hedge": hedge,
    }
    config["config_sha256"] = canonical_sha256(config)
    return config


_NUMERIC = re.compile(
    r"(?<![\w.])[-+]?\s*\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*/\s*\d[\d,]*)?"
)


def normalize_numeric_answer(raw: str) -> str | None:
    """Normalize a finite integer/decimal/fraction without guessing."""

    value = raw.strip()
    value = value.replace("$", "").replace(",", "").replace(" ", "")
    value = value.rstrip(".;,:!?")
    if not value:
        return None
    try:
        if "/" in value:
            numerator, denominator = value.split("/", maxsplit=1)
            fraction = Fraction(Decimal(numerator)) / Fraction(
                Decimal(denominator)
            )
            if fraction.denominator == 1:
                return str(fraction.numerator)
            return f"{fraction.numerator}/{fraction.denominator}"
        decimal = Decimal(value)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None
    if not decimal.is_finite():
        return None
    if decimal == decimal.to_integral():
        return str(int(decimal))
    rendered = format(decimal.normalize(), "f").rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def _last_boxed(text: str) -> str | None:
    values: list[str] = []
    cursor = 0
    marker = r"\boxed{"
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            break
        content_start = start + len(marker)
        depth = 1
        index = content_start
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth == 0:
            values.append(text[content_start : index - 1])
            cursor = index
        else:
            cursor = content_start
    return values[-1] if values else None


def _last_numeric(text: str) -> str | None:
    matches = list(_NUMERIC.finditer(text))
    return matches[-1].group(0) if matches else None


def extract_reference_answer(answer: str) -> dict[str, Any]:
    """Extract only the canonical last GSM8K #### answer."""

    if "####" not in answer:
        return {
            "status": "parse_failure",
            "rule": "reference_last_hash",
            "raw": None,
            "normalized": None,
        }
    candidate = _last_numeric(answer.rsplit("####", maxsplit=1)[1])
    normalized = (
        normalize_numeric_answer(candidate) if candidate is not None else None
    )
    return {
        "status": "ok" if normalized is not None else "parse_failure",
        "rule": "reference_last_hash",
        "raw": candidate,
        "normalized": normalized,
    }


def extract_model_answer(text: str) -> dict[str, Any]:
    """Apply the fixed boxed/hash/final-answer/last-number precedence."""

    boxed = _last_boxed(text)
    candidates: list[tuple[str, str | None]] = [("last_boxed", boxed)]
    if "####" in text:
        candidates.append(
            ("last_hash", _last_numeric(text.rsplit("####", maxsplit=1)[1]))
        )
    final_matches = list(
        re.finditer(
            r"(?is)final\s+answer\s*(?:is|:|=)?\s*([^\n]+)",
            text,
        )
    )
    candidates.append(
        (
            "explicit_final_answer",
            (
                _last_numeric(final_matches[-1].group(1))
                if final_matches
                else None
            ),
        )
    )
    candidates.append(("last_numeric", _last_numeric(text)))
    for rule, candidate in candidates:
        if candidate is None:
            continue
        normalized = normalize_numeric_answer(candidate)
        if normalized is not None:
            return {
                "status": "ok",
                "rule": rule,
                "raw": candidate,
                "normalized": normalized,
            }
    return {
        "status": "parse_failure",
        "rule": None,
        "raw": None,
        "normalized": None,
    }


def answers_match(reference: str | None, model: str | None) -> bool:
    if reference is None or model is None:
        return False
    try:
        return Fraction(reference) == Fraction(model)
    except (ValueError, ZeroDivisionError):
        return reference == model


class TransportFailure(RuntimeError):
    """One bounded API attempt failed before a valid response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def urllib_json_transport(
    url: str,
    body: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=canonical_json_bytes(body),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # The experiment API is lane-local.  Do not let inherited HTTP_PROXY
    # settings redirect loopback requests away from the registered server.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        failure_body = error.read().decode("utf-8", errors="replace")
        raise TransportFailure(
            f"HTTP {error.code}",
            status_code=error.code,
            response_body=failure_body,
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TransportFailure(str(error)) from error
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise TransportFailure(
            "response is not valid JSON",
            response_body=payload,
        ) from error
    if not isinstance(value, dict):
        raise TransportFailure("response JSON is not an object")
    return value


def _response_fields(
    response: Mapping[str, Any],
) -> tuple[str, list[int], int]:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise TransportFailure("response does not have exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise TransportFailure("response choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(
        message.get("content"), str
    ):
        raise TransportFailure("response choice lacks message content")
    meta_info = choice.get("meta_info")
    candidates = [
        choice.get("token_ids"),
        message.get("token_ids"),
        response.get("token_ids"),
        (
            meta_info.get("output_token_ids")
            if isinstance(meta_info, dict)
            else None
        ),
        (
            response.get("meta_info", {}).get("output_token_ids")
            if isinstance(response.get("meta_info"), dict)
            else None
        ),
    ]
    token_ids: list[int] | None = None
    for candidate in candidates:
        if isinstance(candidate, list) and all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in candidate
        ):
            token_ids = list(candidate)
            break
    if isinstance(meta_info, dict) and (
        "output_token_logprobs" in meta_info
    ):
        triples = meta_info["output_token_logprobs"]
        if not isinstance(triples, list) or not all(
            isinstance(triple, (list, tuple))
            and len(triple) == 3
            and isinstance(triple[0], (int, float))
            and not isinstance(triple[0], bool)
            and isinstance(triple[1], int)
            and not isinstance(triple[1], bool)
            and isinstance(triple[2], str)
            for triple in triples
        ):
            raise TransportFailure(
                "response output token logprobs are not complete triples"
            )
        triple_token_ids = [int(triple[1]) for triple in triples]
        declared_length = meta_info.get("output_token_logprobs_length")
        if (
            not isinstance(declared_length, int)
            or isinstance(declared_length, bool)
            or declared_length != len(triple_token_ids)
        ):
            raise TransportFailure(
                "response output token logprobs declared length differs"
            )
        meta_completion_tokens = meta_info.get("completion_tokens")
        if (
            not isinstance(meta_completion_tokens, int)
            or isinstance(meta_completion_tokens, bool)
            or meta_completion_tokens != len(triple_token_ids)
        ):
            raise TransportFailure(
                "response meta completion tokens differ from token IDs"
            )
        if token_ids is not None and token_ids != triple_token_ids:
            raise TransportFailure(
                "response token ID fields disagree with logprob triples"
            )
        token_ids = triple_token_ids
    if token_ids is None:
        raise TransportFailure("response lacks complete output token IDs")
    usage = response.get("usage")
    if (
        not isinstance(usage, dict)
        or not isinstance(usage.get("completion_tokens"), int)
        or isinstance(usage.get("completion_tokens"), bool)
    ):
        raise TransportFailure("response lacks completion token usage")
    completion_tokens = int(usage["completion_tokens"])
    if completion_tokens < 0:
        raise TransportFailure("completion token usage is negative")
    if completion_tokens != len(token_ids):
        raise TransportFailure(
            "response completion token usage differs from token IDs"
        )
    return message["content"], token_ids, completion_tokens


def _response_meta_request_id(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise TransportFailure("response does not have exactly one choice")
    choice = choices[0]
    meta_info = choice.get("meta_info") if isinstance(choice, dict) else None
    request_id = (
        meta_info.get("id") if isinstance(meta_info, dict) else None
    )
    if not isinstance(request_id, str) or not request_id:
        raise TransportFailure("response meta_info.id is missing")
    envelope_id = response.get("id")
    if envelope_id != request_id:
        raise TransportFailure(
            "response id differs from response meta_info.id"
        )
    return request_id


def _finite_number(value: object, *, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise TransportFailure(f"Eagle3 trace {field} is not finite")
    return float(value)


def extract_eagle3_proposal_trace(
    payload: Mapping[str, Any],
    *,
    expected_sample_id: str,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    """Validate one-DP `/server_info` and select one response's trace."""

    internal_states = payload.get("internal_states")
    if not isinstance(internal_states, list) or len(internal_states) != 1:
        raise TransportFailure(
            "Eagle3 trace requires exactly one DP internal state"
        )
    state = internal_states[0]
    if not isinstance(state, dict):
        raise TransportFailure("Eagle3 internal state is not an object")
    envelope = state.get("eagle3_hedge_info_record")
    if not isinstance(envelope, dict):
        raise TransportFailure(
            "server_info lacks eagle3_hedge_info_record"
        )
    if envelope.get("schema_version") != 1:
        raise TransportFailure("Eagle3 trace schema_version is not 1")
    mode = envelope.get("mode")
    if mode not in {"disabled", "b0", "enabled"}:
        raise TransportFailure("Eagle3 trace mode is invalid")
    if expected_mode is not None and mode != expected_mode:
        raise TransportFailure(
            f"Eagle3 trace mode differs: {mode!r} != {expected_mode!r}"
        )
    if envelope.get("proposal_width") != 3:
        raise TransportFailure("Eagle3 trace proposal_width is not 3")
    if envelope.get("verify_width") != 4:
        raise TransportFailure("Eagle3 trace verify_width is not 4")
    if envelope.get("active_request_states") != 0:
        raise TransportFailure(
            "Eagle3 trace request state was not cleaned at terminal response"
        )
    dropped = envelope.get("trace_rows_dropped")
    if dropped != 0:
        raise TransportFailure(
            f"Eagle3 trace has dropped rows: {dropped!r}"
        )
    trace = envelope.get("trace")
    seen = envelope.get("trace_rows_seen")
    if (
        not isinstance(trace, list)
        or not isinstance(seen, int)
        or isinstance(seen, bool)
        or seen != len(trace)
    ):
        raise TransportFailure(
            "Eagle3 trace_rows_seen differs from stored trace"
        )

    validated: list[dict[str, Any]] = []
    proposal_ids: list[int] = []
    for row in trace:
        if not isinstance(row, dict):
            raise TransportFailure("Eagle3 proposal trace row is not an object")
        if row.get("schema_version") != 1 or row.get("mode") != mode:
            raise TransportFailure(
                "Eagle3 proposal row schema or mode differs"
            )
        proposal_id = row.get("proposal_id")
        if (
            not isinstance(proposal_id, int)
            or isinstance(proposal_id, bool)
            or proposal_id < 0
        ):
            raise TransportFailure("Eagle3 proposal_id is invalid")
        proposal_ids.append(proposal_id)
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise TransportFailure("Eagle3 proposal sample_id is invalid")
        for field in ("draft_token_ids", "target_top_token_ids"):
            values = row.get(field)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in values
                )
            ):
                raise TransportFailure(
                    f"Eagle3 proposal {field} does not have width 3"
                )
        for field in (
            "target_top_logits",
            "target_draft_token_logits",
            "regrets",
            "values",
        ):
            values = row.get(field)
            if not isinstance(values, list) or len(values) != 3:
                raise TransportFailure(
                    f"Eagle3 proposal {field} does not have width 3"
                )
            for value in values:
                _finite_number(value, field=field)
        strict = row.get("strict_accepted_drafts")
        accepted = row.get("hedge_accepted_drafts")
        relaxed = row.get("relaxed_mismatches")
        if (
            not isinstance(strict, int)
            or isinstance(strict, bool)
            or not 0 <= strict <= 3
            or not isinstance(accepted, int)
            or isinstance(accepted, bool)
            or not 0 <= accepted <= 3
            or row.get("commit_length") != accepted + 1
            or relaxed not in (0, 1)
        ):
            raise TransportFailure(
                "Eagle3 proposal acceptance fields are inconsistent"
            )
        barrier = row.get("first_strict_rejection")
        if strict == 3:
            if barrier is not None:
                raise TransportFailure(
                    "all-accepted Eagle3 proposal has a strict barrier"
                )
        else:
            if not isinstance(barrier, dict):
                raise TransportFailure(
                    "rejected Eagle3 proposal lacks a strict barrier"
                )
            if barrier.get("position") != strict:
                raise TransportFailure(
                    "Eagle3 strict barrier position differs"
                )
            regret = _finite_number(
                barrier.get("regret"),
                field="barrier regret",
            )
            value = _finite_number(
                barrier.get("value"),
                field="barrier value",
            )
            ratio = _finite_number(
                barrier.get("regret_over_value"),
                field="barrier regret_over_value",
            )
            if regret < 0 or value <= 0 or not math.isclose(
                ratio,
                regret / value,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise TransportFailure(
                    "Eagle3 strict barrier values are inconsistent"
                )
        validated.append(dict(row))
    if proposal_ids != list(range(len(proposal_ids))):
        raise TransportFailure(
            "Eagle3 proposal IDs are not a contiguous drained sequence"
        )

    selected = [
        row for row in validated if row["sample_id"] == expected_sample_id
    ]
    foreign = [
        row for row in validated if row["sample_id"] != expected_sample_id
    ]
    if not selected:
        foreign_ids = sorted({row["sample_id"] for row in foreign})
        raise TransportFailure(
            "Eagle3 trace lacks expected sample_id "
            f"{expected_sample_id!r}; foreign={foreign_ids!r}"
        )
    barriers = []
    for row in selected:
        barrier = row["first_strict_rejection"]
        if barrier is not None:
            barriers.append(
                {
                    "sample_id": expected_sample_id,
                    "proposal_id": row["proposal_id"],
                    **barrier,
                }
            )
    return {
        "schema_version": 1,
        "mode": mode,
        "sample_id": expected_sample_id,
        "proposal_trace": selected,
        "strict_rejection_barriers": barriers,
        "foreign_trace_row_count": len(foreign),
        "foreign_sample_ids": sorted(
            {row["sample_id"] for row in foreign}
        ),
        "trace_rows_seen": seen,
        "trace_rows_dropped": 0,
    }


Transport = Callable[
    [str, Mapping[str, Any], float],
    dict[str, Any],
]

ControlTransport = Callable[
    [str, str, Mapping[str, Any] | None, float],
    Any,
]


def urllib_json_control_transport(
    method: str,
    url: str,
    body: Mapping[str, Any] | None,
    timeout_seconds: float,
) -> Any:
    """JSON control transport; unlike generation, POST may return a list."""

    request = urllib.request.Request(
        url,
        data=None if body is None else canonical_json_bytes(body),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        failure_body = error.read().decode("utf-8", errors="replace")
        raise TransportFailure(
            f"HTTP {error.code}",
            status_code=error.code,
            response_body=failure_body,
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TransportFailure(str(error)) from error
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise TransportFailure(
            "control response is not valid JSON",
            response_body=raw,
        ) from error


class Eagle3TraceControl:
    """Clear and drain the lane-local Eagle3 trace through control endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        expected_mode: str,
        timeout_seconds: float = 30.0,
        transport: ControlTransport = urllib_json_control_transport,
    ) -> None:
        if expected_mode not in {"disabled", "b0", "enabled"}:
            raise ValueError("invalid expected Eagle3 HEDGE mode")
        self.base_url = base_url.rstrip("/")
        self.expected_mode = expected_mode
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def clear(self) -> None:
        response = self.transport(
            "POST",
            f"{self.base_url}/set_internal_state",
            {
                "server_args": {
                    "eagle3_hedge_clear_info_records": True,
                }
            },
            self.timeout_seconds,
        )
        if response != [True]:
            raise TransportFailure(
                "Eagle3 trace clear did not return fixed DP=1 [true]"
            )

    def drain(self, *, expected_sample_id: str) -> dict[str, Any]:
        response = self.transport(
            "GET",
            f"{self.base_url}/server_info",
            None,
            self.timeout_seconds,
        )
        if not isinstance(response, dict):
            raise TransportFailure("server_info response is not an object")
        return extract_eagle3_proposal_trace(
            response,
            expected_sample_id=expected_sample_id,
            expected_mode=self.expected_mode,
        )


class SequentialOpenAIRunner:
    """Run fixed warmup/formal requests with at most one request in flight."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        max_attempts: int = 3,
        timeout_seconds: float = 120.0,
        retry_delays_seconds: Sequence[float] = (1.0, 2.0),
        transport: Transport = urllib_json_transport,
        trace_control: Any | None = None,
        require_proposal_trace: bool = False,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts != 3:
            raise ValueError("experiment protocol requires 3 total attempts")
        if len(retry_delays_seconds) != max_attempts - 1:
            raise ValueError("retry delay count differs from max attempts")
        if require_proposal_trace and trace_control is None:
            raise ValueError(
                "required proposal trace needs an Eagle3 trace control"
            )
        self.endpoint = endpoint
        self.model = model
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds
        self.retry_delays_seconds = tuple(retry_delays_seconds)
        self.transport = transport
        self.trace_control = trace_control
        self.require_proposal_trace = require_proposal_trace
        self.monotonic = monotonic
        self.sleep = sleep
        self._in_flight = 0
        self.maximum_in_flight = 0

    def _request_body(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        messages = sample.get("request_messages")
        if (
            not isinstance(messages, list)
            or len(messages) != 1
            or messages[0].get("role") != "user"
            or set(messages[0]) != {"role", "content"}
        ):
            raise ValueError("sample request messages violate prompt contract")
        return {
            "model": self.model,
            "messages": messages,
            **GENERATION,
        }

    def _retry_trace_operation(
        self,
        *,
        operation_name: str,
        operation: Callable[[], Any],
        model_attempt: int,
    ) -> tuple[Any | None, list[dict[str, Any]], str | None]:
        attempts = []
        terminal_error = None
        for attempt_index in range(self.max_attempts):
            started = self.monotonic()
            try:
                value = operation()
                attempts.append(
                    {
                        "operation": operation_name,
                        "model_attempt": model_attempt,
                        "attempt": attempt_index + 1,
                        "status": "success",
                        "monotonic_started": started,
                        "monotonic_finished": self.monotonic(),
                    }
                )
                return value, attempts, None
            except TransportFailure as error:
                terminal_error = str(error)
                attempts.append(
                    {
                        "operation": operation_name,
                        "model_attempt": model_attempt,
                        "attempt": attempt_index + 1,
                        "status": "failure",
                        "monotonic_started": started,
                        "monotonic_finished": self.monotonic(),
                        "error": str(error),
                        "status_code": error.status_code,
                        "response_body": error.response_body,
                    }
                )
            if attempt_index + 1 < self.max_attempts:
                self.sleep(self.retry_delays_seconds[attempt_index])
        return None, attempts, terminal_error

    def _execute(
        self,
        sample: Mapping[str, Any],
        *,
        phase: str,
        position: int,
        timed: bool,
    ) -> dict[str, Any]:
        if self._in_flight:
            raise RuntimeError("runner attempted a concurrent request")
        body = self._request_body(sample)
        attempts: list[dict[str, Any]] = []
        terminal_response: dict[str, Any] | None = None
        terminal_error: str | None = None
        content: str | None = None
        token_ids: list[int] = []
        completion_tokens = 0
        proposal_trace: list[dict[str, Any]] = []
        strict_rejection_barriers: list[dict[str, Any]] = []
        trace_metadata: dict[str, Any] | None = None
        trace_clear_attempts: list[dict[str, Any]] = []
        trace_drain_attempts: list[dict[str, Any]] = []
        first_request_started: float | None = None
        request_terminal_monotonic: float | None = None
        for attempt_index in range(self.max_attempts):
            if self.trace_control is not None:
                _, clear_attempts, clear_error = self._retry_trace_operation(
                    operation_name="clear",
                    operation=self.trace_control.clear,
                    model_attempt=attempt_index + 1,
                )
                trace_clear_attempts.extend(clear_attempts)
                if clear_error is not None:
                    terminal_error = f"trace clear failed: {clear_error}"
                    break
            started = self.monotonic()
            if first_request_started is None:
                first_request_started = started
            self._in_flight += 1
            self.maximum_in_flight = max(
                self.maximum_in_flight,
                self._in_flight,
            )
            try:
                response = self.transport(
                    self.endpoint,
                    body,
                    self.timeout_seconds,
                )
                content, token_ids, completion_tokens = _response_fields(
                    response
                )
                request_id = (
                    _response_meta_request_id(response)
                    if self.trace_control is not None
                    else None
                )
                request_terminal_monotonic = self.monotonic()
                terminal_response = response
                attempts.append(
                    {
                        "attempt": attempt_index + 1,
                        "status": "success",
                        "monotonic_started": started,
                        "monotonic_finished": request_terminal_monotonic,
                        "response": response,
                    }
                )
                if self.trace_control is not None:
                    (
                        trace_metadata,
                        drain_attempts,
                        drain_error,
                    ) = self._retry_trace_operation(
                        operation_name="drain",
                        operation=lambda: self.trace_control.drain(
                            expected_sample_id=request_id
                        ),
                        model_attempt=attempt_index + 1,
                    )
                    trace_drain_attempts.extend(drain_attempts)
                    if drain_error is not None:
                        terminal_error = (
                            f"trace drain failed: {drain_error}"
                        )
                        break
                    if not isinstance(trace_metadata, dict):
                        terminal_error = (
                            "trace drain failed: result is not an object"
                        )
                        break
                    proposal_trace = list(
                        trace_metadata["proposal_trace"]
                    )
                    strict_rejection_barriers = list(
                        trace_metadata["strict_rejection_barriers"]
                    )
                terminal_error = None
                break
            except TransportFailure as error:
                terminal_error = str(error)
                request_terminal_monotonic = self.monotonic()
                attempts.append(
                    {
                        "attempt": attempt_index + 1,
                        "status": "failure",
                        "monotonic_started": started,
                        "monotonic_finished": request_terminal_monotonic,
                        "error": str(error),
                        "status_code": error.status_code,
                        "response_body": error.response_body,
                    }
                )
            finally:
                self._in_flight -= 1
            if attempt_index + 1 < self.max_attempts:
                self.sleep(self.retry_delays_seconds[attempt_index])
        reference = extract_reference_answer(str(sample.get("answer", "")))
        model_answer = (
            extract_model_answer(content)
            if content is not None
            else {
                "status": "parse_failure",
                "rule": None,
                "raw": None,
                "normalized": None,
            }
        )
        generation_success = terminal_response is not None
        trace_complete = (
            trace_metadata is not None
            if self.trace_control is not None
            else None
        )
        success = generation_success and (
            not self.require_proposal_trace or trace_complete is True
        )
        all_trace_attempts = trace_clear_attempts + trace_drain_attempts
        record_terminal_monotonic = self.monotonic()
        return {
            "schema_version": 1,
            "phase": phase,
            "position": position,
            "timed": timed,
            "partition": sample.get("partition"),
            "partition_index": sample.get("partition_index"),
            "source_index": sample.get("source_index"),
            "request_body": body,
            "attempts": attempts,
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "generation_retry_count": max(0, len(attempts) - 1),
            "trace_retry_count": sum(
                item["attempt"] > 1 for item in all_trace_attempts
            ),
            "trace_clear_attempts": trace_clear_attempts,
            "trace_drain_attempts": trace_drain_attempts,
            "generation_status": (
                "success" if generation_success else "failure"
            ),
            "trace_status": (
                "not_requested"
                if trace_complete is None
                else ("success" if trace_complete else "failure")
            ),
            "terminal_status": "success" if success else "failure",
            "terminal_error": terminal_error,
            "first_request_monotonic_started": first_request_started,
            "request_terminal_monotonic": request_terminal_monotonic,
            "record_terminal_monotonic": record_terminal_monotonic,
            "full_response": terminal_response,
            "response_text": content,
            "output_token_ids": token_ids,
            "completion_tokens": completion_tokens,
            "proposal_trace": proposal_trace,
            "strict_rejection_barriers": strict_rejection_barriers,
            "trace_metadata": trace_metadata,
            "reference_answer": reference,
            "model_answer": model_answer,
            "answer_match": (
                answers_match(
                    reference.get("normalized"),
                    model_answer.get("normalized"),
                )
                if generation_success
                else False
            ),
        }

    def run(
        self,
        manifest: Mapping[str, Any],
        *,
        warmup_count: int = 10,
    ) -> dict[str, Any]:
        calibration = manifest.get("calibration")
        formal = manifest.get("formal")
        if not isinstance(calibration, list) or len(calibration) < warmup_count:
            raise ValueError("manifest lacks fixed warmup samples")
        if not isinstance(formal, list) or len(formal) != 500:
            raise ValueError("manifest formal partition is not exactly 500")
        warmups = [
            self._execute(
                calibration[index],
                phase="warmup",
                position=index,
                timed=False,
            )
            for index in range(warmup_count)
        ]
        formal_records = [
            self._execute(
                sample,
                phase="formal",
                position=index,
                timed=True,
            )
            for index, sample in enumerate(formal)
        ]
        if self._in_flight != 0 or self.maximum_in_flight != 1:
            raise RuntimeError("runner sequentiality invariant failed")
        if any(
            record["terminal_status"] not in {"success", "failure"}
            for record in formal_records
        ):
            raise RuntimeError("formal request did not reach terminal state")
        formal_started, formal_finished = formal_timing_bounds(
            formal_records
        )
        result = {
            "schema_version": 1,
            "endpoint": self.endpoint,
            "model": self.model,
            "warmup_count": len(warmups),
            "formal_count": len(formal_records),
            "maximum_in_flight": self.maximum_in_flight,
            "formal_monotonic_started": formal_started,
            "formal_monotonic_finished": formal_finished,
            "formal_wall_seconds": formal_finished - formal_started,
            "warmup": warmups,
            "formal": formal_records,
        }
        result["summary"] = summarize_run(result)
        return result


def formal_timing_bounds(
    records: Sequence[Mapping[str, Any]],
) -> tuple[float, float]:
    if not records:
        raise RuntimeError("formal run has no records")
    started = records[0].get("first_request_monotonic_started")
    if (
        not isinstance(started, (int, float))
        or isinstance(started, bool)
        or not math.isfinite(float(started))
    ):
        raise RuntimeError("first formal generation request was never issued")
    finished = records[-1].get("record_terminal_monotonic")
    if (
        not isinstance(finished, (int, float))
        or isinstance(finished, bool)
        or not math.isfinite(float(finished))
        or float(finished) < float(started)
    ):
        raise RuntimeError("last formal request lacks a valid terminal time")
    return float(started), float(finished)


def summarize_run(run: Mapping[str, Any]) -> dict[str, Any]:
    formal = run.get("formal")
    if not isinstance(formal, list):
        raise ValueError("run lacks formal records")
    terminal = len(formal)
    successes = sum(
        record.get("terminal_status") == "success" for record in formal
    )
    failures = terminal - successes
    generation_successes = sum(
        record.get(
            "generation_status",
            (
                "success"
                if record.get("terminal_status") == "success"
                else "failure"
            ),
        )
        == "success"
        for record in formal
    )
    generation_failures = terminal - generation_successes
    trace_successes = sum(
        record.get("trace_status") == "success" for record in formal
    )
    trace_failures = sum(
        record.get("trace_status") == "failure" for record in formal
    )
    trace_not_requested = sum(
        record.get("trace_status", "not_requested") == "not_requested"
        for record in formal
    )
    retries = sum(int(record.get("retry_count", 0)) for record in formal)
    trace_retries = sum(
        int(record.get("trace_retry_count", 0)) for record in formal
    )
    parse_failures = sum(
        record.get("model_answer", {}).get("status") == "parse_failure"
        for record in formal
    )
    matches = sum(bool(record.get("answer_match")) for record in formal)
    completion_tokens = sum(
        int(record.get("completion_tokens", 0)) for record in formal
    )
    wall = float(run.get("formal_wall_seconds", 0.0))
    return {
        "schema_version": 1,
        "formal_terminal": terminal,
        "successes": successes,
        "failures": failures,
        "generation_successes": generation_successes,
        "generation_failures": generation_failures,
        "trace_successes": trace_successes,
        "trace_failures": trace_failures,
        "trace_not_requested": trace_not_requested,
        "retries": retries,
        "generation_retries": retries,
        "trace_retries": trace_retries,
        "parse_failures": parse_failures,
        "matches": matches,
        "match_rate": matches / terminal if terminal else None,
        "completion_tokens": completion_tokens,
        "formal_wall_seconds": wall,
        "end_to_end_output_tps": (
            completion_tokens / wall if wall > 0 else None
        ),
    }


def first_divergence(
    left: Sequence[int],
    right: Sequence[int],
) -> int | None:
    for index, (left_value, right_value) in enumerate(zip(left, right)):
        if left_value != right_value:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def compare_b0_token_ids(
    native: Sequence[Mapping[str, Any]],
    b0: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(native) != 32 or len(b0) != 32:
        raise ValueError("B0 comparison requires exactly 32 records per arm")
    first_mismatch: dict[str, Any] | None = None
    for index, (native_record, b0_record) in enumerate(zip(native, b0)):
        if native_record.get("source_index") != b0_record.get("source_index"):
            raise ValueError("B0 sample identity/order differs")
        native_ids = native_record.get("output_token_ids")
        b0_ids = b0_record.get("output_token_ids")
        if not isinstance(native_ids, list) or not isinstance(b0_ids, list):
            raise ValueError("B0 records lack output token IDs")
        divergence = first_divergence(native_ids, b0_ids)
        if divergence is not None:
            first_mismatch = {
                "calibration_index": index,
                "source_index": native_record.get("source_index"),
                "first_divergence": divergence,
                "native_token_ids": native_ids,
                "b0_token_ids": b0_ids,
                "native_text": native_record.get("response_text"),
                "b0_text": b0_record.get("response_text"),
                "native_proposal_trace": native_record.get("proposal_trace"),
                "b0_proposal_trace": b0_record.get("proposal_trace"),
            }
            break
    return {
        "schema_version": 1,
        "status": "B0_PASS" if first_mismatch is None else "B0_FAIL",
        "compared": 32,
        "first_mismatch": first_mismatch,
    }


def calibrate_q25(
    barriers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    import numpy

    raw_values: list[float] = []
    identities: list[dict[str, Any]] = []
    for barrier in barriers:
        value = float(barrier["regret_over_value"])
        if not math.isfinite(value):
            raise ValueError("calibration trace contains a non-finite value")
        if value > 0:
            raw_values.append(value)
            identities.append(
                {
                    "sample_id": barrier.get("sample_id"),
                    "proposal_id": barrier.get("proposal_id"),
                    "regret_over_value": value,
                }
            )
    if not raw_values:
        raise ValueError("calibration trace has no finite positive values")
    gate = float(numpy.quantile(raw_values, 0.25, method="linear"))
    result = {
        "schema_version": 1,
        "status": "PASS",
        "quantile": 0.25,
        "quantile_method": "linear",
        "numpy_version": numpy.__version__,
        "value_scheme": "normalized_suffix",
        "positive_value_count": len(raw_values),
        "positive_values": raw_values,
        "identities": identities,
        "g": gate,
        "B": gate,
        "m": 1,
    }
    result["config_sha256"] = canonical_sha256(result)
    return result


def experiment_table(
    native: Mapping[str, Any],
    hedge: Mapping[str, Any],
    *,
    b0_status: str,
) -> str:
    rows = [
        "| Metric | Native | HEDGE B+ | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("Formal terminal", "formal_terminal"),
        ("Successes", "successes"),
        ("Failures", "failures"),
        ("Retries", "retries"),
        ("Parse failures", "parse_failures"),
        ("Matches", "matches"),
        ("Completion tokens", "completion_tokens"),
        ("Wall seconds", "formal_wall_seconds"),
        ("Output TPS", "end_to_end_output_tps"),
    ):
        left = native.get(key)
        right = hedge.get(key)
        delta = (
            float(right) - float(left)
            if isinstance(left, (int, float))
            and isinstance(right, (int, float))
            else "—"
        )
        rows.append(f"| {label} | {left} | {right} | {delta} |")
    rows.append("")
    rows.append(f"B0 status: `{b0_status}`")
    return "\n".join(rows) + "\n"


def _proc_stat(pid: int) -> tuple[int, int, int, int]:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close_paren = payload.rfind(")")
    if close_paren < 0:
        raise RuntimeError("malformed proc stat")
    fields = payload[close_paren + 2 :].split()
    ppid = int(fields[1])
    pgid = int(fields[2])
    sid = int(fields[3])
    start_ticks = int(fields[19])
    return ppid, pgid, sid, start_ticks


def _command_line(pid: int) -> tuple[str, ...]:
    return tuple(
        value.decode("utf-8", errors="surrogateescape")
        for value in Path(f"/proc/{pid}/cmdline")
        .read_bytes()
        .rstrip(b"\0")
        .split(b"\0")
        if value
    )


@dataclass(frozen=True)
class RegisteredProcess:
    pid: int
    ppid: int
    pgid: int
    sid: int
    start_ticks: int
    command_line: tuple[str, ...]
    executable: str


def capture_registered_process(pid: int) -> RegisteredProcess:
    ppid, pgid, sid, start_ticks = _proc_stat(pid)
    return RegisteredProcess(
        pid=pid,
        ppid=ppid,
        pgid=pgid,
        sid=sid,
        start_ticks=start_ticks,
        command_line=_command_line(pid),
        executable=os.path.realpath(f"/proc/{pid}/exe"),
    )


def validate_registered_process(
    registered: RegisteredProcess,
) -> RegisteredProcess:
    current = capture_registered_process(registered.pid)
    if current != registered:
        raise RuntimeError("registered process identity changed")
    if current.pgid != current.pid or current.sid != current.pid:
        raise RuntimeError("registered process is not its PGID/SID leader")
    return current


def terminate_registered_process(
    registered: RegisteredProcess,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    current = validate_registered_process(registered)
    os.killpg(current.pgid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            payload = Path(f"/proc/{current.pid}/stat").read_text(
                encoding="utf-8"
            )
        except ProcessLookupError:
            return {
                "status": "terminated",
                "signal": "SIGTERM",
                "kill_fallback": False,
                "registered": asdict(registered),
            }
        except FileNotFoundError:
            return {
                "status": "terminated",
                "signal": "SIGTERM",
                "kill_fallback": False,
                "registered": asdict(registered),
            }
        close_paren = payload.rfind(")")
        if close_paren >= 0 and payload[close_paren + 2 :].split()[0] == "Z":
            return {
                "status": "terminated",
                "signal": "SIGTERM",
                "kill_fallback": False,
                "registered": asdict(registered),
            }
        time.sleep(0.05)
    validate_registered_process(registered)
    os.killpg(current.pgid, signal.SIGKILL)
    return {
        "status": "terminated",
        "signal": "SIGKILL",
        "kill_fallback": True,
        "registered": asdict(registered),
    }


def collect_gpu_sample() -> dict[str, Any]:
    """Sample utilization/memory without creating a CUDA context."""

    completed = subprocess.run(
        (
            "nvidia-smi",
            "--query-gpu=index,uuid,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 4:
            raise RuntimeError(f"unexpected nvidia-smi row: {line!r}")
        rows.append(
            {
                "index": int(fields[0]),
                "uuid": fields[1],
                "utilization_gpu_percent": float(fields[2]),
                "memory_used_mib": int(fields[3]),
            }
        )
    return {
        "monotonic": time.monotonic(),
        "wall_time_ns": time.time_ns(),
        "gpus": rows,
    }
