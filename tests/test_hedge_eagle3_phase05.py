from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolve_module = load_script("hedge_eagle3_phase05_resolve")
run_module = load_script("hedge_eagle3_phase05_run")


def record(position: int, *, warmup: bool) -> dict:
    return {
        "schema_version": 1,
        "phase": "warmup" if warmup else "formal",
        "position": position,
        "timed": not warmup,
        "partition": "calibration" if warmup else "formal",
        "partition_index": position,
        "source_index": position if warmup else position + 1000,
        "attempts": [{"attempt": 1, "status": "success"}],
        "attempt_count": 1,
        "retry_count": 0,
        "generation_retry_count": 0,
        "trace_retry_count": 0,
        "generation_status": "success",
        "trace_status": "success",
        "terminal_status": "success",
        "first_request_monotonic_started": None if warmup else float(position),
        "record_terminal_monotonic": None if warmup else float(position + 1),
        "full_response": {"id": f"request-{position}"},
        "response_text": r"The answer is \boxed{1}.",
        "output_token_ids": [42],
        "completion_tokens": 1,
        "proposal_trace": [
            {
                "proposal_id": 0,
                "sample_id": f"request-{position}",
                "strict_accepted_drafts": 3,
                "hedge_accepted_drafts": 3,
                "commit_length": 4,
            },
            {
                "proposal_id": 1,
                "sample_id": f"request-{position}",
                "strict_accepted_drafts": 1,
                "hedge_accepted_drafts": 1,
                "commit_length": 2,
            },
        ],
        "reference_answer": {"status": "ok", "normalized": "1"},
        "model_answer": {"status": "ok", "normalized": "1"},
        "answer_match": True,
    }


class Phase05FormalToolTest(unittest.TestCase):
    def test_native_wrapper_preserves_phase04_server_command(self) -> None:
        phase05 = resolve_module.resolve_native(
            "20260729T060000Z-phase-05-native-formal-01",
            require_worker_hostname=False,
        )
        phase04 = resolve_module.phase04.resolve(
            "native",
            "20260729T060000Z-phase-05-native-formal-01",
            gate=None,
            require_worker_hostname=False,
        )
        self.assertEqual(phase05["command"], phase04["command"])
        self.assertEqual(phase05["environment"], phase04["environment"])
        self.assertEqual(phase05["source"], phase04["source"])
        self.assertEqual(phase05["phase"], "05")
        self.assertEqual(
            phase05["environment"]["SGLANG_EAGLE3_HEDGE_MODE"], "disabled"
        )
        self.assertNotIn(
            "SGLANG_EAGLE3_HEDGE_CONFIG_JSON", phase05["environment"]
        )

    def test_ten_warmup_then_500_formal_summary_is_recomputable(self) -> None:
        warmup = [record(index, warmup=True) for index in range(10)]
        formal = [record(index, warmup=False) for index in range(500)]
        protocol_run = {
            "schema_version": 1,
            "warmup_count": 10,
            "formal_count": 500,
            "maximum_in_flight": 1,
            "formal_monotonic_started": 0.0,
            "formal_monotonic_finished": 500.0,
            "formal_wall_seconds": 500.0,
            "warmup": warmup,
            "formal": formal,
        }
        runner = SimpleNamespace(
            run=lambda manifest, warmup_count: protocol_run
        )
        manifest = {
            "calibration": [
                {"source_index": index} for index in range(32)
            ],
            "formal": [
                {"source_index": index + 1000} for index in range(500)
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = run_module.run_and_write(
                manifest=manifest,
                runner=runner,
                output_dir=output,
                dataset_sha256=run_module.EXPECTED_DATASET_SHA256,
            )
            self.assertEqual(
                len((output / "warmup_outputs.jsonl").read_text().splitlines()),
                10,
            )
            self.assertEqual(
                len((output / "request_outputs.jsonl").read_text().splitlines()),
                500,
            )
            self.assertEqual(
                len((output / "acceptance_trace.jsonl").read_text().splitlines()),
                1000,
            )
            self.assertEqual(summary["total"], 500)
            self.assertEqual(summary["completion_tokens"], 500)
            self.assertEqual(summary["timed_seconds"], 500.0)
            self.assertEqual(summary["output_tps"], 1.0)
            self.assertEqual(summary["proposal_count"], 1000)
            self.assertEqual(
                summary["accepted_draft_tokens_per_proposal"], 2.0
            )
            self.assertEqual(summary["mean_accept_length"], 3.0)
            self.assertEqual(
                summary["acceptance_length_distribution"],
                {"2": 500, "4": 500},
            )
            self.assertEqual(
                summary["accepted_by_position"],
                [
                    {"position": 0, "accepted": 1000, "rate": 1.0},
                    {"position": 1, "accepted": 500, "rate": 0.5},
                    {"position": 2, "accepted": 500, "rate": 0.5},
                ],
            )

    def test_duplicate_guard_rejects_existing_output_or_accepted_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "attempt"
            marker = root / "native.complete.json"
            output.mkdir()
            (output / "summary.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "formal output"):
                run_module.assert_available(output, marker)
            (output / "summary.json").unlink()
            marker.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "accepted native"):
                run_module.assert_available(output, marker)


if __name__ == "__main__":
    unittest.main()
