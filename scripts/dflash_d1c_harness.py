#!/usr/bin/env python3
"""Pinned GSM8K preparation and sequential DFlash experiment harness."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

DATASET_REPO = "openai/gsm8k"
DATASET_CONFIG = "main"
DATASET_SPLIT = "test"
DATASET_REVISION = "740312add88f781978c0658806c59bc2815b9866"
SHUFFLE_SEED = 980406
CALIBRATION_COUNT = 32
FORMAL_COUNT = 500
WARMUP_COUNT = 10
PROMPT_SUFFIX = (
    r"Please reason step by step, and put your final answer within \boxed{}."
)

NUMBER_PATTERN = (
    r"[-+]?(?:\$\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
)
LOCAL_HTTP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_chat_request(sample: Mapping[str, Any], *, model: str) -> dict[str, Any]:
    prompt = sample.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("sample prompt must be a string")
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 512,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        # Observational only: DFlash D1C must preserve the tokenized input.
        "return_prompt_token_ids": True,
        # Canonical output token IDs are supplied in choices[0].meta_info.
        "return_meta_info": True,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payload = "".join(_canonical_json(row) + "\n" for row in rows).encode()
    path.write_bytes(payload)
    return {"row_count": len(rows), "sha256": _sha256_bytes(payload)}


def _write_json(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.write_bytes(payload)
    return {"sha256": _sha256_bytes(payload)}


def normalize_number(raw: str) -> str | None:
    candidate = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        value = Decimal(candidate)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def extract_reference_answer(answer: str) -> str | None:
    matches = re.findall(rf"####\s*({NUMBER_PATTERN})", answer)
    return normalize_number(matches[-1]) if matches else None


def extract_model_answer(text: str) -> tuple[str | None, str | None]:
    boxed_matches = re.findall(
        rf"\\boxed\{{\s*({NUMBER_PATTERN})\s*\}}",
        text,
    )
    if boxed_matches:
        normalized = normalize_number(boxed_matches[-1])
        if normalized is not None:
            return normalized, "last_boxed"
    hashes_matches = re.findall(rf"####\s*({NUMBER_PATTERN})", text)
    if hashes_matches:
        normalized = normalize_number(hashes_matches[-1])
        if normalized is not None:
            return normalized, "last_hashes"
    final_matches = re.findall(
        rf"(?i)\bfinal\s+answer\s*(?::|=|\bis\b)?\s*({NUMBER_PATTERN})",
        text,
    )
    if final_matches:
        normalized = normalize_number(final_matches[-1])
        if normalized is not None:
            return normalized, "explicit_final_answer"
    number_matches = re.findall(rf"({NUMBER_PATTERN})", text)
    if number_matches:
        normalized = normalize_number(number_matches[-1])
        if normalized is not None:
            return normalized, "last_number"
    return None, None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _post_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=_canonical_json(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with LOCAL_HTTP_OPENER.open(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    if not isinstance(decoded, dict):
        raise ValueError("API response must be a JSON object")
    return decoded


def _extract_response_evidence(
    response: Mapping[str, Any],
) -> tuple[str, list[int], list[int], dict[str, Any]]:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("response choice must be an object")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("response must contain assistant message content")
    prompt_token_ids = choice.get("prompt_token_ids")
    if not isinstance(prompt_token_ids, list) or not all(
        isinstance(token_id, int) for token_id in prompt_token_ids
    ):
        raise ValueError("response is missing integer prompt_token_ids")
    meta_info = choice.get("meta_info")
    if not isinstance(meta_info, dict):
        raise ValueError("response is missing choice meta_info")
    output_token_ids = meta_info.get("output_token_ids")
    if not isinstance(output_token_ids, list) or not all(
        isinstance(token_id, int) for token_id in output_token_ids
    ):
        raise ValueError("response is missing integer meta_info.output_token_ids")
    usage = response.get("usage")
    if not isinstance(usage, dict) or not isinstance(
        usage.get("completion_tokens"), int
    ):
        raise ValueError("response is missing integer usage.completion_tokens")
    if usage["completion_tokens"] != len(output_token_ids):
        raise ValueError("completion token count differs from output token ID count")
    return message["content"], prompt_token_ids, output_token_ids, dict(usage)


def run_cohort(
    samples: Sequence[Mapping[str, Any]],
    *,
    base_url: str,
    model: str,
    output_path: Path,
    summary_path: Path,
    max_attempts: int,
    request_timeout_seconds: float,
    retry_backoff_seconds: float,
    cohort_kind: str = "test",
) -> dict[str, Any]:
    """Run one cohort sequentially and persist every request's terminal record."""

    if not samples:
        raise ValueError("cohort must not be empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    expected_counts = {"calibration": 32, "warmup": 10, "formal": 500}
    if cohort_kind not in {"test", *expected_counts}:
        raise ValueError(f"unsupported cohort_kind: {cohort_kind}")
    if cohort_kind in expected_counts and len(samples) != expected_counts[cohort_kind]:
        raise ValueError(
            f"{cohort_kind} cohort must contain exactly "
            f"{expected_counts[cohort_kind]} requests"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_started_ns: int | None = None
    run_started_at: str | None = None
    run_ended_ns: int | None = None
    run_ended_at: str | None = None
    completion_tokens = 0
    counts = {
        "success": 0,
        "request_failure": 0,
        "match": 0,
        "mismatch": 0,
        "parse_failure": 0,
    }

    with output_path.open("w", encoding="utf-8") as output:
        for request_index, sample in enumerate(samples):
            payload = build_chat_request(sample, model=model)
            attempts: list[dict[str, Any]] = []
            request_started_at: str | None = None
            request_started_ns: int | None = None
            response: dict[str, Any] | None = None
            evidence: tuple[str, list[int], list[int], dict[str, Any]] | None = None
            for attempt_number in range(1, max_attempts + 1):
                attempt_started_at = _utc_now()
                attempt_started_ns = time.monotonic_ns()
                if request_started_ns is None:
                    request_started_ns = attempt_started_ns
                    request_started_at = attempt_started_at
                if run_started_ns is None:
                    run_started_ns = attempt_started_ns
                    run_started_at = attempt_started_at
                try:
                    candidate_response = _post_json(
                        base_url.rstrip("/") + "/v1/chat/completions",
                        payload,
                        request_timeout_seconds,
                    )
                    candidate_evidence = _extract_response_evidence(candidate_response)
                    response_received_ns = time.monotonic_ns()
                    attempts.append(
                        {
                            "attempt": attempt_number,
                            "status": "success",
                            "started_at_utc": attempt_started_at,
                            "ended_at_utc": _utc_now(),
                            "latency_seconds": (
                                response_received_ns - attempt_started_ns
                            )
                            / 1_000_000_000,
                        }
                    )
                    response = candidate_response
                    evidence = candidate_evidence
                    break
                except (OSError, ValueError) as error:
                    attempt_ended_ns = time.monotonic_ns()
                    body = ""
                    status_code = None
                    if isinstance(error, urllib.error.HTTPError):
                        status_code = error.code
                        body = error.read().decode(errors="replace")
                    attempts.append(
                        {
                            "attempt": attempt_number,
                            "status": "error",
                            "started_at_utc": attempt_started_at,
                            "ended_at_utc": _utc_now(),
                            "latency_seconds": (
                                attempt_ended_ns - attempt_started_ns
                            )
                            / 1_000_000_000,
                            "error_type": type(error).__name__,
                            "error": str(error),
                            "http_status": status_code,
                            "response_body": body,
                        }
                    )
                    if attempt_number < max_attempts:
                        time.sleep(retry_backoff_seconds)
            if response is None or evidence is None:
                assert request_started_at is not None
                assert request_started_ns is not None
                terminal_at = _utc_now()
                terminal_ns = time.monotonic_ns()
                run_ended_ns = terminal_ns
                run_ended_at = terminal_at
                record = {
                    "schema_version": 1,
                    "request_index": request_index,
                    "dataset_index": sample.get("dataset_index"),
                    "cohort": sample.get("cohort"),
                    "cohort_position": sample.get("cohort_position"),
                    "question": sample.get("question"),
                    "answer": sample.get("answer"),
                    "reference_answer": sample.get("reference_answer"),
                    "prompt": sample.get("prompt"),
                    "request_payload": payload,
                    "request_started_at_utc": request_started_at,
                    "attempts": attempts,
                    "retry_count": len(attempts) - 1,
                    "terminal": True,
                    "terminal_state": "request_failed",
                    "terminal_at_utc": terminal_at,
                    "latency_seconds": (terminal_ns - request_started_ns)
                    / 1_000_000_000,
                    "tokenized_input": {
                        "source": "unavailable_after_request_failure",
                        "token_ids": None,
                        "count": None,
                    },
                    "full_response": None,
                    "model_text": None,
                    "output_token_ids": [],
                    "usage": None,
                    "extracted_answer": None,
                    "extraction_rule": None,
                    "parse_status": "not_attempted_after_request_failure",
                    "answer_status": "request_failed",
                }
                output.write(_canonical_json(record) + "\n")
                output.flush()
                counts["request_failure"] += 1
                continue
            (
                model_text,
                prompt_token_ids,
                output_token_ids,
                usage,
            ) = evidence
            extracted_answer, extraction_rule = extract_model_answer(model_text)
            reference_answer = sample.get("reference_answer")
            if extracted_answer is None or not isinstance(reference_answer, str):
                answer_status = "parse_failure"
            elif extracted_answer == reference_answer:
                answer_status = "match"
            else:
                answer_status = "mismatch"
            terminal_at = _utc_now()
            terminal_ns = time.monotonic_ns()
            run_ended_ns = terminal_ns
            run_ended_at = terminal_at
            assert request_started_at is not None
            assert request_started_ns is not None
            record = {
                "schema_version": 1,
                "request_index": request_index,
                "dataset_index": sample.get("dataset_index"),
                "cohort": sample.get("cohort"),
                "cohort_position": sample.get("cohort_position"),
                "question": sample.get("question"),
                "answer": sample.get("answer"),
                "reference_answer": reference_answer,
                "prompt": sample.get("prompt"),
                "request_payload": payload,
                "request_started_at_utc": request_started_at,
                "attempts": attempts,
                "retry_count": len(attempts) - 1,
                "terminal": True,
                "terminal_state": "success",
                "terminal_at_utc": terminal_at,
                "latency_seconds": (terminal_ns - request_started_ns)
                / 1_000_000_000,
                "tokenized_input": {
                    "source": "choices[0].prompt_token_ids",
                    "token_ids": prompt_token_ids,
                    "count": len(prompt_token_ids),
                },
                "full_response": response,
                "model_text": model_text,
                "output_token_ids": output_token_ids,
                "usage": usage,
                "extracted_answer": extracted_answer,
                "extraction_rule": extraction_rule,
                "parse_status": (
                    "parse_failure"
                    if answer_status == "parse_failure"
                    else "parsed"
                ),
                "answer_status": answer_status,
            }
            output.write(_canonical_json(record) + "\n")
            output.flush()
            completion_tokens += usage["completion_tokens"]
            counts["success"] += 1
            counts[answer_status] += 1

    assert run_started_ns is not None
    assert run_started_at is not None
    assert run_ended_ns is not None
    assert run_ended_at is not None
    wall_time_seconds = (run_ended_ns - run_started_ns) / 1_000_000_000
    summary = {
        "schema_version": 1,
        "cohort_kind": cohort_kind,
        "request_count": len(samples),
        "timed_request_count": len(samples),
        "request_order": "single_request_sequential",
        "all_terminal": counts["success"] + counts["request_failure"] == len(samples),
        "terminal_counts": counts,
        "retry_count": sum(
            max(0, len(json.loads(line)["attempts"]) - 1)
            for line in output_path.read_text().splitlines()
        ),
        "completion_tokens": completion_tokens,
        "wall_time_started_at_utc": run_started_at,
        "wall_time_ended_at_utc": run_ended_at,
        "wall_time_started_monotonic_ns": run_started_ns,
        "wall_time_ended_monotonic_ns": run_ended_ns,
        "wall_time_seconds": wall_time_seconds,
        "e2e_output_tps": (
            completion_tokens / wall_time_seconds if wall_time_seconds > 0 else None
        ),
        "timing_definition": (
            "before first request dispatch through final request terminal state; "
            "includes HTTP, generation, failures, retries, and retry backoff"
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return summary


def prepare_dataset_records(
    records: Sequence[Mapping[str, Any]],
    output_dir: Path,
    *,
    datasets_fingerprint: str,
    generator_versions: Mapping[str, str],
    acquisition_metadata: Mapping[str, Any] | None = None,
    shared_manifest: Mapping[str, Any] | None = None,
    shared_manifest_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the fixed D1C calibration/formal cohorts from ordered test rows."""

    if len(records) < CALIBRATION_COUNT + FORMAL_COUNT:
        raise ValueError("GSM8K test data must contain at least 532 rows")
    source_rows: list[dict[str, Any]] = []
    for dataset_index, record in enumerate(records):
        question = record.get("question")
        answer = record.get("answer")
        if not isinstance(question, str) or not isinstance(answer, str):
            raise ValueError(
                f"row {dataset_index} must contain string question and answer"
            )
        reference_answer = extract_reference_answer(answer)
        if reference_answer is None:
            raise ValueError(f"row {dataset_index} has no parseable #### answer")
        source_rows.append(
            {
                "dataset_index": dataset_index,
                "question": question,
                "answer": answer,
                "reference_answer": reference_answer,
            }
        )

    source_payload = "".join(
        _canonical_json(
            {
                "dataset_index": row["dataset_index"],
                "question": row["question"],
                "answer": row["answer"],
            }
        )
        + "\n"
        for row in source_rows
    ).encode()
    source_content_sha256 = _sha256_bytes(source_payload)
    shuffled_indices = list(range(len(source_rows)))
    random.Random(SHUFFLE_SEED).shuffle(shuffled_indices)
    calibration_indices = shuffled_indices[:CALIBRATION_COUNT]
    formal_indices = shuffled_indices[
        CALIBRATION_COUNT : CALIBRATION_COUNT + FORMAL_COUNT
    ]
    selection_authority = "locally_recomputed_pinned_protocol"
    shared_selection: dict[str, Any] | None = None
    if shared_manifest is not None:
        if shared_manifest_provenance is None:
            raise ValueError("shared manifest provenance is required")
        expected_source = {
            "repo_id": DATASET_REPO,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "revision": DATASET_REVISION,
            "resolved_revision": DATASET_REVISION,
        }
        shared_source = shared_manifest.get("source")
        shared_dataset = shared_manifest.get("dataset")
        shared_selection_data = shared_manifest.get("selection")
        if not isinstance(shared_source, Mapping):
            raise ValueError("shared manifest source is missing")
        if not isinstance(shared_dataset, Mapping):
            raise ValueError("shared manifest dataset identity is missing")
        if not isinstance(shared_selection_data, Mapping):
            raise ValueError("shared manifest selection is missing")
        for field, expected in expected_source.items():
            if shared_source.get(field) != expected:
                raise ValueError(f"shared manifest source mismatch: {field}")
        expected_dataset = {
            "row_count": len(source_rows),
            "datasets_fingerprint": datasets_fingerprint,
            "content_sha256": source_content_sha256,
        }
        for field, expected in expected_dataset.items():
            if shared_dataset.get(field) != expected:
                raise ValueError(f"shared manifest dataset mismatch: {field}")
        expected_selection = {
            "seed": SHUFFLE_SEED,
            "calibration_count": CALIBRATION_COUNT,
            "formal_count": FORMAL_COUNT,
            "calibration_indices": calibration_indices,
            "formal_indices": formal_indices,
            "cohorts_disjoint": True,
        }
        for field, expected in expected_selection.items():
            if shared_selection_data.get(field) != expected:
                raise ValueError(f"shared manifest selection mismatch: {field}")
        calibration_indices = list(shared_selection_data["calibration_indices"])
        formal_indices = list(shared_selection_data["formal_indices"])
        selection_authority = "dspark_published_shared_manifest"
        shared_selection = {
            **dict(shared_manifest_provenance),
            "local_copy": "dflash_d1c_dspark_shared_dataset_manifest.json",
            "validation": "PASS",
            "validated_fields": [
                "source repo/config/split/revision/resolved_revision",
                "dataset row_count/datasets_fingerprint/content_sha256",
                "selection seed/counts/indices/disjointness",
            ],
        }

    def cohort_rows(name: str, indices: Sequence[int]) -> list[dict[str, Any]]:
        result = []
        for cohort_position, dataset_index in enumerate(indices):
            source = source_rows[dataset_index]
            result.append(
                {
                    "schema_version": 1,
                    "dataset_repo": DATASET_REPO,
                    "dataset_config": DATASET_CONFIG,
                    "dataset_split": DATASET_SPLIT,
                    "dataset_revision": DATASET_REVISION,
                    "dataset_fingerprint": datasets_fingerprint,
                    "dataset_index": dataset_index,
                    "cohort": name,
                    "cohort_position": cohort_position,
                    "question": source["question"],
                    "answer": source["answer"],
                    "reference_answer": source["reference_answer"],
                    "reference_extraction_rule": "last_hashes",
                    "prompt": source["question"] + "\n" + PROMPT_SUFFIX,
                }
            )
        return result

    calibration = cohort_rows("calibration", calibration_indices)
    formal = cohort_rows("formal", formal_indices)
    warmup = calibration[:WARMUP_COUNT]
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_name = "dflash_d1c_gsm8k_calibration_32.jsonl"
    formal_name = "dflash_d1c_gsm8k_formal_500.jsonl"
    warmup_name = "dflash_d1c_gsm8k_warmup_10.jsonl"
    artifact_entries = {
        calibration_name: _write_jsonl(output_dir / calibration_name, calibration),
        formal_name: _write_jsonl(output_dir / formal_name, formal),
        warmup_name: _write_jsonl(output_dir / warmup_name, warmup),
    }

    shuffled_payload = _canonical_json(shuffled_indices).encode()
    source_identity = {
        "provider": "Hugging Face",
        "repo_id": DATASET_REPO,
        "config": DATASET_CONFIG,
        "split": DATASET_SPLIT,
        "revision": DATASET_REVISION,
        "resolved_revision": DATASET_REVISION,
    }
    dataset_identity = {
        "schema_version": 1,
        "immutable": True,
        "source": source_identity,
        "dataset": {
            "row_count": len(source_rows),
            "column_names": ["question", "answer"],
            "datasets_fingerprint": datasets_fingerprint,
            "content_sha256": source_content_sha256,
        },
        "generator": {"versions": dict(generator_versions)},
        "acquisition": dict(acquisition_metadata or {}),
        "selection_authority": {
            "authority": selection_authority,
            "shared_manifest": shared_selection,
        },
    }
    calibration_index_document = {
        "schema_version": 1,
        "dataset_revision": DATASET_REVISION,
        "seed": SHUFFLE_SEED,
        "cohort": "calibration",
        "count": len(calibration_indices),
        "dataset_indices": calibration_indices,
        "indices_sha256": _sha256_bytes(
            _canonical_json(calibration_indices).encode()
        ),
        "disjoint_from_formal": set(calibration_indices).isdisjoint(
            formal_indices
        ),
    }
    formal_index_document = {
        "schema_version": 1,
        "dataset_revision": DATASET_REVISION,
        "seed": SHUFFLE_SEED,
        "cohort": "formal",
        "count": len(formal_indices),
        "dataset_indices": formal_indices,
        "indices_sha256": _sha256_bytes(_canonical_json(formal_indices).encode()),
        "disjoint_from_calibration": set(formal_indices).isdisjoint(
            calibration_indices
        ),
    }
    calibration_prompt_payload = "".join(
        _canonical_json(
            {
                "dataset_index": row["dataset_index"],
                "prompt": row["prompt"],
            }
        )
        + "\n"
        for row in calibration
    ).encode()
    warmup_prompt_payload = "".join(
        _canonical_json(
            {
                "dataset_index": row["dataset_index"],
                "prompt": row["prompt"],
            }
        )
        + "\n"
        for row in warmup
    ).encode()
    formal_prompt_payload = "".join(
        _canonical_json(
            {
                "dataset_index": row["dataset_index"],
                "prompt": row["prompt"],
            }
        )
        + "\n"
        for row in formal
    ).encode()
    prompt_manifest = {
        "schema_version": 1,
        "prompt": {
            "composition": "raw_question + newline + exact_suffix",
            "separator": "\n",
            "suffix": PROMPT_SUFFIX,
            "messages": [{"role": "user", "content": "<composed prompt>"}],
            "system_prompt": None,
        },
        "generation": {
            "temperature": 0,
            "top_p": 1,
            "max_tokens": 512,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        "evidence_extensions": {
            "return_prompt_token_ids": True,
            "return_meta_info": True,
            "logprobs_requested": False,
            "observational_only": [
                "return_prompt_token_ids",
                "return_meta_info",
            ],
            "prompt_token_ids_path": "choices[0].prompt_token_ids",
            "output_token_ids_path": "choices[0].meta_info.output_token_ids",
        },
        "execution": {
            "request_order": "single_request_sequential",
            "max_concurrency": 1,
        },
        "cohorts": {
            "warmup": {
                "count": len(warmup),
                "source": "first 10 calibration rows in fixed order",
                "prompt_content_sha256": _sha256_bytes(warmup_prompt_payload),
            },
            "calibration": {
                "count": len(calibration),
                "prompt_content_sha256": _sha256_bytes(
                    calibration_prompt_payload
                ),
            },
            "formal": {
                "count": len(formal),
                "prompt_content_sha256": _sha256_bytes(formal_prompt_payload),
            },
        },
    }
    artifact_schema = {
        "schema_version": 1,
        "request_record": {
            "format": "JSON Lines; one durable terminal record per sample",
            "required_fields": [
                "request_index",
                "dataset_index",
                "cohort",
                "cohort_position",
                "question",
                "answer",
                "reference_answer",
                "prompt",
                "request_payload",
                "request_started_at_utc",
                "attempts",
                "retry_count",
                "terminal",
                "terminal_state",
                "terminal_at_utc",
                "latency_seconds",
                "tokenized_input",
                "full_response",
                "model_text",
                "output_token_ids",
                "usage",
                "extracted_answer",
                "extraction_rule",
                "parse_status",
                "answer_status",
            ],
            "terminal_states": ["success", "request_failed"],
            "answer_statuses": [
                "match",
                "mismatch",
                "parse_failure",
                "request_failed",
            ],
        },
        "summary": {
            "required_fields": [
                "cohort_kind",
                "request_count",
                "timed_request_count",
                "all_terminal",
                "terminal_counts",
                "retry_count",
                "completion_tokens",
                "wall_time_started_at_utc",
                "wall_time_ended_at_utc",
                "wall_time_seconds",
                "e2e_output_tps",
                "timing_definition",
            ],
            "e2e_output_tps": "completion_tokens / wall_time_seconds",
        },
        "response_evidence": {
            "prompt_token_ids_path": "choices[0].prompt_token_ids",
            "output_token_ids_path": "choices[0].meta_info.output_token_ids",
            "output_token_ids_required": True,
            "logprob_fallback_forbidden": True,
            "completion_tokens_path": "usage.completion_tokens",
            "completion_tokens_must_equal_output_token_id_count": True,
        },
    }
    supplemental_documents = {
        "dflash_d1c_dataset_identity.json": dataset_identity,
        "dflash_d1c_calibration_indices.json": calibration_index_document,
        "dflash_d1c_formal_indices.json": formal_index_document,
        "dflash_d1c_prompt_manifest.json": prompt_manifest,
        "dflash_d1c_artifact_schema.json": artifact_schema,
    }
    if shared_manifest is not None:
        supplemental_documents[
            "dflash_d1c_dspark_shared_dataset_manifest.json"
        ] = dict(shared_manifest)
    for artifact_name, document in supplemental_documents.items():
        artifact_entries[artifact_name] = _write_json(
            output_dir / artifact_name,
            document,
        )
    manifest = {
        "schema_version": 1,
        "immutable": True,
        "source": source_identity,
        "dataset": dataset_identity["dataset"],
        "selection": {
            "authority": selection_authority,
            "shared_manifest": shared_selection,
            "algorithm": (
                "indices=list(range(test_size)); "
                "random.Random(980406).shuffle(indices)"
            ),
            "seed": SHUFFLE_SEED,
            "calibration_count": CALIBRATION_COUNT,
            "formal_count": FORMAL_COUNT,
            "warmup_count": WARMUP_COUNT,
            "calibration_indices": calibration_indices,
            "formal_indices": formal_indices,
            "warmup_indices": calibration_indices[:WARMUP_COUNT],
            "cohorts_disjoint": set(calibration_indices).isdisjoint(formal_indices),
            "shuffled_indices_sha256": _sha256_bytes(shuffled_payload),
        },
        "generator": {"versions": dict(generator_versions)},
        "artifacts": artifact_entries,
    }
    manifest_path = output_dir / "dflash_d1c_dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _prepare_command(args: argparse.Namespace) -> int:
    from datasets import load_dataset
    from huggingface_hub import HfApi

    resolved_revision = HfApi().dataset_info(
        DATASET_REPO,
        revision=DATASET_REVISION,
    ).sha
    if resolved_revision != DATASET_REVISION:
        raise RuntimeError(
            f"resolved revision {resolved_revision!r} does not match pin "
            f"{DATASET_REVISION!r}"
        )
    dataset = load_dataset(
        DATASET_REPO,
        DATASET_CONFIG,
        split=DATASET_SPLIT,
        revision=DATASET_REVISION,
        cache_dir=str(args.cache_dir),
    )
    records = [
        {"question": row["question"], "answer": row["answer"]} for row in dataset
    ]
    versions = {
        "python": platform.python_version(),
        "datasets": _package_version("datasets"),
        "huggingface_hub": _package_version("huggingface-hub"),
        "pyarrow": _package_version("pyarrow"),
        "fsspec": _package_version("fsspec"),
    }
    shared_manifest = None
    shared_manifest_provenance = None
    if (args.shared_manifest is None) != (
        args.shared_manifest_git_commit is None
    ):
        raise ValueError(
            "--shared-manifest and --shared-manifest-git-commit must be used together"
        )
    if args.shared_manifest is not None:
        shared_manifest_bytes = args.shared_manifest.read_bytes()
        shared_manifest = json.loads(shared_manifest_bytes)
        shared_manifest_provenance = {
            "provider_lane": "dspark",
            "published_git_branch": "origin/exp/hedge-v4-dspark",
            "git_commit": args.shared_manifest_git_commit,
            "source_path_at_generation": str(args.shared_manifest.resolve()),
            "sha256": _sha256_bytes(shared_manifest_bytes),
        }
    manifest = prepare_dataset_records(
        records,
        args.output_dir,
        datasets_fingerprint=str(dataset._fingerprint),
        generator_versions=versions,
        acquisition_metadata={
            "cache_dir": str(args.cache_dir.resolve()),
            "provider_revision_resolved_via": "HfApi.dataset_info",
            "requested_revision": DATASET_REVISION,
            "resolved_revision": resolved_revision,
        },
        shared_manifest=shared_manifest,
        shared_manifest_provenance=shared_manifest_provenance,
    )
    print(
        json.dumps(
            {
                "status": "prepared",
                "output_dir": str(args.output_dir),
                "dataset_content_sha256": manifest["dataset"]["content_sha256"],
                "datasets_fingerprint": manifest["dataset"][
                    "datasets_fingerprint"
                ],
                "calibration_count": manifest["selection"]["calibration_count"],
                "formal_count": manifest["selection"]["formal_count"],
            },
            sort_keys=True,
        )
    )
    return 0


def _run_command(args: argparse.Namespace) -> int:
    samples = [
        json.loads(line)
        for line in args.dataset.read_text().splitlines()
        if line.strip()
    ]
    summary = run_cohort(
        samples,
        cohort_kind=args.cohort_kind,
        base_url=args.base_url,
        model=args.model,
        output_path=args.output,
        summary_path=args.summary,
        max_attempts=args.max_attempts,
        request_timeout_seconds=args.request_timeout_seconds,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    print(json.dumps(summary, sort_keys=True))
    return 2 if summary["terminal_counts"]["request_failure"] else 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "DFlash D1C protocol harness pinned to "
            f"openai/gsm8k@{DATASET_REVISION}"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser(
        "prepare",
        help="acquire the pinned GSM8K revision and write 32+500 artifacts",
    )
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--cache-dir", type=Path, required=True)
    prepare.add_argument("--shared-manifest", type=Path)
    prepare.add_argument("--shared-manifest-git-commit")
    prepare.set_defaults(handler=_prepare_command)

    run = subparsers.add_parser(
        "run",
        help="run one OpenAI-compatible cohort sequentially",
    )
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument(
        "--cohort-kind",
        choices=("calibration", "warmup", "formal"),
        required=True,
    )
    run.add_argument("--base-url", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--summary", type=Path, required=True)
    run.add_argument("--max-attempts", type=int, choices=(1, 2, 3), default=3)
    run.add_argument("--request-timeout-seconds", type=float, default=300)
    run.add_argument("--retry-backoff-seconds", type=float, default=1)
    run.set_defaults(handler=_run_command)
    return parser


def main() -> int:
    args = _argument_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
