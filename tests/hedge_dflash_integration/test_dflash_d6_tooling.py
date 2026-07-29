from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts/dflash_d6_attempt.sh"
LIFECYCLE = REPO / "scripts/dflash_d6_lifecycle.py"
API = REPO / "scripts/dflash_d6_api.py"
PROGRESS = REPO / "scripts/dflash_d6_progress.sh"
ATTEMPT = "dflash-d6-native-20260729T091800Z-a01"
HARD_STOP_UTC = "2026-07-29T16:31:29Z"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample(cohort: str, position: int, dataset_index: int) -> dict:
    return {
        "cohort": cohort,
        "cohort_position": position,
        "dataset_index": dataset_index,
        "prompt": (
            f"question-{dataset_index}\n"
            r"Please reason step by step, and put your final answer within \boxed{}."
        ),
    }


class D6ToolingTest(unittest.TestCase):
    def test_native_formal_contract_is_frozen_and_non_mutating(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(LAUNCHER),
                "contract",
                ATTEMPT,
                HARD_STOP_UTC,
            ],
            cwd=REPO,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        contract = json.loads(completed.stdout)
        self.assertEqual(contract["phase"], "D6")
        self.assertEqual(contract["arm"], "native")
        self.assertEqual(
            contract["source_sha"],
            "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1",
        )
        self.assertEqual(
            contract["source_tree"],
            "53fc45b1b04963736254dc7ed582047313b8075a",
        )
        self.assertEqual(contract["worker_id"], "4099543")
        self.assertEqual(contract["tp_size"], 8)
        self.assertEqual(contract["dflash_block_size"], 8)
        self.assertEqual(contract["proposal_width"], 7)
        self.assertEqual(contract["warmup_count"], 10)
        self.assertEqual(contract["formal_count"], 500)
        self.assertFalse(contract["hedge_enabled"])
        self.assertFalse(contract["calibration_trace"])
        self.assertIsNone(contract["hedge_config"])
        self.assertEqual(contract["environment"]["HEDGE_ENABLED"], "0")
        self.assertEqual(
            contract["environment"]["SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"],
            "0",
        )
        self.assertIn("excludes startup and warmup", contract["timing_boundary"])
        self.assertFalse(contract["gpu_action"])

    def test_protocol_cohorts_lock_exact_warmup_and_non_overlap(self) -> None:
        api = load(API, "dflash_d6_api_protocol")
        calibration = [sample("calibration", i, i) for i in range(32)]
        warmup = calibration[:10]
        formal = [sample("formal", i, 1000 + i) for i in range(500)]
        api.validate_protocol_inputs(calibration, warmup, formal)
        with self.assertRaisesRegex(ValueError, "exact first 10"):
            api.validate_protocol_inputs(calibration, list(reversed(warmup)), formal)
        formal[0]["dataset_index"] = 0
        with self.assertRaisesRegex(ValueError, "overlap"):
            api.validate_protocol_inputs(calibration, warmup, formal)

    def test_formal_acceptance_and_timing_summary_are_reproducible(self) -> None:
        api = load(API, "dflash_d6_api_metrics")
        rows = []
        for index in range(500):
            histogram = [1, 1, 1]
            rows.append(
                {
                    "request_index": index,
                    "terminal_state": "success",
                    # The terminal response has one extra emitted token beyond
                    # proposals + accepted drafts. This distinguishes the
                    # response-defined 7/3 length from the wrong 1+3/3 formula.
                    "usage": {"completion_tokens": 7},
                    "full_response": {
                        "choices": [
                            {
                                "meta_info": {
                                    "spec_verify_ct": 3,
                                    "spec_num_correct_drafts": 3,
                                    "spec_num_proposed_drafts": 21,
                                    "spec_accept_length": 7 / 3,
                                    "spec_correct_drafts_histogram": histogram,
                                }
                            }
                        ]
                    },
                }
            )
        cohort = {
            "completion_tokens": 3500,
            "wall_time_seconds": 100.0,
            "e2e_output_tps": 35.0,
            "terminal_counts": {
                "success": 500,
                "request_failure": 0,
                "match": 400,
                "mismatch": 90,
                "parse_failure": 10,
            },
            "retry_count": 2,
        }
        enriched, summary = api.enrich_and_summarize(
            rows, cohort_summary=cohort
        )
        self.assertEqual(len(enriched), 500)
        self.assertEqual(summary["proposals"], 1500)
        self.assertEqual(summary["accepted_draft_tokens"], 1500)
        self.assertEqual(summary["mean_accepted_drafts_per_proposal"], 1.0)
        self.assertEqual(summary["mean_accept_length_including_current"], 7 / 3)
        self.assertEqual(
            summary["acceptance_length_histogram_0_to_7"],
            [500, 500, 500, 0, 0, 0, 0, 0],
        )
        self.assertEqual(
            summary["accepted_draft_tokens_by_position_1_to_7"],
            [1000, 500, 0, 0, 0, 0, 0],
        )
        self.assertEqual(summary["completion_tokens"], 3500)
        self.assertEqual(summary["timed_wall_seconds"], 100.0)
        self.assertEqual(summary["e2e_output_tps"], 35.0)
        self.assertEqual(summary["retry_count"], 2)
        self.assertIn("speculative_metrics", enriched[0])

    def test_native_snapshot_requires_hedge_and_trace_off(self) -> None:
        api = load(API, "dflash_d6_api_snapshot")
        snapshot = {
            "mode": "disabled",
            "config": None,
            "proposal_width": 7,
            "experiment_switches": {
                "HEDGE_ENABLED": 0,
                "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": 0,
            },
            "requests_initialized": 0,
            "requests_finished": 0,
            "slot_reuse_resets": 0,
            "requests_non_natural": 0,
            "proposals": 0,
            "draft_tokens_verifiable": 0,
            "strict_accepted_draft_tokens": 0,
            "hedge_accepted_draft_tokens": 0,
            "relaxed_mismatches": 0,
            "budget_exhaustion_events": 0,
            "active_request_states": 0,
            "state_leaks": 0,
            "request_state": [],
        }
        api.validate_native_snapshot(snapshot)
        snapshot["experiment_switches"]["HEDGE_ENABLED"] = 1
        with self.assertRaisesRegex(ValueError, "HEDGE_ENABLED"):
            api.validate_native_snapshot(snapshot)

    def test_launcher_helpers_syntax_and_targeted_cleanup(self) -> None:
        subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)
        subprocess.run(["bash", "-n", str(PROGRESS)], check=True)
        for path in (LIFECYCLE, API):
            ast.parse(path.read_text(), filename=str(path))
        lifecycle_source = LIFECYCLE.read_text()
        self.assertIn("process_matches(server.pid, ticks, command)", lifecycle_source)
        self.assertIn("os.killpg(server.pid, signal.SIGTERM)", lifecycle_source)
        self.assertNotRegex(lifecycle_source, r"\b(?:pkill|killall)\b")
        progress_source = PROGRESS.read_text()
        self.assertIn("complete_json_rows", progress_source)
        self.assertNotIn("kill ", progress_source)
        for index, block in enumerate(
            re.findall(r"<<'PY'\n(.*?)\nPY\n", progress_source, re.DOTALL)
        ):
            ast.parse(block, filename=f"{PROGRESS}:heredoc-{index}")

    def test_deadline_and_attempt_id_are_exact(self) -> None:
        lifecycle = load(LIFECYCLE, "dflash_d6_lifecycle_deadline")
        lifecycle.hard_stop(HARD_STOP_UTC)
        lifecycle.paths(ATTEMPT)
        for value in (
            "2026-07-29 16:31:29Z",
            "2026-07-29T16:31:29+00:00",
            "2026-02-30T16:31:29Z",
        ):
            with self.assertRaises((ValueError, OverflowError)):
                lifecycle.hard_stop(value)
        with self.assertRaisesRegex(ValueError, "invalid D6"):
            lifecycle.paths("dflash-d5-native-20260729T091800Z-a01")


if __name__ == "__main__":
    unittest.main()
