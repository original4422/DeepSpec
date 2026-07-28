"""Offline fixtures for the fixed SGLang DSpark HEDGE integration."""

from __future__ import annotations

import ast
import inspect
import os
import sys
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch


SGLANG_SOURCE = Path(
    os.environ.get(
        "HEDGE_SGLANG_SOURCE",
        "/home/tiger/src/"
        "hedge-v4-dspark-sglang-"
        "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
    )
).resolve()
SGLANG_PYTHON = SGLANG_SOURCE / "python"
if str(SGLANG_PYTHON) not in sys.path:
    sys.path.insert(0, str(SGLANG_PYTHON))

from sglang.srt.entrypoints.openai.serving_chat import (  # noqa: E402
    _meta_info_with_output_token_ids,
)
from sglang.srt.speculative.dspark_components.dspark_draft import (  # noqa: E402
    DraftBlockResult,
)
from sglang.srt.speculative.dspark_components.dspark_verify import (  # noqa: E402
    TargetVerifyExecutor,
)
from sglang.srt.speculative.dspark_components.hedge_dspark import (  # noqa: E402
    DSparkHedgeAdapter,
    DSparkHedgeSettings,
)
from sglang.srt.speculative.hedge_spec.budget import (  # noqa: E402
    RequestRiskState,
    TokenScores,
    choose_prefix,
)
from sglang.srt.speculative.hedge_spec.config import (  # noqa: E402
    HedgeConfig,
)


def _config(*, B: float, g: float = 100.0, m: int = 1) -> HedgeConfig:
    return HedgeConfig(
        risk_budget=B,
        max_regret_per_value=g,
        max_relaxed_mismatches_per_block=m,
        block_size=5,
    )


def _batch(*pairs: tuple[str, int], pool_capacity: int = 8):
    reqs = [
        SimpleNamespace(rid=rid, req_pool_idx=slot) for rid, slot in pairs
    ]
    return SimpleNamespace(
        reqs=reqs,
        req_pool_indices_cpu=torch.tensor(
            [slot for _, slot in pairs], dtype=torch.int64
        ),
        req_to_token_pool=SimpleNamespace(_alloc_size=pool_capacity),
    )


def _adapter(
    *,
    mode: str = "enabled",
    config: HedgeConfig | None = None,
    trace_capacity: int = 64,
) -> DSparkHedgeAdapter:
    if mode == "enabled" and config is None:
        config = _config(B=10.0)
    settings = DSparkHedgeSettings(
        mode=mode,
        config=config,
        trace_capacity=trace_capacity,
    )
    return DSparkHedgeAdapter(
        settings=settings,
        gamma=5,
        verify_num_draft_tokens=6,
        device="cpu",
    )


def _full_logits(
    *,
    top_tokens: list[list[int]],
    draft_tokens: list[list[int]],
    regrets: list[list[float]],
    vocab_size: int = 32,
) -> torch.Tensor:
    """Build full-vocab rows whose first five scores have exact regrets."""

    rows = []
    for row_top, row_draft, row_regret in zip(
        top_tokens, draft_tokens, regrets
    ):
        if len(row_top) != 6 or len(row_draft) != 5 or len(row_regret) != 5:
            raise ValueError("fixture requires width-six target and width-five draft")
        for position, top_token in enumerate(row_top):
            logits = torch.full((vocab_size,), -100.0, dtype=torch.float32)
            logits[top_token] = 10.0
            if position < 5:
                draft_token = row_draft[position]
                regret = row_regret[position]
                if draft_token != top_token:
                    logits[draft_token] = 10.0 - regret
            rows.append(logits)
    return torch.stack(rows)


