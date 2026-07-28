#!/usr/bin/env python3
"""Sequential GSM8K smoke runner with bounded retries and numeric comparison."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

NUMBER = r"[-+]?(?:\$\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def normalize_number(raw: str) -> str | None:
    value = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        return None
    if not decimal.is_finite():
        return None
    if decimal == 0:
        return "0"
    rendered = format(decimal, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def extract_reference(answer: str) -> str | None:
    matches = re.findall(rf"####\s*({NUMBER})", answer)
    return normalize_number(matches[-1]) if matches else None


def extract_model_answer(text: str) -> tuple[str | None, str | None]:
    rules = (
        ("boxed", rf"\\boxed\{{\s*({NUMBER})\s*\}}"),
        ("hashes", rf"####\s*({NUMBER})"),
        (
            "final_answer",
            rf"(?i)\bfinal\s+answer\s*(?::|=|\bis\b)?\s*({NUMBER})",
        ),
        ("last_number", rf"({NUMBER})"),
    )
    for rule, pattern in rules:
        matches = re.findall(pattern, text)
        if matches:
            normalized = normalize_number(matches[-1])
            if normalized is not None:
                return normalized, rule
    return None, None


def request_json(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with LOCAL_OPENER.open(request, timeout=timeout) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default="deepseek-v4-flash-dspark")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()
    if not 1 <= args.max_attempts <= 3:
        raise ValueError("max-attempts must be between 1 and 3")
    samples = [json.loads(line) for line in args.dataset.read_text().splitlines()]
    if len(samples) != 10:
        raise ValueError("dataset must contain exactly 10 samples")
    counts = {
        "total": 10,
        "success_requests": 0,
        "failed_requests": 0,
        "matches": 0,
        "mismatches": 0,
        "parse_failures": 0,
    }
    with args.output.open("w") as output:
        for index, sample in enumerate(samples):
            expected = extract_reference(sample["answer"])
            attempts: list[dict] = []
            response = None
            for attempt in range(1, args.max_attempts + 1):
                try:
                    response = request_json(
                        f"{args.base_url}/v1/chat/completions",
                        {
                            "model": args.model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        "Solve this math word problem. End with "
                                        "`Final answer: <number>`.\n\n"
                                        + sample["question"]
                                    ),
                                }
                            ],
                            "temperature": 0.0,
                            "top_p": 1.0,
                            "max_tokens": args.max_tokens,
                            "stream": False,
                        },
                        args.timeout,
                    )
                    attempts.append({"attempt": attempt, "status": "success"})
                    break
                except (OSError, ValueError, urllib.error.HTTPError) as error:
                    body = ""
                    if isinstance(error, urllib.error.HTTPError):
                        body = error.read().decode(errors="replace")
                    attempts.append(
                        {
                            "attempt": attempt,
                            "status": "error",
                            "error": repr(error),
                            "response_body": body,
                        }
                    )
                    if attempt < args.max_attempts:
                        time.sleep(1)
            record = {
                "sample_index": index,
                "question": sample["question"],
                "reference_response": sample["answer"],
                "reference_answer": expected,
                "attempts": attempts,
                "request_succeeded": response is not None,
                "response": response,
            }
            if response is None:
                counts["failed_requests"] += 1
                record.update(
                    parse_status="not_attempted_after_request_failure",
                    extracted_answer=None,
                    extraction_rule=None,
                    matched=False,
                )
            else:
                counts["success_requests"] += 1
                text = response["choices"][0]["message"].get("content") or ""
                extracted, rule = extract_model_answer(text)
                record["model_text"] = text
                record["extracted_answer"] = extracted
                record["extraction_rule"] = rule
                if extracted is None or expected is None:
                    counts["parse_failures"] += 1
                    record["parse_status"] = "parse_failure"
                    record["matched"] = False
                else:
                    record["parse_status"] = "parsed"
                    record["matched"] = extracted == expected
                    counts["matches" if record["matched"] else "mismatches"] += 1
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            output.flush()
    counts["all_terminal"] = (
        counts["success_requests"] + counts["failed_requests"] == counts["total"]
    )
    args.summary.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n")
    if counts["failed_requests"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
