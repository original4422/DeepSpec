from __future__ import annotations

import hashlib
import importlib.util
import unittest
import json
from pathlib import Path
import subprocess
import tempfile

from deepspec.hedge_eagle3_phase01b.tools import (
    Eagle3TraceControl,
    SequentialOpenAIRunner,
    TransportFailure,
    build_resolved_config,
    extract_eagle3_proposal_trace,
    formal_timing_bounds,
    summarize_run,
)

ROOT = Path(__file__).resolve().parents[1]
FINALIZER_SPEC = importlib.util.spec_from_file_location(
    "hedge_eagle3_phase03_finalize_identity",
    ROOT / "scripts/hedge_eagle3_phase03_finalize_identity.py",
)
if FINALIZER_SPEC is None or FINALIZER_SPEC.loader is None:
    raise RuntimeError("cannot load Phase 03 identity finalizer")
finalizer = importlib.util.module_from_spec(FINALIZER_SPEC)
FINALIZER_SPEC.loader.exec_module(finalizer)


def proposal(
    *,
    sample_id: str = "req-0",
    proposal_id: int = 0,
) -> dict:
    return {
        "schema_version": 1,
        "mode": "b0",
        "proposal_id": proposal_id,
        "sample_id": sample_id,
        "request_serial": 1,
        "request_pool_slot": 2,
        "draft_token_ids": [10, 20, 30],
        "target_top_token_ids": [10, 21, 30],
        "target_top_logits": [8.0, 7.0, 6.0],
        "target_draft_token_logits": [8.0, 6.5, 6.0],
        "regrets": [0.0, 0.5, 0.0],
        "values": [1.0, 2.0 / 3.0, 1.0 / 3.0],
        "strict_accepted_drafts": 1,
        "hedge_accepted_drafts": 1,
        "commit_length": 2,
        "relaxed_mismatches": 0,
        "first_strict_rejection": {
            "position": 1,
            "regret": 0.5,
            "value": 2.0 / 3.0,
            "regret_over_value": 0.75,
        },
        "spent": 0.0,
        "remaining_before": 0.0,
        "remaining_after": 0.0,
    }


def server_info(
    *,
    sample_id: str = "req-0",
    dropped: int = 0,
) -> dict:
    return {
        "internal_states": [
            {
                "eagle3_hedge_info_record": {
                    "schema_version": 1,
                    "mode": "b0",
                    "proposal_width": 3,
                    "verify_width": 4,
                    "active_request_states": 0,
                    "trace_rows_seen": 1,
                    "trace_rows_dropped": dropped,
                    "trace": [proposal(sample_id=sample_id)],
                }
            }
        ]
    }


def response(*, request_id: str = "req-0") -> dict:
    return {
        "id": request_id,
        "choices": [
            {
                "message": {"role": "assistant", "content": "\\boxed{4}"},
                "meta_info": {
                    "id": request_id,
                    "completion_tokens": 2,
                    "output_token_logprobs": [
                        [-0.1, 22, "4"],
                        [-0.2, 1, "<eos>"],
                    ],
                    "output_token_logprobs_length": 2,
                },
            }
        ],
        "usage": {"completion_tokens": 2},
    }


def sample() -> dict:
    return {
        "partition": "calibration",
        "partition_index": 0,
        "source_index": 17,
        "answer": "#### 4",
        "request_messages": [{"role": "user", "content": "question"}],
    }


