from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "dflash_d4_b0_attempt.sh"
API_HELPER = REPO_ROOT / "scripts" / "dflash_d4_b0_api.py"
ATTEMPT_ID = "dflash-d4-b0-20260729T000000Z-a01"


class D4CLauncherContractTests(unittest.TestCase):
    def test_launcher_syntax_and_sampler_are_d4_self_contained(self) -> None:
        subprocess.run(
            ["bash", "-n", str(LAUNCHER)],
            cwd=REPO_ROOT,
            check=True,
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('setsid nohup bash "$0" _sample', source)
        self.assertNotIn("scripts/dflash_d3_attempt.sh", source)
        self.assertIn(
            '"${REPO}/scripts/dflash_d4_b0_attempt.sh"',
            source,
        )
        self.assertIn('--counters-output "${SCRATCH}/hedge_counters.json"', source)
        self.assertIn(
            '--expected-output-token-ids "${EXPECTED_OUTPUT_TOKEN_IDS}"',
            source,
        )
        python_blocks = re.findall(
            r"<<'PY'\n(.*?)\nPY\n",
            source,
            flags=re.DOTALL,
        )
        self.assertGreaterEqual(len(python_blocks), 1)
        for index, block in enumerate(python_blocks):
            ast.parse(block, filename=f"{LAUNCHER}:heredoc-{index}")

    def test_contract_pins_final_source_lane_and_b0(self) -> None:
        completed = subprocess.run(
            ["bash", str(LAUNCHER), "contract", ATTEMPT_ID],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        contract = json.loads(completed.stdout)

        self.assertEqual(
            contract["source_sha"],
            "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1",
        )
        self.assertEqual(contract["worker_id"], "4099543")
        self.assertEqual(contract["port"], 31457)
        self.assertEqual(contract["tp_size"], 8)
        self.assertEqual(contract["dflash_block_size"], 8)
        self.assertEqual(contract["proposal_width"], 7)
        self.assertEqual(
            contract["hedge_config"],
            {
                "B": 0,
                "g": 1_000_000,
                "m": 1,
                "value_scheme": "normalized_suffix",
                "block_size": 7,
            },
        )
        self.assertEqual(contract["environment"]["HEDGE_ENABLED"], "1")
        self.assertEqual(
            contract["environment"][
                "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"
            ],
            "0",
        )
        self.assertEqual(
            contract["expected_output_token_ids"],
            [22, 1],
        )


class D4CApiSnapshotTests(unittest.TestCase):
    def test_snapshot_validator_accepts_strict_b0_and_clean_lifecycle(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "dflash_d4_b0_api",
            API_HELPER,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        hedge = {
            "mode": "enabled",
            "config": {
                "B": 0,
                "g": 1_000_000,
                "m": 1,
                "value_scheme": "normalized_suffix",
                "block_size": 7,
            },
            "proposal_width": 7,
            "proposals": 2,
            "draft_tokens_verifiable": 14,
            "strict_accepted_draft_tokens": 3,
            "hedge_accepted_draft_tokens": 3,
            "accepted_draft_tokens_by_position": [2, 1, 0, 0, 0, 0, 0],
            "accept_length_histogram": [0, 1, 1, 0, 0, 0, 0, 0],
            "relaxed_mismatches": 0,
            "regret_charged": 0.0,
            "requests_initialized": 1,
            "requests_finished": 1,
            "active_request_states": 0,
            "state_leaks": 0,
        }
        server_info = {
            "internal_states": [
                {
                    "dflash_info_record": {
                        "hedge": hedge,
                    }
                }
            ]
        }

        observed = module.validate_hedge_snapshot(server_info)

        self.assertEqual(observed, hedge)


if __name__ == "__main__":
    unittest.main()
