#!/usr/bin/env python3
"""Small filesystem fixtures for the offline Phase 06 acceptance audit."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phase06_accept import (
    FAIL,
    MISSING,
    PASS,
    build_acceptance,
    check_keepalive_after,
    main,
    render_markdown,
)


FIXED_COMMIT = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_fixture(run_dir: Path) -> None:
    command = [
        "/home/tiger/venvs/deepspec-dspark/bin/python",
        "-m",
        "sglang.launch_server",
        "--tp-size",
        "4",
        "--speculative-algorithm",
        "DSPARK",
        "--speculative-dspark-block-size",
        "5",
        "--moe-runner-backend",
        "flashinfer_mxfp4",
        "--speculative-moe-runner-backend",
        "flashinfer_mxfp4",
        "--max-running-requests",
        "1",
        "--disable-cuda-graph",
        "--disable-overlap-schedule",
        "--disable-radix-cache",
    ]
    write_json(
        run_dir / "resolved_config.json",
        {
            "model_path": "/fixture/model",
            "python": command[0],
            "sglang_commit": FIXED_COMMIT,
            "command": command,
            "environment": {
                "CUDA_VISIBLE_DEVICES": "0,1,2,3",
                "SGLANG_RAGGED_VERIFY_MODE": "static",
                "SGLANG_DSV4_FP4_EXPERTS": "1",
            },
            "unset_environment": ["SGLANG_DSV4_FP4_DEQUANT"],
        },
    )
    log_lines = [
        "INFO speculative_algorithm='DSPARK'",
        "INFO selected MoE runner backend=flashinfer_mxfp4",
        "INFO expert layout=packed FP4",
    ]
    for rank in range(4):
        log_lines.append(f"[TP{rank}] tensor parallel rank initialized")
        log_lines.append(
            f"[TP{rank}] loaded DSpark draft architecture: "
            "DeepseekV4ForCausalLM"
        )
    log_lines.append("INFO received SIGTERM for graceful shutdown")
    (run_dir / "server.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )
    write_json(
        run_dir / "startup.json",
        {
            "status": "ready",
            "server_pid": 123,
            "started_at": "2026-07-29T00:00:00+00:00",
            "finished_at": "2026-07-29T00:00:00.5+00:00",
            "elapsed_seconds": 0.5,
        },
    )

    with (run_dir / "gpu_samples.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "timestamp_utc",
                "gpu_index",
                "gpu_uuid",
                "utilization_gpu_percent",
                "memory_used_mib",
                "memory_total_mib",
                "server_pid_alive",
            ]
        )
        for second in (1, 2, 3):
            for index in range(4):
                writer.writerow(
                    [
                        f"2026-07-29T00:00:0{second}+00:00",
                        index,
                        f"GPU-fixture-{index}",
                        50 + index,
                        40000 + index,
                        97887,
                        True,
                    ]
                )

    write_json(
        run_dir / "api_smoke.json",
        {
            "status": "PASS",
            "started_at": "2026-07-29T00:00:00+00:00",
            "finished_at": "2026-07-29T00:00:04+00:00",
            "models_response": {
                "http_status": 200,
                "body": {"data": [{"id": "fixture-model"}]},
            },
            "chat_response": {
                "http_status": 200,
                "body": {
                    "choices": [{"message": {"content": "4"}}],
                },
            },
        },
    )

    counts = {
        "total": 10,
        "success_requests": 10,
        "failed_requests": 0,
        "matches": 3,
        "mismatches": 5,
        "parse_failures": 2,
        "all_terminal": True,
    }
    with (run_dir / "gsm8k_outputs.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for index in range(10):
            parse_failure = index >= 8
            matched = index < 3
            record = {
                "sample_index": index,
                "question": f"fixture question {index}",
                "reference_response": f"work #### {index}",
                "reference_answer": str(index),
                "attempts": [{"attempt": 1, "status": "success"}],
                "request_succeeded": True,
                "response": {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "no numeric answer"
                                    if parse_failure
                                    else f"Final answer: {index + (not matched)}"
                                )
                            }
                        }
                    ]
                },
                "model_text": (
                    "no numeric answer"
                    if parse_failure
                    else f"Final answer: {index + (not matched)}"
                ),
                "extracted_answer": (
                    None if parse_failure else str(index + (not matched))
                ),
                "extraction_rule": None if parse_failure else "final_answer",
                "parse_status": "parse_failure" if parse_failure else "parsed",
                "matched": matched,
            }
            stream.write(json.dumps(record) + "\n")
    write_json(run_dir / "summary.json", counts)
    (run_dir / "cuda_contexts_after_server.txt").write_text(
        "2026-07-29T00:01:00Z attempt=1 contexts=none\n",
        encoding="utf-8",
    )
    health = {
        "schema_version": 1,
        "healthy": True,
        "expected_gpus": 4,
        "minimum_utilization": 40.0,
        "platform_reclamation_threshold": 30.0,
        "sample_count": 10,
        "underutilized_gpus": [],
        "per_gpu": {
            str(index): {
                "sample_count": 10,
                "mean_utilization": 90.0,
                "minimum_observed": 80.0,
                "maximum_observed": 100.0,
            }
            for index in range(4)
        },
    }
    (run_dir / "keepalive_after.txt").write_text(
        "HEALTHY on fixture worker=fixture pid=123\n"
        + json.dumps(health)
        + "\n",
        encoding="utf-8",
    )


class Phase06AcceptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name) / "completed-phase05-fixture"
        self.run_dir.mkdir()
        make_fixture(self.run_dir)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_fixture_passes_despite_accuracy_observations(self) -> None:
        audit = build_acceptance(self.run_dir)
        self.assertEqual(audit["candidate_conclusion"], "MVP_PASS")
        self.assertFalse(audit["phase06_executed"])
        self.assertEqual(audit["failed_checks"], [])
        self.assertEqual(audit["missing_evidence"], [])
        self.assertEqual(audit["observations"]["gsm8k"]["matches"], 3)
        self.assertEqual(audit["observations"]["gsm8k"]["parse_failures"], 2)
        self.assertFalse(
            audit["observations"]["gsm8k"]["accuracy_is_gate"]
        )
        self.assertIn("离线验收报告草稿", render_markdown(audit))

    def test_unknown_log_wording_is_missing_evidence(self) -> None:
        path = self.run_dir / "server.log"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "INFO expert layout=packed FP4\n", ""
            ),
            encoding="utf-8",
        )
        audit = build_acceptance(self.run_dir)
        self.assertEqual(audit["candidate_conclusion"], "MVP_INCOMPLETE")
        self.assertEqual(
            audit["checks"]["server_log_packed_fp4"]["status"], MISSING
        )
        self.assertIn("server_log_packed_fp4", audit["missing_evidence"])

    def test_actual_dsv4_mxfp4_log_wording_is_packed_fp4_evidence(
        self,
    ) -> None:
        path = self.run_dir / "server.log"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "INFO expert layout=packed FP4",
                "Preparing DSv4 MXFP4 experts for FlashInfer SM90 CUTLASS "
                "(quant_method=Mxfp4FlashinferCutlassMoEMethod)",
            ),
            encoding="utf-8",
        )
        audit = build_acceptance(self.run_dir)
        self.assertEqual(
            audit["checks"]["server_log_packed_fp4"]["status"], PASS
        )

    def test_keepalive_text_uses_last_health_json(self) -> None:
        path = self.run_dir / "keepalive_after.txt"
        final_health = json.loads(
            next(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("{")
            )
        )
        initial_health = {
            **final_health,
            "sample_count": 3,
            "per_gpu": {
                index: {**item, "sample_count": 3}
                for index, item in final_health["per_gpu"].items()
            },
        }
        path.write_text(
            "HEALTHY on fixture worker=fixture pid=123\n"
            + json.dumps(initial_health)
            + "\nHEALTHY on fixture worker=fixture pid=123\n"
            + json.dumps(final_health)
            + "\n",
            encoding="utf-8",
        )
        keepalive = check_keepalive_after(self.run_dir)
        self.assertEqual(keepalive["status"], PASS)
        self.assertEqual(keepalive["details"]["sample_count"], 10)
        write_json(self.run_dir / "keepalive_final.json", final_health)
        path.write_text(json.dumps(initial_health) + "\n", encoding="utf-8")
        keepalive = check_keepalive_after(self.run_dir)
        self.assertEqual(keepalive["status"], PASS)
        self.assertEqual(keepalive["details"]["sample_count"], 10)

    def test_cli_writes_json_and_markdown_draft(self) -> None:
        with patch(
            "sys.argv", ["phase06_accept.py", str(self.run_dir)]
        ):
            return_code = main()
        self.assertEqual(return_code, 0)
        acceptance = json.loads(
            (self.run_dir / "acceptance.json").read_text(encoding="utf-8")
        )
        report = (self.run_dir / "acceptance_report.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(acceptance["candidate_conclusion"], "MVP_PASS")
        self.assertFalse(acceptance["phase06_executed"])
        self.assertIn("只有主 Agent", report)

    def test_cuda_failure_is_not_misclassified_as_shutdown(self) -> None:
        with (self.run_dir / "server.log").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("RuntimeError: CUDA out of memory\n")
        audit = build_acceptance(self.run_dir)
        self.assertEqual(audit["candidate_conclusion"], "MVP_INCOMPLETE")
        self.assertEqual(
            audit["checks"][
                "server_log_no_unhandled_cuda_nccl_crash"
            ]["status"],
            FAIL,
        )
        self.assertEqual(
            audit["checks"]["server_log_dspark"]["status"], PASS
        )

    def test_startup_failure_is_separate_from_missing_requests_and_keepalive(
        self,
    ) -> None:
        write_json(
            self.run_dir / "startup.json",
            {
                "status": "server_exited",
                "server_pid": 123,
                "elapsed_seconds": 12.0,
            },
        )
        (self.run_dir / "api_smoke.json").unlink()
        (self.run_dir / "gsm8k_outputs.jsonl").unlink()
        (self.run_dir / "summary.json").unlink()
        audit = build_acceptance(self.run_dir)
        self.assertEqual(audit["checks"]["startup"]["status"], FAIL)
        self.assertEqual(audit["checks"]["api_smoke"]["status"], MISSING)
        self.assertEqual(
            audit["checks"]["gsm8k_ten_terminal_records"]["status"],
            MISSING,
        )
        self.assertEqual(
            audit["checks"]["keepalive_after"]["status"], PASS
        )


if __name__ == "__main__":
    unittest.main()
