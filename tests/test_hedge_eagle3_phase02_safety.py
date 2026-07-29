"""Offline negative tests for the Phase 02 GPU lifecycle safety gates."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load_module(
    "hedge_eagle3_phase02_runtime",
    "scripts/hedge_eagle3_phase02_runtime.py",
)
resolver = load_module(
    "hedge_eagle3_phase02_resolve",
    "scripts/hedge_eagle3_phase02_resolve.py",
)
api = load_module(
    "hedge_eagle3_phase02_api",
    "scripts/hedge_eagle3_phase02_api.py",
)


def context(uuid: str) -> dict[str, object]:
    return {
        "gpu_uuid": uuid,
        "host_pid": 100,
        "process_name": "fixture",
        "used_gpu_memory_mib": 1,
    }


def flag_value(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return command[index + 1]


class Phase02SafetyTests(unittest.TestCase):
    def test_keepalive_argv_path_is_not_resolved_but_exe_is(self) -> None:
        self.assertEqual(
            str(runtime.EXPECTED_KEEPALIVE_PYTHON_ARGV),
            "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python",
        )
        self.assertEqual(
            str(runtime.EXPECTED_KEEPALIVE_EXECUTABLE),
            "/usr/bin/python3.11",
        )

    def test_exact_context_gate_accepts_one_per_assigned_uuid(self) -> None:
        rows = [context(uuid) for uuid in runtime.EXPECTED_UUIDS]
        self.assertTrue(runtime.exact_assigned_gpu_contexts(rows))

    def test_exact_context_gate_rejects_unknown_uuid(self) -> None:
        rows = [context(uuid) for uuid in runtime.EXPECTED_UUIDS[:-1]]
        rows.append(context("GPU-unknown"))
        self.assertFalse(runtime.exact_assigned_gpu_contexts(rows))

    def test_exact_context_gate_rejects_duplicate_assigned_uuid(self) -> None:
        rows = [context(uuid) for uuid in runtime.EXPECTED_UUIDS[:-1]]
        rows.append(context(runtime.EXPECTED_UUIDS[0]))
        self.assertFalse(runtime.exact_assigned_gpu_contexts(rows))

    def test_target_rejects_dirty_fixed_source(self) -> None:
        identity = {"worktree_status": [" M file.py"], "diff_bytes": 1}
        with self.assertRaisesRegex(RuntimeError, "clean fixed SGLang base"):
            resolver.assert_source_state("target", identity)

    @staticmethod
    def _reviewed_native_source_identity() -> dict:
        return {
            "worktree_status": [
                " M python/sglang/srt/arg_groups/deepseek_v4_hook.py",
                " M python/sglang/srt/models/deepseek_v4.py",
                (
                    "?? test/registered/unit/models/"
                    "test_deepseek_v4_eagle3_aux.py"
                ),
            ],
            "diff_bytes": 19_290,
            "diff_sha256": resolver.NATIVE_RUNTIME_PATCH_SHA256,
            "tracked_diff_files": list(
                resolver.NATIVE_RUNTIME_TRACKED_FILES
            ),
            "untracked_files": [resolver.NATIVE_SOURCE_TEST],
            "source_test_sha256": resolver.NATIVE_SOURCE_TEST_SHA256,
        }

    def test_native_requires_exact_reviewed_source_identity(self) -> None:
        resolver.assert_source_state(
            "native",
            self._reviewed_native_source_identity(),
        )

    def test_native_rejects_runtime_or_test_source_drift(self) -> None:
        changed_hash = self._reviewed_native_source_identity()
        changed_hash["diff_sha256"] = "0" * 64
        extra_runtime_file = self._reviewed_native_source_identity()
        extra_runtime_file["tracked_diff_files"].append("unexpected.py")
        changed_test = self._reviewed_native_source_identity()
        changed_test["source_test_sha256"] = "f" * 64
        cases = (
            (changed_hash, "reviewed runtime patch"),
            (extra_runtime_file, "tracked file set"),
            (changed_test, "source test identity"),
        )
        for identity, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    resolver.assert_source_state("native", identity)

    def test_only_native_enables_once_per_rank_aux_trace(self) -> None:
        self.assertEqual(
            resolver.environment("native")["SGLANG_EAGLE3_V4_AUX_TRACE"],
            "1",
        )
        self.assertNotIn(
            "SGLANG_EAGLE3_V4_AUX_TRACE",
            resolver.environment("target"),
        )

    def test_native_routes_only_llama_draft_to_flashinfer(self) -> None:
        config = json.loads(
            (resolver.DRAFT / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            config["architectures"],
            ["LlamaForCausalLMEagle3"],
        )
        self.assertEqual(config["model_type"], "llama")
        self.assertEqual(config["head_dim"], 128)

        from sglang.srt.model_executor.model_runner_components.attention_backend_setup import (
            _resolve_attention_backend_strs,
        )

        class Args:
            speculative_draft_attention_backend = "flashinfer"

            @staticmethod
            def get_attention_backends():
                return "dsv4", "dsv4"

        target = _resolve_attention_backend_strs(
            server_args=Args(),
            is_draft_worker=False,
        )
        draft = _resolve_attention_backend_strs(
            server_args=Args(),
            is_draft_worker=True,
        )
        self.assertEqual((target.prefill, target.decode), ("dsv4", "dsv4"))
        self.assertFalse(target.is_draft_override)
        self.assertEqual(
            (draft.prefill, draft.decode),
            ("flashinfer", "flashinfer"),
        )
        self.assertTrue(draft.is_draft_override)

        native_command = resolver.command("native")
        target_command = resolver.command("target")
        self.assertEqual(
            flag_value(
                native_command,
                "--speculative-draft-attention-backend",
            ),
            "flashinfer",
        )
        self.assertNotIn(
            "--speculative-draft-attention-backend",
            target_command,
        )
        resolved = resolver.resolve("native", "offline-draft-backend")
        self.assertEqual(
            resolved["attention_backends"],
            {
                "target": "dsv4",
                "draft": "flashinfer",
                "draft_override_only": True,
            },
        )

    def test_native_acceptance_trace_proves_three_token_proposals(self) -> None:
        trace = api.extract_native_acceptance_trace(
            {
                "choices": [
                    {
                        "meta_info": {
                            "spec_accept_length": 2.0,
                            "spec_accept_rate": 0.5,
                            "spec_correct_drafts_histogram": [0, 1, 1, 0],
                            "spec_num_correct_drafts": 3,
                            "spec_num_proposed_drafts": 6,
                            "spec_verify_ct": 2,
                        }
                    }
                ]
            },
            proposal_tokens=3,
        )
        self.assertEqual(trace["proposal_tokens"], 3)
        self.assertEqual(trace["internal_verify_width"], 4)
        self.assertEqual(trace["verify_count"], 2)
        self.assertEqual(trace["proposed_draft_tokens"], 6)
        self.assertEqual(trace["accepted_draft_tokens"], 3)

    def test_native_acceptance_histogram_normalizes_missing_tail_bins(
        self,
    ) -> None:
        histograms = (
            [2],
            [1, 2],
            [0, 1, 2],
            [0, 1, 1, 1],
        )
        for histogram in histograms:
            verify_count = sum(histogram)
            accepted = sum(
                index * count
                for index, count in enumerate(histogram)
            )
            with self.subTest(histogram=histogram):
                trace = api.extract_native_acceptance_trace(
                    {
                        "choices": [
                            {
                                "meta_info": {
                                    "spec_accept_length": 5.0,
                                    "spec_accept_rate": (
                                        accepted / (verify_count * 3)
                                    ),
                                    "spec_correct_drafts_histogram": histogram,
                                    "spec_num_correct_drafts": accepted,
                                    "spec_num_proposed_drafts": (
                                        verify_count * 3
                                    ),
                                    "spec_verify_ct": verify_count,
                                }
                            }
                        ]
                    },
                    proposal_tokens=3,
                )
                self.assertEqual(
                    trace["accepted_drafts_histogram"],
                    histogram + [0] * (4 - len(histogram)),
                )
                self.assertEqual(trace["acceptance_length"], 5.0)

        with self.assertRaisesRegex(
            RuntimeError,
            "valid acceptance histogram",
        ):
            api.extract_native_acceptance_trace(
                {
                    "choices": [
                        {
                            "meta_info": {
                                "spec_accept_length": 1.0,
                                "spec_accept_rate": 1.0,
                                "spec_correct_drafts_histogram": [
                                    0,
                                    0,
                                    0,
                                    1,
                                    0,
                                ],
                                "spec_num_correct_drafts": 3,
                                "spec_num_proposed_drafts": 3,
                                "spec_verify_ct": 1,
                            }
                        }
                    ]
                },
                proposal_tokens=3,
            )

    def test_worker_hostname_gate_rejects_another_host(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "worker hostname differs"):
            resolver.validate_worker_hostname("not-the-assigned-worker")

    def test_shell_requires_main_completion_and_nonzero_signals(self) -> None:
        shell = (ROOT / "scripts/hedge_eagle3_phase02_attempt.sh").read_text()
        self.assertIn("main_complete=0", shell)
        self.assertIn('if [ "${main_complete}" -ne 1 ]; then', shell)
        self.assertIn("main_complete=1", shell)
        self.assertIn("exit 130", shell)
        self.assertIn("exit 143", shell)

    def test_proc_start_ticks_is_a_positive_integer(self) -> None:
        self.assertGreater(runtime.proc_stat(os.getpid())["start_ticks"], 0)


if __name__ == "__main__":
    unittest.main()
