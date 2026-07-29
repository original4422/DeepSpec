from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolve_module = load_script("hedge_eagle3_phase04_resolve")
run_module = load_script("hedge_eagle3_phase04_run")
calibrate_module = load_script("hedge_eagle3_phase04_calibrate")


class Phase04ConfigTest(unittest.TestCase):
    def test_three_arms_share_one_frozen_server_command(self) -> None:
        values = {
            mode: resolve_module.resolve(
                mode,
                f"20260729T034000Z-phase-04-{mode}-fixture-01",
                gate=0.25 if mode == "B+" else None,
                require_worker_hostname=False,
            )
            for mode in ("native", "B0", "B+")
        }
        self.assertTrue(
            all(
                value["source"]["final_sha"]
                == "2600c7b16c648d281be060b33ffadc7ae320f7e3"
                for value in values.values()
            )
        )
        self.assertTrue(
            all(
                value["source"]["reviewed_patch_sha256"]
                == "73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf"
                and len(value["source"]["changed_files"]) == 14
                and value["source"]["reviewed_patch"].endswith(
                    "patches/hedge_eagle3_phase04/"
                    "sglang-final-candidate.patch"
                )
                for value in values.values()
            )
        )
        self.assertTrue(
            all(
                value["command"] == values["native"]["command"]
                for value in values.values()
            )
        )
        self.assertEqual(
            {
                mode: value["environment"]["SGLANG_EAGLE3_HEDGE_MODE"]
                for mode, value in values.items()
            },
            {"native": "disabled", "B0": "b0", "B+": "enabled"},
        )


class Phase04RunnerGateTest(unittest.TestCase):
    @staticmethod
    def records(count: int) -> list[dict]:
        return [
            {
                "terminal_status": "success",
                "generation_status": "success",
                "trace_status": "success",
                "retry_count": 0,
                "trace_retry_count": 0,
                "model_answer": {"status": "ok"},
                "answer_match": True,
                "completion_tokens": 2,
                "proposal_trace": [{"proposal_id": 0}],
                "strict_rejection_barriers": [],
                "trace_metadata": {"sample_id": f"sample-{index}"},
            }
            for index in range(count)
        ]

    def test_pass_requires_complete_proposal_identity(self) -> None:
        runner = SimpleNamespace(maximum_in_flight=1)
        records = self.records(32)
        summary = run_module.build_summary(
            mode="native",
            records=records,
            runner=runner,
            started_at="start",
            finished_at="finish",
        )
        self.assertEqual(summary["status"], "PASS")
        records[7]["trace_metadata"] = {}
        failed = run_module.build_summary(
            mode="native",
            records=records,
            runner=runner,
            started_at="start",
            finished_at="finish",
        )
        self.assertEqual(failed["status"], "FAIL")
        self.assertFalse(failed["all_proposal_identity_complete"])

    def test_api_gate_requires_nonempty_response_and_complete_ids(self) -> None:
        records = self.records(3)
        for record in records:
            record["response_text"] = "answer"
            record["output_token_ids"] = [1, 2]
        summary = run_module.build_summary(
            mode="B+",
            records=records,
            runner=SimpleNamespace(maximum_in_flight=1),
            started_at="start",
            finished_at="finish",
        )
        api = run_module.build_api_smoke(
            mode="B+",
            model="fixture",
            records=records,
            summary=summary,
        )
        self.assertEqual(api["status"], "PASS")
        records[1]["response_text"] = ""
        self.assertEqual(
            run_module.build_api_smoke(
                mode="B+",
                model="fixture",
                records=records,
                summary=summary,
            )["status"],
            "FAIL",
        )


class Phase04CalibrationTest(unittest.TestCase):
    def test_b0_and_linear_q25_are_recomputable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            native_path = root / "native.jsonl"
            b0_path = root / "b0.jsonl"
            values = [float((index % 4) + 1) for index in range(32)]
            native = []
            b0 = []
            for index, value in enumerate(values):
                base = {
                    "terminal_status": "success",
                    "source_index": 1000 + index,
                    "output_token_ids": [index, index + 1],
                    "response_text": str(index),
                    "proposal_trace": [{"proposal_id": 0}],
                }
                native.append({**base, "strict_rejection_barriers": []})
                b0.append(
                    {
                        **base,
                        "strict_rejection_barriers": [
                            {
                                "sample_id": f"sample-{index}",
                                "proposal_id": 0,
                                "position": 0,
                                "regret": value,
                                "value": 1.0,
                                "regret_over_value": value,
                            }
                        ],
                    }
                )
            for path, records in ((native_path, native), (b0_path, b0)):
                path.write_text(
                    "".join(
                        json.dumps(record, sort_keys=True) + "\n"
                        for record in records
                    ),
                    encoding="utf-8",
                )
            output = root / "frozen"
            self.assertEqual(
                calibrate_module.main(
                    [
                        "--native",
                        str(native_path),
                        "--b0",
                        str(b0_path),
                        "--output-dir",
                        str(output),
                    ]
                ),
                0,
            )
            comparison = json.loads(
                (output / "b0_comparison.json").read_text()
            )
            calibration = json.loads(
                (output / "calibration.json").read_text()
            )
            expected = float(
                numpy.quantile(values, 0.25, method="linear")
            )
            self.assertEqual(comparison["status"], "B0_PASS")
            self.assertEqual(calibration["g"], expected)
            self.assertEqual(calibration["B"], expected)
            self.assertEqual(calibration["m"], 1)
            self.assertEqual(
                len(
                    (output / "positive_values.jsonl")
                    .read_text()
                    .splitlines()
                ),
                32,
            )


if __name__ == "__main__":
    unittest.main()
