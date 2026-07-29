from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
import csv
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hedge_dspark_p06_prepare import (  # noqa: E402
    CALIBRATION_SHA256,
    FORMAL_SHA256,
    FROZEN_CONFIG_FINGERPRINT,
    P05_FREEZE_COMMIT,
    resolve_attempt,
    validate_formal_datasets,
)
from hedge_dspark_p06_client import (  # noqa: E402
    clear_native_formal_evidence,
    normalize_spec_acceptance,
    run_native_formal,
    validate_native_server_snapshot,
)
from deepspec.hedge_protocol.config import DATASET_REVISION, PROMPT_SUFFIX
from deepspec.hedge_protocol.io import load_jsonl
from hedge_dspark_p06_validate import (  # noqa: E402
    REQUIRED_ARTIFACTS,
    ensure_required_artifacts,
    validate_client_artifacts,
    validate_formal_gpu_window,
    validate_lifecycle_events,
    validate_resolved_contract,
)


def _sample(
    index: int, *, cohort: str, cohort_position: int
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cohort": cohort,
        "cohort_position": cohort_position,
        "dataset_index": index,
        "dataset_revision": DATASET_REVISION,
        "dataset_fingerprint": "fixture-fingerprint",
        "question": f"Question {index}?",
        "answer": f"fixture\n#### {index}",
        "reference_answer": str(index),
        "reference_answer_raw": str(index),
        "reference_extraction_rule": "last_hashes",
        "user_content": f"Question {index}?\n{PROMPT_SUFFIX}",
    }


def _acceptance() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "proposal_count": 1,
        "draft_tokens_proposed": 5,
        "accepted_draft_tokens": 2,
        "accepted_draft_tokens_by_position": [1, 1, 0, 0, 0],
        "acceptance_length_including_bonus_sum": 3,
        "acceptance_length_including_bonus_count": 1,
    }


def _response(answer: int) -> dict[str, Any]:
    token_ids = [answer + 100, answer + 200]
    histogram = [0, 1, 0, 0, 0, 0]
    return {
        "id": f"response-{answer}",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": rf"work \boxed{{{answer}}}",
                },
                "finish_reason": "stop",
                "meta_info": {
                    "output_token_ids": token_ids,
                    "spec_verify_ct": 1,
                    "spec_num_proposed_drafts": 5,
                    "spec_proposed_drafts": 5,
                    "spec_num_correct_drafts": 1,
                    "spec_accepted_drafts": 1,
                    "spec_correct_drafts_histogram": histogram,
                    "spec_accept_histogram": histogram,
                    "spec_accept_rate": 0.2,
                    "spec_accept_length": 2.0,
                    "completion_tokens": len(token_ids),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": len(token_ids),
            "total_tokens": 7 + len(token_ids),
        },
    }


class _Clock:
    def __init__(self) -> None:
        self.now_ns = 0

    def __call__(self) -> int:
        return self.now_ns

    def advance(self, seconds: float) -> None:
        self.now_ns += int(seconds * 1_000_000_000)

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


