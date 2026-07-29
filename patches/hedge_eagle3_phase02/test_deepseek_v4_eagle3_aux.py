import unittest
from types import SimpleNamespace

import torch

from sglang.srt.arg_groups.deepseek_v4_hook import (
    validate_deepseek_v4_speculative_algorithm,
)
from sglang.srt.models.deepseek_v4 import (
    DeepseekV4ForCausalLM,
    assemble_eagle3_aux_hidden_states,
    build_eagle3_aux_trace,
    capture_eagle3_completed_hidden_state,
    reduce_eagle3_mhc_hidden_state,
)
from sglang.test.ci.ci_register import register_cpu_ci


register_cpu_ci(est_time=2, suite="base-a-test-cpu")


class TestDeepseekV4Eagle3Guard(unittest.TestCase):
    @staticmethod
    def _args(algorithm):
        return SimpleNamespace(
            speculative_algorithm=algorithm,
            speculative_eagle_topk=1,
        )

    def test_eagle3_is_an_explicit_deepseek_v4_capability(self):
        validate_deepseek_v4_speculative_algorithm(
            self._args("EAGLE3"),
            "DeepseekV4ForCausalLM",
        )

    def test_unknown_speculative_algorithm_remains_rejected(self):
        with self.assertRaisesRegex(
            AssertionError,
            "Only EAGLE, EAGLE3 and DSPARK",
        ):
            validate_deepseek_v4_speculative_algorithm(
                self._args("UNKNOWN"),
                "DeepseekV4ForCausalLM",
            )


class TestDeepseekV4Eagle3CaptureConfiguration(unittest.TestCase):
    @staticmethod
    def _target():
        target = DeepseekV4ForCausalLM.__new__(DeepseekV4ForCausalLM)
        target.pp_group = SimpleNamespace(is_last_rank=True)
        target.config = SimpleNamespace(num_hidden_layers=43)
        target.capture_aux_hidden_states = False
        target.model = SimpleNamespace(
            dspark_layers_to_capture=["dspark-sentinel"],
            eagle3_logical_layers_to_capture=None,
            eagle3_hook_layers_to_capture=None,
        )
        return target

    def test_setter_maps_logical_layers_to_independent_hooks(self):
        target = self._target()

        target.set_eagle3_layers_to_capture([1, 21, 40])

        self.assertTrue(target.capture_aux_hidden_states)
        self.assertEqual(
            target.model.eagle3_logical_layers_to_capture,
            [1, 21, 40],
        )
        self.assertEqual(
            target.model.eagle3_hook_layers_to_capture,
            [2, 22, 41],
        )
        self.assertEqual(
            target.model.dspark_layers_to_capture,
            ["dspark-sentinel"],
        )

    def test_setter_rejects_missing_non_increasing_or_out_of_range_ids(self):
        cases = (
            (None, "explicit logical"),
            ([1, 21], "exactly three"),
            ([1, 10, 21, 40], "exactly three"),
            ([1, 1, 40], "strictly increasing"),
            ([21, 1, 40], "strictly increasing"),
            ([-1, 21, 40], "outside target layer range"),
            ([1, 21, 43], "outside target layer range"),
        )
        for logical_ids, message in cases:
            with self.subTest(logical_ids=logical_ids):
                with self.assertRaisesRegex(ValueError, message):
                    self._target().set_eagle3_layers_to_capture(logical_ids)