def _accept(
    adapter: DSparkHedgeAdapter,
    *,
    candidates: torch.Tensor,
    logits: torch.Tensor,
    slots: list[int],
    cutoff: list[int] | None = None,
    forward_ct: int = 1,
    native_accept=None,
):
    if native_accept is None:
        native_accept = lambda: (_ for _ in ()).throw(
            AssertionError("enabled HEDGE must not call native acceptance")
        )
    return adapter.accept_or_native(
        candidates=candidates,
        target_logits=logits,
        cutoff_verify_lens=(
            None if cutoff is None else torch.tensor(cutoff, dtype=torch.int64)
        ),
        req_pool_indices=torch.tensor(slots, dtype=torch.int64),
        forward_ct=forward_ct,
        all_greedy=True,
        native_accept=native_accept,
    )


class SettingsAndNativePathTests(unittest.TestCase):
    def test_disabled_mode_does_not_parse_or_require_config(self) -> None:
        settings = DSparkHedgeSettings.from_environ(
            {
                "HEDGE_ENABLED": "0",
            }
        )
        self.assertEqual(settings.mode, "disabled")
        self.assertIsNone(settings.config)

    def test_external_arm_switches_are_strict_and_conflict_checked(self) -> None:
        with self.assertRaisesRegex(ValueError, "internal HEDGE mode"):
            DSparkHedgeSettings(mode="mystery")
        with self.assertRaisesRegex(ValueError, "exactly 0 or 1"):
            DSparkHedgeSettings.from_environ({"HEDGE_ENABLED": "true"})
        with self.assertRaisesRegex(ValueError, "conflicts"):
            DSparkHedgeSettings.from_environ(
                {
                    "HEDGE_ENABLED": "1",
                    "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": "1",
                }
            )
        with self.assertRaisesRegex(ValueError, "not an experiment arm switch"):
            DSparkHedgeSettings.from_environ(
                {"SGLANG_DSPARK_HEDGE_MODE": "enabled"}
            )
        with self.assertRaisesRegex(ValueError, "invalid"):
            DSparkHedgeSettings.from_environ(
                {
                    "HEDGE_ENABLED": "0",
                    "SGLANG_DSPARK_HEDGE_CONFIG_JSON": "{}",
                }
            )
        calibration = DSparkHedgeSettings.from_environ(
            {
                "HEDGE_ENABLED": "0",
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": "1",
                "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY": "123",
            }
        )
        self.assertEqual(calibration.mode, "calibration")
        self.assertEqual(calibration.trace_capacity, 123)
        enabled = DSparkHedgeSettings.from_environ(
            {
                "HEDGE_ENABLED": "1",
                "SGLANG_DSPARK_HEDGE_CONFIG_JSON": (
                    '{"B":0.0,"g":100.0,"m":5,'
                    '"value_scheme":"normalized_suffix","block_size":5}'
                ),
            }
        )
        self.assertEqual(enabled.mode, "enabled")
        self.assertEqual(enabled.config.B, 0.0)

    def test_disabled_path_is_exact_native_call_through(self) -> None:
        adapter = _adapter(mode="disabled", config=None)
        expected = (
            torch.tensor([2], dtype=torch.int32),
            torch.tensor([17], dtype=torch.int64),
            torch.tensor([0], dtype=torch.int32),
        )
        calls = 0

        def native():
            nonlocal calls
            calls += 1
            return expected

        actual = adapter.accept_or_native(
            candidates=None,
            target_logits=None,
            cutoff_verify_lens=None,
            req_pool_indices=None,
            forward_ct=0,
            all_greedy=False,
            native_accept=native,
        )
        self.assertIs(actual, expected)
        self.assertEqual(calls, 1)
        self.assertEqual(adapter.snapshot()["proposals"], 0)

    def test_verify_executor_uses_native_accept_directly_when_adapter_is_none(
        self,
    ) -> None:
        executor = TargetVerifyExecutor(
            target_worker=None,
            gamma=5,
            verify_num_draft_tokens=6,
            model_runner=None,
            kv_injector=None,
        )
        native_tuple = (
            torch.tensor([2], dtype=torch.int32),
            torch.tensor([19], dtype=torch.int64),
            torch.tensor([0], dtype=torch.int32),
        )
        draft_tokens = torch.tensor([[1, 2, 3, 4, 5]])
        draft_block = DraftBlockResult(
            draft_tokens=draft_tokens,
            corrected_logits=None,
            greedy_mask=torch.tensor([True]),
            temperatures=torch.tensor([1.0]),
        )
        with patch(
            "sglang.srt.speculative.dspark_components.dspark_verify."
            "accept_draft_tokens",
            return_value=native_tuple,
        ) as native:
            result = executor.accept_and_finalize(
                folded_accept=False,
                bs=1,
                verify_ids_2d=torch.tensor([[99, 1, 2, 3, 4, 5]]),
                target_logits=torch.zeros((6, 32)),
                draft_block=draft_block,
                sampling_info=None,
                draft_input=None,
                layout=None,
                prefix_lens=torch.tensor([10]),
                draft_tokens=draft_tokens,
                hedge_adapter=None,
            )
        native.assert_called_once()
        self.assertEqual(result.correct_len.tolist(), [2])
        self.assertEqual(result.commit_lens.tolist(), [3])
        self.assertEqual(result.out_tokens[0, :3].tolist(), [1, 2, 19])

    def test_active_mode_fails_loudly_outside_frozen_runtime(self) -> None:
        adapter = _adapter()
        with self.assertRaisesRegex(ValueError, "CUDA graph"):
            adapter.require_supported_runtime(
                disable_cuda_graph=False,
                disable_overlap_schedule=True,
                ragged_verify_mode="static",
                simulate_accept_length=0.0,
            )
        with self.assertRaisesRegex(ValueError, "requires 'static'"):
            adapter.require_supported_runtime(
                disable_cuda_graph=True,
                disable_overlap_schedule=True,
                ragged_verify_mode="cap",
                simulate_accept_length=0.0,
            )

    def test_active_mode_rejects_sampling(self) -> None:
        adapter = _adapter()
        adapter.bind_batch(_batch(("r", 1)))
        candidates = torch.tensor([[9, 1, 2, 3, 4, 5]])
        logits = _full_logits(
            top_tokens=[[1, 2, 3, 4, 5, 6]],
            draft_tokens=[[1, 2, 3, 4, 5]],
            regrets=[[0, 0, 0, 0, 0]],
        )
        with self.assertRaisesRegex(ValueError, "greedy"):
            adapter.accept_or_native(
                candidates=candidates,
                target_logits=logits,
                cutoff_verify_lens=None,
                req_pool_indices=torch.tensor([1]),
                forward_ct=1,
                all_greedy=False,
                native_accept=lambda: None,
            )


