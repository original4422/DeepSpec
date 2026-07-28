#!/usr/bin/env python3
"""Executable DFlash-on-DeepSeek-V4 contract audit using CPU-only tensors."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

import torch

from sglang.srt.speculative.dflash_utils import parse_dflash_draft_config


WORKTREE = pathlib.Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
SGLANG_SOURCE = pathlib.Path(
    "/home/tiger/src/deepspec-sglang-hedge-dflash"
)
SGLANG_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
ARTIFACT_DIR = (
    WORKTREE
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1b"
)
PRIMARY_CONFIG = ARTIFACT_DIR / "dflash_d1b_primary_config.json"
HEADER_SUMMARY = (
    ARTIFACT_DIR / "dflash_d1b_safetensors_header_summary.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_primary_config_for_contract_audit(
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Expose primary checkpoint fields through SGLang's existing parser schema.

    This is an audit-only adapter. It is deliberately not wired into SGLang and
    does not constitute the production D2 integration.
    """

    normalized = dict(raw)
    normalized["text_config"] = dict(raw["transformer_layer_config"])
    normalized["dflash_config"] = {
        "block_size": raw["block_size"],
        "mask_token_id": raw["mask_token_id"],
        "target_layer_ids": list(raw["aux_hidden_state_layer_ids"]),
    }
    return normalized


def require_projection_width(tensor: torch.Tensor, expected: int) -> None:
    if tensor.ndim != 2 or tensor.shape[-1] != expected:
        raise ValueError(
            "DFlash checkpoint fc input mismatch: "
            f"expected [N, {expected}], got {list(tensor.shape)}"
        )


def check_checkpoint_contract(
    config: dict[str, Any], header: dict[str, Any]
) -> dict[str, Any]:
    layer = config["transformer_layer_config"]
    aux_ids = config["aux_hidden_state_layer_ids"]
    proposal = config["speculators_config"]["proposal_methods"][0]
    fc_shape = header["selected_tensors"]["fc.weight"]["shape"]

    assert config["architectures"] == ["DFlashDraftModel"]
    assert config["block_size"] == 8
    assert proposal["speculative_tokens"] == 7
    assert proposal["speculative_tokens"] == config["block_size"] - 1
    assert aux_ids == [3, 13, 23, 32, 42]
    assert layer["num_hidden_layers"] == len(aux_ids) == 5
    assert layer["hidden_size"] == 4096
    assert layer["hc_mult"] == 4
    assert layer["layer_types"] == ["sliding_attention"] * 5
    assert layer["sliding_window"] == 2048
    assert config["target_hidden_size"] is None

    # The checkpoint README names 4x4096 multi-stream target features, while
    # the weight header independently fixes the only load-compatible widths.
    effective_target_feature_width = layer["hc_mult"] * layer["hidden_size"]
    checkpoint_context_width = len(aux_ids) * effective_target_feature_width
    fixed_base_context_width = len(aux_ids) * layer["hidden_size"]
    assert effective_target_feature_width == 16384
    assert checkpoint_context_width == 81920
    assert fc_shape == [4096, checkpoint_context_width]
    assert fixed_base_context_width == 20480
    assert fixed_base_context_width != checkpoint_context_width
    assert header["selected_tensors"]["layers.0.self_attn.q_proj.weight"][
        "shape"
    ] == [16384, 4096]
    assert header["selected_tensors"]["layers.0.self_attn.o_proj.weight"][
        "shape"
    ] == [4096, 16384]
    assert (
        header["header_length_prefix_bytes"]
        + header["header_json_bytes"]
        + header["body_bytes_from_data_offsets"]
        == header["lfs"]["size"]
    )

    return {
        "pass": True,
        "aux_hidden_state_layer_ids_in_order": aux_ids,
        "block_size": config["block_size"],
        "draft_candidates": proposal["speculative_tokens"],
        "draft_hidden_size": layer["hidden_size"],
        "hc_mult": layer["hc_mult"],
        "effective_target_feature_width": effective_target_feature_width,
        "context_width_for_five_aux_layers": checkpoint_context_width,
        "checkpoint_fc_shape": fc_shape,
        "fixed_sglang_base_formula_width": fixed_base_context_width,
        "target_hidden_size_null_resolution": (
            "Infer 4*4096=16384 from hc_mult/hidden_size, and require agreement "
            "with fc.weight[4096,81920]; do not fall back to 4096."
        ),
    }


