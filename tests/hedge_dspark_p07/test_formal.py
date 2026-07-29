from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hedge_dspark_p04_client import SERVER_FIELDS  # noqa: E402
from hedge_dspark_p07_client import (  # noqa: E402
    clear_hedge_formal_evidence,
    run_hedge_formal,
    validate_hedge_server_snapshot,
)
from hedge_dspark_p07_prepare import (  # noqa: E402
    FROZEN_CONFIG,
    FROZEN_CONFIG_FINGERPRINT,
    FROZEN_CONFIG_SHA256,
    P06_ARCHIVE,
    prepare_attempt,
    resolve_attempt,
)
from hedge_dspark_p07_validate import (  # noqa: E402
    REQUIRED_ARTIFACTS,
    archive_attempt,
    record_shutdown,
    validate_client_artifacts,
    validate_resolved_contract,
    validate_shutdown_artifact,
)
from deepspec.hedge_protocol.config import (  # noqa: E402
    DATASET_REVISION,
    PROMPT_SUFFIX,
)
from deepspec.hedge_protocol.io import load_jsonl  # noqa: E402


CONFIG = {
    "B": 2.0625,
    "block_size": 5,
    "g": 2.0625,
    "m": 1,
    "value_scheme": "normalized_suffix",
}
SCORE_SEAM = (
    "native full-vocab next_token_logits after the existing "
    "LogitsProcessor TP all-gather; HEDGE adds no TP collective"
)


def _snapshot(
    *,
    requests: int,
    proposals: int,
    finished_requests: int | None = None,
    active_requests: int = 0,
) -> dict[str, object]:
    if finished_requests is None:
        finished_requests = requests - active_requests
    positions = (
        [
            proposals,
            proposals // 2,
            proposals // 4,
            proposals // 8,
            proposals // 16,
        ]
        if proposals
        else [0, 0, 0, 0, 0]
    )
    accepted = sum(positions)
    return {
        "mode": "enabled",
        "experiment_switches": {
            "HEDGE_ENABLED": 1,
            "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
        },
        "config": CONFIG,
        "config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
        "gamma": 5,
        "verify_num_draft_tokens": 6,
        "counter_schema_version": 1,
        "candidate_alignment": {
            "anchor_index": 0,
            "draft_indices": [1, 6],
            "target_draft_logit_indices": [0, 5],
        },
        "score_seam": SCORE_SEAM,
        "proposals": proposals,
        "draft_tokens_verifiable": proposals * 5,
        "strict_accepted_draft_tokens": max(
            accepted - (1 if proposals else 0), 0
        ),
        "hedge_accepted_draft_tokens": accepted,
        "hedge_accepted_draft_tokens_by_position": positions,
        "relaxed_mismatches": 1 if proposals else 0,
        "regret_charged": 0.5 if proposals else 0.0,
        "cap_trim_lens": 1 if proposals else 0,
        "budget_exhaustion_events": 1 if proposals else 0,
        "remaining_budget_total": (
            requests * float(CONFIG["B"]) - (0.5 if proposals else 0.0)
        ),
        "requests_initialized": requests,
        "requests_finished": finished_requests,
        "requests_non_natural": 0,
        "slot_reuse_resets": 0,
        "active_request_states": active_requests,
        "state_leaks": active_requests,
        "trace_rows_seen": 0,
        "trace_rows_dropped": 0,
        "strict_rejection_trace": [],
        "remaining_budget_by_request": [],
    }


def _server_info(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        **SERVER_FIELDS,
        "internal_states": [{"dspark_info_record": {"hedge": snapshot}}],
    }


