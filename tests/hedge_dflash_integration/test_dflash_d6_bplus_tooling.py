from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
NATIVE_API = REPO / "scripts/dflash_d6_api.py"
NATIVE_LIFECYCLE = REPO / "scripts/dflash_d6_lifecycle.py"
BPLUS_API = REPO / "scripts/dflash_d6_bplus_api.py"
BPLUS_LIFECYCLE = REPO / "scripts/dflash_d6_bplus_lifecycle.py"
BPLUS_LAUNCHER = REPO / "scripts/dflash_d6_bplus_attempt.sh"
BPLUS_PROGRESS = REPO / "scripts/dflash_d6_bplus_progress.py"
BPLUS_PROGRESS_LAUNCHER = REPO / "scripts/dflash_d6_bplus_progress.sh"
C1_ACCEPTANCE = (
    REPO
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/"
    "continuation-c1/continuation_c1_acceptance.json"
)
C2_ACCEPTANCE = (
    REPO
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/"
    "continuation-c2/continuation_c2_acceptance.json"
)
ATTEMPT = "dflash-d6-bplus-20260729T120000Z-a01"
HARD_STOP_UTC = "2026-07-29T16:31:29Z"
EXPECTED_CONFIG = {
    "B": 12.5,
    "block_size": 7,
    "g": 12.5,
    "m": 1,
    "value_scheme": "normalized_suffix",
}
EXPECTED_CANONICAL = (
    '{"B":12.5,"block_size":7,"g":12.5,"m":1,'
    '"value_scheme":"normalized_suffix"}'
)
EXPECTED_SHA256 = (
    "ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746"
)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class D6BPlusToolingTest(unittest.TestCase):
    def test_sealed_c1_config_and_c2_b0_pass_are_required(self) -> None:
        lifecycle = load(BPLUS_LIFECYCLE, "dflash_d6_bplus_identity")
        identity = lifecycle.load_protocol_identity(C1_ACCEPTANCE, C2_ACCEPTANCE)
        self.assertEqual(identity["config"], EXPECTED_CONFIG)
        self.assertEqual(identity["canonical_json"], EXPECTED_CANONICAL)
        self.assertEqual(identity["sha256"], EXPECTED_SHA256)
        self.assertEqual(identity["c1_status"], "PASS")
        self.assertEqual(identity["c2_status"], "PASS")
        self.assertEqual(identity["b0_status"], "PASS")

        c1 = json.loads(C1_ACCEPTANCE.read_text())
        c2 = json.loads(C2_ACCEPTANCE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            c1_path = root / "c1.json"
            c2_path = root / "c2.json"
            c1_bad = copy.deepcopy(c1)
            c1_bad["calibration"]["frozen_config"]["B"] = 12.0
            c1_path.write_text(json.dumps(c1_bad))
            c2_path.write_text(json.dumps(c2))
            with self.assertRaisesRegex(ValueError, "frozen B\\+ config"):
                lifecycle.load_protocol_identity(c1_path, c2_path)

            c1_path.write_text(json.dumps(c1))
            c2_bad = copy.deepcopy(c2)
            c2_bad["b0_comparison"]["status"] = "FAIL"
            c2_path.write_text(json.dumps(c2_bad))
            with self.assertRaisesRegex(ValueError, "B0 PASS"):
                lifecycle.load_protocol_identity(c1_path, c2_path)

    def test_bplus_contract_differs_from_native_only_at_hedge_switches(self) -> None:
        native = load(NATIVE_LIFECYCLE, "dflash_d6_native_contract")
        bplus = load(BPLUS_LIFECYCLE, "dflash_d6_bplus_contract")
        native_contract = native.contract(HARD_STOP_UTC)
        bplus_contract = bplus.contract(HARD_STOP_UTC)

        self.assertEqual(bplus_contract["arm"], "B+")
        self.assertTrue(bplus_contract["hedge_enabled"])
        self.assertFalse(bplus_contract["calibration_trace"])
        self.assertEqual(bplus_contract["hedge_config"], EXPECTED_CONFIG)
        self.assertEqual(bplus_contract["hedge_config_sha256"], EXPECTED_SHA256)
        self.assertEqual(bplus_contract["b0_status"], "PASS")
        self.assertEqual(bplus_contract["command"], native_contract["command"])
        self.assertEqual(bplus_contract["prep_live_attempts_used"], 0)
        self.assertEqual(bplus_contract["maximum_live_attempts"], 3)
        self.assertFalse(bplus_contract["gpu_action"])

        allowed_contract_differences = {
            "arm",
            "hedge_enabled",
            "hedge_config",
            "hedge_config_canonical_json",
            "hedge_config_sha256",
            "b0_status",
            "c1_acceptance",
            "c2_acceptance",
            "prep_live_attempts_used",
            "maximum_live_attempts",
            "environment",
            "unset_environment",
        }
        for key, native_value in native_contract.items():
            if key not in allowed_contract_differences:
                self.assertEqual(bplus_contract[key], native_value, key)

        native_environment = native_contract["environment"]
        bplus_environment = bplus_contract["environment"]
        for key, native_value in native_environment.items():
            if key != "HEDGE_ENABLED":
                self.assertEqual(bplus_environment[key], native_value, key)
        self.assertEqual(bplus_environment["HEDGE_ENABLED"], "1")
        self.assertEqual(
            bplus_environment["SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"], "0"
        )
        self.assertEqual(
            bplus_environment["SGLANG_DFLASH_HEDGE_CONFIG_JSON"],
            EXPECTED_CANONICAL,
        )
        native_full_environment = native.server_environment()
        bplus_full_environment = bplus.server_environment()
        hedge_fields = {
            "HEDGE_ENABLED",
            "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE",
            "SGLANG_DFLASH_HEDGE_CONFIG_JSON",
            "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
        }
        self.assertEqual(
            {
                key: value
                for key, value in bplus_full_environment.items()
                if key not in hedge_fields
            },
            {
                key: value
                for key, value in native_full_environment.items()
                if key not in hedge_fields
            },
        )

    def test_bplus_snapshot_enforces_budget_counters_and_clean_lifecycle(self) -> None:
        api = load(BPLUS_API, "dflash_d6_bplus_snapshot")
        snapshot = {
            "mode": "enabled",
            "config": EXPECTED_CONFIG,
            "config_fingerprint": EXPECTED_SHA256,
            "proposal_width": 7,
            "experiment_switches": {
                "HEDGE_ENABLED": 1,
                "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": 0,
            },
            "proposals": 5,
            "draft_tokens_verifiable": 35,
            "strict_accepted_draft_tokens": 4,
            "hedge_accepted_draft_tokens": 6,
            "accepted_draft_tokens_by_position": [3, 2, 1, 0, 0, 0, 0],
            "accept_length_histogram": [2, 1, 1, 1, 0, 0, 0, 0],
            "relaxed_mismatches": 2,
            "regret_charged": 12.5,
            "budget_exhaustion_events": 1,
            "requests_initialized": 512,
            "requests_finished": 511,
            "slot_reuse_resets": 1,
            "requests_non_natural": 1,
            "active_request_states": 0,
            "state_leaks": 0,
            "request_state": [],
        }
        validated = api.validate_bplus_snapshot(snapshot, EXPECTED_CONFIG)
        self.assertEqual(validated["risk_budget_upper_bound"], 6400.0)
        self.assertEqual(validated["relaxed_draft_gain"], 2)
        self.assertEqual(validated["lifecycle_terminal_count"], 512)

        excessive = copy.deepcopy(snapshot)
        excessive["regret_charged"] = 6400.01
        with self.assertRaisesRegex(ValueError, "risk budget"):
            api.validate_bplus_snapshot(excessive, EXPECTED_CONFIG)

        wrong_fingerprint = copy.deepcopy(snapshot)
        wrong_fingerprint["config_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            api.validate_bplus_snapshot(wrong_fingerprint, EXPECTED_CONFIG)

        leaked = copy.deepcopy(snapshot)
        leaked["state_leaks"] = 1
        with self.assertRaisesRegex(ValueError, "state leak"):
            api.validate_bplus_snapshot(leaked, EXPECTED_CONFIG)

    def test_bplus_reuses_native_protocol_metrics_and_timing_schema(self) -> None:
        native = load(NATIVE_API, "dflash_d6_native_metrics")
        bplus = load(BPLUS_API, "dflash_d6_bplus_metrics")
        self.assertEqual(
            bplus.validate_protocol_inputs.__module__, "dflash_d6_api"
        )
        self.assertEqual(
            bplus.enrich_and_summarize.__module__, "dflash_d6_api"
        )
        fixture = {
            "terminal_state": "success",
            "usage": {"completion_tokens": 7},
            "full_response": {
                "choices": [
                    {
                        "meta_info": {
                            "spec_verify_ct": 3,
                            "spec_num_correct_drafts": 3,
                            "spec_num_proposed_drafts": 21,
                            "spec_accept_length": 7 / 3,
                            "spec_correct_drafts_histogram": [1, 1, 1],
                        }
                    }
                ]
            },
        }
        self.assertEqual(
            bplus.response_speculative_metrics(fixture),
            native.response_speculative_metrics(fixture),
        )
        self.assertEqual(bplus.PROPOSAL_WIDTH, native.PROPOSAL_WIDTH)
        self.assertEqual(
            bplus.FORMAL_TIMING_FIELDS,
            (
                "completion_tokens",
                "wall_time_seconds",
                "e2e_output_tps",
                "terminal_counts",
                "retry_count",
            ),
        )

    def test_formal_hedge_delta_excludes_warmup_and_is_budget_bounded(self) -> None:
        api = load(BPLUS_API, "dflash_d6_bplus_delta")
        after_warmup = {
            "proposals": 5,
            "draft_tokens_verifiable": 35,
            "strict_accepted_draft_tokens": 4,
            "hedge_accepted_draft_tokens": 6,
            "accepted_draft_tokens_by_position": [3, 2, 1, 0, 0, 0, 0],
            "accept_length_histogram": [2, 1, 1, 1, 0, 0, 0, 0],
            "relaxed_mismatches": 2,
            "regret_charged": 12.5,
            "budget_exhaustion_events": 1,
            "requests_initialized": 12,
            "requests_finished": 11,
            "slot_reuse_resets": 1,
            "requests_non_natural": 1,
        }
        after_formal = {
            "proposals": 105,
            "draft_tokens_verifiable": 735,
            "strict_accepted_draft_tokens": 54,
            "hedge_accepted_draft_tokens": 86,
            "accepted_draft_tokens_by_position": [63, 22, 1, 0, 0, 0, 0],
            "accept_length_histogram": [42, 41, 21, 1, 0, 0, 0, 0],
            "relaxed_mismatches": 32,
            "regret_charged": 1012.5,
            "budget_exhaustion_events": 11,
            "requests_initialized": 512,
            "requests_finished": 511,
            "slot_reuse_resets": 1,
            "requests_non_natural": 1,
        }
        delta = api.formal_hedge_counter_delta(
            after_warmup,
            after_formal,
            EXPECTED_CONFIG,
            formal_request_count=500,
        )
        self.assertEqual(delta["proposals"], 100)
        self.assertEqual(delta["hedge_accepted_draft_tokens"], 80)
        self.assertEqual(delta["regret_charged"], 1000.0)
        self.assertEqual(delta["risk_budget_upper_bound"], 6250.0)
        self.assertEqual(delta["requests_initialized"], 500)
        self.assertTrue(delta["pass"])
        api.validate_formal_counter_alignment(
            delta,
            {
                "proposals": 100,
                "accepted_draft_tokens": 80,
                "acceptance_length_histogram_0_to_7": [
                    40,
                    40,
                    20,
                    0,
                    0,
                    0,
                    0,
                    0,
                ],
                "accepted_draft_tokens_by_position_1_to_7": [
                    60,
                    20,
                    0,
                    0,
                    0,
                    0,
                    0,
                ],
            },
        )
        with self.assertRaisesRegex(ValueError, "response metrics"):
            api.validate_formal_counter_alignment(
                delta,
                {
                    "proposals": 100,
                    "accepted_draft_tokens": 79,
                    "acceptance_length_histogram_0_to_7": [
                        40,
                        40,
                        20,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                    "accepted_draft_tokens_by_position_1_to_7": [
                        60,
                        20,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ],
                },
            )

        non_monotonic = copy.deepcopy(after_formal)
        non_monotonic["relaxed_mismatches"] = 1
        with self.assertRaisesRegex(ValueError, "not monotonic"):
            api.formal_hedge_counter_delta(
                after_warmup,
                non_monotonic,
                EXPECTED_CONFIG,
                formal_request_count=500,
            )

    def test_adapter_relabels_artifacts_without_mutating_native_input(self) -> None:
        lifecycle = load(BPLUS_LIFECYCLE, "dflash_d6_bplus_adapter")
        original = {
            "schema_version": 1,
            "phase": "D6",
            "arm": "native",
            "hedge_enabled": False,
            "calibration_trace": False,
            "hedge_config": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / "summary.json"
            (summary_path.parent / "hedge_counters.json").write_text(
                json.dumps(
                    {
                        "risk_lifecycle_audit": {
                            "risk_budget_per_request": 12.5,
                            "regret_charged": 8.0,
                            "state_leaks": 0,
                            "pass": True,
                        },
                        "formal_hedge_counter_delta": {
                            "requests_initialized": 500,
                            "regret_charged": 8.0,
                            "pass": True,
                        },
                    }
                )
            )
            adapted = lifecycle.adapt_document(summary_path, original)
        self.assertEqual(original["arm"], "native")
        self.assertEqual(adapted["arm"], "B+")
        self.assertTrue(adapted["hedge_enabled"])
        self.assertEqual(adapted["hedge_config"], EXPECTED_CONFIG)
        self.assertEqual(adapted["hedge_config_sha256"], EXPECTED_SHA256)
        self.assertEqual(
            adapted["risk_lifecycle_audit"],
            {
                "risk_budget_per_request": 12.5,
                "regret_charged": 8.0,
                "state_leaks": 0,
                "pass": True,
            },
        )
        self.assertEqual(
            adapted["formal_hedge_counter_delta"]["requests_initialized"], 500
        )

    def test_independent_launcher_is_syntax_valid_and_prep_is_non_gpu(self) -> None:
        subprocess.run(["bash", "-n", str(BPLUS_LAUNCHER)], check=True)
        for path in (BPLUS_API, BPLUS_LIFECYCLE):
            compile(path.read_text(), str(path), "exec")
        completed = subprocess.run(
            [
                "bash",
                str(BPLUS_LAUNCHER),
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
        self.assertFalse(contract["gpu_action"])
        lifecycle_source = BPLUS_LIFECYCLE.read_text()
        self.assertIn("import dflash_d6_lifecycle as native", lifecycle_source)
        self.assertNotIn("mlx worker login", lifecycle_source)
        self.assertNotRegex(lifecycle_source, r"\b(?:pkill|killall)\b")

    def test_bplus_progress_snapshot_is_read_only_and_counts_durable_rows(self) -> None:
        progress = load(BPLUS_PROGRESS, "dflash_d6_bplus_progress")
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            (scratch / "formal.active").touch()
            (scratch / "warmup_outputs.jsonl").write_text(
                json.dumps(
                    {
                        "terminal_state": "success",
                        "retry_count": 0,
                        "usage": {"completion_tokens": 3},
                        "answer_status": "match",
                    }
                )
                + "\n"
            )
            (scratch / "formal_outputs.raw.jsonl").write_text(
                json.dumps(
                    {
                        "terminal_state": "success",
                        "retry_count": 1,
                        "usage": {"completion_tokens": 7},
                        "answer_status": "mismatch",
                    }
                )
                + "\n"
            )
            (scratch / "server.log").write_text("healthy\n")
            observed = progress.snapshot(scratch)
        self.assertEqual(observed["phase"], "formal")
        self.assertEqual(observed["formal"]["complete_json_rows"], 1)
        self.assertEqual(observed["formal"]["retry_count"], 1)
        self.assertEqual(observed["formal"]["completion_tokens"], 7)
        self.assertEqual(observed["formal"]["mismatch"], 1)
        self.assertEqual(
            observed["server_fatal_pattern_counts"],
            {"cuda_error": 0, "nccl_error": 0, "traceback": 0, "worker_crash": 0},
        )
        subprocess.run(["bash", "-n", str(BPLUS_PROGRESS_LAUNCHER)], check=True)
        source = BPLUS_PROGRESS.read_text()
        self.assertNotIn("write_text", source)
        self.assertNotRegex(source, r"\b(?:kill|unlink|remove|rmtree)\b")


if __name__ == "__main__":
    unittest.main()
