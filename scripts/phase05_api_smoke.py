#!/usr/bin/env python3
"""Minimal OpenAI-compatible models and chat-completions smoke."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request_json(url: str, *, payload: dict | None, timeout: float) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with LOCAL_OPENER.open(request, timeout=timeout) as response:
        return {"http_status": response.status, "body": json.loads(response.read())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "model": args.model,
    }
    try:
        models = request_json(
            f"{args.base_url}/v1/models", payload=None, timeout=args.timeout
        )
        if not models["body"].get("data"):
            raise ValueError("models response has no data")
        chat = request_json(
            f"{args.base_url}/v1/chat/completions",
            payload={
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
            },
            timeout=args.timeout,
        )
        content = chat["body"]["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("chat response content is empty")
        result.update(status="PASS", models_response=models, chat_response=chat)
    except Exception as error:
        body = ""
        if isinstance(error, urllib.error.HTTPError):
            body = error.read().decode(errors="replace")
        result.update(status="FAIL", error=repr(error), error_body=body)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
