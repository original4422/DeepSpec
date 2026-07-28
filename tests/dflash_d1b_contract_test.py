#!/usr/bin/env python3
"""Regression test for the audited DFlash-on-DeepSeek-V4 tensor contract."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest


WORKTREE = pathlib.Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
PROBE = WORKTREE / "scripts/dflash_d1b_contract_probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location(
        "dflash_d1b_contract_probe", PROBE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import D1B probe from {PROBE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DFlashD1BContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = load_probe().run_contract_checks()

    def test_all_contract_groups_pass(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertTrue(
            all(
                check["pass"]
                for check in self.result["checks"].values()
            )
        )

    def test_mhc_width_and_mean_rejection(self) -> None:
        layout = self.result["checks"]["mhc_layout"]
        self.assertEqual(layout["per_layer_width"], 16384)
        self.assertEqual(layout["concatenated_shape"], [2, 81920])
        self.assertTrue(layout["mean_dim_1"]["rejected"])
        self.assertEqual(layout["mean_dim_1"]["shape"], [2, 20480])

    def test_aux_order_and_layer_index_rule(self) -> None:
        checkpoint = self.result["checks"]["checkpoint"]
        layer_index = self.result["checks"]["layer_index_and_source"]
        self.assertEqual(
            checkpoint["aux_hidden_state_layer_ids_in_order"],
            [3, 13, 23, 32, 42],
        )
        self.assertEqual(
            layer_index["generic_before_layer_capture_indices"],
            [4, 14, 24, 33, 43],
        )
        self.assertEqual(
            layer_index["deepseek_v4_after_layer_capture_indices"],
            [3, 13, 23, 32, 42],
        )

    def test_block_eight_has_seven_draft_candidates(self) -> None:
        block = self.result["checks"]["block_candidates"]
        self.assertEqual(block["hedge_draft_candidate_shape"], [2, 7])
        self.assertEqual(
            block["hedge_draft_candidates"],
            [
                [101, 102, 103, 104, 105, 106, 107],
                [201, 202, 203, 204, 205, 206, 207],
            ],
        )

    def test_primary_parser_gap_is_executable_evidence(self) -> None:
        parser = self.result["checks"]["parser"]
        self.assertIsNone(
            parser["raw_primary_parser_result"]["num_hidden_layers"]
        )
        self.assertIsNone(
            parser["raw_primary_parser_result"]["target_layer_ids"]
        )
        self.assertEqual(
            parser["audit_adapter_result"]["num_hidden_layers"], 5
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
