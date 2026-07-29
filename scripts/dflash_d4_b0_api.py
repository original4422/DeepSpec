#!/usr/bin/env python3
"""One bounded DFlash HEDGE B=0 smoke and lifecycle/counter audit."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
EXPECTED_CONFIG = {
    "B": 0,
    "g": 1_000_000,
    "m": 1,
    "value_scheme": "normalized_suffix",
    "block_size": 7,
}
EXPECTED_D3_OUTPUT_TOKEN_IDS = [22, 1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request_json(url: str, payload: dict | None, timeout: float) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with OPENER.open(request, timeout=timeout) as response:
        return {
            "http_status": response.status,
            "body": json.loads(response.read()),
        }


def validate_hedge_snapshot(server_info: dict) -> dict:
    """Validate the final DP=1 DFlash HEDGE snapshot and return its counters."""

    internal_states = server_info.get("internal_states")
    if not isinstance(internal_states, list) or len(internal_states) != 1:
        raise ValueError("expected exactly one DP internal state")
    dflash = internal_states[0].get("dflash_info_record")
    if not isinstance(dflash, dict):
        raise ValueError("dflash_info_record is missing")
    hedge = dflash.get("hedge")
    if not isinstance(hedge, dict):
        raise ValueError("dflash_info_record.hedge is missing")
    if hedge.get("mode") != "enabled":
        raise ValueError(f"unexpected HEDGE mode: {hedge.get('mode')!r}")
    if hedge.get("config") != EXPECTED_CONFIG:
        raise ValueError(f"unexpected HEDGE config: {hedge.get('config')!r}")
    if hedge.get("proposal_width") != 7:
        raise ValueError("DFlash HEDGE proposal_width is not 7")

    proposals = int(hedge.get("proposals", -1))
    verifiable = int(hedge.get("draft_tokens_verifiable", -1))
    strict = int(hedge.get("strict_accepted_draft_tokens", -1))
    accepted = int(hedge.get("hedge_accepted_draft_tokens", -1))
    if proposals < 1:
        raise ValueError("no DFlash proposal was observed")
    if verifiable != proposals * 7:
        raise ValueError(
            f"verifiable draft count mismatch: {verifiable} != {proposals}*7"
        )
    if strict != accepted:
        raise ValueError(
            f"B=0 strict/HEDGE accepted mismatch: {strict} != {accepted}"
        )
    if int(hedge.get("relaxed_mismatches", -1)) != 0:
        raise ValueError("B=0 recorded a relaxed mismatch")
    charged = float(hedge.get("regret_charged", math.nan))
    if not math.isfinite(charged) or charged != 0.0:
        raise ValueError(f"B=0 charged non-zero regret: {charged}")

    positions = hedge.get("accepted_draft_tokens_by_position")
    if not isinstance(positions, list) or len(positions) != 7:
        raise ValueError("accepted-by-position must contain seven entries")
    positions = [int(value) for value in positions]
    if any(value < 0 for value in positions):
        raise ValueError("accepted-by-position contains a negative count")
    if any(left < right for left, right in zip(positions, positions[1:])):
        raise ValueError("accepted-by-position is not a prefix distribution")
    if sum(positions) != accepted:
        raise ValueError("accepted-by-position does not sum to accepted drafts")

    histogram = hedge.get("accept_length_histogram")
    if not isinstance(histogram, list) or len(histogram) != 8:
        raise ValueError("accept-length histogram must contain 0..7")
    histogram = [int(value) for value in histogram]
    if any(value < 0 for value in histogram):
        raise ValueError("accept-length histogram contains a negative count")
    if sum(histogram) != proposals:
        raise ValueError("accept-length histogram does not sum to proposals")
    if sum(length * count for length, count in enumerate(histogram)) != accepted:
        raise ValueError("accept-length histogram does not sum to accepted drafts")

    if int(hedge.get("requests_initialized", -1)) < 1:
        raise ValueError("request initialization counter is missing")
    if int(hedge.get("requests_finished", -1)) < 1:
        raise ValueError("request finish counter is missing")
    if int(hedge.get("active_request_states", -1)) != 0:
        raise ValueError("request state remained active after terminal response")
    if int(hedge.get("state_leaks", -1)) != 0:
        raise ValueError("HEDGE request state leak detected")
    request_state = hedge.get("request_state", [])
    if request_state != []:
        raise ValueError("request_state was not cleared")
    return hedge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests-output", type=Path, required=True)
    parser.add_argument("--counters-output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--expected-output-token-ids",
        default=json.dumps(EXPECTED_D3_OUTPUT_TOKEN_IDS),
    )
    args = parser.parse_args()
    expected_output_ids = json.loads(args.expected_output_token_ids)
    if expected_output_ids != EXPECTED_D3_OUTPUT_TOKEN_IDS:
        raise ValueError(
            "D4-C must compare against the sealed D3 a05 token IDs "
            f"{EXPECTED_D3_OUTPUT_TOKEN_IDS}"
        )

    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": "What is 2+2? Reply with the number only.",
            }
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 32,
        "stream": False,
        "reasoning_effort": "none",
        "chat_template_kwargs": {
            "enable_thinking": False,
            "thinking": False,
        },
        "return_meta_info": True,
        "return_prompt_token_ids": True,
    }
    result = {
        "schema_version": 1,
        "phase": "D4-C",
        "mode": "dflash_hedge_b0",
        "started_at_utc": utc_now(),
        "base_url": args.base_url,
        "model": args.model,
        "request": payload,
        "expected_d3_output_token_ids": expected_output_ids,
    }
    started = time.monotonic()
    try:
        models = request_json(
            f"{args.base_url}/v1/models",
            None,
            min(args.timeout, 30.0),
        )
        server_info_before = request_json(
            f"{args.base_url}/get_server_info",
            None,
            min(args.timeout, 30.0),
        )
        request_marker = args.output.parent / "request.active"
        request_marker.write_text(utc_now() + "\n")
        try:
            chat = request_json(
                f"{args.base_url}/v1/chat/completions",
                payload,
                args.timeout,
            )
        finally:
            request_marker.unlink(missing_ok=True)

        choice = chat["body"]["choices"][0]
        content = choice["message"].get("content")
        usage = chat["body"].get("usage") or {}
        meta = choice.get("meta_info") or {}
        output_ids = meta.get("output_token_ids")
        completion_tokens = int(usage.get("completion_tokens", -1))
        if not models["body"].get("data"):
            raise ValueError("models response has no data")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("chat response content is empty")
        if not isinstance(output_ids, list):
            raise ValueError("choices[0].meta_info.output_token_ids is missing")
        output_ids = [int(token_id) for token_id in output_ids]
        if completion_tokens < 0 or len(output_ids) != completion_tokens:
            raise ValueError(
                "output token ID count mismatch: "
                f"ids={len(output_ids)} completion_tokens={completion_tokens}"
            )
        if output_ids != expected_output_ids:
            raise ValueError(
                "D4 B=0 differs from sealed D3 native smoke token IDs: "
                f"{output_ids} != {expected_output_ids}"
            )

        snapshot_deadline = time.monotonic() + min(args.timeout, 30.0)
        snapshot_error = None
        server_info_after = None
        hedge = None
        while time.monotonic() < snapshot_deadline:
            server_info_after = request_json(
                f"{args.base_url}/get_server_info",
                None,
                min(args.timeout, 30.0),
            )
            try:
                hedge = validate_hedge_snapshot(server_info_after["body"])
                break
            except ValueError as error:
                snapshot_error = error
                time.sleep(0.2)
        if hedge is None:
            raise ValueError(
                "terminal HEDGE snapshot did not become valid: "
                f"{snapshot_error!r}"
            )

        counters_document = {
            "schema_version": 1,
            "status": "PASS",
            "phase": "D4-C",
            "mode": "dflash_hedge_b0",
            "captured_at_utc": utc_now(),
            "endpoint": "/get_server_info",
            "hedge": hedge,
        }
        args.counters_output.write_text(
            json.dumps(counters_document, indent=2, sort_keys=True) + "\n"
        )
        result.update(
            status="PASS",
            models_response=models,
            server_info_before=server_info_before,
            server_info_after=server_info_after,
            chat_response=chat,
            output_token_ids=output_ids,
            output_token_id_count=len(output_ids),
            completion_tokens=completion_tokens,
            d3_token_id_match=True,
            hedge_snapshot=hedge,
        )
    except Exception as error:
        error_body = ""
        if isinstance(error, urllib.error.HTTPError):
            error_body = error.read().decode(errors="replace")
        result.update(status="FAIL", error=repr(error), error_body=error_body)
    result["elapsed_seconds"] = time.monotonic() - started
    result["finished_at_utc"] = utc_now()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    with args.requests_output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