def check_parser_contract(config: dict[str, Any]) -> dict[str, Any]:
    raw = parse_dflash_draft_config(draft_hf_config=config)
    assert raw.num_hidden_layers is None
    assert raw.target_layer_ids is None
    assert raw.mask_token_id is None
    assert raw.block_size == 8

    raw_failure = ""
    try:
        raw.require_num_layers()
    except ValueError as error:
        raw_failure = str(error)
    assert "without num_hidden_layers" in raw_failure

    normalized_dict = normalize_primary_config_for_contract_audit(config)
    normalized = parse_dflash_draft_config(
        draft_hf_config=normalized_dict
    )
    assert normalized.require_num_layers() == 5
    assert normalized.resolve_block_size() == 8
    assert normalized.target_layer_ids == [3, 13, 23, 32, 42]
    assert normalized.mask_token_id == 1
    assert normalized.resolve_target_layer_ids(target_num_layers=43) == [
        3,
        13,
        23,
        32,
        42,
    ]

    return {
        "pass": True,
        "raw_primary_parser_result": {
            "num_hidden_layers": raw.num_hidden_layers,
            "target_layer_ids": raw.target_layer_ids,
            "mask_token_id": raw.mask_token_id,
            "block_size": raw.block_size,
            "require_num_layers_error": raw_failure,
        },
        "audit_adapter_result": {
            "num_hidden_layers": normalized.num_hidden_layers,
            "target_layer_ids": normalized.target_layer_ids,
            "mask_token_id": normalized.mask_token_id,
            "block_size": normalized.block_size,
        },
        "production_requirement": (
            "D2 must deliberately normalize transformer_layer_config and "
            "aux_hidden_state_layer_ids; D1B did not patch SGLang."
        ),
    }


def make_identifiable_aux_tensor(
    *, batch_size: int, aux_slot: int, hidden_size: int, hc_mult: int
) -> torch.Tensor:
    batch = torch.arange(batch_size, dtype=torch.int64).view(-1, 1, 1)
    stream = torch.arange(hc_mult, dtype=torch.int64).view(1, -1, 1)
    feature = torch.arange(hidden_size, dtype=torch.int64).view(1, 1, -1)
    return (
        batch * 100_000_000
        + aux_slot * 1_000_000
        + stream * 10_000
        + feature
    )


