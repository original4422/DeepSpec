from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hedge_dspark_p04_prepare import (  # noqa: E402
    B0_CONFIG,
    FIXED_PORT,
    build_checkpoint_identity,
    build_engine_identity,
    parse_gpu_inventory,
    parse_keepalive_status,
    prepare_attempt,
    resolve_attempt,
)
import hedge_dspark_p04_prepare as p04_prepare  # noqa: E402
from hedge_dspark_p04_gpu_sampler import (  # noqa: E402
    parse_gpu_sample,
    run_sampler,
)
from hedge_dspark_p04_client import (  # noqa: E402
    run_smoke,
    validate_server_info,
    wait_ready,
)
from hedge_dspark_p04_process import (  # noqa: E402
    ProcessIdentityError,
    capture_identity,
    record_unregistered_exit,
    terminate_registered,
    verify_registered,
)
from hedge_dspark_p04_validate import (  # noqa: E402
    REQUIRED_ARTIFACTS,
    archive_attempt,
    ensure_required_artifacts,
    finalize_attempt,
    validate_lifecycle_events,
    validate_live,
)


class ResolvedArmContractTests(unittest.TestCase):
    def test_native_has_exact_server_contract_and_no_hedge_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            resolved = resolve_attempt(
                arm="native",
                attempt_id="20260729T010203Z-p04-native-fixture",
                scratch=scratch,
            )

        command = resolved["server"]["command"]
        self.assertEqual(FIXED_PORT, 31066)
        self.assertEqual(command[0:3], [
            "/home/tiger/venvs/hedge-v4-dspark/bin/python",
            "-m",
            "sglang.launch_server",
        ])
        expected_pairs = {
            "--model-path": (
                "/mnt/hdfs/pengzegang/DeepSpec/models/"
                "deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/"
                "modelscope-"
                "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
            ),
            "--served-model-name": "deepseek-v4-flash-dspark",
            "--host": "127.0.0.1",
            "--port": "31066",
            "--tp-size": "8",
            "--speculative-algorithm": "DSPARK",
            "--speculative-dspark-block-size": "5",
            "--moe-runner-backend": "flashinfer_mxfp4",
            "--speculative-moe-runner-backend": "flashinfer_mxfp4",
            "--context-length": "4096",
            "--max-running-requests": "1",
            "--mem-fraction-static": "0.80",
        }
        for flag, expected in expected_pairs.items():
            self.assertEqual(command[command.index(flag) + 1], expected)
        for switch in (
            "--disable-cuda-graph",
            "--disable-overlap-schedule",
            "--disable-radix-cache",
        ):
            self.assertEqual(command.count(switch), 1)

        environment = resolved["server"]["environment"]
        self.assertEqual(environment["HEDGE_ENABLED"], "0")
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE"], "0"
        )
        self.assertEqual(
            environment["CUDA_VISIBLE_DEVICES"], "0,1,2,3,4,5,6,7"
        )
        self.assertEqual(environment["SGLANG_RAGGED_VERIFY_MODE"], "static")
        self.assertEqual(environment["SGLANG_DSV4_FP4_EXPERTS"], "1")
        self.assertEqual(
            environment["SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH"], "1"
        )
        self.assertEqual(environment["TOKENIZERS_PARALLELISM"], "false")
        self.assertNotIn("SGLANG_DSPARK_HEDGE_CONFIG_PATH", environment)
        self.assertNotIn("SGLANG_DSPARK_HEDGE_CONFIG_JSON", environment)
        self.assertIsNone(resolved["hedge"]["config"])
        self.assertFalse((scratch / "hedge_config.json").exists())

    def test_b0_writes_only_the_exact_frozen_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            resolved = resolve_attempt(
                arm="b0",
                attempt_id="20260729T010204Z-p04-b0-fixture",
                scratch=scratch,
            )
            config_path = scratch / "hedge_config.json"
            self.assertEqual(
                config_path.read_bytes(),
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
        self.assertEqual(
            environment["SGLANG_DSPARK_HEDGE_CONFIG_PATH"], str(config_path)
        )
        self.assertNotIn("SGLANG_DSPARK_HEDGE_CONFIG_JSON", environment)
        self.assertEqual(resolved["hedge"]["config"], B0_CONFIG)
        self.assertEqual(resolved["hedge"]["mode"], "enabled")


class ExactGpuInventoryTests(unittest.TestCase):
    def test_inventory_requires_indices_zero_through_seven_and_unique_uuids(
        self,
    ) -> None:
        payload = "\n".join(
            f"{index}, GPU-fixture-{index}, NVIDIA H20, 97871"
            for index in range(8)
        )
        rows = parse_gpu_inventory(payload)
        self.assertEqual([row["index"] for row in rows], list(range(8)))
        self.assertEqual(
            [row["uuid"] for row in rows],
            [f"GPU-fixture-{index}" for index in range(8)],
        )
        self.assertTrue(all(row["name"] == "NVIDIA H20" for row in rows))

    def test_keepalive_gate_is_exactly_eight_by_ten_at_the_floor(self) -> None:
        health = {
            "schema_version": 1,
            "healthy": True,
            "expected_gpus": 8,
            "minimum_utilization": 40.0,
            "platform_reclamation_threshold": 30.0,
            "sample_count": 10,
            "per_gpu": {
                str(index): {
                    "sample_count": 10,
                    "mean_utilization": 40.0 + index,
                    "minimum_observed": 40.0,
                    "maximum_observed": 100.0,
                }
                for index in range(8)
            },
            "underutilized_gpus": [],
        }
        raw = (
            "HEALTHY on fixture worker=4106666 pid=11 pgid=11 sid=11\n"
            + json.dumps(health)
            + "\n"
        )
        parsed = parse_keepalive_status(raw)
        self.assertEqual(parsed["status"], "PASS")
        self.assertEqual(parsed["supervisor_pid"], 11)
        self.assertEqual(parsed["health"], health)


class RuntimeIdentityTests(unittest.TestCase):
    def test_installed_engine_matches_the_fixed_p03_wheel_and_source(self) -> None:
        identity = build_engine_identity(
            decode_config_fingerprint="fixture-decode-fingerprint"
        )
        self.assertEqual(identity["status"], "PASS")
        self.assertEqual(
            identity["wheel"]["sha256"],
            "a5c14bd799117d0c491323b916a123c5"
            "c2196940dc09a5567e0a561fa8de71f9",
        )
        self.assertEqual(
            identity["source"]["upstream_base_sha"],
            "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
        )
        self.assertEqual(
            identity["hedge_core"]["deepspec_commit"],
            "4d96f44065c07030ede67484a262006ec149626a",
        )
        self.assertEqual(
            identity["dspark_integration"]["deepspec_commit"],
            "e028d2c31658a06b4f5a5ee072d7e21c79d51c36",
        )
        self.assertEqual(
            identity["decode_config_fingerprint"],
            "fixture-decode-fingerprint",
        )
        self.assertEqual(
            identity["source"]["patched_tree_sha256"],
            "69e80df97b815587a5b7b57665c99cd"
            "436b2ceb617dc71f31c7e44807ab82422",
        )
        self.assertEqual(
            identity["wheel"]["formal_actual_sha256"],
            identity["wheel"]["sha256"],
        )
        self.assertEqual(
            set(identity["wheel"]["installed_import_paths"]),
            {"sglang", "adapter", "core"},
        )
        self.assertTrue(
            all(check is True for check in identity["checks"].values())
        )

    def test_prepare_materializes_all_three_pre_pause_identity_artifacts(
        self,
    ) -> None:
        inventory = "\n".join(
            f"{index}, GPU-fixture-{index}, NVIDIA H20, 97871"
            for index in range(8)
        )
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            result = prepare_attempt(
                arm="native",
                attempt_id="20260729T010205Z-p04-native-fixture",
                scratch=scratch,
                gpu_inventory_payload=inventory,
            )
            resolved = json.loads(
                (scratch / "resolved_config.json").read_text()
            )
            engine = json.loads(
                (scratch / "engine_identity.json").read_text()
            )
            checkpoint = json.loads(
                (scratch / "checkpoint_identity.json").read_text()
            )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(resolved["arm"], "native")
        self.assertEqual(engine["status"], "PASS")
        self.assertEqual(checkpoint["status"], "PASS")
        self.assertEqual(len(resolved["gpu_inventory"]), 8)

    def test_readonly_engine_probe_cli_writes_a_passing_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "engine_identity.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "hedge_dspark_p04_prepare.py"),
                    "probe-engine",
                    "--worker-id",
                    "4106666",
                    "--decode-config-fingerprint",
                    "readonly-persistent-wheel-probe",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            identity = json.loads(output.read_text(encoding="utf-8"))
            summary = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(identity["status"], "PASS")
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["false_checks"], [])
        self.assertEqual(
            identity["wheel"]["persistent_path"],
            str(p04_prepare.PERSISTENT_WHEEL_PATH),
        )