class AcceptanceAlignmentTests(unittest.TestCase):
    def test_compact_gather_matches_full_vocab_reference(self) -> None:
        config = _config(B=3.0, g=5.0, m=1)
        adapter = _adapter(config=config)
        adapter.bind_batch(_batch(("r0", 1), ("r1", 2)))
        draft = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        top = [[1, 11, 3, 4, 5, 12], [6, 7, 8, 13, 10, 14]]
        regret = [[0, 1, 0, 0, 0], [0, 0, 0, 2, 0]]
        candidates = torch.tensor([[99, *draft[0]], [98, *draft[1]]])
        logits = _full_logits(
            top_tokens=top, draft_tokens=draft, regrets=regret
        )

        correct_len, bonus, trim = _accept(
            adapter,
            candidates=candidates,
            logits=logits,
            slots=[1, 2],
        )

        expected_len = []
        expected_bonus = []
        for row in range(2):
            logits_3d = logits.view(2, 6, -1)
            top_logits, top_ids = logits_3d[row, :5].max(dim=-1)
            draft_logits = logits_3d[row, :5].gather(
                1, torch.tensor(draft[row]).unsqueeze(1)
            ).squeeze(1)
            state = RequestRiskState(total_budget=config.B)
            decision = choose_prefix(
                draft_token_ids=draft[row],
                scores=TokenScores(
                    top_logits=tuple(float(v) for v in top_logits),
                    top_token_ids=tuple(int(v) for v in top_ids),
                    draft_logits=tuple(float(v) for v in draft_logits),
                ),
                state=state,
                config=config,
            )
            expected_len.append(decision.accepted_tokens)
            full_top_ids = logits_3d[row].argmax(dim=-1)
            expected_bonus.append(
                int(full_top_ids[decision.accepted_tokens])
            )
        self.assertEqual(correct_len.tolist(), expected_len)
        self.assertEqual(bonus.tolist(), expected_bonus)
        self.assertEqual(trim.tolist(), [0, 0])

    def test_b0_rejects_zero_regret_argmax_tie(self) -> None:
        adapter = _adapter(config=_config(B=0.0, g=100.0, m=5))
        adapter.bind_batch(_batch(("tie", 1)))
        draft = [[7, 2, 3, 4, 5]]
        # Token 1 and draft token 7 tie at 10; torch argmax chooses token 1.
        logits = _full_logits(
            top_tokens=[[1, 2, 3, 4, 5, 6]],
            draft_tokens=draft,
            regrets=[[0, 0, 0, 0, 0]],
        )
        correct_len, bonus, _ = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=logits,
            slots=[1],
        )
        self.assertEqual(correct_len.tolist(), [0])
        self.assertEqual(bonus.tolist(), [1])
        self.assertEqual(adapter.snapshot()["regret_charged"], 0.0)

    def test_bonus_comes_from_final_accepted_position(self) -> None:
        adapter = _adapter(config=_config(B=2.0, g=10.0, m=1))
        adapter.bind_batch(_batch(("bonus", 1)))
        draft = [[1, 2, 3, 4, 5]]
        logits = _full_logits(
            top_tokens=[[1, 9, 3, 4, 5, 17]],
            draft_tokens=draft,
            regrets=[[0, 1, 0, 0, 0]],
        )
        correct_len, bonus, _ = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=logits,
            slots=[1],
        )
        self.assertEqual(correct_len.tolist(), [5])
        self.assertEqual(bonus.tolist(), [17])

    def test_cutoff_precedes_budget_charge_and_trim_is_hedge_uncapped(self) -> None:
        adapter = _adapter(config=_config(B=2.0, g=10.0, m=1))
        adapter.bind_batch(_batch(("cutoff", 1)))
        draft = [[1, 2, 3, 4, 5]]
        logits = _full_logits(
            top_tokens=[[1, 2, 9, 4, 5, 16]],
            draft_tokens=draft,
            regrets=[[0, 0, 1, 0, 0]],
        )
        correct_len, _, trim = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=logits,
            slots=[1],
            cutoff=[3],
        )
        self.assertEqual(correct_len.tolist(), [2])
        # Uncapped HEDGE accepted all five; verify window commits only two.
        self.assertEqual(trim.tolist(), [3])
        snapshot = adapter.snapshot()
        self.assertEqual(snapshot["regret_charged"], 0.0)
        self.assertEqual(
            snapshot["remaining_budget_by_request"][0]["remaining_budget"],
            2.0,
        )


