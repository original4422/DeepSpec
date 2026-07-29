from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts" / "dflash_d5_attempt.sh"
API = REPO / "scripts" / "dflash_d5_api.py"
ATTEMPT = "dflash-d5-native-20260729T000000Z-a01"


def load_api():
    spec = importlib.util.spec_from_file_location("dflash_d5_api", API)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class D5ToolingTest(unittest.TestCase):
    def test_native_contract_and_frozen_identity(self) -> None:
        completed = subprocess.run(
            ["bash", str(LAUNCHER), "contract", ATTEMPT, "native", "none"],
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
        self.assertEqual(contract["hard_stop_utc"], "2026-07-29T05:55:48Z")
        self.assertFalse(contract["gpu_action"])

    def test_launcher_syntax_heredocs_deadline_and_self_calls(self) -> None:
        subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)
        source = LAUNCHER.read_text()
        self.assertNotIn('"phase": "D4-C"', source)
        self.assertGreaterEqual(source.count("before_hard_stop"), 5)
        self.assertIn(
            'cleanup-resume "${ATTEMPT_ID}" "${ARM}" "${NATIVE_ATTEMPT_ID}"',
            source,
        )
        self.assertIn(
            '"$0" _sample \\\n      "${ATTEMPT_ID}" "${ARM}" "${NATIVE_ATTEMPT_ID}"',
            source,
        )
        self.assertIn('sample_gpus "${5:?server pid}" "${6:?start ticks}"', source)
        self.assertNotIn("scripts/dflash_d4_b0_attempt.sh", source)
        for index, block in enumerate(
            re.findall(r"<<'PY'\n(.*?)\nPY\n", source, flags=re.DOTALL)
        ):
            ast.parse(block, filename=f"{LAUNCHER}:heredoc-{index}")

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
