#!/usr/bin/env python3
"""Run the complete CPU-only Phase 01B runner and cleanup fixtures."""

from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Mapping, Sequence

from deepspec.hedge_eagle3_phase01b.tools import (
    GENERATION,
    SequentialOpenAIRunner,
    build_resolved_config,
    calibrate_q25,
    capture_registered_process,
    compare_b0_token_ids,
    experiment_table,
    extract_model_answer,
    extract_reference_answer,
    terminate_registered_process,
)


DATASET_MANIFEST = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12/"
    "gsm8k_split_manifest.json"
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


class MockState:
    def __init__(self, samples: Sequence[Mapping[str, Any]]) -> None:
        self.lock = threading.Lock()
        self.samples = {
            sample["request_messages"][0]["content"]: sample
            for sample in samples
        }
        if len(self.samples) != len(samples):
            raise RuntimeError("mock fixture prompt identities are not unique")
        self.attempts: dict[str, int] = {}
        self.active = 0
        self.maximum_active = 0
        self.request_bodies: list[dict[str, Any]] = []
        self.fail_first_formal = {0, 100, 200, 300, 400}


def build_handler(state: MockState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send(self, status: int, value: object) -> None:
            payload = (
                json.dumps(value, separators=(",", ":"), sort_keys=True)
                + "\n"
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/chat/completions":
                self._send(404, {"error": "unexpected path"})
                return
            with state.lock:
                state.active += 1
                state.maximum_active = max(
                    state.maximum_active,
                    state.active,
                )
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    self._send(400, {"error": "body is not an object"})
                    return
                content = body["messages"][0]["content"]
                sample = state.samples[content]
                with state.lock:
                    state.request_bodies.append(body)
                    attempt = state.attempts.get(content, 0) + 1
                    state.attempts[content] = attempt
                should_fail = (
                    sample["partition"] == "formal"
                    and sample["partition_index"] in state.fail_first_formal
                    and attempt == 1
                )
                if should_fail:
                    self._send(
                        503,
                        {
                            "error": {
                                "message": "fixture transient failure",
                                "type": "fixture",
                            }
                        },
                    )
                    return
                reference = extract_reference_answer(sample["answer"])
                if reference["status"] != "ok":
                    raise RuntimeError("fixture reference did not parse")
                token_ids = [
                    100_000 + int(sample["source_index"]),
                    attempt,
                    99,
                ]
                self._send(
                    200,
                    {
                        "id": (
                            f"mock-{sample['partition']}-"
                            f"{sample['partition_index']}-{attempt}"
                        ),
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": (
                                        "Mock reasoning. Final answer: "
                                        f"\\boxed{{{reference['normalized']}}}"
                                    ),
                                },
                                "finish_reason": "stop",
                                "token_ids": token_ids,
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 7,
                            "completion_tokens": len(token_ids),
                            "total_tokens": 7 + len(token_ids),
                        },
                    },
                )
            finally:
                with state.lock:
                    state.active -= 1

    return Handler


