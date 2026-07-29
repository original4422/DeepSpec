#!/usr/bin/env python3
"""Exercise the Phase 02 OpenAI seam with bounded sequential requests."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_eagle3_phase01b.tools import _response_fields


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROMPTS = (
    "What is 2+2? Reply with the number only.",
    "What is 7 minus 3? Reply with the number only.",
    "What is 3 times 5? Reply with the number only.",
)


def extract_native_acceptance_trace(
    response: dict,
    *,
    proposal_tokens: int,
) -> dict:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise RuntimeError(
            "native response does not have exactly one choice"
        )
    meta_info = choices[0].get("meta_info")
    if not isinstance(meta_info, dict):
        raise RuntimeError("native response lacks speculative meta_info")

    integer_fields = {
        "spec_verify_ct": "verify_count",
        "spec_num_correct_drafts": "accepted_draft_tokens",
        "spec_num_proposed_drafts": "proposed_draft_tokens",
    }
    observed = {}
    for source_name, output_name in integer_fields.items():
        value = meta_info.get(source_name)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise RuntimeError(
                f"native response has invalid {source_name}: {value!r}"
            )
        observed[output_name] = value
    if observed["verify_count"] <= 0:
        raise RuntimeError("native response has no target verify step")
    if observed["proposed_draft_tokens"] != (
        observed["verify_count"] * proposal_tokens
    ):
        raise RuntimeError(
            "native proposed draft count does not prove the fixed "
            f"{proposal_tokens}-token width"
        )
    if (
        observed["accepted_draft_tokens"]
        > observed["proposed_draft_tokens"]
    ):
        raise RuntimeError("native accepted draft count exceeds proposals")

    histogram = meta_info.get("spec_correct_drafts_histogram")
    if (
        not isinstance(histogram, list)
        or not 1 <= len(histogram) <= proposal_tokens + 1
        or not all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            for value in histogram
        )
    ):
        raise RuntimeError("native response lacks a valid acceptance histogram")
    histogram = list(histogram) + [0] * (
        proposal_tokens + 1 - len(histogram)
    )
    if sum(histogram) != observed["verify_count"]:
        raise RuntimeError("native acceptance histogram count differs")
    if sum(
        accepted * count for accepted, count in enumerate(histogram)
    ) != observed["accepted_draft_tokens"]:
        raise RuntimeError("native acceptance histogram weighted sum differs")

    accept_rate = meta_info.get("spec_accept_rate")
    accept_length = meta_info.get("spec_accept_length")
    if (
        not isinstance(accept_rate, (int, float))
        or isinstance(accept_rate, bool)
        or not 0 <= float(accept_rate) <= 1
    ):
        raise RuntimeError("native response has invalid acceptance rate")
    expected_rate = (
        observed["accepted_draft_tokens"]
        / observed["proposed_draft_tokens"]
    )
    if abs(float(accept_rate) - expected_rate) > 1e-12:
        raise RuntimeError("native acceptance rate differs from counts")
    if (
        not isinstance(accept_length, (int, float))
        or isinstance(accept_length, bool)
        or float(accept_length) <= 0
    ):
        raise RuntimeError("native response has invalid acceptance length")
    return {
        "proposal_tokens": proposal_tokens,
        "internal_verify_width": proposal_tokens + 1,
        **observed,
        "acceptance_rate": float(accept_rate),
        "acceptance_length": float(accept_length),
        "accepted_drafts_histogram": list(histogram),
    }


def request_json(url: str, payload: dict | None, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with OPENER.open(request, timeout=timeout) as response:
        return {
            "http_status": response.status,
            "body": json.loads(response.read()),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", choices=("target", "native"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": args.mode,
        "model": args.model,
        "sequential": True,
        "maximum_in_flight": 1,
        "responses": [],
        "acceptance_trace": [],
    }
    try:
        models = request_json(
            f"{args.base_url}/v1/models", None, args.timeout
        )
        if not models["body"].get("data"):
            raise RuntimeError("models endpoint returned no models")
        count = 1 if args.mode == "target" else 3
        for index, prompt in enumerate(PROMPTS[:count]):
            payload = {
                "model": args.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 32,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "return_meta_info": True,
                "logprobs": True,
                "top_logprobs": 0,
            }
            response = request_json(
                f"{args.base_url}/v1/chat/completions",
                payload,
                args.timeout,
            )
            content, output_token_ids, completion_tokens = (
                _response_fields(response["body"])
            )
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError(f"request {index} has empty content")
            acceptance_trace = None
            if args.mode == "native":
                acceptance_trace = extract_native_acceptance_trace(
                    response["body"],
                    proposal_tokens=3,
                )
                result["acceptance_trace"].append(
                    {"request_index": index, **acceptance_trace}
                )
            result["responses"].append(
                {
                    "index": index,
                    "request": payload,
                    "response": response,
                    "output_token_ids": output_token_ids,
                    "completion_tokens": completion_tokens,
                    "acceptance_trace": acceptance_trace,
                }
            )
        result.update(status="PASS", models_response=models)
    except Exception as error:
        error_body = ""
        if isinstance(error, urllib.error.HTTPError):
            error_body = error.read().decode(errors="replace")
        result.update(
            status="FAIL",
            error=repr(error),
            error_body=error_body,
        )
    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