def write_pending_finalize_fixture(root: Path) -> tuple[Path, ...]:
    placeholder = finalizer.PLACEHOLDER
    contents = {
        Path("deepspec/hedge_eagle3_phase01b/tools.py"): (
            f'final_commit = "{placeholder}"\n'
        ),
        finalizer.PATCH_DIR / "README.md": (
            "# Final source\n\n"
            f"- SGLang final commit: `{placeholder}`\n\n"
            "`manifest.json` records every changed file, the uv lock identity, "
            "and the\nclean-base replay evidence. Before the main Agent commits "
            "the exact candidate,\nthe final SHA field and status remain "
            "pending. The Phase 03 identity finalizer\nverifies the committed "
            "tree, replaces the unique placeholder above, and marks\nthe "
            "status frozen before Phase 04.\n\n"
            "After committing the exact SGLang candidate:\n\n"
            "```bash\nfinalize --sglang-final-sha <sha>\n```\n\n"
            "Replay:\n\nfixture\n"
        ),
        finalizer.PATCH_DIR / "phase-03-handoff.md": (
            "# Handoff\n\n"
            "`FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT`\n\n"
            f"SGLang final commit: `{placeholder}`\n\n"
            "## Main-Agent completion required\n\n"
            "Before Phase 04:\n\n1. Commit and finalize.\n\n"
            "Until those steps complete, Phase 03 is a verified final "
            "candidate, not a\nfrozen final SGLang source.\n"
        ),
        Path("docs/experiment/hedge-deepseek-v4-flash-eagle3.md"): (
            "# Experiment\n\n"
            "> **状态："
            "`PHASE_03_FINAL_CANDIDATE_PASS_PENDING_MAIN_SOURCE_COMMIT`。**\n"
            "> clean fixed-base replay 与联合回归均 PASS。由于 phase executor 不提交，\n"
            f"> `sglang_final_sha` 为 `{placeholder}`，仍待主 Agent\n"
            "> 对这份精确候选 commit 后由 finalizer 回填；该动作完成前\n"
            "> 不得进入 Phase 04。\n\n"
            "结论。operational keepalive 未被暂停或替换。manifest 状态为\n"
            "`FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT`；主 Agent 必须先提交精确 SGLang\n"
            "candidate、回填 `sglang_final_sha` 并把 marker 标为 frozen，再验收进入 Phase 04。\n\n"
            "| result |\n| --- |\n"
            "| FINAL CANDIDATE PASS；final source commit pending main Agent |\n\n"
            "## 下一步\n\n必须先提交再进入 Phase 04。\n"
        ),
        Path("docs/progress/hedge-deepseek-v4-flash-eagle3.md"): (
            "# Progress\n\n"
            "> 当前状态："
            "`PHASE_03_EXECUTOR_COMPLETE_PENDING_MAIN_SOURCE_COMMIT`\n\n"
            f"| executor 不 commit，final SHA `{placeholder}`；等待主 Agent提交精确 "
            "candidate、运行 identity finalizer 并提交/push DeepSpec，验收后才可派 Phase 04 |\n"
        ),
    }
    for relative, content in contents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest_path = root / finalizer.PATCH_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT",
                "sglang_final_sha": placeholder,
                "sglang_final_sha_status": "PENDING_MAIN_AGENT_COMMIT",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    regression_path = (
        root / finalizer.PATCH_DIR / "regression-summary.json"
    )
    regression_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "sglang_final_sha": placeholder,
                "sglang_final_sha_status": "PENDING_MAIN_AGENT_COMMIT",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return (
        *finalizer.PLAIN_FILES,
        finalizer.PATCH_DIR / "manifest.json",
        finalizer.PATCH_DIR / "regression-summary.json",
    )


