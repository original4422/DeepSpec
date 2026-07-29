from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts" / "dflash_d5_attempt.sh"
API = REPO / "scripts" / "dflash_d5_api.py"
PROGRESS = REPO / "scripts" / "dflash_d5_progress.sh"
ATTEMPT = "dflash-d5-native-20260729T000000Z-a01"
B0_ATTEMPT = "dflash-d5-b0-20260729T000000Z-a01"
SEALED_NATIVE_ATTEMPT = "dflash-d5-native-20260729T073139Z-a01"
HARD_STOP_UTC = "2026-07-29T16:31:29Z"


def load_api():
    spec = importlib.util.spec_from_file_location("dflash_d5_api", API)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class D5ToolingTest(unittest.TestCase):
    def test_native_contract_and_frozen_identity(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(LAUNCHER),
                "contract",
                ATTEMPT,
                "native",
                "none",
                HARD_STOP_UTC,
            ],
            cwd=REPO,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        contract = json.loads(completed.stdout)
        self.assertEqual(contract["phase"], "D5")
        self.assertEqual(contract["arm"], "native")
        self.assertEqual(contract["source_sha"], "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1")
        self.assertEqual(contract["worker_id"], "4099543")
        self.assertEqual(contract["tp_size"], 8)
        self.assertEqual(contract["dflash_block_size"], 8)
        self.assertEqual(contract["proposal_width"], 7)
        self.assertIsNone(contract["hedge_config"])
        self.assertEqual(contract["environment"]["HEDGE_ENABLED"], "0")
        self.assertEqual(
            contract["environment"]["SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"],
            "1",
        )
        self.assertNotIn(
            "SGLANG_DFLASH_HEDGE_CONFIG_JSON", contract["environment"]
        )
        self.assertEqual(contract["hard_stop_utc"], HARD_STOP_UTC)
        self.assertFalse(contract["gpu_action"])

    def test_b0_contract_uses_zero_budget_and_frozen_q25_gate(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(LAUNCHER),
                "contract",
                B0_ATTEMPT,
                "b0",
                SEALED_NATIVE_ATTEMPT,
                HARD_STOP_UTC,
            ],
            cwd=REPO,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        contract = json.loads(completed.stdout)
        self.assertEqual(contract["arm"], "b0")
        self.assertEqual(
            contract["hedge_config"],
            {
                "B": 0,
                "g": 12.5,
                "m": 1,
                "value_scheme": "normalized_suffix",
                "block_size": 7,
            },
        )
        self.assertEqual(contract["environment"]["HEDGE_ENABLED"], "1")
        self.assertEqual(
            contract["environment"]["SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"],
            "0",
        )
        self.assertEqual(
            json.loads(
                contract["environment"]["SGLANG_DFLASH_HEDGE_CONFIG_JSON"]
            ),
            contract["hedge_config"],
        )

    def test_launcher_syntax_heredocs_deadline_and_self_calls(self) -> None:
        subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)
        subprocess.run(["bash", "-n", str(PROGRESS)], check=True)
        source = LAUNCHER.read_text()
        self.assertNotIn('"phase": "D4-C"', source)
        self.assertGreaterEqual(source.count("before_hard_stop"), 5)
        self.assertIn(
            'cleanup-resume "${ATTEMPT_ID}" "${ARM}" '
            '"${NATIVE_ATTEMPT_ID}" "${HARD_STOP_UTC}"',
            source,
        )
        self.assertIn(
            '"$0" _sample \\\n      "${ATTEMPT_ID}" "${ARM}" '
            '"${NATIVE_ATTEMPT_ID}" "${HARD_STOP_UTC}"',
            source,
        )
        self.assertIn('sample_gpus "${6:?server pid}" "${7:?start ticks}"', source)
        self.assertNotIn('readonly HARD_STOP_UTC="2026-', source)
        self.assertNotIn("scripts/dflash_d4_b0_attempt.sh", source)
        for index, block in enumerate(
            re.findall(r"<<'PY'\n(.*?)\nPY\n", source, flags=re.DOTALL)
        ):
            ast.parse(block, filename=f"{LAUNCHER}:heredoc-{index}")
        progress_source = PROGRESS.read_text()
        self.assertIn("complete_json_rows", progress_source)
        self.assertNotIn("kill ", progress_source)
        for index, block in enumerate(
            re.findall(r"<<'PY'\n(.*?)\nPY\n", progress_source, flags=re.DOTALL)
        ):
            ast.parse(block, filename=f"{PROGRESS}:heredoc-{index}")

    def test_deadline_is_required_exact_utc_and_parseable(self) -> None:
        base = ["bash", str(LAUNCHER), "contract", ATTEMPT, "native", "none"]
        for deadline in (
            None,
            "2026-07-29 16:31:29Z",
            "2026-07-29T16:31:29+00:00",
            "2026-02-30T16:31:29Z",
        ):
            command = base if deadline is None else [*base, deadline]
            completed = subprocess.run(
                command,
                cwd=REPO,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 2, deadline)

    def test_linear_q25_and_trace_validation_are_reproducible(self) -> None:
        module = load_api()
        values = [1.0, 2.0, 10.0, 20.0]
        trace = [
            {
                "proposal_ordinal": index,
                "request_serial": index + 1,
                "rid": f"r{index}",
                "request_pool_slot": 0,
                "forward_ct": index,
                "barrier_position": 0,
                "regret": value,
                "value": 1.0,
                "regret_per_value": value,
            }
            for index, value in enumerate(values)
        ]
        snapshot = {
            "mode": "calibration",
            "config": None,
            "proposal_width": 7,
            "proposals": 4,
            "draft_tokens_verifiable": 28,
            "requests_initialized": 32,
            "requests_finished": 32,
            "slot_reuse_resets": 0,
            "requests_non_natural": 0,
            "active_request_states": 0,
            "state_leaks": 0,
            "request_state": [],
            "trace_rows_seen": 4,
            "trace_rows_dropped": 0,
            "strict_rejection_trace": trace,
        }
        observed_trace, distribution, calibration = module.build_calibration(snapshot)
        expected = float(
            np.quantile(np.asarray(values), 0.25, method="linear")
        )
        self.assertEqual(observed_trace, trace)
        self.assertEqual(distribution["quantile_method"], "linear")
        self.assertEqual(calibration["q25"], expected)
        self.assertEqual(calibration["frozen_config"]["B"], expected)
        self.assertEqual(calibration["frozen_config"]["g"], expected)
        self.assertEqual(calibration["frozen_config"]["m"], 1)
        self.assertEqual(
            calibration["frozen_config"]["value_scheme"],
            "normalized_suffix",
        )

    def test_b0_config_preserves_frozen_gate_but_zeroes_budget(self) -> None:
        module = load_api()
        frozen = {
            "B": 12.5,
            "g": 12.5,
            "m": 1,
            "value_scheme": "normalized_suffix",
            "block_size": 7,
        }
        with tempfile.TemporaryDirectory() as directory:
            native_run = Path(directory)
            (native_run / ".complete.json").write_text(
                json.dumps({"status": "PASS"})
            )
            (native_run / "summary.json").write_text(
                json.dumps({"status": "PASS"})
            )
            canonical = module.canonical(frozen)
            (native_run / "calibration.json").write_text(
                json.dumps(
                    {
                        "status": "FROZEN",
                        "frozen_config": frozen,
                        "config_canonical_json": canonical,
                        "config_sha256": hashlib.sha256(
                            canonical.encode()
                        ).hexdigest(),
                    }
                )
            )

            observed = module.b0_config(native_run)

        self.assertEqual(observed["B"], 0)
        self.assertEqual(observed["g"], 12.5)
        self.assertEqual(observed["m"], 1)
        self.assertEqual(observed["value_scheme"], "normalized_suffix")
        self.assertEqual(observed["block_size"], 7)
        self.assertEqual(frozen["B"], 12.5)

    def test_b0_comparison_locks_identity_and_writes_full_counterexample(self) -> None:
        module = load_api()
        native_rows = []
        b0_rows = []
        for index in range(32):
            common = {
                "request_index": index,
                "cohort_position": index,
                "dataset_index": 1000 + index,
                "prompt": f"prompt-{index}",
                "question": f"question-{index}",
                "terminal_state": "success",
            }
            native_rows.append(
                {
                    **common,
                    "output_token_ids": [index, 1],
                    "model_text": f"native-{index}",
                }
            )
            b0_rows.append(
                {
                    **common,
                    "output_token_ids": [index, 1],
                    "model_text": f"b0-{index}",
                }
            )
        b0_rows[7]["output_token_ids"] = [7, 2]
        snapshot = {"mode": "enabled", "regret_charged": 0.0}

        comparison, counterexample = module.compare_b0_outputs(
            native_rows, b0_rows, snapshot
        )

        self.assertEqual(comparison["status"], "FAIL")
        self.assertEqual(comparison["compared"], 32)
        self.assertEqual(comparison["identical"], 31)
        self.assertEqual(comparison["mismatches"], 1)
        self.assertEqual(
            counterexample["first_divergence_token_position"], 1
        )
        self.assertEqual(counterexample["native_output_token_ids"], [7, 1])
        self.assertEqual(counterexample["b0_output_token_ids"], [7, 2])
        self.assertEqual(counterexample["native_model_text"], "native-7")
        self.assertEqual(counterexample["b0_model_text"], "b0-7")
        self.assertEqual(counterexample["hedge_snapshot"], snapshot)
        self.assertEqual(
            counterexample["prompt_sha256"],
            hashlib.sha256(b"prompt-7").hexdigest(),
        )

        b0_rows[8]["dataset_index"] = -1
        with self.assertRaisesRegex(ValueError, "identity/order mismatch"):
            module.compare_b0_outputs(native_rows, b0_rows, snapshot)

    def test_lifecycle_allows_sglang_internal_slot_reuse_accounting(self) -> None:
        module = load_api()
        snapshot = {
            "mode": "calibration",
            "proposal_width": 7,
            "proposals": 40,
            "draft_tokens_verifiable": 280,
            "requests_initialized": 34,
            "requests_finished": 33,
            "slot_reuse_resets": 1,
            "requests_non_natural": 1,
            "active_request_states": 0,
            "state_leaks": 0,
            "request_state": [],
        }
        module.validate_lifecycle(snapshot, expected_mode="calibration")


if __name__ == "__main__":
    unittest.main()
