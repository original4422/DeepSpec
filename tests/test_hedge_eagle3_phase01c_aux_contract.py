import unittest

import torch

from deepspec.hedge_eagle3_phase01c.aux_contract import (
    CAPTURE_HOOK_IDS,
    HIDDEN_SIZE,
    LOGICAL_LAYER_IDS,
    MHC_STREAMS,
    build_eagle3_aux_state,
)


class Eagle3AuxContractTest(unittest.TestCase):
    def _state(self, logical_layer_id: int, num_tokens: int = 2) -> torch.Tensor:
        token = torch.arange(num_tokens, dtype=torch.float32).view(-1, 1, 1) * 16
        stream = torch.arange(MHC_STREAMS, dtype=torch.float32).view(1, -1, 1) * 2
        feature = (
            torch.arange(HIDDEN_SIZE, dtype=torch.float32).remainder(2).view(1, 1, -1)
        )
        return (logical_layer_id * 4 + token + stream + feature).to(torch.bfloat16)

    def test_fixed_hooks_four_stream_mean_and_runner_layout(self) -> None:
        # Reverse insertion order proves that logical hook order, not mapping order,
        # controls the three 4096-wide chunks.
        logical_and_hook_ids = list(zip(LOGICAL_LAYER_IDS, CAPTURE_HOOK_IDS))
        captured = {
            hook_id: self._state(logical_layer_id)
            for logical_layer_id, hook_id in reversed(logical_and_hook_ids)
        }

        aux = build_eagle3_aux_state(captured)

        self.assertEqual(aux.logical_layer_ids, LOGICAL_LAYER_IDS)
        self.assertEqual(
            aux.capture_hook_ids,
            tuple(logical_layer_id + 1 for logical_layer_id in LOGICAL_LAYER_IDS),
        )
        self.assertEqual(aux.capture_hook_ids, (2, 22, 41))
        self.assertEqual(tuple(aux.structured.shape), (2, 3, 4096))
        self.assertEqual(tuple(aux.flattened.shape), (2, 12288))
        self.assertIs(aux.structured.dtype, torch.bfloat16)
        self.assertIs(aux.flattened.dtype, torch.bfloat16)
        self.assertEqual(aux.structured.device.type, "cpu")

        for tap_index, logical_layer_id in enumerate(LOGICAL_LAYER_IDS):
            expected = self._state(logical_layer_id).mean(dim=1)
            torch.testing.assert_close(aux.structured[:, tap_index], expected)
            torch.testing.assert_close(
                aux.flattened[:, tap_index * 4096 : (tap_index + 1) * 4096],
                expected,
            )

        # The stream values are 0, 2, 4, 6, so their mean contribution is 3.
        self.assertEqual(aux.structured[0, 0, 0].item(), 7.0)
        self.assertEqual(aux.structured[1, 2, 1].item(), 180.0)

    def test_missing_capture_hook_is_rejected(self) -> None:
        captured = {
            hook_id: self._state(logical_layer_id)
            for logical_layer_id, hook_id in zip(
                LOGICAL_LAYER_IDS[:-1], CAPTURE_HOOK_IDS[:-1]
            )
        }

        with self.assertRaisesRegex(ValueError, r"missing=\[41\]"):
            build_eagle3_aux_state(captured)

    def test_wrong_mhc_stream_count_is_rejected(self) -> None:
        captured = {
            hook_id: self._state(logical_layer_id)
            for logical_layer_id, hook_id in zip(
                LOGICAL_LAYER_IDS, CAPTURE_HOOK_IDS
            )
        }
        captured[22] = captured[22][:, :3, :]

        with self.assertRaisesRegex(ValueError, r"\[num_tokens, 4, 4096\]"):
            build_eagle3_aux_state(captured)


if __name__ == "__main__":
    unittest.main()