def check_mhc_layout(config: dict[str, Any]) -> dict[str, Any]:
    layer = config["transformer_layer_config"]
    aux_ids = config["aux_hidden_state_layer_ids"]
    hidden_size = layer["hidden_size"]
    hc_mult = layer["hc_mult"]
    expected_per_layer = hidden_size * hc_mult
    expected_fc_input = len(aux_ids) * expected_per_layer

    tensors = [
        make_identifiable_aux_tensor(
            batch_size=2,
            aux_slot=slot,
            hidden_size=hidden_size,
            hc_mult=hc_mult,
        )
        for slot, _layer_id in enumerate(aux_ids)
    ]
    assert all(list(tensor.shape) == [2, 4, 4096] for tensor in tensors)

    flattened = [tensor.flatten(1) for tensor in tensors]
    assert all(
        list(tensor.shape) == [2, expected_per_layer]
        for tensor in flattened
    )
    concatenated = torch.cat(flattened, dim=-1)
    assert list(concatenated.shape) == [2, expected_fc_input]
    require_projection_width(concatenated, expected_fc_input)

    sentinels: list[dict[str, int]] = []
    for batch_index in (0, 1):
        for aux_slot in range(len(aux_ids)):
            for stream_index, feature_index in (
                (0, 0),
                (1, 17),
                (3, hidden_size - 1),
            ):
                offset = (
                    aux_slot * expected_per_layer
                    + stream_index * hidden_size
                    + feature_index
                )
                expected_value = (
                    batch_index * 100_000_000
                    + aux_slot * 1_000_000
                    + stream_index * 10_000
                    + feature_index
                )
                actual_value = int(concatenated[batch_index, offset])
                assert actual_value == expected_value
                sentinels.append(
                    {
                        "batch": batch_index,
                        "aux_slot": aux_slot,
                        "target_layer_id": aux_ids[aux_slot],
                        "stream": stream_index,
                        "feature": feature_index,
                        "concat_offset": offset,
                        "encoded_value": actual_value,
                    }
                )

    averaged = torch.cat(
        [tensor.to(torch.float64).mean(dim=1) for tensor in tensors],
        dim=-1,
    )
    assert list(averaged.shape) == [2, len(aux_ids) * hidden_size]
    rejection = ""
    try:
        require_projection_width(averaged, expected_fc_input)
    except ValueError as error:
        rejection = str(error)
    assert "expected [N, 81920], got [2, 20480]" in rejection

    return {
        "pass": True,
        "input_shapes_in_checkpoint_aux_order": [
            list(tensor.shape) for tensor in tensors
        ],
        "per_layer_operation": "completed.flatten(1)",
        "per_layer_width": expected_per_layer,
        "cross_layer_operation": "torch.cat(aux_hidden_states, dim=-1)",
        "concatenated_shape": list(concatenated.shape),
        "sentinels": sentinels,
        "mean_dim_1": {
            "shape": list(averaged.shape),
            "rejected": True,
            "reason": rejection,
        },
    }


def check_layer_index_and_source_contract(
    config: dict[str, Any],
) -> dict[str, Any]:
    aux_ids = config["aux_hidden_state_layer_ids"]
    generic_before_layer_capture = [value + 1 for value in aux_ids]
    deepseek_after_layer_capture = list(aux_ids)
    assert generic_before_layer_capture == [4, 14, 24, 33, 43]
    assert deepseek_after_layer_capture == [3, 13, 23, 32, 42]

    source_root = SGLANG_SOURCE / "python/sglang/srt"
    paths = {
        "dflash_utils": source_root / "speculative/dflash_utils.py",
        "dflash_worker": source_root / "speculative/dflash_worker_v2.py",
        "dflash_model": source_root / "models/dflash.py",
        "deepseek_v4": source_root / "models/deepseek_v4.py",
        "llama": source_root / "models/llama.py",
        "logits_processor": source_root / "layers/logits_processor.py",
    }
    text = {
        name: path.read_text(encoding="utf-8")
        for name, path in paths.items()
    }

    assert (
        "self.model.layers_to_capture = [val + 1 for val in layer_ids]"
        in text["llama"]
    )
    assert (
        "self.model.dspark_layers_to_capture = list(layer_ids)"
        in text["deepseek_v4"]
    )
    assert "def set_dflash_layers_to_capture" not in text["deepseek_v4"]
    layer_call = text["deepseek_v4"].index(
        "hidden_states, prev_residual, prev_post, prev_comb = layer("
    )
    capture_check = text["deepseek_v4"].index(
        "if capture_dspark and i in self.dspark_layers_to_capture:"
    )
    append_mean = text["deepseek_v4"].index(
        "dspark_aux_hidden_states.append(completed.mean(dim=1))"
    )
    assert layer_call < capture_check < append_mean
    assert "torch.cat(aux_hidden_states, dim=-1)" in text["logits_processor"]
    assert "draft_hidden[:, 1:, :]" in text["dflash_worker"]
    assert re.search(r"candidates\[:,\s*1:\]", text["dflash_worker"])
    assert (
        "self.num_context_features * hidden_size, hidden_size"
        in text["dflash_model"]
    )
    assert "target_hidden_size" not in text["dflash_model"]
    assert (
        'config.get("text_config", config)' in text["dflash_utils"]
        and '"target_layer_ids"' in text["dflash_utils"]
    )

    return {
        "pass": True,
        "checkpoint_semantics": "post-layer hidden state IDs",
        "generic_before_layer_capture_indices": generic_before_layer_capture,
        "deepseek_v4_after_layer_capture_indices": deepseek_after_layer_capture,
        "deepseek_rule": (
            "The existing DeepSeek-V4 seam computes the layer, then captures "
            "completed; a DFlash hook at that seam must keep IDs unchanged."
        ),
        "known_incompatible_existing_operation": "completed.mean(dim=1)",
        "required_operation": "completed.flatten(1)",
        "fixed_source_observations": {
            "deepseek_has_dflash_hook": False,
            "deepseek_existing_dspark_capture_is_after_layer": True,
            "deepseek_existing_dspark_capture_averages_mhc": True,
            "logits_processor_concatenates_aux_in_list_order": True,
            "dflash_model_uses_generic_4096_per_context_feature": True,
            "dflash_worker_excludes_candidate_column_zero": True,
        },
        "source_files": {
            name: str(path) for name, path in paths.items()
        },
    }