class FormalWheelStorageDomainTests(unittest.TestCase):
    def test_persistent_path_is_required_and_build_path_is_provenance_only(
        self,
    ) -> None:
        manifest = json.loads(
            p04_prepare.WHEEL_MANIFEST.read_text(encoding="utf-8")
        )
        source_wheel = Path(
            manifest["formal_wheel"]["persistent_path"]
        )
        self.assertTrue(source_wheel.is_file())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            persistent_wheel = root / "shared/formal.whl"
            persistent_wheel.parent.mkdir()
            shutil.copyfile(source_wheel, persistent_wheel)
            ephemeral_missing = root / "worker-local-build/formal.whl"

            persistent_manifest = json.loads(json.dumps(manifest))
            persistent_manifest["formal_wheel"]["path"] = str(
                ephemeral_missing
            )
            persistent_manifest["formal_wheel"]["persistent_path"] = str(
                persistent_wheel
            )
            persistent_manifest_path = root / "persistent-manifest.json"
            self._write_json(
                persistent_manifest_path, persistent_manifest
            )
            with patch.object(
                p04_prepare,
                "WHEEL_MANIFEST",
                persistent_manifest_path,
            ), patch.object(
                p04_prepare,
                "PERSISTENT_WHEEL_PATH",
                persistent_wheel,
            ):
                identity = build_engine_identity(
                    decode_config_fingerprint="persistent-wheel-fixture"
                )
            self.assertEqual(identity["status"], "PASS")
            self.assertEqual(
                identity["wheel"]["build_path"],
                str(ephemeral_missing),
            )
            self.assertEqual(
                identity["wheel"]["verification_path"],
                str(persistent_wheel),
            )
            self.assertEqual(
                identity["wheel"]["formal_actual_sha256"],
                identity["wheel"]["sha256"],
            )

            corrupt_persistent = root / "shared/corrupt.whl"
            corrupt_persistent.write_bytes(b"not the formal wheel")
            no_fallback_manifest = json.loads(json.dumps(manifest))
            no_fallback_manifest["formal_wheel"]["path"] = str(
                source_wheel
            )
            no_fallback_manifest["formal_wheel"]["persistent_path"] = str(
                corrupt_persistent
            )
            no_fallback_manifest_path = root / "no-fallback-manifest.json"
            self._write_json(
                no_fallback_manifest_path, no_fallback_manifest
            )
            with patch.object(
                p04_prepare,
                "WHEEL_MANIFEST",
                no_fallback_manifest_path,
            ), patch.object(
                p04_prepare,
                "PERSISTENT_WHEEL_PATH",
                corrupt_persistent,
            ):
                no_fallback = build_engine_identity(
                    decode_config_fingerprint="no-fallback-fixture"
                )
            self.assertEqual(no_fallback["status"], "FAIL")
            self.assertEqual(
                no_fallback["wheel"]["verification_path"],
                str(corrupt_persistent),
            )
            self.assertNotEqual(
                no_fallback["wheel"]["formal_actual_sha256"],
                no_fallback["wheel"]["sha256"],
            )

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class EightGpuSamplerTests(unittest.TestCase):
    @staticmethod
    def _sample_payload(utilization: int) -> str:
        return "\n".join(
            (
                f"{index}, GPU-fixture-{index}, {utilization + index}, "
                f"{80000 + index}, 97871"
            )
            for index in range(8)
        )

    def test_sampler_writes_one_uuid_keyed_row_per_gpu_each_second(self) -> None:
        parsed = parse_gpu_sample(self._sample_payload(10))
        self.assertEqual(len(parsed), 8)
        self.assertEqual(
            [row["gpu_uuid"] for row in parsed],
            [f"GPU-fixture-{index}" for index in range(8)],
        )

        payloads = iter(
            [self._sample_payload(10), self._sample_payload(20)]
        )
        continuation = iter([True, True, False])
        monotonic_values = iter([1_000_000_000, 2_000_000_000])
        utc_values = iter(
            ["2026-07-29T01:00:00Z", "2026-07-29T01:00:01Z"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "gpu_samples.csv"
            status = run_sampler(
                output=output,
                query=lambda: next(payloads),
                should_continue=lambda: next(continuation),
                monotonic_ns=lambda: next(monotonic_values),
                utc_now=lambda: next(utc_values),
                sleeper=lambda _: None,
                interval_seconds=1.0,
            )
            rows = list(csv.DictReader(io.StringIO(output.read_text())))

        self.assertEqual(status["status"], "stopped")
        self.assertEqual(len(rows), 16)
        self.assertEqual(
            {row["gpu_uuid"] for row in rows},
            {f"GPU-fixture-{index}" for index in range(8)},
        )
        self.assertEqual(
            [int(row["monotonic_ns"]) for row in rows[::8]],
            [1_000_000_000, 2_000_000_000],
        )

    def test_sampler_stops_cleanly_when_stop_interrupts_active_query(
        self,
    ) -> None:
        running = True

        def interrupted_query() -> str:
            nonlocal running
            running = False
            raise RuntimeError("nvidia-smi sampling failed: terminated")

        with tempfile.TemporaryDirectory() as temporary:
            status = run_sampler(
                output=Path(temporary) / "gpu_samples.csv",
                query=interrupted_query,
                should_continue=lambda: running,
                sleeper=lambda _: None,
                interval_seconds=1.0,
            )

        self.assertEqual(
            status,
            {
                "schema_version": 1,
                "status": "stopped",
                "sample_count": 0,
                "expected_gpus": 8,
                "gpu_uuids": [],
                "interval_seconds": 1.0,
            },
        )

    def test_sampler_fails_when_active_query_has_real_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                RuntimeError, "nvidia-smi sampling failed: device lost"
            ):
                run_sampler(
                    output=Path(temporary) / "gpu_samples.csv",
                    query=lambda: (_ for _ in ()).throw(
                        RuntimeError(
                            "nvidia-smi sampling failed: device lost"
                        )
                    ),
                    should_continue=lambda: True,
                    sleeper=lambda _: None,
                    interval_seconds=1.0,
                )


class P04ClientAndCounterTests(unittest.TestCase):
    @staticmethod
    def _sample() -> dict:
        path = (
            REPO_ROOT
            / "artifacts/hedge-dspark/p01-protocol/"
            "gsm8k_calibration_32.jsonl"
        )
        return json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    @staticmethod
    def _response() -> dict:
        return {
            "id": "fixture-response",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": r"reasoning \boxed{18}",
                    },
                    "finish_reason": "stop",
                    "meta_info": {"output_token_ids": [101, 102, 103]},
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 3,
                "total_tokens": 23,
            },
        }

    @staticmethod
    def _server_info(*, arm: str, proposals: int) -> dict:
        config = None if arm == "native" else dict(B0_CONFIG)
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
                {
                    "dspark_info_record": {
                        "hedge": {
                            "mode": (
                                "disabled"
                                if arm == "native"
                                else "enabled"
                            ),
                            "experiment_switches": {
                                "HEDGE_ENABLED": (
                                    0 if arm == "native" else 1
                                ),
                                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
                            },
                            "config": config,
                            "gamma": 5,
                            "verify_num_draft_tokens": 6,
                            "proposals": proposals,
                            "state_leaks": 0,
                        }
                    }
                }
            ],
        }

    def test_client_uses_first_calibration_request_and_saves_real_token_ids(
        self,
    ) -> None:
        observed: list[tuple[str, dict, float]] = []

        def transport(url: str, payload: dict, timeout: float) -> dict:
            observed.append((url, payload, timeout))
            return self._response()

        api, counters = run_smoke(
            arm="b0",
            base_url="http://fixture",
            sample=self._sample(),
            chat_transport=transport,
            server_info_get=lambda url, timeout: self._server_info(
                arm="b0", proposals=4
            ),
            sleeper=lambda _: None,
        )
        self.assertEqual(api["status"], "PASS")
        self.assertEqual(api["output_token_ids"], [101, 102, 103])
        self.assertEqual(api["completion_tokens"], 3)
        self.assertEqual(api["raw_response"], self._response())
        request = observed[0][1]
        self.assertEqual(len(request["messages"]), 1)
        self.assertEqual(request["messages"][0]["role"], "user")
        self.assertTrue(
            request["messages"][0]["content"].endswith(
                "Please reason step by step, and put your final answer "
                r"within \boxed{}."
            )
        )
        self.assertNotIn("system", request)
        self.assertEqual(
            request["chat_template_kwargs"], {"enable_thinking": False}
        )
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["top_p"], 1)
        self.assertEqual(request["max_tokens"], 512)
        self.assertFalse(request["stream"])
        self.assertTrue(request["return_meta_info"])
        self.assertEqual(counters["status"], "PASS")
        self.assertEqual(counters["proposal_count"], 4)

    def test_b0_counter_requires_enabled_exact_config_and_positive_proposals(
        self,
    ) -> None:
        evidence = validate_server_info(
            self._server_info(arm="b0", proposals=1), arm="b0"
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["hedge_snapshots"][0]["config"], B0_CONFIG)
        broken = self._server_info(arm="b0", proposals=0)
        with self.assertRaisesRegex(ValueError, "positive proposals"):
            validate_server_info(broken, arm="b0")

    def test_ready_waiter_accepts_empty_health_body_and_watches_identity(
        self,
    ) -> None:
        calls: list[str] = []
        result = wait_ready(
            base_url="http://fixture",
            server_pid=123,
            server_start_ticks="456",
            timeout_seconds=3600,
            health_get=lambda url, timeout: calls.append(url) or 200,
            process_alive=lambda: True,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(calls, ["http://fixture/health"])

    def test_checkpoint_identity_reuses_metadata_without_hashing_weight_bytes(
        self,
    ) -> None:
        identity = build_checkpoint_identity()
        self.assertEqual(identity["status"], "PASS")
        self.assertEqual(identity["file_count"], 75)
        self.assertEqual(identity["shard_count"], 48)
        self.assertEqual(identity["total_bytes"], 166898666759)
        self.assertEqual(
            identity["snapshot_identity"],
            "bb7ac3172e1a257482d3256d7a720f20"
            "ea39ce25625f3cacc1091f59ad43bcae",
        )
        self.assertFalse(identity["full_checkpoint_hash_performed"])
        self.assertTrue(
            all(check is True for check in identity["checks"].values())
        )


class RegisteredProcessGuardTests(unittest.TestCase):
    def test_unregistered_early_exit_is_safe_only_after_pid_is_gone(
        self,
    ) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            preexec_fn=os.setsid,
        )
        try:
            deadline = time.monotonic() + 5
            state = ""
            while time.monotonic() < deadline:
                stat_path = Path(f"/proc/{child.pid}/stat")
                if stat_path.is_file():
                    stat = stat_path.read_text(encoding="utf-8")
                    state = stat[stat.rfind(")") + 2 :].split()[0]
                    if state == "Z":
                        break
                time.sleep(0.01)
            self.assertEqual(state, "Z")
            result = record_unregistered_exit(
                pid=child.pid, role="fixture"
            )
            self.assertEqual(result["status"], "already_exited")
            self.assertIn(
                result["observed_state"], {"zombie", "not_present"}
            )
            self.assertTrue(result["hostname"])
        finally:
            child.wait(timeout=5)

        live = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                "p04-live-unregistered-fixture",
            ],
            preexec_fn=os.setsid,
        )
        try:
            with self.assertRaisesRegex(
                ProcessIdentityError, "still alive"
            ):
                record_unregistered_exit(pid=live.pid, role="fixture")
        finally:
            identity = capture_identity(
                pid=live.pid,
                role="fixture",
                required_arg="p04-live-unregistered-fixture",
            )
            terminate_registered(identity, timeout_seconds=5)
            live.wait(timeout=5)

    def test_cleanup_refuses_changed_ticks_or_cmdline_before_signaling(self) -> None:
        marker = "deepspec-p04-process-fixture"
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                marker,
            ],
            preexec_fn=os.setsid,
        )
        try:
            identity = capture_identity(
                pid=child.pid,
                role="fixture",
                required_arg=marker,
            )
            verify_registered(identity)

            changed_ticks = dict(identity)
            changed_ticks["start_ticks"] = str(
                int(identity["start_ticks"]) + 1
            )
            signal_mock = Mock()
            with self.assertRaisesRegex(
                ProcessIdentityError, "start ticks"
            ):
                terminate_registered(
                    changed_ticks,
                    timeout_seconds=0.1,
                    kill_group=signal_mock,
                )
            signal_mock.assert_not_called()

            changed_cmdline = dict(identity)
            changed_cmdline["cmdline"] = [
                *identity["cmdline"],
                "unexpected",
            ]
            with self.assertRaisesRegex(ProcessIdentityError, "cmdline"):
                terminate_registered(
                    changed_cmdline,
                    timeout_seconds=0.1,
                    kill_group=signal_mock,
                )
            signal_mock.assert_not_called()

            outcome = terminate_registered(
                identity,
                timeout_seconds=5,
            )
            self.assertIn(
                outcome["status"],
                {"terminated", "already_exited"},
            )
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, 9)
                child.wait(timeout=5)


