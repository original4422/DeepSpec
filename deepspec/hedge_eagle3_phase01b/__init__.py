"""Offline-tested experiment tooling for the HEDGE-on-V4 Eagle3 lane."""

from .tools import (
    RegisteredProcess,
    SequentialOpenAIRunner,
    build_resolved_config,
    calibrate_q25,
    capture_registered_process,
    compare_b0_token_ids,
    experiment_table,
    extract_model_answer,
    extract_reference_answer,
    normalize_numeric_answer,
    summarize_run,
    terminate_registered_process,
)

__all__ = [
    "RegisteredProcess",
    "SequentialOpenAIRunner",
    "build_resolved_config",
    "calibrate_q25",
    "capture_registered_process",
    "compare_b0_token_ids",
    "experiment_table",
    "extract_model_answer",
    "extract_reference_answer",
    "normalize_numeric_answer",
    "summarize_run",
    "terminate_registered_process",
]