class RequestLifecycleTests(unittest.TestCase):
    def test_batch_reorder_indexes_budget_by_stable_pool_slot(self) -> None:
        adapter = _adapter(config=_config(B=2.0, g=2.0, m=1))
        adapter.bind_batch(_batch(("r1", 1), ("r2", 2)))
        draft = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        first_logits = _full_logits(
            top_tokens=[[11, 2, 3, 4, 5, 20], [6, 7, 8, 9, 10, 21]],
            draft_tokens=draft,
            regrets=[[1, 0, 0, 0, 0], [0, 0, 0, 0, 0]],
        )
        first, _, _ = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]], [98, *draft[1]]]),
            logits=first_logits,
            slots=[1, 2],
        )
        self.assertEqual(first.tolist(), [5, 5])

        reordered_draft = [draft[1], draft[0]]
        second_logits = _full_logits(
            top_tokens=[[12, 7, 8, 9, 10, 22], [13, 2, 3, 4, 5, 23]],
            draft_tokens=reordered_draft,
            regrets=[[2, 0, 0, 0, 0], [2, 0, 0, 0, 0]],
        )
        second, _, _ = _accept(
            adapter,
            candidates=torch.tensor(
                [[98, *reordered_draft[0]], [99, *reordered_draft[1]]]
            ),
            logits=second_logits,
            slots=[2, 1],
        )
        self.assertEqual(second.tolist(), [5, 0])
        remaining = {
            item["rid"]: item["remaining_budget"]
            for item in adapter.snapshot()["remaining_budget_by_request"]
        }
        self.assertEqual(remaining, {"r1": 1.0, "r2": 0.0})

    def test_abort_finish_and_slot_reuse_do_not_leak_budget(self) -> None:
        adapter = _adapter(config=_config(B=2.0, g=2.0, m=1))
        draft = [[1, 2, 3, 4, 5]]
        spend_one = _full_logits(
            top_tokens=[[11, 2, 3, 4, 5, 20]],
            draft_tokens=draft,
            regrets=[[1, 0, 0, 0, 0]],
        )
        adapter.bind_batch(_batch(("old", 1)))
        _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=spend_one,
            slots=[1],
        )
        adapter.note_request_finished(rid="old", natural_stop=False)
        finished = adapter.snapshot()
        self.assertEqual(finished["active_request_states"], 0)
        self.assertEqual(finished["requests_finished"], 1)
        self.assertEqual(finished["requests_non_natural"], 1)

        adapter.bind_batch(_batch(("new", 1)))
        spend_two = _full_logits(
            top_tokens=[[12, 2, 3, 4, 5, 21]],
            draft_tokens=draft,
            regrets=[[2, 0, 0, 0, 0]],
        )
        correct_len, _, _ = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=spend_two,
            slots=[1],
        )
        self.assertEqual(correct_len.tolist(), [5])

        # Also cover defensive reuse when a finish hook was skipped.
        adapter.bind_batch(_batch(("stale", 2)))
        adapter.bind_batch(_batch(("replacement", 2)))
        self.assertEqual(adapter.snapshot()["slot_reuse_resets"], 1)

    def test_unbound_decode_fails_instead_of_inheriting_slot_state(self) -> None:
        adapter = _adapter()
        candidates = torch.tensor([[99, 1, 2, 3, 4, 5]])
        logits = _full_logits(
            top_tokens=[[1, 2, 3, 4, 5, 6]],
            draft_tokens=[[1, 2, 3, 4, 5]],
            regrets=[[0, 0, 0, 0, 0]],
        )
        with self.assertRaisesRegex(RuntimeError, "before prefill"):
            _accept(
                adapter,
                candidates=candidates,
                logits=logits,
                slots=[1],
            )


