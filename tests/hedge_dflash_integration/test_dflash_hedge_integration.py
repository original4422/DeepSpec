from __future__ import annotations

import hashlib
import inspect
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

import torch


SGLANG_ROOT = Path("/home/tiger/src/deepspec-sglang-hedge-dflash")
SGLANG_PYTHON = SGLANG_ROOT / "python"
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(SGLANG_PYTHON) not in sys.path:
    sys.path.insert(0, str(SGLANG_PYTHON))


class DFlashHedgeSettingsTests(unittest.TestCase):
    def test_native_mode_has_no_decode_config(self) -> None:
        from sglang.srt.speculative.dflash_hedge import DFlashHedgeSettings

        settings = DFlashHedgeSettings.from_environ({})

        self.assertEqual(settings.mode, "disabled")
        self.assertIsNone(settings.config)
        self.assertFalse(settings.active)


class InjectedCoreTests(unittest.TestCase):
    def test_injected_core_is_byte_identical_to_canonical_core(self) -> None:
        filenames = (
            "__init__.py",
            "budget.py",
            "config.py",
            "hedge_core_identity.json",
            "torch_rule.py",
        )
        canonical = REPO_ROOT / "deepspec" / "hedge_spec"
        injected = (
            SGLANG_PYTHON / "sglang" / "srt" / "speculative" / "hedge_spec"
        )

        hashes = []
        for filename in filenames:
            canonical_bytes = (canonical / filename).read_bytes()
            injected_bytes = (injected / filename).read_bytes()
            self.assertEqual(injected_bytes, canonical_bytes)
            hashes.append(hashlib.sha256(injected_bytes).hexdigest())

        self.assertEqual(
            hashes,
            [
                "e51bba48b8a67895270b3285775dfc3741421eb4a0c3cdf566a1cf0e9360daca",
                "c573fe2381416c70511f97968fe14fa9ef1e16d08c805eb55982efc0d23a5ce8",
                "03079c13b327b1c31374421060d07217401dc3049c7b8fb5fb6c68d30b6db176",
                "acd9ebe5cd71bd50313a06c5a7ebb2e02289aa010bc92d9fcd72e9f8ded80d2a",
                "92bb84a3bf3f03fd127636c5d5ef6b7bb9e22d4198cc57dac320606ae1256c72",
            ],
        )


@dataclass
class _Req:
    rid: str
    req_pool_idx: int


class _Pool:
    _alloc_size = 16


class _Batch:
    def __init__(self, *requests: _Req) -> None:
        self.reqs = list(requests)
        self.req_to_token_pool = _Pool()
        self.req_pool_indices = torch.tensor(
            [request.req_pool_idx for request in requests],
            dtype=torch.int64,
        )
        self.req_pool_indices_cpu = self.req_pool_indices.tolist()


def _target_logits(top_ids: list[int], candidate_ids: list[int]) -> torch.Tensor:
    logits = torch.full((8, 32), -20.0, dtype=torch.float32)
    for row, (top_id, candidate_id) in enumerate(zip(top_ids, candidate_ids)):
        logits[row, top_id] = 5.0
        logits[row, candidate_id] = 4.0
    return logits


def _batched_logits(
    *,
    candidates: torch.Tensor,
    top_ids: list[list[int]],
    regrets: list[list[float]],
) -> torch.Tensor:
    batch, width = candidates.shape
    logits = torch.full((batch, width, 64), -20.0, dtype=torch.float32)
    for batch_index in range(batch):
        for position in range(width):
            candidate = int(
                candidates[
                    batch_index,
                    min(position + 1, width - 1),
                ]
            )
            top_id = top_ids[batch_index][position]
            regret = regrets[batch_index][position]
            logits[batch_index, position, candidate] = 5.0 - regret
            logits[batch_index, position, top_id] = 5.0
    return logits.reshape(batch * width, -1)


