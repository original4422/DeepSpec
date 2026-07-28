"""Phase 01C synthetic contracts for DeepSeek-V4-Flash EAGLE3."""

from .aux_contract import (
    CAPTURE_HOOK_IDS,
    HIDDEN_SIZE,
    LOGICAL_LAYER_IDS,
    MHC_STREAMS,
    Eagle3AuxState,
    build_eagle3_aux_state,
)

__all__ = [
    "CAPTURE_HOOK_IDS",
    "HIDDEN_SIZE",
    "LOGICAL_LAYER_IDS",
    "MHC_STREAMS",
    "Eagle3AuxState",
    "build_eagle3_aux_state",
]
