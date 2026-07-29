#!/usr/bin/env python3
"""One bounded, non-thinking OpenAI-compatible DFlash smoke request."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests-output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

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
        "phase": "D3",
        "mode": "native_dflash",
        "started_at_utc": utc_now(),
        "base_url": args.base_url,
        "model": args.model,
        "request": payload,
    }
    started = time.monotonic()
    try:
        models = request_json(
            f"{args.base_url}/v1/models", None, min(args.timeout, 30.0)
        )
        server_info = request_json(
            f"{args.base_url}/server_info", None, min(args.timeout, 30.0)
        )
        request_marker = args.output.parent / "request.active"
        request_marker.write_text(utc_now() + "\n")
        try:
            chat = request_json(
                f"{args.base_url}/v1/chat/completions", payload, args.timeout
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
        if completion_tokens < 0 or len(output_ids) != completion_tokens:
            raise ValueError(
                "output token ID count mismatch: "
                f"ids={len(output_ids)} completion_tokens={completion_tokens}"
            )
        meta_completion = int(meta.get("completion_tokens", completion_tokens))
        if meta_completion != completion_tokens:
            raise ValueError(
                "meta_info completion count differs from usage: "
                f"meta={meta_completion} usage={completion_tokens}"
            )
        result.update(
            status="PASS",
            models_response=models,
            server_info=server_info,
            chat_response=chat,
            output_token_id_count=len(output_ids),
            completion_tokens=completion_tokens,
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
