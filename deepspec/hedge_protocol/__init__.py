"""Frozen dataset and request tooling for HEDGE-on-V4 experiments."""

from .answers import extract_model_answer, extract_reference_answer, normalize_number
from .config import build_chat_request, build_user_content, protocol_config_document
from .dataset import (
    acquire_and_materialize,
    materialize_dataset,
    selected_indices,
    verify_materialized_dataset,
)
from .runner import ProtocolRunner
from .summary import recompute_summary

__all__ = [
    "ProtocolRunner",
    "acquire_and_materialize",
    "build_chat_request",
    "build_user_content",
    "extract_model_answer",
    "extract_reference_answer",
    "materialize_dataset",
    "normalize_number",
    "protocol_config_document",
    "recompute_summary",
    "selected_indices",
    "verify_materialized_dataset",
]