class TraceExtractionTest(unittest.TestCase):
    def test_extracts_one_request_and_first_strict_barriers(self) -> None:
        result = extract_eagle3_proposal_trace(
            server_info(),
            expected_sample_id="req-0",
        )

        self.assertEqual(result["sample_id"], "req-0")
        self.assertEqual(result["mode"], "b0")
        self.assertEqual(len(result["proposal_trace"]), 1)
        self.assertEqual(
            result["strict_rejection_barriers"],
            [
                {
                    "sample_id": "req-0",
                    "proposal_id": 0,
                    "position": 1,
                    "regret": 0.5,
                    "value": 2.0 / 3.0,
                    "regret_over_value": 0.75,
                }
            ],
        )

    def test_mismatched_request_or_dropped_trace_fails_closed(self) -> None:
        with self.assertRaisesRegex(TransportFailure, "sample_id"):
            extract_eagle3_proposal_trace(
                server_info(sample_id="other"),
                expected_sample_id="req-0",
            )
        with self.assertRaisesRegex(TransportFailure, "dropped"):
            extract_eagle3_proposal_trace(
                server_info(dropped=1),
                expected_sample_id="req-0",
            )

    def test_mixed_foreign_and_current_rows_selects_only_response_id(self) -> None:
        payload = server_info()
        envelope = payload["internal_states"][0][
            "eagle3_hedge_info_record"
        ]
        envelope["trace_rows_seen"] = 2
        envelope["trace"] = [
            proposal(sample_id="old-request", proposal_id=0),
            proposal(sample_id="req-0", proposal_id=1),
        ]

        result = extract_eagle3_proposal_trace(
            payload,
            expected_sample_id="req-0",
            expected_mode="b0",
        )

        self.assertEqual(
            [row["sample_id"] for row in result["proposal_trace"]],
            ["req-0"],
        )
        self.assertEqual(result["foreign_trace_row_count"], 1)
        self.assertEqual(result["foreign_sample_ids"], ["old-request"])

    def test_trace_envelope_requires_one_dp_fixed_shape_mode_and_cleanup(self):
        cases = []
        two_dp = server_info()
        two_dp["internal_states"].append({})
        cases.append((two_dp, "one DP"))
        bad_mode = server_info()
        bad_mode["internal_states"][0]["eagle3_hedge_info_record"][
            "mode"
        ] = "other"
        cases.append((bad_mode, "mode"))
        bad_width = server_info()
        bad_width["internal_states"][0]["eagle3_hedge_info_record"][
            "proposal_width"
        ] = 4
        cases.append((bad_width, "proposal_width"))
        active = server_info()
        active["internal_states"][0]["eagle3_hedge_info_record"][
            "active_request_states"
        ] = 1
        cases.append((active, "not cleaned"))
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(TransportFailure, message):
                    extract_eagle3_proposal_trace(
                        payload,
                        expected_sample_id="req-0",
                        expected_mode="b0",
                    )


class FakeTraceControl:
    def __init__(self, *, drain_failures: int = 0) -> None:
        self.clear_calls = 0
        self.drain_calls = 0
        self.drain_failures = drain_failures

    def clear(self) -> None:
        self.clear_calls += 1

    def drain(self, *, expected_sample_id: str) -> dict:
        self.drain_calls += 1
        if self.drain_calls <= self.drain_failures:
            raise TransportFailure("transient trace read")
        return extract_eagle3_proposal_trace(
            server_info(sample_id=expected_sample_id),
            expected_sample_id=expected_sample_id,
        )