class CalibrationTraceTests(unittest.TestCase):
    def test_trace_is_native_and_excludes_cutoff_only_barriers(self) -> None:
        adapter = _adapter(mode="calibration", config=None)
        adapter.bind_batch(_batch(("cal", 1)))
        draft = [[1, 2, 3, 4, 5]]
        logits = _full_logits(
            top_tokens=[[1, 9, 3, 4, 5, 16]],
            draft_tokens=draft,
            regrets=[[0, 1, 0, 0, 0]],
        )
        expected = (
            torch.tensor([1], dtype=torch.int32),
            torch.tensor([9], dtype=torch.int64),
            torch.tensor([0], dtype=torch.int32),
        )
        calls = 0

        def native():
            nonlocal calls
            calls += 1
            return expected

        excluded = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=logits,
            slots=[1],
            cutoff=[2],
            native_accept=native,
        )
        included = _accept(
            adapter,
            candidates=torch.tensor([[99, *draft[0]]]),
            logits=logits,
            slots=[1],
            cutoff=[6],
            forward_ct=2,
            native_accept=native,
        )
        self.assertIs(excluded, expected)
        self.assertIs(included, expected)
        self.assertEqual(calls, 2)
        snapshot = adapter.snapshot()
        self.assertEqual(snapshot["trace_rows_seen"], 2)
        self.assertEqual(len(snapshot["strict_rejection_trace"]), 1)
        trace = snapshot["strict_rejection_trace"][0]
        self.assertEqual(trace["rid"], "cal")
        self.assertEqual(trace["barrier_position"], 1)
        self.assertEqual(trace["regret_per_value"], 1.25)

    def test_trace_overflow_uses_sentinel_without_overwriting_retained_rows(
        self,
    ) -> None:
        adapter = _adapter(
            mode="calibration", config=None, trace_capacity=2
        )
        adapter.bind_batch(_batch(("cal", 1)))
        draft = [1, 2, 3, 4, 5]
        candidates = torch.tensor([[99, *draft]])
        expected = (
            torch.tensor([0], dtype=torch.int32),
            torch.tensor([9], dtype=torch.int64),
            torch.tensor([0], dtype=torch.int32),
        )
        fixtures = (
            ([9, 2, 3, 4, 5, 6], [1, 0, 0, 0, 0]),
            ([1, 9, 3, 4, 5, 6], [0, 2, 0, 0, 0]),
            ([1, 2, 9, 4, 5, 6], [0, 0, 3, 0, 0]),
            ([1, 2, 3, 9, 5, 6], [0, 0, 0, 4, 0]),
        )
        for forward_ct, (top_tokens, regrets) in enumerate(fixtures, start=1):
            _accept(
                adapter,
                candidates=candidates,
                logits=_full_logits(
                    top_tokens=[top_tokens],
                    draft_tokens=[draft],
                    regrets=[regrets],
                ),
                slots=[1],
                forward_ct=forward_ct,
                native_accept=lambda: expected,
            )

        snapshot = adapter.snapshot()
        self.assertEqual(snapshot["trace_rows_seen"], 4)
        self.assertEqual(snapshot["trace_rows_dropped"], 2)
        retained = snapshot["strict_rejection_trace"]
        self.assertEqual(
            [row["proposal_ordinal"] for row in retained], [0, 1]
        )
        self.assertEqual([row["forward_ct"] for row in retained], [1, 2])
        self.assertEqual([row["barrier_position"] for row in retained], [0, 1])
        self.assertEqual([row["regret"] for row in retained], [1.0, 2.0])


