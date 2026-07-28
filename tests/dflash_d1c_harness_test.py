#!/usr/bin/env python3
"""Behavior tests for the DFlash D1C dataset and request harness."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dflash_d1c_harness import (
    DATASET_REVISION,
    PROMPT_SUFFIX,
    build_chat_request,
    extract_model_answer,
    prepare_dataset_records,
    run_cohort,
)


class _MockOpenAIHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    response_factory = None
    first_request_monotonic_ns: int | None = None
    last_response_monotonic_ns: int | None = None
    active_requests = 0
    maximum_active_requests = 0

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        type(self).first_request_monotonic_ns = (
            type(self).first_request_monotonic_ns or time.monotonic_ns()
        )
        type(self).active_requests += 1
        type(self).maximum_active_requests = max(
            type(self).maximum_active_requests,
            type(self).active_requests,
        )
        try:
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            type(self).requests.append(request)
            status, body = type(self).response_factory(request)
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            type(self).last_response_monotonic_ns = time.monotonic_ns()
        finally:
            type(self).active_requests -= 1

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def mock_openai_server(response_factory) -> Iterator[tuple[str, type]]:
    class Handler(_MockOpenAIHandler):
        pass

    Handler.requests = []
    Handler.response_factory = staticmethod(response_factory)
    Handler.first_request_monotonic_ns = None
    Handler.last_response_monotonic_ns = None
    Handler.active_requests = 0
    Handler.maximum_active_requests = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class DatasetPreparationTest(unittest.TestCase):
    def test_fixed_shuffle_produces_disjoint_32_and_500_cohorts(self) -> None:
        rows = [
            {
                "question": f"Question {index}?",
                "answer": f"Worked solution {index}.\n#### {index:,}",
            }
            for index in range(600)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            manifest = prepare_dataset_records(
                rows,
                output_dir,
                datasets_fingerprint="fixture-hf-fingerprint",
                generator_versions={"python": "fixture"},
            )
            calibration = [
                json.loads(line)
                for line in (
                    output_dir / "dflash_d1c_gsm8k_calibration_32.jsonl"
                ).read_text().splitlines()
            ]
            formal = [
                json.loads(line)
                for line in (
                    output_dir / "dflash_d1c_gsm8k_formal_500.jsonl"
                ).read_text().splitlines()
            ]
            warmup = [
                json.loads(line)
                for line in (
                    output_dir / "dflash_d1c_gsm8k_warmup_10.jsonl"
                ).read_text().splitlines()
            ]

        self.assertEqual(len(calibration), 32)
        self.assertEqual(len(formal), 500)
        self.assertEqual(
            [row["dataset_index"] for row in warmup],
            [row["dataset_index"] for row in calibration[:10]],
        )
        self.assertEqual(
            [row["dataset_index"] for row in calibration[:4]],
            [38, 361, 424, 200],
        )
        self.assertEqual(
            [row["dataset_index"] for row in formal[:4]],
            [293, 299, 7, 398],
        )
        self.assertTrue(
            set(row["dataset_index"] for row in calibration).isdisjoint(
                row["dataset_index"] for row in formal
            )
        )
        first = calibration[0]
        self.assertEqual(first["question"], "Question 38?")
        self.assertEqual(first["answer"], "Worked solution 38.\n#### 38")
        self.assertEqual(first["reference_answer"], "38")
        self.assertEqual(
            first["prompt"],
            "Question 38?\n" + PROMPT_SUFFIX,
        )
        self.assertEqual(manifest["selection"]["calibration_count"], 32)
        self.assertEqual(manifest["selection"]["formal_count"], 500)
        self.assertEqual(manifest["selection"]["warmup_count"], 10)
        self.assertTrue(manifest["selection"]["cohorts_disjoint"])

        with tempfile.TemporaryDirectory() as temporary:
            reused = prepare_dataset_records(
                rows,
                Path(temporary),
                datasets_fingerprint="fixture-hf-fingerprint",
                generator_versions={"python": "fixture"},
                shared_manifest=manifest,
                shared_manifest_provenance={
                    "git_commit": "fixture-commit",
                    "sha256": "fixture-sha256",
                },
            )
        self.assertEqual(
            reused["selection"]["authority"],
            "dspark_published_shared_manifest",
        )
        self.assertEqual(
            reused["selection"]["shared_manifest"]["git_commit"],
            "fixture-commit",
        )

    def test_preparation_publishes_identity_prompt_indices_and_artifact_schema(self) -> None:
        rows = [
            {
                "question": f"Question {index}?",
                "answer": f"Worked solution.\n#### {index}",
            }
            for index in range(532)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            prepare_dataset_records(
                rows,
                output_dir,
                datasets_fingerprint="fixture-fingerprint",
                generator_versions={
                    "python": "3.fixture",
                    "datasets": "fixture",
                },
            )
            identity = json.loads(
                (output_dir / "dflash_d1c_dataset_identity.json").read_text()
            )
            calibration_indices = json.loads(
                (output_dir / "dflash_d1c_calibration_indices.json").read_text()
            )
            formal_indices = json.loads(
                (output_dir / "dflash_d1c_formal_indices.json").read_text()
            )
            prompt_manifest = json.loads(
                (output_dir / "dflash_d1c_prompt_manifest.json").read_text()
            )
            artifact_schema = json.loads(
                (output_dir / "dflash_d1c_artifact_schema.json").read_text()
            )

        self.assertEqual(identity["source"]["revision"], DATASET_REVISION)
        self.assertEqual(identity["dataset"]["datasets_fingerprint"], "fixture-fingerprint")
        self.assertEqual(len(calibration_indices["dataset_indices"]), 32)
        self.assertEqual(len(formal_indices["dataset_indices"]), 500)
        self.assertTrue(calibration_indices["disjoint_from_formal"])
        self.assertEqual(prompt_manifest["prompt"]["suffix"], PROMPT_SUFFIX)
        self.assertIsNone(prompt_manifest["prompt"]["system_prompt"])
        self.assertEqual(
            prompt_manifest["generation"],
            {
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 512,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        self.assertEqual(prompt_manifest["execution"]["max_concurrency"], 1)
        self.assertIn(
            "output_token_ids",
            artifact_schema["request_record"]["required_fields"],
        )
        self.assertIn(
            "wall_time_seconds",
            artifact_schema["summary"]["required_fields"],
        )


class RequestProtocolTest(unittest.TestCase):
    def test_chat_request_has_the_exact_prompt_and_decode_parameters(self) -> None:
        request = build_chat_request(
            {
                "prompt": "How many?\n" + PROMPT_SUFFIX,
            },
            model="fixture-model",
        )

        self.assertEqual(
            request,
            {
                "model": "fixture-model",
                "messages": [
                    {
                        "role": "user",
                        "content": "How many?\n" + PROMPT_SUFFIX,
                    }
                ],
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 512,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "return_prompt_token_ids": True,
                "return_meta_info": True,
            },
        )


class AnswerParsingTest(unittest.TestCase):
    def test_last_boxed_answer_has_priority_over_later_numbers(self) -> None:
        self.assertEqual(
            extract_model_answer(
                r"first \boxed{8}; corrected \boxed{$1,200.00}; checksum 99"
            ),
            ("1200", "last_boxed"),
        )

    def test_last_hashes_is_used_when_no_numeric_boxed_answer_exists(self) -> None:
        self.assertEqual(
            extract_model_answer(r"\boxed{unknown}; #### 3; corrected #### $4.50"),
            ("4.5", "last_hashes"),
        )

    def test_explicit_final_answer_is_used_before_unlabelled_numbers(self) -> None:
        self.assertEqual(
            extract_model_answer("work used 21. Final answer is $007.500; checksum 99"),
            ("7.5", "explicit_final_answer"),
        )

    def test_last_number_is_the_final_numeric_fallback(self) -> None:
        self.assertEqual(
            extract_model_answer("first estimate 10, then corrected to -2.00"),
            ("-2", "last_number"),
        )


class SequentialHarnessTest(unittest.TestCase):
    def test_success_preserves_required_api_evidence_and_terminal_state(self) -> None:
        def respond(_request: dict) -> tuple[int, dict]:
            return (
                200,
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion",
                    "model": "fixture-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": r"Work. \boxed{7}",
                            },
                            "finish_reason": "stop",
                            "prompt_token_ids": [101, 202, 303],
                            "meta_info": {"output_token_ids": [7001, 7002]},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 2,
                        "total_tokens": 5,
                    },
                },
            )

        sample = {
            "dataset_index": 11,
            "cohort": "fixture",
            "cohort_position": 0,
            "question": "How many?",
            "answer": "Reference work.\n#### 7",
            "reference_answer": "7",
            "prompt": "How many?\n" + PROMPT_SUFFIX,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requests.jsonl"
            summary_path = Path(temporary) / "summary.json"
            with mock_openai_server(respond) as (base_url, handler):
                summary = run_cohort(
                    [sample],
                    base_url=base_url,
                    model="fixture-model",
                    output_path=output,
                    summary_path=summary_path,
                    max_attempts=3,
                    request_timeout_seconds=2,
                    retry_backoff_seconds=0,
                )
            record = json.loads(output.read_text())

        self.assertEqual(len(handler.requests), 1)
        self.assertEqual(record["terminal_state"], "success")
        self.assertEqual(record["tokenized_input"]["token_ids"], [101, 202, 303])
        self.assertEqual(record["output_token_ids"], [7001, 7002])
        self.assertEqual(record["usage"]["completion_tokens"], 2)
        self.assertEqual(record["full_response"]["id"], "chatcmpl-fixture")
        self.assertGreaterEqual(record["latency_seconds"], 0)
        self.assertEqual(record["retry_count"], 0)
        self.assertEqual(record["answer_status"], "match")
        self.assertTrue(record["terminal"])
        self.assertEqual(summary["completion_tokens"], 2)
        self.assertTrue(summary["all_terminal"])

    def test_retryable_http_errors_are_bounded_and_preserved(self) -> None:
        calls = 0

        def respond(_request: dict) -> tuple[int, dict]:
            nonlocal calls
            calls += 1
            if calls < 3:
                return 503, {"error": f"fixture failure {calls}"}
            return (
                200,
                {
                    "id": "chatcmpl-after-retry",
                    "choices": [
                        {
                            "message": {"content": "Final answer: 5"},
                            "prompt_token_ids": [10],
                            "meta_info": {"output_token_ids": [50]},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )

        sample = {
            "dataset_index": 12,
            "cohort": "fixture",
            "cohort_position": 0,
            "question": "Retry me?",
            "answer": "Reference.\n#### 5",
            "reference_answer": "5",
            "prompt": "Retry me?\n" + PROMPT_SUFFIX,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requests.jsonl"
            summary_path = Path(temporary) / "summary.json"
            with mock_openai_server(respond) as (base_url, _handler):
                summary = run_cohort(
                    [sample],
                    base_url=base_url,
                    model="fixture-model",
                    output_path=output,
                    summary_path=summary_path,
                    max_attempts=3,
                    request_timeout_seconds=2,
                    retry_backoff_seconds=0,
                )
            record = json.loads(output.read_text())

        self.assertEqual(calls, 3)
        self.assertEqual(
            [attempt["status"] for attempt in record["attempts"]],
            ["error", "error", "success"],
        )
        self.assertEqual(record["retry_count"], 2)
        self.assertEqual(record["terminal_state"], "success")
        self.assertEqual(summary["retry_count"], 2)

    def test_exhausted_retries_become_a_failure_terminal_record(self) -> None:
        def respond(_request: dict) -> tuple[int, dict]:
            return 503, {"error": "fixture remains unavailable"}

        sample = {
            "dataset_index": 13,
            "cohort": "fixture",
            "cohort_position": 0,
            "question": "Always fail?",
            "answer": "Reference.\n#### 9",
            "reference_answer": "9",
            "prompt": "Always fail?\n" + PROMPT_SUFFIX,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requests.jsonl"
            summary_path = Path(temporary) / "summary.json"
            with mock_openai_server(respond) as (base_url, handler):
                summary = run_cohort(
                    [sample],
                    base_url=base_url,
                    model="fixture-model",
                    output_path=output,
                    summary_path=summary_path,
                    max_attempts=3,
                    request_timeout_seconds=2,
                    retry_backoff_seconds=0,
                )
            record = json.loads(output.read_text())

        self.assertEqual(len(handler.requests), 3)
        self.assertEqual(record["terminal_state"], "request_failed")
        self.assertEqual(record["answer_status"], "request_failed")
        self.assertEqual(record["retry_count"], 2)
        self.assertTrue(record["terminal"])
        self.assertIsNone(record["full_response"])
        self.assertEqual(record["output_token_ids"], [])
        self.assertEqual(summary["terminal_counts"]["request_failure"], 1)
        self.assertEqual(summary["completion_tokens"], 0)
        self.assertTrue(summary["all_terminal"])

    def test_unparseable_success_is_a_parse_failure_not_a_request_failure(self) -> None:
        def respond(_request: dict) -> tuple[int, dict]:
            return (
                200,
                {
                    "id": "chatcmpl-unparseable",
                    "choices": [
                        {
                            "message": {"content": "No numeric conclusion."},
                            "prompt_token_ids": [1, 2],
                            "meta_info": {"output_token_ids": [80, 81]},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 2,
                        "completion_tokens": 2,
                        "total_tokens": 4,
                    },
                },
            )

        sample = {
            "dataset_index": 14,
            "cohort": "fixture",
            "cohort_position": 0,
            "question": "Cannot parse?",
            "answer": "Reference.\n#### 4",
            "reference_answer": "4",
            "prompt": "Cannot parse?\n" + PROMPT_SUFFIX,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requests.jsonl"
            summary_path = Path(temporary) / "summary.json"
            with mock_openai_server(respond) as (base_url, _handler):
                summary = run_cohort(
                    [sample],
                    base_url=base_url,
                    model="fixture-model",
                    output_path=output,
                    summary_path=summary_path,
                    max_attempts=3,
                    request_timeout_seconds=2,
                    retry_backoff_seconds=0,
                )
            record = json.loads(output.read_text())

        self.assertEqual(record["terminal_state"], "success")
        self.assertEqual(record["parse_status"], "parse_failure")
        self.assertEqual(record["answer_status"], "parse_failure")
        self.assertEqual(summary["terminal_counts"]["parse_failure"], 1)
        self.assertEqual(summary["terminal_counts"]["request_failure"], 0)

    def test_formal_500_timing_covers_dispatch_through_last_terminal(self) -> None:
        response_index = 0

        def respond(_request: dict) -> tuple[int, dict]:
            nonlocal response_index
            current = response_index
            response_index += 1
            return (
                200,
                {
                    "id": f"chatcmpl-formal-{current}",
                    "choices": [
                        {
                            "message": {"content": r"Work. \boxed{1}"},
                            "prompt_token_ids": [current],
                            "meta_info": {
                                "output_token_ids": [
                                    10000 + current * 2,
                                    10001 + current * 2,
                                ],
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "total_tokens": 3,
                    },
                },
            )

        samples = [
            {
                "dataset_index": index,
                "cohort": "formal",
                "cohort_position": index,
                "question": f"Question {index}?",
                "answer": "Reference.\n#### 1",
                "reference_answer": "1",
                "prompt": f"Question {index}?\n" + PROMPT_SUFFIX,
            }
            for index in range(500)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requests.jsonl"
            summary_path = Path(temporary) / "summary.json"
            with mock_openai_server(respond) as (base_url, handler):
                summary = run_cohort(
                    samples,
                    cohort_kind="formal",
                    base_url=base_url,
                    model="fixture-model",
                    output_path=output,
                    summary_path=summary_path,
                    max_attempts=3,
                    request_timeout_seconds=2,
                    retry_backoff_seconds=0,
                )
            records = [
                json.loads(line) for line in output.read_text().splitlines()
            ]

        self.assertEqual(summary["timed_request_count"], 500)
        self.assertEqual(len(records), 500)
        self.assertEqual(len(handler.requests), 500)
        self.assertEqual(handler.maximum_active_requests, 1)
        self.assertLessEqual(
            summary["wall_time_started_monotonic_ns"],
            handler.first_request_monotonic_ns,
        )
        self.assertGreaterEqual(
            summary["wall_time_ended_monotonic_ns"],
            handler.last_response_monotonic_ns,
        )
        self.assertEqual(summary["completion_tokens"], 1000)
        self.assertAlmostEqual(
            summary["e2e_output_tps"],
            1000 / summary["wall_time_seconds"],
        )
        self.assertTrue(all(record["terminal"] for record in records))


class CommandLineTest(unittest.TestCase):
    def test_cli_exposes_pinned_prepare_and_sequential_run_commands(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/dflash_d1c_harness.py"),
                "--help",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("prepare", completed.stdout)
        self.assertIn("run", completed.stdout)
        self.assertIn(DATASET_REVISION, completed.stdout)


if __name__ == "__main__":
    unittest.main()