class DFlashHedgeAdapterTests(unittest.TestCase):
    def test_hot_path_has_no_tensor_to_host_conversion(self) -> None:
        from sglang.srt.speculative.dflash_hedge import DFlashHedgeAdapter

        source = "\n".join(
            inspect.getsource(method)
            for method in (
                DFlashHedgeAdapter.accept_or_native,
                DFlashHedgeAdapter._compact_scores,
                DFlashHedgeAdapter._record_acceptance,
                DFlashHedgeAdapter._record_calibration,
            )
        )

        self.assertNotIn(".item(", source)
        self.assertNotIn(".cpu(", source)
        self.assertNotIn(".numpy(", source)
        self.assertNotIn(".tolist(", source)

    def test_active_mode_rejects_non_greedy_before_verify(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        adapter = DFlashHedgeAdapter(
            settings=DFlashHedgeSettings.from_environ(
                {
                    "HEDGE_ENABLED": "0",
                    "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": "1",
                }
            ),
            dflash_block_size=8,
            device="cpu",
        )

        with self.assertRaisesRegex(ValueError, "greedy verify only"):
            adapter.require_greedy(all_greedy=False)

    def test_native_config_off_delegates_without_request_state(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        adapter = DFlashHedgeAdapter(
            settings=DFlashHedgeSettings.from_environ({}),
            dflash_block_size=8,
            device="cpu",
        )
        expected_accept = torch.tensor([3], dtype=torch.int32)
        expected_bonus = torch.tensor([29], dtype=torch.int64)

        accepted, bonus = adapter.accept_or_native(
            candidates=torch.zeros((1, 8), dtype=torch.int64),
            target_logits=None,
            req_pool_indices=torch.tensor([3], dtype=torch.int64),
            forward_ct=1,
            all_greedy=True,
            native_accept=lambda: (expected_accept, expected_bonus),
        )

        self.assertIs(accepted, expected_accept)
        self.assertIs(bonus, expected_bonus)
        self.assertEqual(adapter.snapshot()["request_state"], [])

    def test_B_zero_matches_the_strict_prefix_and_bonus(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        settings = DFlashHedgeSettings.from_environ(
            {
                "HEDGE_ENABLED": "1",
                "SGLANG_DFLASH_HEDGE_CONFIG_JSON": (
                    '{"B":0,"g":100,"m":1,'
                    '"value_scheme":"normalized_suffix","block_size":7}'
                ),
            }
        )
        adapter = DFlashHedgeAdapter(
            settings=settings,
            dflash_block_size=8,
            device="cpu",
        )
        adapter.bind_batch(_Batch(_Req("r0", 3)))
        candidates = torch.tensor(
            [[10, 11, 12, 13, 14, 15, 16, 17]],
            dtype=torch.int64,
        )
        logits = _target_logits(
            [11, 20, 13, 14, 15, 16, 17, 18],
            candidates[0, 1:].tolist() + [0],
        )

        def unexpected_native() -> tuple[torch.Tensor, torch.Tensor]:
            raise AssertionError("enabled HEDGE must own the accept decision")

        accepted, bonus = adapter.accept_or_native(
            candidates=candidates,
            target_logits=logits,
            req_pool_indices=torch.tensor([3], dtype=torch.int64),
            forward_ct=1,
            all_greedy=True,
            native_accept=unexpected_native,
        )

        self.assertEqual(accepted.tolist(), [1])
        self.assertEqual(bonus.tolist(), [20])

    def test_request_state_survives_reorder_and_resets_on_slot_reuse(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        settings = DFlashHedgeSettings.from_environ(
            {
                "HEDGE_ENABLED": "1",
                "SGLANG_DFLASH_HEDGE_CONFIG_JSON": (
                    '{"B":1,"g":10,"m":1,'
                    '"value_scheme":"normalized_suffix","block_size":7}'
                ),
            }
        )
        adapter = DFlashHedgeAdapter(
            settings=settings,
            dflash_block_size=8,
            device="cpu",
        )
        request_a = _Req("request-a", 2)
        request_b = _Req("request-b", 5)
        adapter.bind_batch(_Batch(request_a, request_b))
        candidates = torch.tensor(
            [
                [10, 11, 12, 13, 14, 15, 16, 17],
                [20, 21, 22, 23, 24, 25, 26, 27],
            ],
            dtype=torch.int64,
        )
        first_logits = _batched_logits(
            candidates=candidates,
            top_ids=[
                [30, 12, 13, 14, 15, 16, 17, 18],
                [21, 22, 23, 24, 25, 26, 27, 28],
            ],
            regrets=[
                [0.4, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
            ],
        )
        first_accept, _ = adapter.accept_or_native(
            candidates=candidates,
            target_logits=first_logits,
            req_pool_indices=torch.tensor([2, 5], dtype=torch.int64),
            forward_ct=1,
            all_greedy=True,
            native_accept=lambda: (_ for _ in ()).throw(AssertionError()),
        )
        self.assertEqual(first_accept.tolist(), [7, 7])

        adapter.bind_batch(_Batch(request_b, request_a))
        reordered_candidates = candidates[[1, 0]]
        second_logits = _batched_logits(
            candidates=reordered_candidates,
            top_ids=[
                [31, 22, 23, 24, 25, 26, 27, 28],
                [32, 12, 13, 14, 15, 16, 17, 18],
            ],
            regrets=[
                [0.8, 0, 0, 0, 0, 0, 0, 0],
                [0.7, 0, 0, 0, 0, 0, 0, 0],
            ],
        )
        second_accept, _ = adapter.accept_or_native(
            candidates=reordered_candidates,
            target_logits=second_logits,
            req_pool_indices=torch.tensor([5, 2], dtype=torch.int64),
            forward_ct=2,
            all_greedy=True,
            native_accept=lambda: (_ for _ in ()).throw(AssertionError()),
        )
        self.assertEqual(second_accept.tolist(), [7, 0])

        adapter.note_request_finished(rid="request-b", natural_stop=False)
        request_c = _Req("request-c", 5)
        adapter.bind_batch(_Batch(request_c))
        third_candidates = candidates[[1]]
        third_logits = _batched_logits(
            candidates=third_candidates,
            top_ids=[[33, 22, 23, 24, 25, 26, 27, 28]],
            regrets=[[0.9, 0, 0, 0, 0, 0, 0, 0]],
        )
        third_accept, _ = adapter.accept_or_native(
            candidates=third_candidates,
            target_logits=third_logits,
            req_pool_indices=torch.tensor([5], dtype=torch.int64),
            forward_ct=3,
            all_greedy=True,
            native_accept=lambda: (_ for _ in ()).throw(AssertionError()),
        )
        self.assertEqual(third_accept.tolist(), [7])

        snapshot = adapter.snapshot()
        state = {
            item["rid"]: (
                round(item["remaining_budget"], 6),
                item["relaxed_mismatches"],
            )
            for item in snapshot["request_state"]
        }
        self.assertEqual(
            state,
            {
                "request-a": (0.6, 1),
                "request-c": (0.1, 1),
            },
        )
        self.assertEqual(snapshot["proposals"], 5)
        self.assertEqual(snapshot["hedge_accepted_draft_tokens"], 28)
        self.assertEqual(
            snapshot["accepted_draft_tokens_by_position"],
            [4, 4, 4, 4, 4, 4, 4],
        )
        self.assertEqual(
            snapshot["accept_length_histogram"],
            [1, 0, 0, 0, 0, 0, 0, 4],
        )
        self.assertEqual(snapshot["relaxed_mismatches"], 3)
        self.assertAlmostEqual(snapshot["regret_charged"], 2.1, places=5)

        adapter.note_request_finished(rid="request-a", natural_stop=True)
        adapter.note_request_finished(rid="request-c", natural_stop=False)
        sealed = adapter.snapshot()
        self.assertEqual(sealed["request_state"], [])
        self.assertEqual(sealed["state_leaks"], 0)
        self.assertEqual(sealed["requests_finished"], 3)
        self.assertEqual(sealed["requests_non_natural"], 2)

    def test_unannounced_slot_reuse_discards_the_old_budget(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        adapter = DFlashHedgeAdapter(
            settings=DFlashHedgeSettings.from_environ(
                {
                    "HEDGE_ENABLED": "1",
                    "SGLANG_DFLASH_HEDGE_CONFIG_JSON": (
                        '{"B":1,"g":10,"m":1,'
                        '"value_scheme":"normalized_suffix","block_size":7}'
                    ),
                }
            ),
            dflash_block_size=8,
            device="cpu",
        )
        candidates = torch.tensor(
            [[10, 11, 12, 13, 14, 15, 16, 17]],
            dtype=torch.int64,
        )
        adapter.bind_batch(_Batch(_Req("old-request", 7)))
        old_logits = _batched_logits(
            candidates=candidates,
            top_ids=[[30, 12, 13, 14, 15, 16, 17, 18]],
            regrets=[[0.8, 0, 0, 0, 0, 0, 0, 0]],
        )
        adapter.accept_or_native(
            candidates=candidates,
            target_logits=old_logits,
            req_pool_indices=torch.tensor([7], dtype=torch.int64),
            forward_ct=1,
            all_greedy=True,
            native_accept=lambda: (_ for _ in ()).throw(AssertionError()),
        )

        adapter.bind_batch(_Batch(_Req("replacement-request", 7)))
        replacement_logits = _batched_logits(
            candidates=candidates,
            top_ids=[[31, 12, 13, 14, 15, 16, 17, 18]],
            regrets=[[0.9, 0, 0, 0, 0, 0, 0, 0]],
        )
        accepted, _ = adapter.accept_or_native(
            candidates=candidates,
            target_logits=replacement_logits,
            req_pool_indices=torch.tensor([7], dtype=torch.int64),
            forward_ct=2,
            all_greedy=True,
            native_accept=lambda: (_ for _ in ()).throw(AssertionError()),
        )
        snapshot = adapter.snapshot()

        self.assertEqual(accepted.tolist(), [7])
        self.assertEqual(snapshot["slot_reuse_resets"], 1)
        self.assertEqual(
            [item["rid"] for item in snapshot["request_state"]],
            ["replacement-request"],
        )

    def test_calibration_records_the_first_positive_strict_rejection(self) -> None:
        from sglang.srt.speculative.dflash_hedge import (
            DFlashHedgeAdapter,
            DFlashHedgeSettings,
        )

        adapter = DFlashHedgeAdapter(
            settings=DFlashHedgeSettings.from_environ(
                {
                    "HEDGE_ENABLED": "0",
                    "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": "1",
                    "SGLANG_DFLASH_HEDGE_TRACE_CAPACITY": "16",
                }
            ),
            dflash_block_size=8,
            device="cpu",
        )
        adapter.bind_batch(_Batch(_Req("calibration-request", 4)))
        candidates = torch.tensor(
            [[10, 11, 12, 13, 14, 15, 16, 17]],
            dtype=torch.int64,
        )
        logits = _batched_logits(
            candidates=candidates,
            top_ids=[[11, 12, 30, 14, 15, 16, 17, 18]],
            regrets=[[0, 0, 0.6, 0, 0, 0, 0, 0]],
        )
        expected_accept = torch.tensor([2], dtype=torch.int32)
        expected_bonus = torch.tensor([30], dtype=torch.int64)

        accepted, bonus = adapter.accept_or_native(
            candidates=candidates,
            target_logits=logits,
            req_pool_indices=torch.tensor([4], dtype=torch.int64),
            forward_ct=9,
            all_greedy=True,
            native_accept=lambda: (expected_accept, expected_bonus),
        )
        trace = adapter.snapshot()["strict_rejection_trace"]

        self.assertIs(accepted, expected_accept)
        self.assertIs(bonus, expected_bonus)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["rid"], "calibration-request")
        self.assertEqual(trace[0]["barrier_position"], 2)
        self.assertAlmostEqual(trace[0]["regret"], 0.6, places=5)
        self.assertAlmostEqual(trace[0]["value"], 5 / 7, places=12)
        self.assertAlmostEqual(
            trace[0]["regret_per_value"],
            0.6 / (5 / 7),
            places=5,
        )


if __name__ == "__main__":
    unittest.main()
