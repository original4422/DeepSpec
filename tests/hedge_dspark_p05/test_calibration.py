"""Public-seam tests for the bounded P05 DSpark calibration workflow."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from deepspec.hedge_protocol.io import load_jsonl

from scripts.hedge_dspark_p05_client import (
    run_calibration_arm,
    validate_server_snapshot,
)
from scripts.hedge_dspark_p05_reduce import (
    _compare_token_ids,
    _positive_trace_values,
    linear_q25,
    reduce_calibration,
)
from scripts.hedge_dspark_p05_validate import (
    archive_attempt,
    finalize_attempt,
    record_shutdown,
    required_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ATTEMPT = REPO_ROOT / "scripts/hedge_dspark_p05_attempt.sh"
PREPARE = REPO_ROOT / "scripts/hedge_dspark_p05_prepare.py"
PYTHON = Path("/home/tiger/venvs/hedge-v4-dspark/bin/python")
CALIBRATION_INDICES = [
    435,
    902,
    303,
    1168,
    403,
    611,
    608,
    977,
    229,
    1263,
    566,
    1191,
    979,
    1032,
    297,
    1150,
    488,
    1235,
    1266,
    75,
    720,
    331,
    992,
    177,
    983,
    467,
    127,
    114,
    973,
    1085,
    900,
    822,
]


class P05LauncherContractTests(unittest.TestCase):
    def test_launcher_exposes_exact_two_arm_contract(self) -> None:
        completed = subprocess.run(
            ["bash", str(ATTEMPT), "--print-contract"],
            check=True,
            capture_output=True,
            text=True,
        )
        contract = json.loads(completed.stdout)
        self.assertEqual(
            contract["arms"],
            ["native-trace", "b0"],
        )
        self.assertEqual(contract["worker_id"], "4106666")
        self.assertEqual(contract["expected_gpus"], 8)
        self.assertEqual(contract["tp_size"], 8)
        self.assertEqual(contract["proposal_width"], 5)
        self.assertEqual(contract["port"], 31066)
        self.assertEqual(contract["sample_count"], 32)
        self.assertEqual(
            contract["lifecycle"],
            [
                "preflight",
                "pause_keepalive",
                "prove_contexts_none",
                "start_registered_server_and_sampler",
                "run_exact_32_sequential_requests",
                "validate_live_evidence",
                "terminate_registered_server",
                "prove_contexts_none",
                "terminate_registered_sampler",
                "resume_and_validate_keepalive",
                "archive_without_overwrite",
            ],
        )

    def test_launcher_rejects_wrong_worker_before_creating_attempt(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(ATTEMPT),
                "4105641",
                "native-trace",
                "20260729T020000Z-p05-native-calibration-r1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("only 4106666 is authorized", completed.stderr)

    def test_launcher_uses_registered_groups_and_has_no_broad_cleanup(self) -> None:
        source = ATTEMPT.read_text(encoding="utf-8")
        self.assertIn('"$PROCESS_GUARD" terminate', source)
        self.assertIn('exec setsid "${server_command[@]}"', source)
        self.assertNotIn("pkill", source)
        self.assertNotIn("killall", source)
        subprocess.run(["bash", "-n", str(ATTEMPT)], check=True)


class P05ResolveContractTests(unittest.TestCase):
    def _resolve(self, arm: str, attempt_id: str) -> tuple[Path, dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        scratch = Path(temporary.name) / "scratch"
        scratch.mkdir()
        subprocess.run(
            [
                str(PYTHON),
                str(PREPARE),
                "resolve",
                "--arm",
                arm,
                "--attempt-id",
                attempt_id,
                "--scratch",
                str(scratch),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return scratch, json.loads(
            (scratch / "resolved_config.json").read_text(encoding="utf-8")
        )

    def test_native_trace_resolves_frozen_dataset_and_native_acceptance(self) -> None:
        scratch, resolved = self._resolve(
            "native-trace",
            "20260729T020000Z-p05-native-calibration-r1",
        )
        self.assertEqual(resolved["authorized_phase"], "P05")
        self.assertEqual(resolved["arm"], "native-trace")
        self.assertEqual(resolved["worker_id"], "4106666")
        self.assertEqual(
            resolved["dataset"]["calibration_jsonl_sha256"],
            "28a7080565cde90b8cf1db79c88bb463861515fabe3fa7409481802104a6e47d",
        )
        self.assertEqual(resolved["dataset"]["sample_count"], 32)
        self.assertEqual(
            resolved["dataset"]["dataset_indices"],
            CALIBRATION_INDICES,
        )
        self.assertEqual(
            resolved["dataset"]["dataset_revision"],
            "740312add88f781978c0658806c59bc2815b9866",
        )
        environment = resolved["server"]["environment"]
        self.assertEqual(environment["HEDGE_ENABLED"], "0")
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"], "1"
        )
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_TRACE_CAPACITY"], "65536"
        )
        self.assertEqual(resolved["hedge"]["mode"], "calibration")
        self.assertTrue(resolved["hedge"]["native_acceptance_preserved"])
        self.assertIsNone(resolved["hedge"]["config"])
        self.assertFalse((scratch / "hedge_config.json").exists())

    def test_b0_resolves_exact_p04_config_bytes(self) -> None:
        scratch, resolved = self._resolve(
            "b0",
            "20260729T030000Z-p05-b0-calibration-r1",
        )
        self.assertEqual(
            (scratch / "hedge_config.json").read_bytes(),
            (
                b'{"B":0,"g":1e30,"m":5,'
                b'"value_scheme":"normalized_suffix","block_size":5}\n'
            ),
        )
        environment = resolved["server"]["environment"]
        self.assertEqual(environment["HEDGE_ENABLED"], "1")
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"], "0"
        )
        self.assertNotIn(
            "SGLANG_DSPARK_HEDGE_TRACE_CAPACITY",
            environment,
        )
        self.assertEqual(
            resolved["hedge"]["config"],
            {
                "B": 0,
                "g": 1e30,
                "m": 5,
                "value_scheme": "normalized_suffix",
                "block_size": 5,
            },
        )


class P05CalibrationRunnerTests(unittest.TestCase):
    @staticmethod
    def _server_info(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "tp_size": 8,
            "speculative_algorithm": "DSPARK",
            "speculative_dspark_block_size": 5,
            "moe_runner_backend": "flashinfer_mxfp4",
            "speculative_moe_runner_backend": "flashinfer_mxfp4",
            "context_length": 4096,
            "max_running_requests": 1,
            "mem_fraction_static": 0.8,
            "disable_cuda_graph": True,
            "disable_overlap_schedule": True,
            "disable_radix_cache": True,
            "internal_states": [
                {"dspark_info_record": {"hedge": dict(snapshot)}}
            ],
        }

    def test_native_trace_runs_frozen_32_and_preserves_response_token_ids(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        artifact_dir = Path(temporary.name)
        seen_requests: list[dict[str, Any]] = []

        def transport(
            _url: str, payload: dict[str, Any], _timeout: float
        ) -> Mapping[str, Any]:
            seen_requests.append(payload)
            ordinal = len(seen_requests) - 1
            return {
                "choices": [
                    {
                        "message": {"content": f"work \\\\boxed{{{ordinal}}}"},
                        "meta_info": {
                            "output_token_ids": [50000 + ordinal, 7]
                        },
                    }
                ],
                "usage": {"completion_tokens": 2},
            }

        trace_rows = [
            {
                "proposal_ordinal": 3,
                "request_serial": 1,
                "rid": "request-a",
                "request_pool_slot": 4,
                "forward_ct": 7,
                "barrier_position": 1,
                "regret": 2.0,
                "value": 0.8,
                "regret_per_value": 2.5,
            },
            {
                "proposal_ordinal": 17,
                "request_serial": 2,
                "rid": "request-b",
                "request_pool_slot": 9,
                "forward_ct": 11,
                "barrier_position": 4,
                "regret": 0.25,
                "value": 0.2,
                "regret_per_value": 1.25,
            },
        ]
        snapshot = {
            "mode": "calibration",
            "experiment_switches": {
                "HEDGE_ENABLED": 0,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 1,
            },
            "config": None,
            "config_fingerprint": None,
            "gamma": 5,
            "verify_num_draft_tokens": 6,
            "proposals": 64,
            "strict_accepted_draft_tokens": 123,
            "hedge_accepted_draft_tokens": 123,
            "relaxed_mismatches": 0,
            "trace_rows_seen": 64,
            "trace_rows_dropped": 0,
            "strict_rejection_trace": trace_rows,
            "state_leaks": 0,
            "active_request_states": 0,
        }
        result = run_calibration_arm(
            arm="native-trace",
            base_url="http://127.0.0.1:31066",
            dataset=(
                REPO_ROOT
                / "artifacts/hedge-dspark/p01-protocol/"
                "gsm8k_calibration_32.jsonl"
            ),
            outputs_path=artifact_dir / "native_calibration_outputs.jsonl",
            summary_path=artifact_dir / "calibration_request_summary.json",
            counters_path=artifact_dir / "hedge_counters.json",
            trace_path=artifact_dir / "strict_rejection_trace.jsonl",
            transport=transport,
            server_info_get=lambda _url, _timeout: self._server_info(snapshot),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["terminal_counts"], {"succeeded": 32, "failed": 0})
        self.assertEqual(len(seen_requests), 32)
        samples = load_jsonl(
            REPO_ROOT
            / "artifacts/hedge-dspark/p01-protocol/"
            "gsm8k_calibration_32.jsonl"
        )
        self.assertEqual(
            [request["messages"][0]["content"] for request in seen_requests],
            [sample["user_content"] for sample in samples],
        )
        outputs = load_jsonl(
            artifact_dir / "native_calibration_outputs.jsonl"
        )
        self.assertEqual(
            [record["dataset_index"] for record in outputs],
            CALIBRATION_INDICES,
        )
        self.assertEqual(
            [record["output_token_ids"] for record in outputs],
            [[50000 + ordinal, 7] for ordinal in range(32)],
        )
        self.assertEqual(
            load_jsonl(artifact_dir / "strict_rejection_trace.jsonl"),
            [
                {"snapshot_index": 0, **trace_rows[0]},
                {"snapshot_index": 0, **trace_rows[1]},
            ],
        )
        counters = json.loads(
            (artifact_dir / "hedge_counters.json").read_text(encoding="utf-8")
        )
        self.assertEqual(counters["trace_capacity"], 65536)
        self.assertEqual(counters["trace_rows_seen"], 64)
        self.assertEqual(counters["trace_rows_dropped"], 0)
        self.assertTrue(counters["native_acceptance_preserved"])

    def test_b0_snapshot_requires_strict_acceptance_and_no_relaxation(self) -> None:
        snapshot = {
            "mode": "enabled",
            "experiment_switches": {
                "HEDGE_ENABLED": 1,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
            },
            "config": {
                "B": 0,
                "g": 1e30,
                "m": 5,
                "value_scheme": "normalized_suffix",
                "block_size": 5,
            },
            "config_fingerprint": (
                "0be8b8063ac491144e6b6d847bdfba6647be0f22aac5532971536dd3e20561f9"
            ),
            "gamma": 5,
            "verify_num_draft_tokens": 6,
            "proposals": 12,
            "strict_accepted_draft_tokens": 31,
            "hedge_accepted_draft_tokens": 31,
            "relaxed_mismatches": 0,
            "regret_charged": 0.0,
            "trace_rows_seen": 0,
            "trace_rows_dropped": 0,
            "strict_rejection_trace": [],
            "state_leaks": 0,
            "active_request_states": 0,
        }
        counters, trace = validate_server_snapshot(
            self._server_info(snapshot), arm="b0"
        )
        self.assertEqual(counters["status"], "PASS")
        self.assertEqual(counters["proposal_count"], 12)
        self.assertEqual(trace, [])

        snapshot["relaxed_mismatches"] = 1
        with self.assertRaisesRegex(ValueError, "strict zero-budget"):
            validate_server_snapshot(self._server_info(snapshot), arm="b0")

    def test_native_trace_fails_closed_on_dropped_or_empty_rows(self) -> None:
        snapshot = {
            "mode": "calibration",
            "experiment_switches": {
                "HEDGE_ENABLED": 0,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 1,
            },
            "config": None,
            "config_fingerprint": None,
            "gamma": 5,
            "verify_num_draft_tokens": 6,
            "proposals": 0,
            "strict_accepted_draft_tokens": 0,
            "hedge_accepted_draft_tokens": 0,
            "relaxed_mismatches": 0,
            "trace_rows_seen": 1,
            "trace_rows_dropped": 1,
            "strict_rejection_trace": [],
            "state_leaks": 0,
            "active_request_states": 0,
        }
        with self.assertRaisesRegex(ValueError, "dropped"):
            validate_server_snapshot(
                self._server_info(snapshot), arm="native-trace"
            )
        snapshot["trace_rows_dropped"] = 0
        with self.assertRaisesRegex(ValueError, "no positive"):
            validate_server_snapshot(
                self._server_info(snapshot), arm="native-trace"
            )


class P05ReducerTests(unittest.TestCase):
    def test_reducer_compares_full_ids_and_uses_exact_linear_q25(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        native = root / "native.jsonl"
        b0 = root / "b0.jsonl"
        trace = root / "trace.jsonl"
        counters = root / "counters.json"
        output = root / "result"
        records = [
            {
                "cohort": "calibration",
                "cohort_position": position,
                "dataset_index": dataset_index,
                "terminal_status": "succeeded",
                "output_token_ids": [90000 + position, 13, position],
            }
            for position, dataset_index in enumerate(CALIBRATION_INDICES)
        ]
        native.write_text(
            "".join(
                json.dumps(record, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        b0.write_text(native.read_text(encoding="utf-8"), encoding="utf-8")
        trace_rows = [
            {
                "snapshot_index": 0,
                "proposal_ordinal": ordinal,
                "request_serial": ordinal + 1,
                "rid": f"r-{ordinal}",
                "request_pool_slot": ordinal,
                "forward_ct": ordinal + 10,
                "barrier_position": 0,
                "regret": ratio,
                "value": 1.0,
                "regret_per_value": ratio,
            }
            for ordinal, ratio in enumerate((5.0, 1.0, 3.0, 2.0))
        ]
        trace.write_text(
            "".join(
                json.dumps(record, separators=(",", ":")) + "\n"
                for record in trace_rows
            ),
            encoding="utf-8",
        )
        counters.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "arm": "native-trace",
                    "trace_capacity": 65536,
                    "trace_rows_seen": 4,
                    "trace_rows_stored": 4,
                    "trace_rows_dropped": 0,
                    "native_acceptance_preserved": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = reduce_calibration(
            native_outputs=native,
            b0_outputs=b0,
            native_trace=trace,
            native_counters=counters,
            output_dir=output,
        )
        self.assertEqual(result["status"], "PASS")
        equivalence = json.loads(
            (output / "b0_equivalence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(equivalence["b0_status"], "PASS")
        self.assertEqual(equivalence["full_token_id_lists_equal"], 32)
        self.assertEqual(equivalence["mismatch_count"], 0)
        values = load_jsonl(output / "calibration_values.jsonl")
        self.assertEqual(
            [record["regret_per_value"] for record in values],
            [1.0, 2.0, 3.0, 5.0],
        )
        summary = json.loads(
            (output / "calibration_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["positive_value_count"], 4)
        self.assertEqual(
            summary["q25_method"],
            "linear interpolation with h=(n-1)*0.25",
        )
        self.assertEqual(summary["q25"], 1.75)
        self.assertEqual(
            summary["config_fingerprint"],
            "0da1326364cc7949b54d5c5f53a80e2e15bf2b23ca18b00d857777e88e2193c4",
        )
        self.assertEqual(
            json.loads(
                (output / "hedge_config.json").read_text(encoding="utf-8")
            ),
            {
                "B": 1.75,
                "g": 1.75,
                "m": 1,
                "value_scheme": "normalized_suffix",
                "block_size": 5,
            },
        )
        self.assertFalse(
            (output / "first_minimal_counterexample.json").exists()
        )

    def test_token_id_mismatch_reports_first_minimal_counterexample(self) -> None:
        native = [
            {
                "dataset_index": 435,
                "output_token_ids": [10, 20, 30],
            }
        ]
        b0 = [
            {
                "dataset_index": 435,
                "output_token_ids": [10, 99, 30, 40],
            }
        ]
        equivalence, counterexample = _compare_token_ids(
            native,
            b0,
            native_sha256="a" * 64,
            b0_sha256="b" * 64,
        )
        self.assertEqual(equivalence["b0_status"], "FAILED")
        self.assertEqual(equivalence["full_token_id_lists_equal"], 0)
        self.assertEqual(equivalence["mismatch_count"], 1)
        self.assertIsNotNone(counterexample)
        assert counterexample is not None
        self.assertEqual(counterexample["first_differing_token_position"], 1)
        self.assertEqual(counterexample["native_token_id"], 20)
        self.assertEqual(counterexample["b0_token_id"], 99)
        self.assertEqual(
            counterexample["native_output_token_ids"], [10, 20, 30]
        )
        self.assertEqual(
            counterexample["b0_output_token_ids"], [10, 99, 30, 40]
        )

    def test_q25_exact_examples_and_invalid_inputs(self) -> None:
        self.assertEqual(linear_q25([7.0]), 7.0)
        self.assertEqual(linear_q25([2.0, 6.0]), 3.0)
        self.assertEqual(linear_q25([1.0, 2.0, 3.0, 5.0]), 1.75)
        with self.assertRaisesRegex(ValueError, "empty"):
            linear_q25([])
        with self.assertRaisesRegex(ValueError, "sorted positive finite"):
            linear_q25([2.0, 1.0])
        with self.assertRaisesRegex(ValueError, "sorted positive finite"):
            linear_q25([0.0, 1.0])

    def test_ratio_selection_keeps_only_positive_finite_values(self) -> None:
        base = {
            "snapshot_index": 0,
            "proposal_ordinal": 1,
            "request_serial": 1,
            "rid": "r",
            "request_pool_slot": 2,
            "forward_ct": 3,
            "barrier_position": 0,
            "regret": 1.0,
            "value": 1.0,
        }
        selected = _positive_trace_values(
            [
                {**base, "regret_per_value": 0.0},
                {**base, "proposal_ordinal": 2, "regret_per_value": float("nan")},
                {**base, "proposal_ordinal": 3, "regret_per_value": 1.0},
            ]
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["proposal_ordinal"], 3)
        self.assertEqual(selected[0]["regret_per_value"], 1.0)


class P05LifecycleEvidenceTests(unittest.TestCase):
    def test_required_artifacts_include_sampler_terminal_status(self) -> None:
        required = required_artifacts("native-trace")
        self.assertIn("gpu_sampler_status.json", required)
        self.assertEqual(len(required), 15)

    def test_final_artifact_gate_rejects_failed_sampler_status(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        scratch = Path(temporary.name)
        (scratch / "gpu_samples.csv").write_text(
            "sample_ordinal\n0\n",
            encoding="utf-8",
        )
        (scratch / "gpu_sampler_status.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "FAIL",
                    "error": "nvidia-smi sampling failed",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        audit = finalize_attempt(
            scratch=scratch,
            arm="native-trace",
            attempt_id="20260729T020000Z-p05-native-calibration-r1",
        )

        self.assertEqual(
            audit["checks"]["gpu_sampler_status"]["status"],
            "FAIL",
        )

    def test_shutdown_artifact_requires_main_cleanup_contexts_and_keepalive(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        scratch = Path(temporary.name)
        for role in ("server", "sampler"):
            (scratch / f"{role}_shutdown.json").write_text(
                json.dumps({"status": "terminated"}) + "\n",
                encoding="utf-8",
            )
        result = record_shutdown(
            scratch=scratch,
            arm="native-trace",
            attempt_id="20260729T020000Z-p05-native-calibration-r1",
            original_returncode=0,
            cleanup_returncode=0,
            contexts_proven=True,
            keepalive_ready=True,
            signal_name="",
        )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(
            json.loads(
                (scratch / "shutdown.json").read_text(encoding="utf-8")
            ),
            result,
        )

    def test_archive_refuses_nonempty_destination_before_copy(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        scratch = root / "scratch"
        destination = root / "hdfs"
        scratch.mkdir()
        destination.mkdir()
        (destination / "existing").write_text("owned\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not empty"):
            archive_attempt(
                scratch=scratch,
                hdfs_run=destination,
                arm="b0",
            )
        self.assertEqual(
            (destination / "existing").read_text(encoding="utf-8"),
            "owned\n",
        )


if __name__ == "__main__":
    unittest.main()