class DownstreamPropagationTests(unittest.TestCase):
    def _executor_result(self):
        adapter = _adapter(config=_config(B=2.0, g=10.0, m=1))
        adapter.bind_batch(_batch(("propagate", 1)))
        draft_tokens = torch.tensor([[1, 2, 3, 4, 5]], dtype=torch.int64)
        candidates = torch.tensor([[99, 1, 2, 3, 4, 5]], dtype=torch.int64)
        logits = _full_logits(
            top_tokens=[[1, 9, 3, 4, 5, 17]],
            draft_tokens=draft_tokens.tolist(),
            regrets=[[0, 1, 0, 0, 0]],
        )
        executor = TargetVerifyExecutor(
            target_worker=None,
            gamma=5,
            verify_num_draft_tokens=6,
            model_runner=None,
            kv_injector=None,
        )
        draft_block = DraftBlockResult(
            draft_tokens=draft_tokens,
            corrected_logits=None,
            greedy_mask=torch.tensor([True]),
            temperatures=torch.tensor([1.0]),
        )
        result = executor.accept_and_finalize(
            folded_accept=False,
            bs=1,
            verify_ids_2d=candidates,
            target_logits=logits,
            draft_block=draft_block,
            sampling_info=None,
            draft_input=None,
            layout=None,
            prefix_lens=torch.tensor([10], dtype=torch.int64),
            draft_tokens=draft_tokens,
            hedge_adapter=adapter,
            req_pool_indices=torch.tensor([1], dtype=torch.int64),
            forward_ct=4,
        )
        return adapter, result

    def test_one_accepted_length_drives_finalize_tokens_bonus_and_stats(self) -> None:
        adapter, result = self._executor_result()
        self.assertEqual(result.correct_len.tolist(), [5])
        self.assertEqual(result.commit_lens.tolist(), [6])
        self.assertEqual(result.new_seq_lens.tolist(), [16])
        self.assertEqual(result.bonus.tolist(), [17])
        self.assertEqual(result.out_tokens.tolist(), [[1, 2, 3, 4, 5, 17]])
        counters = adapter.snapshot()
        self.assertEqual(counters["hedge_accepted_draft_tokens"], 5)
        self.assertEqual(counters["relaxed_mismatches"], 1)

    def test_counter_only_but_ignored_length_is_detected(self) -> None:
        """Negative fixture: changing counters without state propagation fails."""

        adapter, result = self._executor_result()
        counters = adapter.snapshot()
        deliberately_ignored_length = torch.tensor([1], dtype=torch.int32)
        with self.assertRaises(AssertionError):
            self.assertEqual(
                deliberately_ignored_length.tolist(),
                result.correct_len.tolist(),
                "a counter-only adapter must not pass the propagation contract",
            )
        self.assertEqual(counters["hedge_accepted_draft_tokens"], 5)

    def test_worker_wires_authoritative_acceptance_to_every_downstream_seam(
        self,
    ) -> None:
        worker_source = (
            SGLANG_PYTHON
            / "sglang/srt/speculative/dspark_components/dspark_worker_v2.py"
        ).read_text(encoding="utf-8")
        required_wiring = (
            "commit_lens=accept.commit_lens",
            "correct_len=accept.correct_len",
            "cap_trim_lens=accept.cap_trim_lens",
            "bonus=accept.bonus",
            "bonus_tokens=accept.bonus",
            "next_token_ids=accept.out_tokens.reshape(-1)",
            "accept_lens=accept.commit_lens",
            "new_seq_lens=accept.new_seq_lens",
        )
        for wiring in required_wiring:
            self.assertIn(wiring, worker_source)
        self.assertIn(
            "self._hedge_adapter if self._hedge_adapter.active else None",
            worker_source,
        )
        self.assertIn(
            "self._hedge_adapter.note_request_finished(",
            worker_source,
        )


