"""Public-seam tests for P05 calibration trace scoping."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hedge_dspark_p05_client as client  # noqa: E402
import hedge_dspark_p05_reduce as reducer  # noqa: E402


CALIBRATION_PATH = (
    REPO_ROOT
    / "artifacts/hedge-dspark/p01-protocol/gsm8k_calibration_32.jsonl"
)
CALIBRATION_INDICES = [
    json.loads(line)["dataset_index"]
    for line in CALIBRATION_PATH.read_text(encoding="utf-8").splitlines()
]


class P05TraceScopeClientTests(unittest.TestCase):
    @staticmethod
    def _snapshot(
        *,
        proposals: int,
        trace: list[dict[str, Any]],
        requests_initialized: int,
        requests_finished: int,
    ) -> dict[str, Any]:
        return {
            "mode": "calibration",
            "experiment_switches": {
                "HEDGE_ENABLED": 0,
                "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 1,
            },
            "config": None,
            "config_fingerprint": None,
            "gamma": 5,
            "verify_num_draft_tokens": 6,
            "counter_schema_version": 1,
            "proposals": proposals,
            "draft_tokens_verifiable": proposals * 5,
            "strict_accepted_draft_tokens": proposals,
            "hedge_accepted_draft_tokens": proposals,
            "hedge_accepted_draft_tokens_by_position": [
                proposals,
                0,
                0,
                0,
                0,
            ],
            "relaxed_mismatches": 0,
            "regret_charged": 0.0,
            "cap_trim_lens": 0,
            "budget_exhaustion_events": 0,
            "remaining_budget_total": 0.0,
            "requests_initialized": requests_initialized,
            "requests_finished": requests_finished,
            "requests_non_natural": 0,
            "slot_reuse_resets": 0,
            "active_request_states": 0,
            "state_leaks": 0,
            "remaining_budget_by_request": [],
            "strict_rejection_trace": trace,
            "trace_rows_seen": len(trace),
            "trace_rows_dropped": 0,
        }

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

    def test_scoped_client_clears_and_verifies_before_first_cohort_request(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        artifact_dir = Path(temporary.name)
        events: list[str] = []
        posts: list[tuple[str, Mapping[str, Any], float]] = []
        response_ids = [f"cohort-{ordinal:02d}" for ordinal in range(32)]

        cleared = self._snapshot(
            proposals=0,
            trace=[],
            requests_initialized=0,
            requests_finished=0,
        )
        post_cohort = self._snapshot(
            proposals=1,
            trace=[
                {
                    "proposal_ordinal": 0,
                    "request_serial": 1,
                    "rid": response_ids[0],
                    "request_pool_slot": 0,
                    "forward_ct": 1,
                    "barrier_position": 0,
                    "regret": 1.0,
                    "value": 1.0,
                    "regret_per_value": 1.0,
                }
            ],
            requests_initialized=32,
            requests_finished=32,
        )

        def state_post(
            url: str, payload: Mapping[str, Any], timeout: float
        ) -> Any:
            events.append("clear")
            posts.append((url, payload, timeout))
            return [True]

        get_count = 0

        def state_get(_url: str, _timeout: float) -> Mapping[str, Any]:
            nonlocal get_count
            get_count += 1
            if get_count == 1:
                events.append("verify-clear")
                return self._server_info(cleared)
            events.append("post-snapshot")
            return self._server_info(post_cohort)

        def transport(
            _url: str, _payload: dict[str, Any], _timeout: float
        ) -> Mapping[str, Any]:
            ordinal = sum(event == "request" for event in events)
            events.append("request")
            return {
                "id": response_ids[ordinal],
                "choices": [
                    {
                        "message": {"content": f"work \\\\boxed{{{ordinal}}}"},
                        "meta_info": {"output_token_ids": [80000 + ordinal]},
                    }
                ],
                "usage": {"completion_tokens": 1},
            }

        result = client.run_scoped_calibration_arm(
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
            server_info_get=state_get,
            internal_state_post=state_post,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(events[:3], ["clear", "verify-clear", "request"])
        self.assertEqual(events.count("request"), 32)
        self.assertEqual(events[-1], "post-snapshot")
        self.assertEqual(
            posts,
            [
                (
                    "http://127.0.0.1:31066/set_internal_state",
                    {"server_args": {"dspark_clear_info_records": 1}},
                    300.0,
                )
            ],
        )
        counters = json.loads(
            (artifact_dir / "hedge_counters.json").read_text(encoding="utf-8")
        )
        self.assertTrue(counters["trace_scope_proven"])
        self.assertEqual(counters["cohort_response_ids"], response_ids)
        self.assertEqual(
            counters["pre_cohort_clear"],
            {
                "status": "PASS",
                "source_endpoint": "/set_internal_state",
                "request_body": {
                    "server_args": {"dspark_clear_info_records": 1}
                },
                "response": [True],
                "verified_snapshot_count": 1,
            },
        )

    def test_post_cohort_snapshot_rejects_ready_probe_trace_rid(self) -> None:
        response_ids = [f"cohort-{ordinal:02d}" for ordinal in range(32)]
        ready_probe_rid = "505959725a104b34a193d3f481be36ac"
        snapshot = self._snapshot(
            proposals=2,
            trace=[
                {
                    "proposal_ordinal": 0,
                    "request_serial": 1,
                    "rid": response_ids[0],
                    "request_pool_slot": 0,
                    "forward_ct": 1,
                    "barrier_position": 0,
                    "regret": 1.0,
                    "value": 1.0,
                    "regret_per_value": 1.0,
                },
                {
                    "proposal_ordinal": 1,
                    "request_serial": 2,
                    "rid": ready_probe_rid,
                    "request_pool_slot": 0,
                    "forward_ct": 2,
                    "barrier_position": 0,
                    "regret": 2.0,
                    "value": 1.0,
                    "regret_per_value": 2.0,
                },
            ],
            requests_initialized=33,
            requests_finished=33,
        )

        with self.assertRaisesRegex(ValueError, ready_probe_rid):
            client.validate_server_snapshot(
                self._server_info(snapshot),
                arm="native-trace",
                cohort_response_ids=response_ids,
            )

    def test_scoped_client_refuses_dirty_clear_snapshot_before_requests(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        artifact_dir = Path(temporary.name)
        requests_sent = 0
        dirty = self._snapshot(
            proposals=1,
            trace=[],
            requests_initialized=1,
            requests_finished=1,
        )

        def transport(
            _url: str, _payload: dict[str, Any], _timeout: float
        ) -> Mapping[str, Any]:
            nonlocal requests_sent
            requests_sent += 1
            raise AssertionError("cohort request must not be sent")

        with self.assertRaisesRegex(ValueError, "nonzero counters"):
            client.run_scoped_calibration_arm(
                arm="native-trace",
                base_url="http://127.0.0.1:31066",
                dataset=CALIBRATION_PATH,
                outputs_path=artifact_dir / "native.jsonl",
                summary_path=artifact_dir / "summary.json",
                counters_path=artifact_dir / "counters.json",
                trace_path=artifact_dir / "trace.jsonl",
                transport=transport,
                server_info_get=lambda _url, _timeout: self._server_info(dirty),
                internal_state_post=lambda _url, _payload, _timeout: [True],
                sleeper=lambda _seconds: None,
            )
        self.assertEqual(requests_sent, 0)
        self.assertFalse((artifact_dir / "native.jsonl").exists())


class P05TraceScopeReducerTests(unittest.TestCase):
    @staticmethod
    def _write_jsonl(path: Path, records: list[Mapping[str, Any]]) -> None:
        path.write_text(
            "".join(
                json.dumps(record, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def test_scoped_reducer_rejects_current_artifact_ready_probe_rid(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        native = root / "native.jsonl"
        b0 = root / "b0.jsonl"
        trace = root / "trace.jsonl"
        counters = root / "counters.json"
        output = root / "result"
        response_ids = [f"cohort-{ordinal:02d}" for ordinal in range(32)]
        ready_probe_rid = "505959725a104b34a193d3f481be36ac"
        outputs = [
            {
                "cohort": "calibration",
                "cohort_position": position,
                "dataset_index": dataset_index,
                "terminal_status": "succeeded",
                "output_token_ids": [90000 + position],
                "attempts": [
                    {
                        "status": "success",
                        "raw_response": {"id": response_ids[position]},
                    }
                ],
            }
            for position, dataset_index in enumerate(CALIBRATION_INDICES)
        ]
        self._write_jsonl(native, outputs)
        self._write_jsonl(b0, outputs)
        trace_rows = [
            {
                "snapshot_index": 0,
                "proposal_ordinal": 0,
                "request_serial": 1,
                "rid": response_ids[0],
                "request_pool_slot": 0,
                "forward_ct": 1,
                "barrier_position": 0,
                "regret": 1.0,
                "value": 1.0,
                "regret_per_value": 1.0,
            },
            {
                "snapshot_index": 0,
                "proposal_ordinal": 1,
                "request_serial": 2,
                "rid": ready_probe_rid,
                "request_pool_slot": 0,
                "forward_ct": 2,
                "barrier_position": 0,
                "regret": 2.0,
                "value": 1.0,
                "regret_per_value": 2.0,
            },
        ]
        self._write_jsonl(trace, trace_rows)
        counters.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "arm": "native-trace",
                    "trace_capacity": 65536,
                    "trace_rows_seen": 2,
                    "trace_rows_stored": 2,
                    "trace_rows_dropped": 0,
                    "native_acceptance_preserved": True,
                    "trace_scope_proven": True,
                    "cohort_response_ids": response_ids,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, ready_probe_rid):
            reducer.reduce_scoped_calibration(
                native_outputs=native,
                b0_outputs=b0,
                native_trace=trace,
                native_counters=counters,
                output_dir=output,
            )
        self.assertFalse(output.exists())

    def test_scoped_reducer_allows_cohort_requests_without_positive_barriers(
        self,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        native = root / "native.jsonl"
        b0 = root / "b0.jsonl"
        trace = root / "trace.jsonl"
        counters = root / "counters.json"
        output = root / "result"
        response_ids = [f"cohort-{ordinal:02d}" for ordinal in range(32)]
        outputs = [
            {
                "cohort": "calibration",
                "cohort_position": position,
                "dataset_index": dataset_index,
                "terminal_status": "succeeded",
                "output_token_ids": [91000 + position],
                "attempts": [
                    {
                        "status": "success",
                        "raw_response": {"id": response_ids[position]},
                    }
                ],
            }
            for position, dataset_index in enumerate(CALIBRATION_INDICES)
        ]
        self._write_jsonl(native, outputs)
        self._write_jsonl(b0, outputs)
        trace_rows = [
            {
                "snapshot_index": 0,
                "proposal_ordinal": ordinal,
                "request_serial": ordinal + 1,
                "rid": response_ids[ordinal % 2],
                "request_pool_slot": 0,
                "forward_ct": ordinal + 1,
                "barrier_position": 0,
                "regret": ratio,
                "value": 1.0,
                "regret_per_value": ratio,
            }
            for ordinal, ratio in enumerate((5.0, 1.0, 3.0, 2.0))
        ]
        self._write_jsonl(trace, trace_rows)
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
                    "trace_scope_proven": True,
                    "cohort_response_ids": response_ids,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = reducer.reduce_scoped_calibration(
            native_outputs=native,
            b0_outputs=b0,
            native_trace=trace,
            native_counters=counters,
            output_dir=output,
        )

        self.assertEqual(result["q25"], 1.75)
        self.assertTrue(result["trace_scope_proven"])
        self.assertEqual(result["cohort_response_id_count"], 32)
        self.assertEqual(result["trace_response_id_count"], 2)


if __name__ == "__main__":
    unittest.main()