def _formal_summary(
    *, success_requests: int = 500, attempts_total: int = 500
) -> dict[str, object]:
    return {
        "total_requests": 500,
        "terminal_requests": 500,
        "success_requests": success_requests,
        "attempts_total": attempts_total,
        "all_terminal": True,
    }


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
                    "completion_tokens": 2,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 2,
            "total_tokens": 9,
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
        self, clock: _Clock, *, retry_once_answer: int | None = None
    ) -> None:
        self.clock = clock
        self.calls = 0
        self.retry_once_answer = retry_once_answer
        self.retry_fired = False

    def __call__(
        self, _url: str, payload: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        self.calls += 1
        self.clock.advance(1)
        match = re.search(
            r"Question (\d+)\?", payload["messages"][0]["content"]
        )
        if match is None:
            raise AssertionError("fixture prompt mismatch")
        answer = int(match.group(1))
        if answer == self.retry_once_answer and not self.retry_fired:
            self.retry_fired = True
            return {
                "id": "fixture-schema-invalid-response",
                "choices": [],
                "usage": {},
            }
        return _response(answer)


class P07ContractTests(unittest.TestCase):
    def test_resolved_contract_is_frozen_hedge_on_and_p06_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            resolved = resolve_attempt(
                attempt_id="20260729T074500Z-p07-hedge-formal-r1",
                scratch=scratch,
            )
        self.assertEqual(resolved["authorized_phase"], "P07")
        self.assertEqual(resolved["arm"], "hedge")
        self.assertNotIn(
            "DEEPSPEC_P07_ENTRYPOINT",
            resolved["server"]["environment"],
        )
        self.assertEqual(resolved["server"]["environment"]["HEDGE_ENABLED"], "1")
        self.assertEqual(
            resolved["server"]["environment"][
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"
            ],
            "0",
        )
        self.assertEqual(resolved["hedge"]["config"], CONFIG)
        self.assertEqual(
            resolved["hedge"]["config_fingerprint"],
            FROZEN_CONFIG_FINGERPRINT,
        )
        self.assertEqual(
            resolved["hedge"]["config_sha256"], FROZEN_CONFIG_SHA256
        )
        self.assertEqual(
            resolved["server"]["environment"][
                "SGLANG_DSPARK_HEDGE_CONFIG_PATH"
            ],
            resolved["hedge"]["config_path"],
        )
        self.assertFalse(resolved["hedge"]["calibration_trace"])
        self.assertEqual(resolved["formal_protocol"]["warmup_count"], 10)
        self.assertEqual(resolved["formal_protocol"]["formal_count"], 500)
        self.assertFalse(
            resolved["formal_protocol"]["resume_or_append_allowed"]
        )
        parity = resolved["p06_identity_parity"]
        self.assertEqual(parity["status"], "PASS")
        self.assertTrue(all(parity["checks"].values()))
        native = json.loads(
            (P06_ARCHIVE / "resolved_config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            resolved["server"]["command"], native["server"]["command"]
        )
        self.assertEqual(resolved["dataset"], native["dataset"])
        self.assertEqual(
            resolved["formal_protocol"], native["formal_protocol"]
        )

    def test_frozen_config_bytes_and_fingerprint_are_exact(self) -> None:
        import hashlib

        from deepspec.hedge_spec.config import HedgeConfig

        self.assertEqual(
            hashlib.sha256(FROZEN_CONFIG.read_bytes()).hexdigest(),
            FROZEN_CONFIG_SHA256,
        )
        self.assertEqual(
            HedgeConfig.from_mapping(CONFIG).fingerprint(),
            FROZEN_CONFIG_FINGERPRINT,
        )
        contract = json.loads(
            (
                REPO_ROOT
                / "artifacts/hedge-dspark/p07-tooling/contract.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(contract["authorized_phase"], "P07")
        self.assertEqual(contract["arm"], "hedge")
        self.assertEqual(contract["hedge"]["config"], CONFIG)
        self.assertEqual(
            contract["hedge"]["config_sha256"], FROZEN_CONFIG_SHA256
        )
        self.assertEqual(
            contract["hedge"]["config_fingerprint"],
            FROZEN_CONFIG_FINGERPRINT,
        )
        self.assertEqual(
            contract["p06_reference"]["archive"], str(P06_ARCHIVE)
        )
        self.assertEqual(
            contract["hedge"]["runtime_snapshot_identity"],
            {
                "candidate_alignment": {
                    "anchor_index": 0,
                    "draft_indices": [1, 6],
                    "target_draft_logit_indices": [0, 5],
                },
                "counter_schema_version": 1,
                "score_seam": SCORE_SEAM,
            },
        )
        self.assertEqual(
            contract["formal_protocol"]["request_counter_bound"],
            (
                "success_requests <= requests_initialized == "
                "requests_finished <= attempts_total"
            ),
        )
        self.assertTrue(
            contract["launcher_entrypoint_marker"][
                "scrubbed_before_child_inheritance"
            ]
        )

    def test_prepare_materializes_exact_config_and_runtime_identity_parity(
        self,
    ) -> None:
        inventory = "\n".join(
            f"{index}, GPU-fixture-{index}, NVIDIA H20, 97871"
            for index in range(8)
        )
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            result = prepare_attempt(
                attempt_id="20260729T074500Z-p07-hedge-formal-r1",
                scratch=scratch,
                inventory_payload=inventory,
            )
            resolved = json.loads(
                (scratch / "resolved_config.json").read_text(encoding="utf-8")
            )
            engine = json.loads(
                (scratch / "engine_identity.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads(
                (scratch / "checkpoint_identity.json").read_text(
                    encoding="utf-8"
                )
            )
            config_bytes = (scratch / "hedge_config.json").read_bytes()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(config_bytes, FROZEN_CONFIG.read_bytes())
        self.assertEqual(
            resolved["p06_runtime_identity_parity"]["status"], "PASS"
        )
        self.assertTrue(
            all(
                resolved["p06_runtime_identity_parity"][
                    "checks"
                ].values()
            )
        )
        self.assertEqual(engine["authorized_phase"], "P07")
        self.assertEqual(checkpoint["authorized_phase"], "P07")

    def test_resolved_validator_rejects_unapproved_extra_identity(self) -> None:
        inventory = "\n".join(
            f"{index}, GPU-fixture-{index}, NVIDIA H20, 97871"
            for index in range(8)
        )
        attempt_id = "20260729T074500Z-p07-hedge-formal-r1"
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            prepare_attempt(
                attempt_id=attempt_id,
                scratch=scratch,
                inventory_payload=inventory,
            )
            resolved = json.loads(
                (scratch / "resolved_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                validate_resolved_contract(
                    resolved,
                    attempt_id=attempt_id,
                    scratch=scratch,
                )["status"],
                "PASS",
            )
            resolved["unapproved_decode_override"] = True
            with self.assertRaisesRegex(ValueError, "fields"):
                validate_resolved_contract(
                    resolved,
                    attempt_id=attempt_id,
                    scratch=scratch,
                )

    def test_positive_budget_snapshot_proves_runtime_and_request_lifecycle(
        self,
    ) -> None:
        result = validate_hedge_server_snapshot(
            _server_info(_snapshot(requests=500, proposals=17)),
            require_exact_zero=False,
            formal_summary=_formal_summary(),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["runtime_calls"], 17)
        self.assertEqual(result["requests_initialized"], 500)
        self.assertEqual(result["requests_finished"], 500)
        self.assertEqual(result["active_request_states"], 0)
        self.assertEqual(result["state_leaks"], 0)
        self.assertEqual(result["relaxed_mismatches"], 1)
        self.assertEqual(result["regret_charged"], 0.5)

    def test_snapshot_rejects_leak_and_wrong_frozen_config(self) -> None:
        snapshot = _snapshot(requests=500, proposals=17)
        snapshot["requests_finished"] = 499
        snapshot["active_request_states"] = 1
        snapshot["state_leaks"] = 1
        snapshot["remaining_budget_by_request"] = [
            {"rid": "leaked", "slot": 3, "remaining_budget": 1.0}
        ]
        with self.assertRaisesRegex(ValueError, "leak"):
            validate_hedge_server_snapshot(
                _server_info(snapshot),
                require_exact_zero=False,
                formal_summary=_formal_summary(),
            )
        snapshot = _snapshot(requests=500, proposals=17)
        snapshot["config"] = {**CONFIG, "B": 9.0}
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_hedge_server_snapshot(
                _server_info(snapshot),
                require_exact_zero=False,
                formal_summary=_formal_summary(),
            )
        snapshot = _snapshot(requests=500, proposals=17)
        snapshot["trace_rows_seen"] = 1
        snapshot["strict_rejection_trace"] = [{"unexpected": True}]
        with self.assertRaisesRegex(ValueError, "calibration trace"):
            validate_hedge_server_snapshot(
                _server_info(snapshot),
                require_exact_zero=False,
                formal_summary=_formal_summary(),
            )
        snapshot = _snapshot(requests=500, proposals=17)
        snapshot["remaining_budget_total"] = 0.0
        with self.assertRaisesRegex(ValueError, "conserve"):
            validate_hedge_server_snapshot(
                _server_info(snapshot),
                require_exact_zero=False,
                formal_summary=_formal_summary(),
            )

    def test_snapshot_request_initialization_stays_within_retry_bounds(
        self,
    ) -> None:
        summary = _formal_summary(attempts_total=501)
        for requests in (499, 502):
            with self.subTest(requests=requests):
                with self.assertRaisesRegex(ValueError, "attempt bounds"):
                    validate_hedge_server_snapshot(
                        _server_info(
                            _snapshot(requests=requests, proposals=17)
                        ),
                        require_exact_zero=False,
                        formal_summary=summary,
                    )

    def test_snapshot_rejects_schema_alignment_and_score_seam_drift(
        self,
    ) -> None:
        mutations = {
            "counter_schema_version": lambda snapshot: snapshot.__setitem__(
                "counter_schema_version", 2
            ),
            "candidate_alignment": lambda snapshot: snapshot.__setitem__(
                "candidate_alignment",
                {
                    "anchor_index": 0,
                    "draft_indices": [1, 5],
                    "target_draft_logit_indices": [0, 5],
                },
            ),
            "score_seam": lambda snapshot: snapshot.__setitem__(
                "score_seam", SCORE_SEAM + " drift"
            ),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                snapshot = _snapshot(requests=500, proposals=17)
                mutate(snapshot)
                with self.assertRaisesRegex(ValueError, "identity"):
                    validate_hedge_server_snapshot(
                        _server_info(snapshot),
                        require_exact_zero=False,
                        formal_summary=_formal_summary(),
                    )

    def test_snapshot_rejects_physically_impossible_counters(self) -> None:
        position_overflow = _snapshot(requests=500, proposals=17)
        position_overflow[
            "hedge_accepted_draft_tokens_by_position"
        ] = [18, 7, 4, 2, 1]

        position_increase = _snapshot(requests=500, proposals=17)
        position_increase[
            "hedge_accepted_draft_tokens_by_position"
        ] = [17, 7, 8, 0, 0]

        non_natural = _snapshot(requests=500, proposals=17)
        non_natural["requests_non_natural"] = 501

        too_many_exhaustions = _snapshot(requests=500, proposals=17)
        too_many_exhaustions["budget_exhaustion_events"] = 501

        too_many_trims = _snapshot(requests=500, proposals=17)
        too_many_trims["cap_trim_lens"] = 86

        cases = (
            ("position_overflow", position_overflow, "position"),
            ("position_increase", position_increase, "position"),
            ("non_natural", non_natural, "lifecycle"),
            ("budget_exhaustion", too_many_exhaustions, "exhaustion"),
            ("cap_trim", too_many_trims, "cap trim"),
        )
        for name, snapshot, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message):
                    validate_hedge_server_snapshot(
                        _server_info(snapshot),
                        require_exact_zero=False,
                        formal_summary=_formal_summary(),
                    )

        active_lifecycle = _snapshot(
            requests=2,
            proposals=0,
            finished_requests=0,
            active_requests=1,
        )
        active_lifecycle["remaining_budget_by_request"] = [
            {
                "rid": "active-lifecycle",
                "slot": 3,
                "remaining_budget": float(CONFIG["B"]),
            }
        ]
        with self.assertRaisesRegex(ValueError, "lifecycle"):
            validate_hedge_server_snapshot(
                _server_info(active_lifecycle),
                require_exact_zero=False,
                allow_active=True,
            )

        active_budget = _snapshot(
            requests=1,
            proposals=0,
            active_requests=1,
        )
        active_budget["remaining_budget_by_request"] = [
            {
                "rid": "active-budget",
                "slot": 4,
                "remaining_budget": float(CONFIG["B"]) - 0.25,
            }
        ]
        active_budget["remaining_budget_total"] = (
            float(CONFIG["B"]) - 0.25
        )
        with self.assertRaisesRegex(ValueError, "conserve"):
            validate_hedge_server_snapshot(
                _server_info(active_budget),
                require_exact_zero=False,
                allow_active=True,
            )

    def test_attempt_contract_exposes_only_hedge_arm(self) -> None:
        output = subprocess.check_output(
            [
                "bash",
                str(SCRIPTS / "hedge_dspark_p07_attempt.sh"),
                "--print-contract",
            ],
            text=True,
        )
        contract = json.loads(output)
        self.assertEqual(contract["arms"], ["hedge"])
        self.assertTrue(contract["hedge_enabled"])
        self.assertEqual(contract["warmup_count"], 10)
        self.assertEqual(contract["formal_count"], 500)
        self.assertFalse(contract["resume_allowed"])
        self.assertEqual(contract["p06_reuse"], "exact-lifecycle")
        native_environment = dict(os.environ)
        native_environment["DEEPSPEC_FORMAL_PHASE"] = "P07"
        native_environment["DEEPSPEC_P07_ENTRYPOINT"] = str(
            SCRIPTS / "hedge_dspark_p07_attempt.sh"
        )
        native = json.loads(
            subprocess.check_output(
                [
                    "bash",
                    str(SCRIPTS / "hedge_dspark_p06_attempt.sh"),
                    "--print-contract",
                ],
                text=True,
                env=native_environment,
            )
        )
        self.assertEqual(native["arms"], ["native"])
        self.assertFalse(native["hedge_enabled"])

    def test_launcher_scrubs_p07_entrypoint_before_server_inheritance(
        self,
    ) -> None:
        p07 = json.loads(
            subprocess.check_output(
                [
                    "bash",
                    str(SCRIPTS / "hedge_dspark_p07_attempt.sh"),
                    "--print-server-inherited-environment",
                ],
                text=True,
            )
        )
        self.assertEqual(p07["formal_phase"], "P07")
        self.assertFalse(p07["entrypoint_marker_present"])

        native_environment = dict(os.environ)
        native_environment["DEEPSPEC_P07_ENTRYPOINT"] = "ambient-forgery"
        native = json.loads(
            subprocess.check_output(
                [
                    "bash",
                    str(SCRIPTS / "hedge_dspark_p06_attempt.sh"),
                    "--print-server-inherited-environment",
                ],
                text=True,
                env=native_environment,
            )
        )
        self.assertEqual(native["formal_phase"], "P06")
        self.assertFalse(native["entrypoint_marker_present"])

    def test_archive_keeps_p07_identity_and_runtime_config_artifact(
        self,
    ) -> None:
        cleanup = [
            "terminate_registered_server",
            "prove_cuda_contexts_none",
            "terminate_registered_sampler",
            "resume_keepalive_if_cleanup_proven",
            "validate_keepalive_8x10_mean_ge_40",
            "validate_required_artifacts",
            "archive_without_overwrite",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scratch = root / "scratch"
            destination = root / "archive"
            scratch.mkdir()
            destination.mkdir()
            for name in REQUIRED_ARTIFACTS:
                (scratch / name).write_text(
                    f"fixture {name}\n", encoding="utf-8"
                )
            (scratch / "lifecycle_events.jsonl").write_text(
                "".join(
                    json.dumps({"stage": stage}) + "\n"
                    for stage in cleanup
                ),
                encoding="utf-8",
            )
            result = archive_attempt(
                scratch=scratch,
                hdfs_run=destination,
            )
            manifest = json.loads(
                (destination / "archive_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(manifest["authorized_phase"], "P07")
        self.assertEqual(manifest["arm"], "hedge")
        self.assertIn(
            "hedge_config.json",
            {record["path"] for record in manifest["files"]},
        )
        self.assertNotIn(
            "p05_frozen_hedge_config.json",
            {record["path"] for record in manifest["files"]},
        )

    def test_shutdown_requires_every_cleanup_gate_and_exact_attempt(
        self,
    ) -> None:
        attempt_id = "20260729T074500Z-p07-hedge-formal-r1"
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            for role in ("server", "sampler"):
                (scratch / f"{role}_shutdown.json").write_text(
                    json.dumps({"status": "terminated"}) + "\n",
                    encoding="utf-8",
                )
            result = record_shutdown(
                scratch=scratch,
                attempt_id=attempt_id,
                original_returncode=0,
                cleanup_returncode=0,
                contexts_proven=True,
                keepalive_ready=True,
                signal_name="",
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                validate_shutdown_artifact(
                    scratch=scratch,
                    attempt_id=attempt_id,
                )["status"],
                "PASS",
            )
            forged = json.loads(
                (scratch / "shutdown.json").read_text(encoding="utf-8")
            )
            forged["checks"]["contexts_proven"] = False
            (scratch / "shutdown.json").write_text(
                json.dumps(forged, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "shutdown"):
                validate_shutdown_artifact(
                    scratch=scratch,
                    attempt_id=attempt_id,
                )

    def test_clear_waits_for_quiescence_and_proves_hedge_exact_zero(
        self,
    ) -> None:
        clock = _Clock()
        active = _snapshot(requests=1, proposals=0, active_requests=1)
        active["remaining_budget_by_request"] = [
            {
                "rid": "warmup-active",
                "slot": 3,
                "remaining_budget": float(CONFIG["B"]),
            }
        ]
        dirty = _snapshot(requests=1, proposals=1)
        zero = _snapshot(requests=0, proposals=0)
        snapshots = iter(
            (_server_info(active), _server_info(dirty), _server_info(zero))
        )
        posts: list[dict[str, Any]] = []
        result = clear_hedge_formal_evidence(
            base_url="http://fixture",
            server_info_get=lambda _url, _timeout: next(snapshots),
            internal_state_post=lambda _url, payload, _timeout: (
                posts.append(dict(payload)) or [True]
            ),
            sleeper=clock.sleep,
            monotonic_ns=clock,
            timeout_seconds=5,
            poll_seconds=1,
        )
        self.assertEqual(result["authorized_phase"], "P07")
        self.assertEqual(result["arm"], "hedge")
        self.assertTrue(result["exact_zero"])
        self.assertEqual(result["clear_attempt_count"], 1)
        self.assertEqual(
            posts, [{"server_args": {"dspark_clear_info_records": 1}}]
        )

    def test_formal_client_reuses_exact_10_plus_500_protocol(self) -> None:
        clock = _Clock()
        transport = _Transport(clock, retry_once_answer=1000)
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
                "authorized_phase": "P07",
                "status": "PASS",
                "arm": "hedge",
                "started_monotonic_ns": started,
                "finished_monotonic_ns": clock(),
                "verified_snapshot_count": 1,
                "quiescent": True,
                "exact_zero": True,
                "clear_attempt_count": 1,
            }

        final_snapshot = _snapshot(requests=501, proposals=500)
        final_snapshot["strict_accepted_draft_tokens"] = 499
        final_snapshot["hedge_accepted_draft_tokens"] = 500
        final_snapshot["hedge_accepted_draft_tokens_by_position"] = [
            500,
            0,
            0,
            0,
            0,
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_hedge_formal(
                base_url="http://fixture",
                warmup_samples=warmups,
                formal_samples=formal,
                artifact_dir=root,
                transport=transport,
                sleeper=clock.sleep,
                clock_ns=clock,
                counter_clear=clear,
                server_info_get=lambda _url, _timeout: _server_info(
                    final_snapshot
                ),
            )
            audit = validate_client_artifacts(
                scratch=root,
                expected_warmup_indices=list(range(10)),
                expected_formal_indices=list(range(1000, 1500)),
            )
            timing = json.loads(
                (root / "formal_timing.json").read_text(encoding="utf-8")
            )
            counters = json.loads(
                (root / "hedge_counters.json").read_text(encoding="utf-8")
            )
            formal_records = load_jsonl(root / "formal_outputs.jsonl")
            for forged_initialized in (499, 502):
                forged = json.loads(json.dumps(counters))
                forged_snapshot = forged["hedge_snapshots"][0]
                forged_snapshot["requests_initialized"] = (
                    forged_initialized
                )
                forged_snapshot["requests_finished"] = forged_initialized
                forged_snapshot["remaining_budget_total"] = (
                    forged_initialized * float(CONFIG["B"])
                    - forged_snapshot["regret_charged"]
                )
                (root / "hedge_counters.json").write_text(
                    json.dumps(forged, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "attempt bounds"):
                    validate_client_artifacts(
                        scratch=root,
                        expected_warmup_indices=list(range(10)),
                        expected_formal_indices=list(range(1000, 1500)),
                    )
            forged = dict(counters)
            forged["relaxed_mismatches"] += 1
            (root / "hedge_counters.json").write_text(
                json.dumps(forged, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "counter"):
                validate_client_artifacts(
                    scratch=root,
                    expected_warmup_indices=list(range(10)),
                    expected_formal_indices=list(range(1000, 1500)),
                )
        self.assertEqual(transport.calls, 511)
        self.assertEqual(len(formal_records), 500)
        self.assertEqual(formal_records[0]["attempt_count"], 2)
        self.assertEqual(
            formal_records[0]["attempts"][0]["status"], "error"
        )
        self.assertIn("raw_response", formal_records[0]["attempts"][0])
        self.assertEqual(result["authorized_phase"], "P07")
        self.assertEqual(result["arm"], "hedge")
        self.assertFalse(timing["warmup_included"])
        self.assertEqual(timing["formal_record_count"], 500)
        self.assertEqual(audit["terminal_requests"], 500)
        self.assertEqual(audit["retry_attempts"], 1)
        self.assertEqual(counters["requests_initialized"], 501)
        self.assertEqual(counters["requests_finished"], 501)
        self.assertEqual(counters["runtime_calls"], 500)


if __name__ == "__main__":
    unittest.main()
