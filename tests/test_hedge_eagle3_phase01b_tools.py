from __future__ import annotations

import unittest

from deepspec.hedge_eagle3_phase01b.tools import (
    GENERATION,
    TransportFailure,
    _response_fields,
    build_resolved_config,
    calibrate_q25,
    compare_b0_token_ids,
    extract_model_answer,
    normalize_numeric_answer,
)


class Phase01BToolsTest(unittest.TestCase):
    def test_runtime_logprob_triples_supply_complete_token_ids(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "4",
                    },
                    "meta_info": {
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

        self.assertEqual(
            _response_fields(response),
            ("4", [22, 1], 2),
        )
        self.assertEqual(GENERATION["return_meta_info"], True)
        self.assertEqual(GENERATION["logprobs"], True)
        self.assertEqual(GENERATION["top_logprobs"], 0)

    def test_runtime_token_id_metadata_mismatches_fail_closed(self) -> None:
        def response() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "4",
                        },
                        "meta_info": {
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

        malformed_triple = response()
        malformed_triple["choices"][0]["meta_info"][
            "output_token_logprobs"
        ][0][1] = True
        declared_length = response()
        declared_length["choices"][0]["meta_info"][
            "output_token_logprobs_length"
        ] = 1
        meta_completion = response()
        meta_completion["choices"][0]["meta_info"]["completion_tokens"] = 1
        usage_completion = response()
        usage_completion["usage"]["completion_tokens"] = 1
        disagreeing_fields = response()
        disagreeing_fields["choices"][0]["token_ids"] = [99, 1]
        cases = (
            (malformed_triple, "complete triples"),
            (declared_length, "declared length differs"),
            (meta_completion, "meta completion tokens differ"),
            (usage_completion, "usage differs"),
            (disagreeing_fields, "fields disagree"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(TransportFailure, message):
                    _response_fields(payload)

    def test_answer_normalization_and_precedence(self) -> None:
        self.assertEqual(normalize_numeric_answer("$1,234.50"), "1234.5")
        self.assertEqual(normalize_numeric_answer("6/8"), "3/4")
        self.assertEqual(
            extract_model_answer(
                "first 1\n#### 2\nfinal answer 3\n\\boxed{4}"
            ),
            {
                "status": "ok",
                "rule": "last_boxed",
                "raw": "4",
                "normalized": "4",
            },
        )

    def test_q25_linear_and_mode_invariants(self) -> None:
        result = calibrate_q25(
            [
                {
                    "sample_id": index,
                    "proposal_id": index,
                    "regret_over_value": value,
                }
                for index, value in enumerate((1.0, 2.0, 3.0, 4.0))
            ]
        )
        self.assertEqual(result["g"], 1.75)
        self.assertEqual(result["B"], 1.75)
        self.assertEqual(result["m"], 1)
        configs = {
            mode: build_resolved_config(
                mode,
                gate=result["g"] if mode == "B+" else None,
            )
            for mode in ("native", "B0", "B+")
        }
        self.assertEqual(configs["native"]["server"], configs["B0"]["server"])
        self.assertEqual(configs["B0"]["server"], configs["B+"]["server"])
        self.assertEqual(configs["native"]["request"], configs["B+"]["request"])
        self.assertEqual(configs["native"]["lane"], configs["B+"]["lane"])
        self.assertEqual(configs["native"]["proposal_tokens"], 3)
        self.assertEqual(configs["native"]["internal_verify_width"], 4)
        self.assertEqual(
            configs["native"]["server"]["speculative_num_steps"],
            3,
        )
        self.assertEqual(
            configs["native"]["server"]["speculative_num_draft_tokens"],
            4,
        )
        self.assertEqual(
            configs["native"]["server"][
                "speculative_draft_attention_backend"
            ],
            "flashinfer",
        )

    def test_b0_first_mismatch_and_nonfinite_rejected(self) -> None:
        native = [
            {
                "source_index": index,
                "output_token_ids": [index, 1],
                "response_text": "native",
            }
            for index in range(32)
        ]
        b0 = [dict(record) for record in native]
        b0[3] = {**b0[3], "output_token_ids": [3, 2]}
        result = compare_b0_token_ids(native, b0)
        self.assertEqual(result["status"], "B0_FAIL")
        self.assertEqual(result["first_mismatch"]["calibration_index"], 3)
        self.assertEqual(result["first_mismatch"]["first_divergence"], 1)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            calibrate_q25(
                [
                    {
                        "sample_id": 1,
                        "proposal_id": 1,
                        "regret_over_value": float("nan"),
                    }
                ]
            )

    def test_response_without_complete_token_ids_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            TransportFailure,
            "complete output token IDs",
        ):
            _response_fields(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "The response text is not re-tokenized.",
                            }
                        }
                    ],
                    "usage": {"completion_tokens": 8},
                }
            )


if __name__ == "__main__":
    unittest.main()
