"""Executable EAGLE3 auxiliary-state contract for Phase 01C.

This is deliberately independent of SGLang.  Phase 02 can use it as a
reference test surface while wiring the equivalent operation into the fixed
SGLang source.
"""

from dataclasses import dataclass
from typing import Mapping

import torch


LOGICAL_LAYER_IDS = (1, 21, 40)
CAPTURE_HOOK_IDS = tuple(layer_id + 1 for layer_id in LOGICAL_LAYER_IDS)
MHC_STREAMS = 4
HIDDEN_SIZE = 4096
NUM_AUX_STATES = len(LOGICAL_LAYER_IDS)


@dataclass(frozen=True)
class Eagle3AuxState:
    """Validated target auxiliary state in structured and runner layouts."""

    logical_layer_ids: tuple[int, ...]
    capture_hook_ids: tuple[int, ...]
    structured: torch.Tensor
    flattened: torch.Tensor


def build_eagle3_aux_state(
    captured_by_hook: Mapping[int, torch.Tensor],
) -> Eagle3AuxState:
    """Reduce and order the fixed DeepSeek-V4-Flash EAGLE3 target taps.

    Each input value is the completed mHC state for one capture hook and must
    have shape ``[num_tokens, 4, 4096]`` and dtype ``torch.bfloat16``.  The four
    mHC streams are averaged, then the three logical taps are ordered as
    ``[1, 21, 40]``.  The returned layouts are:

    * ``structured``: ``[num_tokens, 3, 4096]``;
    * ``flattened``: ``[num_tokens, 12288]`` for the SGLang draft runner.
    """

    expected_hooks = set(CAPTURE_HOOK_IDS)
    actual_hooks = set(captured_by_hook)
    if actual_hooks != expected_hooks:
        missing = sorted(expected_hooks - actual_hooks)
        unexpected = sorted(actual_hooks - expected_hooks)
        raise ValueError(
            "capture hook mismatch: "
            f"missing={missing}, unexpected={unexpected}, "
            f"expected={list(CAPTURE_HOOK_IDS)}"
        )

    reduced_states: list[torch.Tensor] = []
    batch_size: int | None = None
    expected_device: torch.device | None = None

    for hook_id in CAPTURE_HOOK_IDS:
        state = captured_by_hook[hook_id]
        if not isinstance(state, torch.Tensor):
            raise TypeError(
                f"capture hook {hook_id} must contain a torch.Tensor, "
                f"got {type(state).__name__}"
            )
        if state.ndim != 3 or tuple(state.shape[1:]) != (MHC_STREAMS, HIDDEN_SIZE):
            raise ValueError(
                f"capture hook {hook_id} must have shape "
                f"[num_tokens, {MHC_STREAMS}, {HIDDEN_SIZE}], "
                f"got {list(state.shape)}"
            )
        if state.dtype != torch.bfloat16:
            raise TypeError(
                f"capture hook {hook_id} must use torch.bfloat16, got {state.dtype}"
            )
        if batch_size is None:
            batch_size = state.shape[0]
            expected_device = state.device
        elif state.shape[0] != batch_size:
            raise ValueError(
                f"capture hook {hook_id} has num_tokens={state.shape[0]}, "
                f"expected {batch_size}"
            )
        elif state.device != expected_device:
            raise ValueError(
                f"capture hook {hook_id} is on {state.device}, "
                f"expected {expected_device}"
            )

        reduced = state.mean(dim=1)
        if reduced.dtype != torch.bfloat16:
            raise TypeError(
                f"capture hook {hook_id} reduction changed dtype to {reduced.dtype}"
            )
        reduced_states.append(reduced)

    structured = torch.stack(reduced_states, dim=1)
    flattened = structured.reshape(structured.shape[0], -1)
    return Eagle3AuxState(
        logical_layer_ids=LOGICAL_LAYER_IDS,
        capture_hook_ids=CAPTURE_HOOK_IDS,
        structured=structured,
        flattened=flattened,
    )