class LifecycleContractTests(unittest.TestCase):
    def test_cleanup_stops_registered_groups_before_resuming_keepalive(
        self,
    ) -> None:
        script = REPO_ROOT / "scripts/hedge_dspark_p04_attempt.sh"
        completed = subprocess.run(
            ["bash", str(script), "--print-contract"],
            check=True,
            capture_output=True,
            text=True,
        )
        contract = json.loads(completed.stdout)
        self.assertEqual(contract["worker_id"], "4106666")
        self.assertEqual(contract["expected_gpus"], 8)
        self.assertEqual(contract["port"], 31066)
        cleanup = contract["cleanup_order"]
        self.assertEqual(
            cleanup,
            [
                "terminate_registered_server",
                "prove_cuda_contexts_none",
                "terminate_registered_sampler",
                "resume_keepalive_if_cleanup_proven",
                "validate_keepalive_8x10_mean_ge_40",
                "validate_required_artifacts",
                "archive_without_overwrite",
            ],
        )
        script_text = script.read_text(encoding="utf-8")
        self.assertIn(
            '"$server_pid" server "$SCRATCH/server_shutdown.json"',
            script_text,
        )
        self.assertIn(
            '"$sampler_pid" sampler "$SCRATCH/sampler_shutdown.json"',
            script_text,
        )