class TestDeepseekV4Eagle3AuxTensorContract(unittest.TestCase):
    def test_four_mhc_streams_reduce_to_one_bf16_hidden_state(self):
        raw = torch.stack(
            [
                torch.full((2, 4096), value, dtype=torch.bfloat16)
                for value in (0, 2, 4, 6)
            ],
            dim=1,
        )

        reduced = reduce_eagle3_mhc_hidden_state(
            raw,
            hc_mult=4,
            hidden_size=4096,
        )

        self.assertEqual(reduced.shape, (2, 4096))
        self.assertEqual(reduced.dtype, torch.bfloat16)
        torch.testing.assert_close(
            reduced,
            torch.full((2, 4096), 3, dtype=torch.bfloat16),
        )

    def test_reduction_rejects_wrong_shape_or_dtype(self):
        cases = (
            (
                torch.zeros((2, 3, 4096), dtype=torch.bfloat16),
                "expected raw EAGLE3 mHC shape",
            ),
            (
                torch.zeros((2, 4, 2048), dtype=torch.bfloat16),
                "expected raw EAGLE3 mHC shape",
            ),
            (
                torch.zeros((2, 4096), dtype=torch.bfloat16),
                "expected raw EAGLE3 mHC shape",
            ),
            (
                torch.zeros((2, 4, 4096), dtype=torch.float32),
                "expected raw EAGLE3 mHC dtype torch.bfloat16",
            ),
        )
        for raw, message in cases:
            with self.subTest(shape=raw.shape, dtype=raw.dtype):
                with self.assertRaisesRegex(ValueError, message):
                    reduce_eagle3_mhc_hidden_state(
                        raw,
                        hc_mult=4,
                        hidden_size=4096,
                    )

    def test_aux_states_are_ordered_and_expose_structured_layout(self):
        captured = {
            40: torch.full((2, 4096), 40, dtype=torch.bfloat16),
            1: torch.full((2, 4096), 1, dtype=torch.bfloat16),
            21: torch.full((2, 4096), 21, dtype=torch.bfloat16),
        }

        ordered, structured = assemble_eagle3_aux_hidden_states(
            [1, 21, 40],
            captured,
            hidden_size=4096,
        )

        self.assertEqual(structured.shape, (2, 3, 4096))
        self.assertEqual(structured.dtype, torch.bfloat16)
        self.assertEqual(
            [float(hidden[0, 0]) for hidden in ordered],
            [1.0, 21.0, 40.0],
        )
        runner_hidden = torch.cat(ordered, dim=-1)
        self.assertEqual(runner_hidden.shape, (2, 12288))
        self.assertTrue(torch.equal(runner_hidden[:, :4096], captured[1]))
        self.assertTrue(
            torch.equal(runner_hidden[:, 4096:8192], captured[21])
        )
        self.assertTrue(torch.equal(runner_hidden[:, 8192:], captured[40]))

    def test_aux_assembly_rejects_missing_or_malformed_taps(self):
        valid = {
            layer_id: torch.zeros((2, 4096), dtype=torch.bfloat16)
            for layer_id in (1, 21, 40)
        }
        with self.assertRaisesRegex(ValueError, "missing EAGLE3 aux taps"):
            assemble_eagle3_aux_hidden_states(
                [1, 21, 40],
                {1: valid[1], 40: valid[40]},
                hidden_size=4096,
            )

        malformed = dict(valid)
        malformed[21] = torch.zeros((2, 2048), dtype=torch.bfloat16)
        with self.assertRaisesRegex(
            ValueError,
            "expected reduced EAGLE3 aux shape",
        ):
            assemble_eagle3_aux_hidden_states(
                [1, 21, 40],
                malformed,
                hidden_size=4096,
            )

        wrong_dtype = dict(valid)
        wrong_dtype[21] = torch.zeros((2, 4096), dtype=torch.float32)
        with self.assertRaisesRegex(
            ValueError,
            "expected reduced EAGLE3 aux dtype torch.bfloat16",
        ):
            assemble_eagle3_aux_hidden_states(
                [1, 21, 40],
                wrong_dtype,
                hidden_size=4096,
            )

    def test_aux_assembly_requires_exactly_three_states(self):
        captured = {
            layer_id: torch.zeros((2, 4096), dtype=torch.bfloat16)
            for layer_id in (1, 21)
        }
        with self.assertRaisesRegex(ValueError, "exactly three"):
            assemble_eagle3_aux_hidden_states(
                [1, 21],
                captured,
                hidden_size=4096,
            )

    def test_runtime_trace_binds_layout_to_one_tp_rank_and_device(self):
        ordered = [
            torch.full((2, 8), value, dtype=torch.bfloat16)
            for value in (1, 21, 40)
        ]
        structured = torch.stack(ordered, dim=1)
        runner_hidden = torch.cat(ordered, dim=-1)

        trace = build_eagle3_aux_trace(
            logical_layer_ids=[1, 21, 40],
            hook_layer_ids=[2, 22, 41],
            raw_shapes_by_logical_id={
                layer_id: [2, 4, 8] for layer_id in (1, 21, 40)
            },
            structured_hidden_states=structured,
            runner_hidden_states=runner_hidden,
            hc_mult=4,
            hidden_size=8,
            tp_rank=3,
            tp_world_size=8,
            expected_local_device=torch.device("cpu"),
        )

        self.assertEqual(trace["tp_rank"], 3)
        self.assertEqual(trace["tp_world_size"], 8)
        self.assertEqual(trace["logical_layer_ids"], [1, 21, 40])
        self.assertEqual(trace["hook_layer_ids"], [2, 22, 41])
        self.assertEqual(trace["raw_shapes"], [[2, 4, 8]] * 3)
        self.assertEqual(trace["structured_shape"], [2, 3, 8])
        self.assertEqual(trace["runner_shape"], [2, 24])
        self.assertEqual(trace["dtype"], "torch.bfloat16")
        self.assertEqual(trace["device"], "cpu")

    def test_after_layer_hooks_select_exact_logical_outputs(self):
        captured = {}
        for executed_layer_id in range(43):
            completed = torch.full(
                (1, 4, 8),
                executed_layer_id,
                dtype=torch.bfloat16,
            )
            capture_eagle3_completed_hidden_state(
                executed_layer_id,
                completed,
                logical_layer_ids=[1, 21, 40],
                hook_layer_ids=[2, 22, 41],
                captured_by_logical_id=captured,
                hc_mult=4,
                hidden_size=8,
            )

        self.assertEqual(list(captured), [1, 21, 40])
        self.assertEqual(
            [float(captured[layer_id][0, 0]) for layer_id in captured],
            [1.0, 21.0, 40.0],
        )


if __name__ == "__main__":
    unittest.main()