def b0_fixtures(
    calibration: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    native = [
        {
            "source_index": sample["source_index"],
            "output_token_ids": [index, index + 1, index + 2],
            "response_text": f"native-{index}",
            "proposal_trace": [{"accepted": 3}],
        }
        for index, sample in enumerate(calibration)
    ]
    b0_pass = [dict(record) for record in native]
    pass_result = compare_b0_token_ids(native, b0_pass)
    b0_fail = [dict(record) for record in native]
    b0_fail[7] = {
        **b0_fail[7],
        "output_token_ids": [7, 777, 9],
        "response_text": "b0-first-minimal-mismatch",
    }
    fail_result = compare_b0_token_ids(native, b0_fail)
    if pass_result["status"] != "B0_PASS":
        raise RuntimeError("B0 pass fixture failed")
    if (
        fail_result["status"] != "B0_FAIL"
        or fail_result["first_mismatch"]["calibration_index"] != 7
        or fail_result["first_mismatch"]["first_divergence"] != 1
    ):
        raise RuntimeError("B0 mismatch fixture failed")
    return pass_result, fail_result


def process_fixture() -> dict[str, Any]:
    child_code = (
        "import signal,sys,time;"
        "signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));"
        "print('READY',flush=True);"
        "time.sleep(300)"
    )
    command = [sys.executable, "-c", child_code]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        if process.stdout is None or process.stdout.readline().strip() != "READY":
            raise RuntimeError("cleanup fixture did not become ready")
        registered = capture_registered_process(process.pid)
        if list(registered.command_line) != command:
            raise RuntimeError("cleanup fixture command identity differs")
        wrong = replace(
            registered,
            start_ticks=registered.start_ticks + 1,
        )
        refused = False
        try:
            terminate_registered_process(wrong, timeout_seconds=1.0)
        except RuntimeError:
            refused = True
        if not refused or process.poll() is not None:
            raise RuntimeError("mismatched cleanup identity was not refused")
        termination = terminate_registered_process(
            registered,
            timeout_seconds=3.0,
        )
        returncode = process.wait(timeout=5)
        if returncode not in {0, -15}:
            raise RuntimeError(
                f"cleanup fixture returned unexpected code: {returncode}"
            )
        return {
            "schema_version": 1,
            "status": "PASS",
            "registered_identity": {
                **registered.__dict__,
                "command_line": list(registered.command_line),
            },
            "mismatched_identity_refused": True,
            "signal_sent_to_unregistered_process": False,
            "termination": termination,
            "returncode": returncode,
            "broad_kill_used": False,
        }
    finally:
        if process.poll() is None:
            registered = capture_registered_process(process.pid)
            terminate_registered_process(registered, timeout_seconds=1.0)
            process.wait(timeout=5)


def main(argv: Sequence[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        raise RuntimeError("refusing to overwrite Phase 01B fixture output")
    args.output_dir.mkdir(parents=True)
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    calibration = manifest["calibration"]
    formal = manifest["formal"]

    q25 = calibrate_q25(
        [
            {
                "sample_id": f"sample-{index}",
                "proposal_id": f"proposal-{index}",
                "regret_over_value": value,
            }
            for index, value in enumerate((1.0, 2.0, 3.0, 4.0))
        ]
    )
    if q25["g"] != 1.75 or q25["B"] != 1.75 or q25["m"] != 1:
        raise RuntimeError("q25 linear fixture differs from expected 1.75")
    configs = {
        mode: build_resolved_config(
            mode,
            gate=q25["g"] if mode == "B+" else None,
        )
        for mode in ("native", "B0", "B+")
    }
    key_sets = {mode: set(config) for mode, config in configs.items()}
    if len({frozenset(keys) for keys in key_sets.values()}) != 1:
        raise RuntimeError("resolved mode schemas differ")
    if not all(
        config["server"] == configs["native"]["server"]
        and config["request"] == configs["native"]["request"]
        and config["lane"] == configs["native"]["lane"]
        for config in configs.values()
    ):
        raise RuntimeError("mode configs changed decode-affecting common fields")
    for mode, config in configs.items():
        write_json(args.output_dir / f"resolved_config_{mode}.json", config)

    b0_pass, b0_fail = b0_fixtures(calibration)
    answer_fixtures = {
        "boxed_precedence": extract_model_answer(
            "earlier 2, then #### 3, final answer 4, \\boxed{5}"
        ),
        "hash_fallback": extract_model_answer("work 2\n#### 1,234"),
        "final_fallback": extract_model_answer("The final answer is $12.50."),
        "numeric_fallback": extract_model_answer("work 3 then 44"),
        "parse_failure": extract_model_answer("no numeric result"),
    }
    expected_answers = {
        "boxed_precedence": "5",
        "hash_fallback": "1234",
        "final_fallback": "12.5",
        "numeric_fallback": "44",
    }
    for name, expected in expected_answers.items():
        if answer_fixtures[name]["normalized"] != expected:
            raise RuntimeError(f"answer extraction fixture failed: {name}")
    if answer_fixtures["parse_failure"]["status"] != "parse_failure":
        raise RuntimeError("answer parse-failure fixture failed")

    state = MockState([*calibration[:10], *formal])
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="eagle3-phase01b-mock-api",
        daemon=True,
    )
    server_thread.start()
    try:
        endpoint = (
            f"http://127.0.0.1:{server.server_address[1]}"
            "/v1/chat/completions"
        )
        runner = SequentialOpenAIRunner(
            endpoint=endpoint,
            model="fixture-eagle3",
            retry_delays_seconds=(0.0, 0.0),
            timeout_seconds=10.0,
        )
        run = runner.run(manifest, warmup_count=10)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
    summary = run["summary"]
    expected_runner_observation = {
        "warmup_count": 10,
        "formal_count": 500,
        "maximum_runner_in_flight": 1,
        "maximum_server_active": 1,
        "formal_terminal": 500,
        "successes": 500,
        "failures": 0,
        "retries": 5,
        "parse_failures": 0,
        "matches": 500,
        "completion_tokens": 1500,
        "http_request_attempt_count": 515,
    }
    observed_runner_observation = {
        "warmup_count": run["warmup_count"],
        "formal_count": run["formal_count"],
        "maximum_runner_in_flight": run["maximum_in_flight"],
        "maximum_server_active": state.maximum_active,
        "formal_terminal": summary["formal_terminal"],
        "successes": summary["successes"],
        "failures": summary["failures"],
        "retries": summary["retries"],
        "parse_failures": summary["parse_failures"],
        "matches": summary["matches"],
        "completion_tokens": summary["completion_tokens"],
        "http_request_attempt_count": len(state.request_bodies),
    }
    write_json(args.output_dir / "mock_runner_outputs.json", run)
    write_json(
        args.output_dir / "mock_runner_diagnostic.json",
        {
            "schema_version": 1,
            "expected": expected_runner_observation,
            "observed": observed_runner_observation,
            "differing_fields": {
                key: {
                    "expected": expected_runner_observation[key],
                    "observed": observed_runner_observation[key],
                }
                for key in expected_runner_observation
                if expected_runner_observation[key]
                != observed_runner_observation[key]
            },
        },
    )
    if observed_runner_observation != expected_runner_observation:
        raise RuntimeError(
            "mock sequential runner summary differs: "
            + json.dumps(
                {
                    key: {
                        "expected": expected_runner_observation[key],
                        "observed": observed_runner_observation[key],
                    }
                    for key in expected_runner_observation
                    if expected_runner_observation[key]
                    != observed_runner_observation[key]
                },
                sort_keys=True,
            )
        )
    expected_body_keys = {
        "model",
        "messages",
        *GENERATION.keys(),
    }
    if not all(
        set(body) == expected_body_keys
        and body["temperature"] == 0
        and body["top_p"] == 1
        and body["max_tokens"] == 512
        and body["chat_template_kwargs"] == {"enable_thinking": False}
        and len(body["messages"]) == 1
        and body["messages"][0]["role"] == "user"
        for body in state.request_bodies
    ):
        raise RuntimeError("mock request body contract differs")
    table = experiment_table(
        summary,
        {**summary, "end_to_end_output_tps": summary["end_to_end_output_tps"] + 1},
        b0_status=b0_pass["status"],
    )
    (args.output_dir / "experiment_table_fixture.md").write_text(
        table,
        encoding="utf-8",
    )
    process_summary = process_fixture()
    write_json(
        args.output_dir / "process_fixture_summary.json",
        process_summary,
    )
    runner_summary = {
        "schema_version": 1,
        "status": "PASS",
        "dataset_manifest": str(DATASET_MANIFEST),
        "resolved_config_schema_keys": sorted(key_sets["native"]),
        "resolved_config_hashes": {
            mode: config["config_sha256"]
            for mode, config in configs.items()
        },
        "common_decode_fields_identical": True,
        "q25_fixture": q25,
        "b0_pass_fixture": b0_pass,
        "b0_fail_fixture": b0_fail,
        "answer_extraction_fixtures": answer_fixtures,
        "mock_api": {
            "warmup_count": run["warmup_count"],
            "formal_count": run["formal_count"],
            "maximum_runner_in_flight": run["maximum_in_flight"],
            "maximum_server_active": state.maximum_active,
            "http_request_attempt_count": len(state.request_bodies),
            "summary": summary,
            "full_outputs": str(
                args.output_dir / "mock_runner_outputs.json"
            ),
        },
        "experiment_table": str(
            args.output_dir / "experiment_table_fixture.md"
        ),
        "cuda_operation_performed": False,
    }
    write_json(
        args.output_dir / "runner_fixture_summary.json",
        runner_summary,
    )
    print(
        "PHASE01B_FIXTURES_PASS "
        f"warmup={run['warmup_count']} formal={run['formal_count']} "
        f"retries={summary['retries']} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Phase 01B fixture error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