class P04ArtifactValidatorTests(unittest.TestCase):
    REQUIRED = {
        "resolved_config.json",
        "engine_identity.json",
        "checkpoint_identity.json",
        "server.log",
        "gpu_samples.csv",
        "gpu_sampler_status.json",
        "api_smoke.json",
        "hedge_counters.json",
        "shutdown.json",
        "cuda_contexts_after.txt",
        "keepalive_before.json",
        "keepalive_after.json",
    }

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _resolved(arm: str, attempt_id: str, scratch: Path) -> dict:
        resolved = resolve_attempt(
            arm=arm,
            attempt_id=attempt_id,
            scratch=scratch,
        )
        resolved["gpu_inventory"] = [
            {
                "index": index,
                "uuid": f"GPU-fixture-{index}",
                "name": "NVIDIA H20",
                "memory_total_mib": 97871,
            }
            for index in range(8)
        ]
        return resolved

    @staticmethod
    def _server_log() -> str:
        lines = [
            "server_args tp_size=8 speculative_algorithm='DSPARK' "
            "speculative_dspark_block_size=5",
            "moe_runner_backend=flashinfer_mxfp4 "
            "quant_method=Mxfp4FlashinferCutlassMoEMethod",
            "100% Completed | 48/48 [target]",
            "100% Completed | 48/48 [draft]",
            "Initialized DSpark draft runner gamma=5 "
            "verify_num_draft_tokens=6",
            "The server is fired up and ready to roll!",
        ]
        for rank in range(8):
            lines.extend(
                [
                    f"[2026-07-29 TP{rank}] rank {rank} nranks 8 "
                    "NCCL Init COMPLETE",
                    f"[2026-07-29 TP{rank}] Load weight end. "
                    "type=DeepseekV4ForCausalLM, quant=fp8.",
                    f"[2026-07-29 TP{rank}] Draft checkpoint bundles a "
                    "DSpark head; loading draft arch "
                    "DeepseekV4ForCausalLMDSpark.",
                    f"[2026-07-29 TP{rank}] Load weight end. "
                    "type=DeepseekV4ForCausalLMDSpark, quant=fp8.",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _write_samples(
        path: Path,
        *,
        omit_gpu: int | None = None,
        omit_ordinal: int | None = None,
        sample_times_ns: list[int] | None = None,
    ) -> None:
        times = sample_times_ns or [
            (ordinal + 1) * 1_000_000_000 for ordinal in range(6)
        ]
        fields = [
            "sample_ordinal",
            "timestamp_utc",
            "monotonic_ns",
            "gpu_index",
            "gpu_uuid",
            "utilization_gpu_percent",
            "memory_used_mib",
            "memory_total_mib",
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for ordinal, sample_time in enumerate(times):
                if omit_ordinal == ordinal:
                    continue
                for index in range(8):
                    if omit_gpu == index and ordinal == 3:
                        continue
                    writer.writerow(
                        {
                            "sample_ordinal": ordinal,
                            "timestamp_utc": (
                                datetime(
                                    2026, 7, 29, 1, 0, ordinal,
                                    tzinfo=timezone.utc,
                                )
                                .isoformat()
                                .replace("+00:00", "Z")
                            ),
                            "monotonic_ns": sample_time,
                            "gpu_index": index,
                            "gpu_uuid": f"GPU-fixture-{index}",
                            "utilization_gpu_percent": 50 + index,
                            "memory_used_mib": 80000 + index,
                            "memory_total_mib": 97871,
                        }
                    )

    def _write_live_fixture(
        self,
        scratch: Path,
        *,
        arm: str = "b0",
        omit_gpu: int | None = None,
        omit_ordinal: int | None = None,
        sample_times_ns: list[int] | None = None,
    ) -> str:
        attempt_id = f"20260729T010203Z-p04-{arm}-fixture"
        resolved = self._resolved(arm, attempt_id, scratch)
        self._write_json(scratch / "resolved_config.json", resolved)
        self._write_json(
            scratch / "engine_identity.json",
            {
                "status": "PASS",
                "decode_config_fingerprint": (
                    resolved["decode_config_fingerprint"]
                ),
            },
        )
        self._write_json(
            scratch / "checkpoint_identity.json",
            {"status": "PASS"},
        )
        self._write_json(
            scratch / "api_smoke.json",
            {
                "status": "PASS",
                "arm": arm,
                "request_started_monotonic_ns": 2_000_000_000,
                "request_finished_monotonic_ns": 4_000_000_000,
                "raw_response": {"id": "fixture"},
                "output_token_ids": [101, 102, 103],
                "completion_tokens": 3,
            },
        )
        self._write_json(
            scratch / "hedge_counters.json",
            {
                "status": "PASS",
                "arm": arm,
                "proposal_count": 4 if arm == "b0" else 0,
                "hedge_snapshots": [
                    {
                        "mode": "enabled" if arm == "b0" else "disabled",
                        "experiment_switches": {
                            "HEDGE_ENABLED": 1 if arm == "b0" else 0,
                            "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
                        },
                        "config": dict(B0_CONFIG) if arm == "b0" else None,
                        "gamma": 5,
                        "verify_num_draft_tokens": 6,
                        "proposals": 4 if arm == "b0" else 0,
                    }
                ],
                "request_interval_monotonic_ns": {
                    "start": 2_000_000_000,
                    "end": 4_000_000_000,
                },
            },
        )
        (scratch / "server.log").write_text(
            self._server_log(), encoding="utf-8"
        )
        self._write_samples(
            scratch / "gpu_samples.csv",
            omit_gpu=omit_gpu,
            omit_ordinal=omit_ordinal,
            sample_times_ns=sample_times_ns,
        )
        return attempt_id

    @staticmethod
    def _set_request_interval(
        scratch: Path, *, start: int, end: int
    ) -> None:
        api_path = scratch / "api_smoke.json"
        api = json.loads(api_path.read_text(encoding="utf-8"))
        api["request_started_monotonic_ns"] = start
        api["request_finished_monotonic_ns"] = end
        P04ArtifactValidatorTests._write_json(api_path, api)
        counters_path = scratch / "hedge_counters.json"
        counters = json.loads(counters_path.read_text(encoding="utf-8"))
        counters["request_interval_monotonic_ns"] = {
            "start": start,
            "end": end,
        }
        P04ArtifactValidatorTests._write_json(counters_path, counters)

    def test_required_artifact_set_includes_sampler_terminal_status(self) -> None:
        self.assertEqual(set(REQUIRED_ARTIFACTS), self.REQUIRED)
        self.assertEqual(len(REQUIRED_ARTIFACTS), 12)

    def test_live_validator_accepts_exact_b0_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            attempt_id = self._write_live_fixture(scratch)
            audit = validate_live(
                scratch=scratch,
                arm="b0",
                attempt_id=attempt_id,
            )
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["gpu_evidence"]["sample_count"], 6)
        self.assertEqual(len(audit["gpu_evidence"]["gpu_uuids"]), 8)
        self.assertTrue(audit["gpu_evidence"]["request_bracketed"])
        self.assertEqual(audit["server_log"]["tp_ranks"], list(range(8)))

    def test_final_artifact_gate_rejects_failed_sampler_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            self._write_samples(scratch / "gpu_samples.csv")
            self._write_json(
                scratch / "gpu_sampler_status.json",
                {
                    "schema_version": 1,
                    "status": "FAIL",
                    "error": "nvidia-smi sampling failed",
                },
            )
            audit = finalize_attempt(
                scratch=scratch,
                arm="b0",
                attempt_id="20260729T010203Z-p04-b0-fixture",
            )

        self.assertEqual(
            audit["checks"]["gpu_sampler_status"]["status"],
            "FAIL",
        )

    def test_final_artifact_gate_rejects_sampler_csv_count_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            self._write_samples(scratch / "gpu_samples.csv")
            self._write_json(
                scratch / "gpu_sampler_status.json",
                {
                    "schema_version": 1,
                    "status": "stopped",
                    "sample_count": 5,
                },
            )
            audit = finalize_attempt(
                scratch=scratch,
                arm="b0",
                attempt_id="20260729T010203Z-p04-b0-fixture",
            )

        self.assertEqual(
            audit["checks"]["gpu_sampler_status"]["status"],
            "FAIL",
        )

    def test_final_artifact_gate_accepts_stopped_sampler_with_csv_count(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            self._write_samples(scratch / "gpu_samples.csv")
            self._write_json(
                scratch / "gpu_sampler_status.json",
                {
                    "schema_version": 1,
                    "status": "stopped",
                    "sample_count": 6,
                },
            )
            audit = finalize_attempt(
                scratch=scratch,
                arm="b0",
                attempt_id="20260729T010203Z-p04-b0-fixture",
            )

        self.assertEqual(
            audit["checks"]["gpu_sampler_status"],
            {
                "status": "PASS",
                "sample_count": 6,
                "csv_sample_ordinal_count": 6,
            },
        )

    def test_off_request_scheduler_jitter_is_diagnostic_not_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            attempt_id = self._write_live_fixture(
                scratch,
                sample_times_ns=[
                    1_000_000_000,
                    2_000_000_000,
                    3_000_000_000,
                    4_000_000_000,
                    6_600_000_000,
                    7_600_000_000,
                ],
            )
            audit = validate_live(
                scratch=scratch,
                arm="b0",
                attempt_id=attempt_id,
            )
        cadence = audit["gpu_evidence"]["cadence"]
        self.assertEqual(cadence["interval_seconds_target"], 1.0)
        self.assertEqual(cadence["global"]["outlier_count_gt_2_5s"], 1)
        self.assertAlmostEqual(cadence["global"]["max_seconds"], 2.6)
        self.assertEqual(
            cadence["request_window"]["outlier_count_gt_2_5s"], 0
        )

    def test_live_validator_rejects_any_incomplete_eight_gpu_sample(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            attempt_id = self._write_live_fixture(
                scratch, omit_gpu=7
            )
            with self.assertRaisesRegex(
                ValueError, "sample ordinal 3.*exactly 8"
            ):
                validate_live(
                    scratch=scratch,
                    arm="b0",
                    attempt_id=attempt_id,
                )

    def test_structural_and_request_window_evidence_remains_fail_closed(
        self,
    ) -> None:
        cases = (
            {
                "name": "missing ordinal",
                "fixture": {"omit_ordinal": 3},
                "interval": None,
                "error": "ordinals must be contiguous",
            },
            {
                "name": "missing row",
                "fixture": {"omit_gpu": 7},
                "interval": None,
                "error": "must contain exactly 8 rows",
            },
            {
                "name": "nonmonotonic timestamps",
                "fixture": {
                    "sample_times_ns": [
                        1_000_000_000,
                        2_000_000_000,
                        3_000_000_000,
                        2_500_000_000,
                        5_000_000_000,
                        6_000_000_000,
                    ]
                },
                "interval": None,
                "error": "timestamps are not strictly increasing",
            },
            {
                "name": "no request sample",
                "fixture": {},
                "interval": (2_200_000_000, 2_800_000_000),
                "error": "no observation during the API request",
            },
            {
                "name": "request unbracketed",
                "fixture": {},
                "interval": (500_000_000, 4_000_000_000),
                "error": "do not bracket the API request interval",
            },
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                with tempfile.TemporaryDirectory() as temporary:
                    scratch = Path(temporary)
                    attempt_id = self._write_live_fixture(
                        scratch, **case["fixture"]
                    )
                    if case["interval"] is not None:
                        self._set_request_interval(
                            scratch,
                            start=case["interval"][0],
                            end=case["interval"][1],
                        )
                    with self.assertRaisesRegex(
                        ValueError, case["error"]
                    ):
                        validate_live(
                            scratch=scratch,
                            arm="b0",
                            attempt_id=attempt_id,
                        )

    def test_failure_placeholders_make_missing_artifacts_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            missing = ensure_required_artifacts(
                scratch=scratch,
                reason="fixture stopped before model start",
            )
            names = {path.name for path in scratch.iterdir()}
            api = json.loads(
                (scratch / "api_smoke.json").read_text(encoding="utf-8")
            )
        self.assertEqual(set(missing), self.REQUIRED)
        self.assertTrue(self.REQUIRED.issubset(names))
        self.assertEqual(api["status"], "MISSING")
        self.assertIn("fixture stopped", api["reason"])

    def test_lifecycle_validator_enforces_cleanup_before_resume(self) -> None:
        expected = [
            "terminate_registered_server",
            "prove_cuda_contexts_none",
            "terminate_registered_sampler",
            "resume_keepalive_if_cleanup_proven",
            "validate_keepalive_8x10_mean_ge_40",
            "validate_required_artifacts",
            "archive_without_overwrite",
        ]
        self.assertEqual(
            validate_lifecycle_events(
                [{"stage": stage} for stage in expected]
            )["status"],
            "PASS",
        )
        with self.assertRaisesRegex(ValueError, "cleanup stage order"):
            validate_lifecycle_events(
                [
                    {"stage": "resume_keepalive_if_cleanup_proven"},
                    {"stage": "terminate_registered_server"},
                ]
            )

    def test_archive_hashes_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scratch = root / "scratch"
            destination = root / "hdfs-run"
            scratch.mkdir()
            destination.mkdir()
            for name in REQUIRED_ARTIFACTS:
                (scratch / name).write_text(
                    f"fixture:{name}\n", encoding="utf-8"
                )
            result = archive_attempt(
                scratch=scratch, hdfs_run=destination
            )
            manifest = json.loads(
                (destination / "archive_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                {record["path"] for record in manifest["files"]},
                self.REQUIRED,
            )
            with self.assertRaisesRegex(
                FileExistsError, "destination is not empty"
            ):
                archive_attempt(
                    scratch=scratch, hdfs_run=destination
                )
