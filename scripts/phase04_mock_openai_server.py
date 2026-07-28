#!/usr/bin/env python3
"""Small OpenAI-compatible fixture used only by Phase 04 offline tests."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from phase05_gsm8k_smoke import extract_reference


class Handler(BaseHTTPRequestHandler):
    answers: dict[str, str] = {}
    seen: dict[str, int] = {}
    fail_first = False
    model = "deepseek-v4-flash-dspark"

    def write_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.write_json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self.write_json(
                200, {"object": "list", "data": [{"id": self.model, "object": "model"}]}
            )
        else:
            self.write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        prompt = request["messages"][-1]["content"]
        answer = "4"
        question = next((q for q in self.answers if q in prompt), None)
        if question is not None:
            count = self.seen.get(question, 0) + 1
            self.seen[question] = count
            if self.fail_first and count == 1:
                self.write_json(503, {"error": "intentional first-attempt fixture"})
                return
            answer = self.answers[question]
        self.write_json(
            200,
            {
                "id": "chatcmpl-phase04-fixture",
                "object": "chat.completion",
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"Fixture reasoning. Final answer: {answer}",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fail-first-gsm8k", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text().splitlines()]
    Handler.answers = {
        row["question"]: extract_reference(row["answer"]) or "" for row in rows
    }
    Handler.fail_first = args.fail_first_gsm8k
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fixture_ready host={args.host} port={args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