def check_block_candidate_contract(config: dict[str, Any]) -> dict[str, Any]:
    candidates = torch.tensor(
        [
            [9000, 101, 102, 103, 104, 105, 106, 107],
            [8000, 201, 202, 203, 204, 205, 206, 207],
        ],
        dtype=torch.int64,
    )
    draft_candidates = candidates[:, 1:]
    expected = torch.tensor(
        [
            [101, 102, 103, 104, 105, 106, 107],
            [201, 202, 203, 204, 205, 206, 207],
        ],
        dtype=torch.int64,
    )
    assert config["block_size"] == candidates.shape[1] == 8
    assert list(draft_candidates.shape) == [2, 7]
    assert torch.equal(draft_candidates, expected)
    assert not torch.isin(candidates[:, 0], draft_candidates).any()
    return {
        "pass": True,
        "candidates": candidates.tolist(),
        "current_token_column": candidates[:, 0].tolist(),
        "hedge_draft_candidates_expression": "candidates[:, 1:]",
        "hedge_draft_candidates": draft_candidates.tolist(),
        "hedge_draft_candidate_shape": list(draft_candidates.shape),
    }


def run_contract_checks() -> dict[str, Any]:
    config = read_json(PRIMARY_CONFIG)
    header = read_json(HEADER_SUMMARY)
    source_head = subprocess.run(
        ["git", "-C", str(SGLANG_SOURCE), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert source_head == SGLANG_SHA

    checks = {
        "checkpoint": check_checkpoint_contract(config, header),
        "parser": check_parser_contract(config),
        "mhc_layout": check_mhc_layout(config),
        "layer_index_and_source": check_layer_index_and_source_contract(config),
        "block_candidates": check_block_candidate_contract(config),
    }
    assert all(item["pass"] for item in checks.values())
    return {
        "schema_version": 1,
        "recorded_at": utc_now(),
        "status": "PASS",
        "scope": (
            "D1B CPU-only contract audit; no model load and no D2 production "
            "integration."
        ),
        "torch_device": "cpu",
        "source_commit": source_head,
        "primary_config": {
            "path": str(PRIMARY_CONFIG),
            "sha256": sha256_file(PRIMARY_CONFIG),
        },
        "safetensors_header_summary": {
            "path": str(HEADER_SUMMARY),
            "sha256": sha256_file(HEADER_SUMMARY),
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    result = run_contract_checks()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