class RunnerTraceControlTest(unittest.TestCase):
    def _runner(self, *, transport, trace_control):
        ticks = iter(float(value) for value in range(100))
        return SequentialOpenAIRunner(
            endpoint="http://127.0.0.1:31001/v1/chat/completions",
            model="target",
            retry_delays_seconds=(0.0, 0.0),
            transport=transport,
            trace_control=trace_control,
            require_proposal_trace=True,
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
        )

    def test_trace_retry_does_not_reissue_successful_generation(self) -> None:
        model_calls = 0

        def transport(*_):
            nonlocal model_calls
            model_calls += 1
            return response()

        trace = FakeTraceControl(drain_failures=1)
        record = self._runner(
            transport=transport,
            trace_control=trace,
        )._execute(
            sample(),
            phase="calibration",
            position=0,
            timed=False,
        )

        self.assertEqual(model_calls, 1)
        self.assertEqual(trace.clear_calls, 1)
        self.assertEqual(trace.drain_calls, 2)
        self.assertEqual(record["terminal_status"], "success")
        self.assertEqual(record["trace_retry_count"], 1)
        self.assertEqual(len(record["proposal_trace"]), 1)
        self.assertEqual(len(record["strict_rejection_barriers"]), 1)

    def test_exhausted_trace_retry_fails_without_reissuing_generation(self) -> None:
        model_calls = 0

        def transport(*_):
            nonlocal model_calls
            model_calls += 1
            return response()

        trace = FakeTraceControl(drain_failures=3)
        record = self._runner(
            transport=transport,
            trace_control=trace,
        )._execute(
            sample(),
            phase="calibration",
            position=0,
            timed=False,
        )

        self.assertEqual(model_calls, 1)
        self.assertEqual(trace.clear_calls, 1)
        self.assertEqual(trace.drain_calls, 3)
        self.assertEqual(record["attempt_count"], 1)
        self.assertEqual(record["terminal_status"], "failure")
        self.assertEqual(record["generation_status"], "success")
        self.assertEqual(record["trace_status"], "failure")
        self.assertIn("trace", record["terminal_error"])
        self.assertEqual(record["proposal_trace"], [])
        self.assertEqual(record["full_response"]["id"], "req-0")
        self.assertEqual(record["output_token_ids"], [22, 1])
        self.assertEqual(record["attempts"][0]["status"], "success")
        self.assertTrue(record["answer_match"])
        summary = summarize_run(
            {"formal": [record], "formal_wall_seconds": 1.0}
        )
        self.assertEqual(summary["generation_retries"], 0)
        self.assertEqual(summary["trace_retries"], 2)
        self.assertEqual(summary["generation_successes"], 1)
        self.assertEqual(summary["generation_failures"], 0)
        self.assertEqual(summary["trace_failures"], 1)
        self.assertEqual(summary["successes"], 0)

    def test_api_retry_clears_again_before_the_second_generation(self) -> None:
        model_calls = 0

        def transport(*_):
            nonlocal model_calls
            model_calls += 1
            if model_calls == 1:
                raise TransportFailure("transient API failure")
            return response()

        trace = FakeTraceControl()
        record = self._runner(
            transport=transport,
            trace_control=trace,
        )._execute(
            sample(),
            phase="calibration",
            position=0,
            timed=False,
        )

        self.assertEqual(model_calls, 2)
        self.assertEqual(trace.clear_calls, 2)
        self.assertEqual(trace.drain_calls, 1)
        self.assertEqual(record["retry_count"], 1)
        self.assertEqual(record["terminal_status"], "success")

    def test_formal_timing_starts_at_first_generation_and_ends_after_drain(self):
        self.assertEqual(
            formal_timing_bounds(
                [
                    {
                        "first_request_monotonic_started": 10.0,
                        "record_terminal_monotonic": 15.0,
                    },
                    {
                        "first_request_monotonic_started": 16.0,
                        "record_terminal_monotonic": 23.0,
                    },
                ]
            ),
            (10.0, 23.0),
        )
        with self.assertRaisesRegex(RuntimeError, "never issued"):
            formal_timing_bounds(
                [
                    {
                        "first_request_monotonic_started": None,
                        "record_terminal_monotonic": 12.0,
                    }
                ]
            )


class ConcreteTraceControlTest(unittest.TestCase):
    def test_control_accepts_dp_bool_list_and_gets_server_info_object(self):
        calls = []

        def transport(method, url, body, timeout):
            calls.append((method, url, body, timeout))
            if method == "POST":
                return [True]
            return server_info()

        control = Eagle3TraceControl(
            base_url="http://127.0.0.1:31001/",
            expected_mode="b0",
            transport=transport,
        )
        control.clear()
        result = control.drain(expected_sample_id="req-0")

        self.assertEqual(result["sample_id"], "req-0")
        self.assertEqual(calls[0][0:2], (
            "POST",
            "http://127.0.0.1:31001/set_internal_state",
        ))
        self.assertEqual(calls[1][0:2], (
            "GET",
            "http://127.0.0.1:31001/server_info",
        ))

    def test_control_rejects_non_dp_list_clear_response(self):
        control = Eagle3TraceControl(
            base_url="http://127.0.0.1:31001",
            expected_mode="b0",
            transport=lambda *_: {"updated": True},
        )
        with self.assertRaisesRegex(TransportFailure, r"DP=1 \[true\]"):
            control.clear()