class OutputTokenAndStaticGateTests(unittest.TestCase):
    def test_nonstreaming_meta_returns_real_output_ids_and_checks_length(self) -> None:
        ret_item = {
            "output_ids": [4, 8, 15, 16, 23, 42],
            "meta_info": {"completion_tokens": 6, "id": "r"},
        }
        actual = _meta_info_with_output_token_ids(ret_item)
        self.assertEqual(actual["output_token_ids"], ret_item["output_ids"])
        self.assertIsNot(actual, ret_item["meta_info"])
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            _meta_info_with_output_token_ids(
                {
                    "output_ids": [1],
                    "meta_info": {"completion_tokens": 2},
                }
            )

    def test_output_token_seam_never_retokenizes(self) -> None:
        source = inspect.getsource(_meta_info_with_output_token_ids)
        self.assertNotIn("tokenizer", source)
        self.assertNotIn("encode(", source)
        self.assertIn('ret_item["output_ids"]', source)

    def test_hot_acceptance_methods_have_no_item_cpu_or_file_io(self) -> None:
        methods = (
            DSparkHedgeAdapter._compact_scores,
            DSparkHedgeAdapter._strict_uncapped,
            DSparkHedgeAdapter._max_verifiable_drafts,
            DSparkHedgeAdapter._record_calibration,
            DSparkHedgeAdapter.accept_or_native,
        )
        forbidden_attrs = {"item", "cpu", "numpy", "tolist", "write_text", "open"}
        for method in methods:
            tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
            attributes = {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            calls = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
            }
            self.assertFalse(
                attributes & forbidden_attrs,
                f"{method.__name__} uses forbidden hot-path attributes",
            )
            self.assertNotIn("open", calls)

    def test_adapter_uses_existing_full_vocab_seam_without_collective(self) -> None:
        source = inspect.getsource(DSparkHedgeAdapter)
        self.assertIn("LogitsProcessor TP all-gather", source)
        self.assertNotIn("all_reduce", source)
        self.assertNotIn("all_gather(", source)


if __name__ == "__main__":
    unittest.main()
