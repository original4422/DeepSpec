from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolve_module = load_script("hedge_eagle3_phase06_resolve")
run_module = load_script("hedge_eagle3_phase06_run")


def proposal(
    proposal_id: int,
    *,
    before: float,
    after: float,
    spent: float,
    strict: int,
    accepted: int,
    relaxed: int,
) -> dict:
    return {
        "schema_version": 1,
        "mode": "enabled",
        "proposal_id": proposal_id,
        "sample_id": "request",
        "strict_accepted_drafts": strict,
        "hedge_accepted_drafts": accepted,
        "commit_length": accepted + 1,
        "relaxed_mismatches": relaxed,
        "remaining_before": before,
        "remaining_after": after,
        "spent": spent,
    }


def record(position: int, *, warmup: bool) -> dict:
    return {
        "schema_version": 1,
        "phase": "warmup" if warmup else "formal",
        "position": position,
        "timed": not warmup,
        "partition": "calibration" if warmup else "formal",
        "partition_index": position,
        "source_index": position if warmup else position + 1000,
        "attempts": [{"attempt": 1, "status": "success"}],
        "attempt_count": 1,
        "retry_count": 0,
        "generation_retry_count": 0,
        "trace_retry_count": 0,
        "generation_status": "success",
        "trace_status": "success",
        "terminal_status": "success",
        "first_request_monotonic_started": None if warmup else float(position),
        "record_terminal_monotonic": None if warmup else float(position + 1),
        "full_response": {"id": f"request-{position}"},
        "response_text": r"The answer is \boxed{1}.",
        "output_token_ids": [42],
        "completion_tokens": 1,
        "proposal_trace": [
            proposal(
                0,
                before=6.75,
                after=5.25,
                spent=1.5,
                strict=0,
                accepted=1,
                relaxed=1,
            ),
            proposal(
                1,
                before=5.25,
                after=5.25,
                spent=0.0,
                strict=3,
                accepted=3,
                relaxed=0,
            ),
        ],
        "reference_answer": {"status": "ok", "normalized": "1"},
        "model_answer": {"status": "ok", "normalized": "1"},
        "answer_match": True,
    }


class Phase06FormalToolTest(unittest.TestCase):
    def test_runner_starts_from_outside_repository_cwd(self) -> None:
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [
                    "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python",
                    str(ROOT / "scripts/hedge_eagle3_phase06_run.py"),
                    "--help",
                ],
                cwd=temporary,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_bplus_wrapper_preserves_phase04_command_and_frozen_gate(self) -> None:
        attempt = "20260729T080000Z-phase-06-bplus-formal-01"
        phase06 = resolve_module.resolve_bplus(
            attempt, require_worker_hostname=False
        )
        phase04 = resolve_module.phase04.resolve(
            "B+", attempt, gate=6.75, require_worker_hostname=False
        )
        self.assertEqual(phase06["command"], phase04["command"])
        self.assertEqual(phase06["environment"], phase04["environment"])
        self.assertEqual(phase06["source"], phase04["source"])
        config = json.loads(
            phase06["environment"]["SGLANG_EAGLE3_HEDGE_CONFIG_JSON"]
        )
        self.assertEqual(
            config,
            {
                "B": 6.75,
                "block_size": 3,
                "g": 6.75,
                "m": 1,
                "value_scheme": "normalized_suffix",
            },
        )

    def test_500_formal_budget_and_metrics_are_recomputable(self) -> None:
        warmup = [record(index, warmup=True) for index in range(10)]
        formal = [record(index, warmup=False) for index in range(500)]
        protocol_run = {
            "schema_version": 1,
            "warmup_count": 10,
            "formal_count": 500,
            "maximum_in_flight": 1,
            "formal_monotonic_started": 0.0,
            "formal_monotonic_finished": 500.0,
            "formal_wall_seconds": 500.0,
            "warmup": warmup,
            "formal": formal,
        }
        runner = SimpleNamespace(run=lambda manifest, warmup_count: protocol_run)
        manifest = {
            "calibration": [{"source_index": index} for index in range(32)],
            "formal": [
                {"source_index": index + 1000} for index in range(500)
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = run_module.run_and_write(
                manifest=manifest,
                runner=runner,
                output_dir=root / "attempt",
                dataset_sha256=run_module.EXPECTED_DATASET_SHA256,
                accepted_marker=root / "bplus.complete.json",
            )
            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["mode"], "B+")
            self.assertEqual(summary["total"], 500)
            self.assertEqual(summary["completion_tokens"], 500)
            self.assertEqual(summary["timed_seconds"], 500.0)
            self.assertEqual(summary["output_tps"], 1.0)
            self.assertEqual(summary["budget_requests_checked"], 500)
            self.assertEqual(summary["budget_invariants_status"], "PASS")
            self.assertEqual(summary["budget_total_spent"], 750.0)
            self.assertEqual(summary["relaxed_proposal_count"], 500)
            self.assertEqual(summary["extra_accepted_draft_tokens"], 500)
            self.assertEqual(summary["proposal_count"], 1000)

    def test_budget_invariants_detect_continuity_and_m_violation(self) -> None:
        row = record(0, warmup=False)
        row["proposal_trace"][1]["remaining_before"] = 4.0
        row["proposal_trace"][1]["relaxed_mismatches"] = 2
        result = run_module.budget_summary([row])
        self.assertEqual(result["budget_invariants_status"], "FAIL")
        reasons = {item["reason"] for item in result["budget_invariant_violations"]}
        self.assertIn("budget continuity", reasons)
        self.assertIn("m exceeds one", reasons)
        failed = record(1, warmup=False)
        failed["terminal_status"] = "failure"
        failed["proposal_trace"] = []
        skipped = run_module.budget_summary([failed])
        self.assertEqual(skipped["budget_invariants_status"], "PASS")
        self.assertEqual(skipped["budget_requests_checked"], 0)
        self.assertEqual(skipped["budget_requests_unchecked_due_failure"], 1)


if __name__ == "__main__":
    unittest.main()