def leaf_differences(left, right, prefix=()):
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return {prefix + ("<keys>",)}
        result = set()
        for key in left:
            result.update(
                leaf_differences(
                    left[key],
                    right[key],
                    prefix + (key,),
                )
            )
        return result
    return set() if left == right else {prefix}


class ResolvedArmConfigTest(unittest.TestCase):
    def test_three_arms_differ_only_in_hedge_mode_and_budget(self):
        configs = {
            "native": build_resolved_config("native"),
            "B0": build_resolved_config("B0"),
            "B+": build_resolved_config("B+", gate=0.25),
        }
        native_b0 = leaf_differences(configs["native"], configs["B0"])
        b0_positive = leaf_differences(configs["B0"], configs["B+"])

        self.assertEqual(
            native_b0,
            {
                ("mode",),
                ("environment", "SGLANG_EAGLE3_HEDGE_MODE"),
                ("environment", "SGLANG_EAGLE3_HEDGE_CONFIG_JSON"),
                ("hedge", "enabled"),
                ("hedge", "risk_budget"),
                ("hedge", "gate"),
                ("config_sha256",),
            },
        )
        self.assertEqual(
            b0_positive,
            {
                ("mode",),
                ("environment", "SGLANG_EAGLE3_HEDGE_MODE"),
                ("environment", "SGLANG_EAGLE3_HEDGE_CONFIG_JSON"),
                ("hedge", "risk_budget"),
                ("hedge", "gate"),
                ("config_sha256",),
            },
        )
        for mode, expected_runtime_mode in (
            ("native", "disabled"),
            ("B0", "b0"),
            ("B+", "enabled"),
        ):
            with self.subTest(mode=mode):
                config = configs[mode]
                self.assertEqual(
                    config["environment"]["SGLANG_EAGLE3_HEDGE_MODE"],
                    expected_runtime_mode,
                )
                self.assertEqual(
                    config["environment"][
                        "SGLANG_EAGLE3_HEDGE_TRACE_CAPACITY"
                    ],
                    "1024",
                )
                self.assertTrue(
                    config["request"]["require_proposal_trace"]
                )
                self.assertEqual(
                    config["environment"]["SGLANG_RAGGED_VERIFY_MODE"],
                    "static",
                )
                self.assertEqual(
                    config["environment"]["SGLANG_EAGLE3_V4_AUX_TRACE"],
                    "1",
                )
                self.assertEqual(
                    config["server"]["mem_fraction_static"],
                    0.60,
                )
                final_commit = config["source"]["final_commit"]
                self.assertTrue(
                    final_commit == finalizer.PLACEHOLDER
                    or finalizer.SHA_RE.fullmatch(final_commit) is not None
                )
        self.assertIsNone(
            configs["native"]["environment"][
                "SGLANG_EAGLE3_HEDGE_CONFIG_JSON"
            ]
        )
        self.assertEqual(
            json.loads(
                configs["B0"]["environment"][
                    "SGLANG_EAGLE3_HEDGE_CONFIG_JSON"
                ]
            ),
            {
                "B": 0.0,
                "g": 0.0,
                "m": 1,
                "value_scheme": "normalized_suffix",
                "block_size": 3,
            },
        )