class _Transport:
    def __init__(
        self, clock: _Clock, *, fail_calls: set[int] | None = None
    ) -> None:
        self.clock = clock
        self.fail_calls = fail_calls or set()
        self.calls = 0
        self.answers: list[int] = []

    def __call__(
        self, url: str, payload: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        self.calls += 1
        self.clock.advance(1)
        match = re.search(
            r"Question (\d+)\?", payload["messages"][0]["content"]
        )
        if match is None:
            raise AssertionError("fixture prompt mismatch")
        answer = int(match.group(1))
        self.answers.append(answer)
        if self.calls in self.fail_calls:
            raise OSError(f"fixture failure {self.calls}")
        return _response(answer)


def _native_snapshot(*, dirty: bool = False) -> dict[str, Any]:
    snapshot = {
        "mode": "disabled",
        "experiment_switches": {
            "HEDGE_ENABLED": 0,
            "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
        },
        "config": None,
        "gamma": 5,
        "verify_num_draft_tokens": 6,
        "proposals": 0 if not dirty else 1,
        "draft_tokens_verifiable": 0,
        "strict_accepted_draft_tokens": 0,
        "hedge_accepted_draft_tokens": 0,
        "relaxed_mismatches": 0,
        "regret_charged": 0.0,
        "cap_trim_lens": 0,
        "budget_exhaustion_events": 0,
        "remaining_budget_total": 0.0,
        "requests_initialized": 0,
        "requests_finished": 0,
        "requests_non_natural": 0,
        "slot_reuse_resets": 0,
        "active_request_states": 0,
        "state_leaks": 0,
        "trace_rows_seen": 0,
        "trace_rows_dropped": 0,
        "hedge_accepted_draft_tokens_by_position": [0, 0, 0, 0, 0],
        "remaining_budget_by_request": [],
        "strict_rejection_trace": [],
    }
    from hedge_dspark_p04_client import SERVER_FIELDS

    return {
        **SERVER_FIELDS,
        "internal_states": [{"dspark_info_record": {"hedge": snapshot}}],
    }


class P06ResolvedContractTests(unittest.TestCase):
    def test_native_contract_freezes_identity_and_disables_hedge(self) -> None:
        attempt_id = "20260729T050000Z-p06-native-formal-r1"
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary).resolve()
            resolved = resolve_attempt(
                attempt_id=attempt_id,
                scratch=scratch,
            )

        self.assertEqual(resolved["authorized_phase"], "P06")
        self.assertEqual(resolved["arm"], "native")
        self.assertEqual(resolved["attempt_id"], attempt_id)
        self.assertEqual(resolved["dataset"]["warmup_count"], 10)
        self.assertEqual(resolved["dataset"]["formal_count"], 500)
        self.assertEqual(
            resolved["dataset"]["calibration_jsonl_sha256"],
            CALIBRATION_SHA256,
        )
        self.assertEqual(
            resolved["dataset"]["formal_jsonl_sha256"], FORMAL_SHA256
        )
        self.assertEqual(
            resolved["p05_freeze"],
            {
                "commit": P05_FREEZE_COMMIT,
                "hedge_config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
                "hedge_config_sha256": (
                    "760128b85b8c3dd67e3b4dee512cc302e"
                    "e59bd2e2a1b3ab3390fd186ade36b71"
                ),
            },
        )
        environment = resolved["server"]["environment"]
        self.assertEqual(environment["HEDGE_ENABLED"], "0")
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"], "0"
        )
        self.assertNotIn("SGLANG_DSPARK_HEDGE_CONFIG_PATH", environment)
        self.assertNotIn("SGLANG_DSPARK_HEDGE_TRACE_CAPACITY", environment)
        self.assertEqual(
            resolved["hedge"],
            {
                "mode": "disabled",
                "enabled": False,
                "calibration_trace": False,
                "config": None,
                "config_path": None,
            },
        )
        self.assertEqual(
            resolved["formal_protocol"]["max_total_attempts_per_request"], 3
        )
        self.assertEqual(
            resolved["formal_protocol"]["clock"], "time.monotonic_ns"
        )
        self.assertFalse(resolved["formal_protocol"]["warmup_included"])

    def test_dataset_contract_is_exact_and_non_overlapping(self) -> None:
        identity = validate_formal_datasets()

        self.assertEqual(identity["warmup_count"], 10)
        self.assertEqual(identity["formal_count"], 500)
        self.assertEqual(len(identity["warmup_indices"]), 10)
        self.assertEqual(len(identity["formal_indices"]), 500)
        self.assertFalse(
            set(identity["warmup_indices"]) & set(identity["formal_indices"])
        )
        manifest = json.loads(
            Path(identity["dataset_manifest"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            identity["warmup_indices"],
            manifest["selection"]["calibration_indices"][:10],
        )
        self.assertEqual(
            identity["formal_indices"],
            manifest["selection"]["formal_indices"],
        )

    def test_attempt_identity_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            for invalid in (
                "20260729T050000Z-p07-native-formal-r1",
                "p06-native-formal",
                "20260729T050000Z-p06-native-formal-INVALID",
            ):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        resolve_attempt(
                            attempt_id=invalid,
                            scratch=scratch,
                        )


class P06FormalClientTests(unittest.TestCase):
    def test_spec_metadata_normalizes_and_names_bonus_separately(self) -> None:
        meta = {
            "spec_verify_ct": 21,
            "spec_num_proposed_drafts": 105,
            "spec_proposed_drafts": 105,
            "spec_num_correct_drafts": 70,
            "spec_accepted_drafts": 70,
            "spec_correct_drafts_histogram": [2, 4, 2, 1, 1, 11],
            "spec_accept_histogram": [2, 4, 2, 1, 1, 11],
            "spec_accept_rate": 70 / 105,
            "spec_accept_length": 91 / 21,
            "completion_tokens": 91,
        }

        normalized, evidence = normalize_spec_acceptance(meta)

        self.assertEqual(
            normalized,
            {
                "schema_version": 1,
                "proposal_count": 21,
                "draft_tokens_proposed": 105,
                "accepted_draft_tokens": 70,
                "accepted_draft_tokens_by_position": [19, 15, 13, 12, 11],
                "acceptance_length_including_bonus_sum": 91,
                "acceptance_length_including_bonus_count": 21,
            },
        )
        self.assertEqual(evidence["bonus_tokens"], 21)
        self.assertEqual(evidence["accepted_tokens_including_bonus"], 91)
        self.assertEqual(
            evidence["accepted_draft_tokens_formula"],
            "sum(i * histogram[i] for i in 0..5)",
        )
        self.assertEqual(
            evidence["accepted_by_position_formula"],
            "position[j] = sum(histogram[j+1:]) for j in 0..4",
        )
        self.assertTrue(all(evidence["cross_checks"].values()))

    def test_spec_metadata_mismatch_fails_closed(self) -> None:
        meta = {
            "spec_verify_ct": 2,
            "spec_num_proposed_drafts": 10,
            "spec_proposed_drafts": 10,
            "spec_num_correct_drafts": 4,
            "spec_accepted_drafts": 5,
            "spec_correct_drafts_histogram": [0, 0, 1, 1, 0, 0],
            "spec_accept_histogram": [0, 0, 1, 1, 0, 0],
            "spec_accept_rate": 0.5,
            "spec_accept_length": 3.5,
            "completion_tokens": 7,
        }
        with self.assertRaisesRegex(ValueError, "spec_num_correct_drafts"):
            normalize_spec_acceptance(meta)

    def test_bonus_is_completion_minus_draft_acceptance(self) -> None:
        histogram = [2, 4, 6, 5, 9, 23]
        meta = {
            "spec_verify_ct": 49,
            "spec_num_proposed_drafts": 245,
            "spec_proposed_drafts": 245,
            "spec_num_correct_drafts": 182,
            "spec_accepted_drafts": 182,
            "spec_correct_drafts_histogram": histogram,
            "spec_accept_histogram": histogram,
            "spec_accept_rate": 182 / 245,
            "spec_accept_length": 232 / 49,
            "completion_tokens": 232,
        }

        normalized, evidence = normalize_spec_acceptance(meta)

        self.assertEqual(normalized["accepted_draft_tokens"], 182)
        self.assertEqual(
            normalized["acceptance_length_including_bonus_sum"], 232
        )
        self.assertEqual(evidence["bonus_tokens"], 50)
        self.assertEqual(evidence["bonus_minus_proposals"], 1)

    def test_warmup_clear_and_exact_500_timing_include_retry(self) -> None:
        clock = _Clock()
        transport = _Transport(clock, fail_calls={11})
        warmups = [
            _sample(index, cohort="calibration", cohort_position=index)
            for index in range(10)
        ]
        formal = [
            _sample(
                1000 + index,
                cohort="formal",
                cohort_position=index,
            )
            for index in range(500)
        ]
        clear_calls: list[int] = []

        def clear() -> dict[str, Any]:
            clear_calls.append(transport.calls)
            started = clock()
            clock.advance(7)
            return {
                "schema_version": 1,
                "authorized_phase": "P06",
                "status": "PASS",
                "started_monotonic_ns": started,
                "finished_monotonic_ns": clock(),
                "verified_snapshot_count": 1,
                "exact_zero": True,
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_native_formal(
                base_url="http://fixture",
                warmup_samples=warmups,
                formal_samples=formal,
                artifact_dir=root,
                transport=transport,
                sleeper=clock.sleep,
                clock_ns=clock,
                counter_clear=clear,
                server_info_get=lambda url, timeout: _native_snapshot(
                    dirty=True
                ),
            )
            warmup_records = load_jsonl(root / "warmup_outputs.jsonl")
            formal_records = load_jsonl(root / "formal_outputs.jsonl")
            timing = json.loads(
                (root / "formal_timing.json").read_text(encoding="utf-8")
            )
            answer = json.loads(
                (root / "answer_summary.json").read_text(encoding="utf-8")
            )
            acceptance = json.loads(
                (root / "acceptance_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            clear_evidence = json.loads(
                (root / "pre_formal_clear.json").read_text(encoding="utf-8")
            )
            self.assertTrue((root / "hedge_counters.json").is_file())
            self.assertFalse(
                (root / "formal_server_counters.json").exists()
            )

        self.assertEqual(clear_calls, [10])
        self.assertEqual(len(warmup_records), 10)
        self.assertEqual(len(formal_records), 500)
        self.assertEqual(timing["formal_start_monotonic_ns"], 17_000_000_000)
        self.assertEqual(timing["formal_end_monotonic_ns"], 519_000_000_000)
        self.assertEqual(timing["timed_wall_seconds"], 502.0)
        self.assertFalse(timing["warmup_included"])
        self.assertEqual(timing["warmup_record_count"], 10)
        self.assertTrue(timing["retry_time_included"])
        self.assertEqual(answer["terminal_requests"], 500)
        self.assertEqual(answer["retry_attempts"], 1)
        self.assertEqual(answer["completion_tokens"], 1000)
        self.assertEqual(
            answer["timing"]["end_to_end_output_tps"], 1000 / 502
        )
        self.assertEqual(acceptance["acceptance"], answer["acceptance"])
        self.assertEqual(acceptance["acceptance"]["proposal_count"], 500)
        self.assertEqual(
            acceptance["sglang_spec_normalization"]["bonus_tokens"], 500
        )
        self.assertEqual(
            acceptance["sglang_spec_normalization"][
                "accepted_tokens_including_bonus"
            ],
            1000,
        )
        self.assertEqual(
            formal_records[0]["spec_acceptance"]["bonus_tokens"], 1
        )
        self.assertNotIn(
            "acceptance_counters",
            formal_records[0]["attempts"][-1]["raw_response"]["choices"][0][
                "meta_info"
            ],
        )
        self.assertEqual(result["completion_tokens"], 1000)
        self.assertEqual(result["retry_attempts"], 1)
        self.assertEqual(clear_evidence["status"], "PASS")
        self.assertEqual(clear_evidence["finished_monotonic_ns"], 17_000_000_000)
        self.assertEqual(transport.answers[:10], list(range(10)))
        self.assertEqual(transport.answers[10:12], [1000, 1000])

    def test_failed_clear_prevents_every_formal_request(self) -> None:
        clock = _Clock()
        transport = _Transport(clock)
        warmups = [
            _sample(index, cohort="calibration", cohort_position=index)
            for index in range(10)
        ]
        formal = [
            _sample(
                1000 + index,
                cohort="formal",
                cohort_position=index,
            )
            for index in range(500)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                run_native_formal(
                    base_url="http://fixture",
                    warmup_samples=warmups,
                    formal_samples=formal,
                    artifact_dir=root,
                    transport=transport,
                    sleeper=clock.sleep,
                    clock_ns=clock,
                    counter_clear=lambda: {
                        "status": "FAIL",
                        "exact_zero": False,
                    },
                    server_info_get=lambda url, timeout: _native_snapshot(),
                )
            self.assertFalse((root / "formal_outputs.jsonl").exists())
            self.assertEqual(transport.calls, 10)

    def test_existing_artifact_refuses_resume_or_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "formal_outputs.jsonl").write_text(
                '{"partial":true}\n', encoding="utf-8"
            )
            with self.assertRaises(FileExistsError):
                run_native_formal(
                    base_url="http://fixture",
                    warmup_samples=[],
                    formal_samples=[],
                    artifact_dir=root,
                )

    def test_native_snapshot_rejects_hedge_config_and_state_leak(self) -> None:
        configured = _native_snapshot(dirty=True)
        configured["internal_states"][0]["dspark_info_record"]["hedge"][
            "config"
        ] = {"B": 2.0625}
        with self.assertRaises(ValueError):
            validate_native_server_snapshot(
                configured, require_exact_zero=False
            )

        leaked = _native_snapshot(dirty=True)
        leaked["internal_states"][0]["dspark_info_record"]["hedge"][
            "state_leaks"
        ] = 1
        with self.assertRaises(ValueError):
            validate_native_server_snapshot(
                leaked, require_exact_zero=False
            )

    def test_clear_waits_for_quiescence_then_proves_exact_zero(self) -> None:
        clock = _Clock()
        active = _native_snapshot()
        active["internal_states"][0]["dspark_info_record"]["hedge"][
            "active_request_states"
        ] = 1
        dirty = _native_snapshot(dirty=True)
        clear = _native_snapshot()
        snapshots = iter((active, dirty, clear))
        posts: list[dict[str, Any]] = []

        result = clear_native_formal_evidence(
            base_url="http://fixture",
            server_info_get=lambda url, timeout: next(snapshots),
            internal_state_post=lambda url, payload, timeout: (
                posts.append(dict(payload)) or [True]
            ),
            sleeper=clock.sleep,
            monotonic_ns=clock,
            timeout_seconds=5,
            poll_seconds=1,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["poll_count"], 3)
        self.assertEqual(result["clear_attempt_count"], 1)
        self.assertEqual(
            posts,
            [{"server_args": {"dspark_clear_info_records": 1}}],
        )
        self.assertTrue(result["exact_zero"])


class P06FormalValidatorTests(unittest.TestCase):
    @staticmethod
    def _materialize_client(root: Path) -> None:
        clock = _Clock()
        transport = _Transport(clock, fail_calls={11})
        warmups = [
            _sample(index, cohort="calibration", cohort_position=index)
            for index in range(10)
        ]
        formal = [
            _sample(
                1000 + index,
                cohort="formal",
                cohort_position=index,
            )
            for index in range(500)
        ]

        def clear() -> dict[str, Any]:
            started = clock()
            clock.advance(2)
            return {
                "schema_version": 1,
                "authorized_phase": "P06",
                "status": "PASS",
                "started_monotonic_ns": started,
                "finished_monotonic_ns": clock(),
                "verified_snapshot_count": 1,
                "quiescent": True,
                "exact_zero": True,
                "clear_attempt_count": 1,
            }

        run_native_formal(
            base_url="http://fixture",
            warmup_samples=warmups,
            formal_samples=formal,
            artifact_dir=root,
            transport=transport,
            sleeper=clock.sleep,
            clock_ns=clock,
            counter_clear=clear,
            server_info_get=lambda url, timeout: _native_snapshot(dirty=True),
        )

    def test_client_artifacts_recompute_exact_formal_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._materialize_client(root)
            result = validate_client_artifacts(
                scratch=root,
                expected_warmup_indices=list(range(10)),
                expected_formal_indices=list(range(1000, 1500)),
            )

        self.assertEqual(result["formal_count"], 500)
        self.assertEqual(result["completion_tokens"], 1000)
        self.assertEqual(result["retry_attempts"], 1)
        self.assertEqual(result["formal_start_monotonic_ns"], 12_000_000_000)
        self.assertEqual(result["formal_end_monotonic_ns"], 514_000_000_000)
        self.assertEqual(result["gpu_request_window"], {
            "start": 12_000_000_000,
            "end": 514_000_000_000,
        })

    def test_forged_summary_is_rejected_by_independent_recompute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._materialize_client(root)
            path = root / "answer_summary.json"
            summary = json.loads(path.read_text(encoding="utf-8"))
            summary["completion_tokens"] += 1
            path.write_text(
                json.dumps(summary, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "answer summary"):
                validate_client_artifacts(
                    scratch=root,
                    expected_warmup_indices=list(range(10)),
                    expected_formal_indices=list(range(1000, 1500)),
                )

    def test_resolved_identity_rejects_any_native_hedge_config(self) -> None:
        attempt_id = "20260729T050000Z-p06-native-formal-r1"
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary).resolve()
            resolved = resolve_attempt(
                attempt_id=attempt_id, scratch=scratch
            )
            resolved["gpu_inventory"] = [
                {
                    "index": index,
                    "uuid": f"GPU-{index}",
                    "name": "NVIDIA H20",
                }
                for index in range(8)
            ]
            result = validate_resolved_contract(
                resolved,
                attempt_id=attempt_id,
                scratch=scratch,
            )
            self.assertEqual(result["status"], "PASS")
            resolved["server"]["environment"][
                "SGLANG_DSPARK_HEDGE_CONFIG_PATH"
            ] = "/tmp/forbidden.json"
            with self.assertRaisesRegex(ValueError, "HEDGE"):
                validate_resolved_contract(
                    resolved,
                    attempt_id=attempt_id,
                    scratch=scratch,
                )

    def test_gpu_validation_uses_only_exact_formal_window(self) -> None:
        uuids = [f"GPU-{index}" for index in range(8)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gpu_samples.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "sample_ordinal",
                        "timestamp_utc",
                        "monotonic_ns",
                        "gpu_index",
                        "gpu_uuid",
                        "utilization_gpu_percent",
                        "memory_used_mib",
                        "memory_total_mib",
                    ],
                )
                writer.writeheader()
                for ordinal, timestamp, utilization in (
                    (0, 5, 0),
                    (1, 15, 50),
                    (2, 25, 0),
                ):
                    for index, uuid in enumerate(uuids):
                        writer.writerow(
                            {
                                "sample_ordinal": ordinal,
                                "timestamp_utc": "fixture",
                                "monotonic_ns": timestamp,
                                "gpu_index": index,
                                "gpu_uuid": uuid,
                                "utilization_gpu_percent": utilization,
                                "memory_used_mib": 100,
                                "memory_total_mib": 1000,
                            }
                        )
            result = validate_formal_gpu_window(
                path,
                expected_uuids=uuids,
                formal_start=10,
                formal_end=20,
            )

        self.assertEqual(result["request_sample_ordinals"], 1)
        self.assertEqual(
            {
                record["request_sample_count"]
                for record in result["participation"].values()
            },
            {1},
        )

    def test_lifecycle_and_missing_artifacts_are_fail_closed(self) -> None:
        cleanup = [
            "terminate_registered_server",
            "prove_cuda_contexts_none",
            "terminate_registered_sampler",
            "resume_keepalive_if_cleanup_proven",
            "validate_keepalive_8x10_mean_ge_40",
            "validate_required_artifacts",
        ]
        self.assertEqual(
            validate_lifecycle_events(
                [{"stage": stage} for stage in cleanup],
                require_archive=False,
            )["status"],
            "PASS",
        )
        with self.assertRaises(ValueError):
            validate_lifecycle_events(
                [{"stage": stage} for stage in reversed(cleanup)],
                require_archive=False,
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "formal_outputs.jsonl"
            sentinel.write_text("do-not-overwrite\n", encoding="utf-8")
            missing = ensure_required_artifacts(
                scratch=root,
                reason="fixture failure",
            )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do-not-overwrite\n")
            self.assertEqual(
                set(missing),
                set(REQUIRED_ARTIFACTS) - {"formal_outputs.jsonl"},
            )


if __name__ == "__main__":
    unittest.main()