class PureCoreInjectionReplayTest(unittest.TestCase):
    def test_injects_fixed_core_into_a_clean_fixed_base_worktree(self):
        deepspec_root = Path(__file__).resolve().parents[1]
        live_sglang = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
        base = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
        with tempfile.TemporaryDirectory(
            prefix="deepspec-eagle3-phase03-replay-",
            dir="/tmp",
        ) as temporary:
            temporary_root = Path(temporary)
            clean_sglang = temporary_root / "sglang"
            manifest_path = temporary_root / "injection.json"
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(live_sglang),
                    "worktree",
                    "add",
                    "--detach",
                    str(clean_sglang),
                    base,
                ),
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            try:
                subprocess.run(
                    (
                        "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python",
                        str(
                            deepspec_root
                            / "scripts/hedge_eagle3_phase03_inject.py"
                        ),
                        "--deepspec-root",
                        str(deepspec_root),
                        "--sglang-root",
                        str(clean_sglang),
                        "--manifest",
                        str(manifest_path),
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(
                    manifest["hedge_source_sha"],
                    "9fb903d676254ea5f5d171051fb15c54f331111c",
                )
                self.assertEqual(
                    manifest["dspark_pure_core_publish_sha"],
                    "4d96f44065c07030ede67484a262006ec149626a",
                )
                self.assertEqual(
                    manifest["eagle3_pure_core_import_sha"],
                    "4cefd0a36ea254e4c14a83f35dc8db15b37a3384",
                )
                self.assertEqual(manifest["sglang_base"], base)
                self.assertEqual(manifest["sglang_head"], base)
                self.assertEqual(manifest["injected_file_count"], 4)
                self.assertEqual(
                    manifest["aggregate_sha256"],
                    "53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815",
                )
                for record in manifest["files"]:
                    self.assertEqual(
                        record["sha256"],
                        record["dspark_publish_sha256"],
                    )
                    self.assertEqual(
                        record["sha256"],
                        record["eagle3_import_sha256"],
                    )
            finally:
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(live_sglang),
                        "worktree",
                        "remove",
                        "--force",
                        str(clean_sglang),
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

    def test_final_candidate_manifest_keeps_all_provenance_distinct(self):
        root = Path(__file__).resolve().parents[1]
        patch_path = (
            root
            / "patches/hedge_eagle3_phase03/sglang-final-candidate.patch"
        )
        patch_payload = patch_path.read_bytes()
        manifest = json.loads(
            (
                root
                / "patches/hedge_eagle3_phase03/manifest.json"
            ).read_text()
        )
        self.assertEqual(
            manifest["hedge_source_sha"],
            "9fb903d676254ea5f5d171051fb15c54f331111c",
        )
        self.assertEqual(
            manifest["dspark_pure_core_publish_sha"],
            "4d96f44065c07030ede67484a262006ec149626a",
        )
        self.assertEqual(
            manifest["eagle3_pure_core_import_sha"],
            "4cefd0a36ea254e4c14a83f35dc8db15b37a3384",
        )
        self.assertEqual(
            manifest["sglang_base_sha"],
            "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
        )
        self.assertEqual(
            manifest["injection"]["aggregate_sha256"],
            "53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815",
        )
        self.assertEqual(
            manifest["sglang_candidate"]["patch_sha256"],
            manifest["clean_replay"]["patch_sha256_after_replay"],
        )
        self.assertEqual(
            hashlib.sha256(patch_payload).hexdigest(),
            "13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945",
        )
        self.assertEqual(
            [
                line_number
                for line_number, line in enumerate(
                    patch_payload.splitlines(),
                    start=1,
                )
                if line == b" "
            ],
            [
                7,
                8,
                33,
                37,
                48,
                49,
                67,
                77,
                92,
                111,
                316,
                321,
                326,
                414,
                460,
                462,
                466,
                1431,
                2053,
                2057,
            ],
        )
        diff_check = manifest["deepspec_staged_diff_check"]
        self.assertEqual(
            diff_check["status"],
            "PASS_WITH_CANONICAL_PATCH_EXCLUDED",
        )
        self.assertEqual(
            diff_check["excluded_path"],
            "patches/hedge_eagle3_phase03/sglang-final-candidate.patch",
        )
        self.assertEqual(diff_check["mechanical_warning_count"], 20)
        self.assertEqual(diff_check["excluded_diff_check"], "PASS")
        self.assertEqual(manifest["clean_replay"]["status"], "PASS")
        self.assertIn(
            manifest["sglang_final_sha_status"],
            {"PENDING_MAIN_AGENT_COMMIT", "FROZEN"},
        )
        if manifest["sglang_final_sha_status"] == "FROZEN":
            self.assertRegex(
                manifest["sglang_final_sha"],
                r"^[0-9a-f]{40}$",
            )
        else:
            self.assertEqual(
                manifest["sglang_final_sha"],
                finalizer.PLACEHOLDER,
            )


class FinalizeIdentityTest(unittest.TestCase):
    def test_pending_to_frozen_is_idempotent_for_the_same_sha(self):
        final_sha = "a" * 40
        with tempfile.TemporaryDirectory(
            prefix="deepspec-eagle3-phase03-finalize-",
            dir="/tmp",
        ) as temporary:
            target = Path(temporary)
            relative_files = write_pending_finalize_fixture(target)

            finalizer.finalize_repository_files(
                deepspec_root=target,
                final_sha=final_sha,
                finalized_at="2026-07-29T03:12:00Z",
            )
            first_frozen = {
                relative: (target / relative).read_bytes()
                for relative in relative_files
            }
            finalizer.finalize_repository_files(
                deepspec_root=target,
                final_sha=final_sha,
                finalized_at="2026-07-29T03:30:00Z",
            )
            second_frozen = {
                relative: (target / relative).read_bytes()
                for relative in relative_files
            }

            self.assertEqual(second_frozen, first_frozen)
            for relative in relative_files:
                text = (target / relative).read_text(encoding="utf-8")
                self.assertNotIn(finalizer.PLACEHOLDER, text)
                self.assertIn(final_sha, text)
            manifest = json.loads(
                (target / finalizer.PATCH_DIR / "manifest.json").read_text()
            )
            self.assertEqual(manifest["status"], "FINAL_CANDIDATE_FROZEN")
            self.assertEqual(manifest["sglang_final_sha_status"], "FROZEN")
            experiment = (
                target
                / "docs/experiment/hedge-deepseek-v4-flash-eagle3.md"
            ).read_text()
            self.assertNotIn("仍待主 Agent", experiment)
            self.assertNotIn("不得进入 Phase 04", experiment)
            self.assertNotIn("必须先提交精确 SGLang", experiment)
            self.assertNotIn("final source commit pending", experiment)
            self.assertIn("Phase 03 source freeze PASS", experiment)
            progress = (
                target
                / "docs/progress/hedge-deepseek-v4-flash-eagle3.md"
            ).read_text()
            self.assertNotIn("等待主 Agent提交精确 candidate", progress)
            self.assertIn("source gate frozen/PASS", progress)
            readme = (
                target / finalizer.PATCH_DIR / "README.md"
            ).read_text()
            self.assertNotIn(
                "Before the main Agent commits",
                readme,
            )
            self.assertNotIn(
                "After committing the exact SGLang candidate",
                readme,
            )
            handoff = (
                target
                / finalizer.PATCH_DIR
                / "phase-03-handoff.md"
            ).read_text()
            self.assertNotIn(
                "Main-Agent completion required",
                handoff,
            )
            self.assertNotIn("Until those steps complete", handoff)
            self.assertIn("Phase 03 source is frozen and PASS", handoff)

    def test_frozen_repository_rejects_malformed_or_different_sha(self):
        with self.assertRaisesRegex(ValueError, "40 lowercase hex"):
            finalizer.validate_sha("not-a-commit")
        with tempfile.TemporaryDirectory(
            prefix="deepspec-eagle3-phase03-finalize-reject-",
            dir="/tmp",
        ) as temporary:
            target = Path(temporary)
            relative_files = write_pending_finalize_fixture(target)
            finalizer.finalize_repository_files(
                deepspec_root=target,
                final_sha="a" * 40,
                finalized_at="2026-07-29T03:12:00Z",
            )
            frozen = {
                relative: (target / relative).read_bytes()
                for relative in relative_files
            }

            with self.assertRaisesRegex(
                RuntimeError,
                "another SGLang final SHA",
            ):
                finalizer.finalize_repository_files(
                    deepspec_root=target,
                    final_sha="b" * 40,
                    finalized_at="2026-07-29T03:30:00Z",
                )
            self.assertEqual(
                {
                    relative: (target / relative).read_bytes()
                    for relative in relative_files
                },
                frozen,
            )


if __name__ == "__main__":
    unittest.main()
