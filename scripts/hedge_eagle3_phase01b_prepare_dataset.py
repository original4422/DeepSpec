#!/usr/bin/env python3
"""Materialize the pinned deterministic GSM8K calibration/formal manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
from typing import Any, Sequence

from datasets import DownloadConfig, load_dataset
from huggingface_hub import HfApi


REPO_ID = "openai/gsm8k"
REVISION = "740312add88f781978c0658806c59bc2815b9866"
CONFIG = "main"
SPLIT = "test"
SEED = 980406
CALIBRATION_COUNT = 32
FORMAL_COUNT = 500
PROMPT_SUFFIX = (
    "Please reason step by step, and put your final answer within \\boxed{}."
)
CACHE_ROOT = Path(
    "/tmp/deepspec-hedge-v4-eagle3/datasets/"
    "openai-gsm8k-740312add88f"
)
SCRATCH_ROOT = Path(
    "/tmp/deepspec-hedge-v4-eagle3/"
    "20260728T230100Z-phase-01b-dataset-revision-12"
)


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def record(
    dataset: Any,
    *,
    partition: str,
    partition_index: int,
    source_index: int,
) -> dict[str, object]:
    row = dataset[source_index]
    question = row["question"]
    answer = row["answer"]
    if not isinstance(question, str) or not question.strip():
        raise RuntimeError("GSM8K question is not a non-empty string")
    if not isinstance(answer, str) or "####" not in answer:
        raise RuntimeError("GSM8K answer lacks the canonical #### delimiter")
    return {
        "partition": partition,
        "partition_index": partition_index,
        "source_index": source_index,
        "question": question,
        "answer": answer,
        "request_messages": [
            {
                "role": "user",
                "content": f"{question}\n{PROMPT_SUFFIX}",
            }
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.with_suffix(
        f"{args.output.suffix}.sha256"
    ).exists():
        raise RuntimeError("refusing to overwrite GSM8K manifest evidence")
    if SCRATCH_ROOT.exists():
        raise RuntimeError("refusing to reuse GSM8K acquisition scratch")
    SCRATCH_ROOT.mkdir(parents=True)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    provider = HfApi().dataset_info(REPO_ID, revision=REVISION)
    if provider.sha != REVISION:
        raise RuntimeError(
            f"provider resolved unexpected revision: {provider.sha}"
        )
    download_config = DownloadConfig(
        cache_dir=str(CACHE_ROOT / "downloads"),
        force_download=False,
        resume_download=True,
    )
    dataset = load_dataset(
        REPO_ID,
        CONFIG,
        split=SPLIT,
        revision=REVISION,
        cache_dir=str(CACHE_ROOT),
        download_config=download_config,
    )
    if len(dataset) < CALIBRATION_COUNT + FORMAL_COUNT:
        raise RuntimeError("GSM8K test split is unexpectedly short")
    source_indices = list(range(len(dataset)))
    random.Random(SEED).shuffle(source_indices)
    calibration_indices = source_indices[:CALIBRATION_COUNT]
    formal_indices = source_indices[
        CALIBRATION_COUNT : CALIBRATION_COUNT + FORMAL_COUNT
    ]
    if (
        len(set(calibration_indices)) != CALIBRATION_COUNT
        or len(set(formal_indices)) != FORMAL_COUNT
        or set(calibration_indices) & set(formal_indices)
    ):
        raise RuntimeError("deterministic GSM8K split invariants failed")
    calibration = [
        record(
            dataset,
            partition="calibration",
            partition_index=index,
            source_index=source_index,
        )
        for index, source_index in enumerate(calibration_indices)
    ]
    formal = [
        record(
            dataset,
            partition="formal",
            partition_index=index,
            source_index=source_index,
        )
        for index, source_index in enumerate(formal_indices)
    ]
    core = {
        "schema_version": 1,
        "dataset": {
            "provider": "huggingface",
            "repo_id": REPO_ID,
            "requested_revision": REVISION,
            "resolved_revision": provider.sha,
            "config": CONFIG,
            "split": SPLIT,
            "row_count": len(dataset),
            "fingerprint": dataset._fingerprint,
        },
        "selection": {
            "algorithm": "random.Random(seed).shuffle(source_indices)",
            "python_implementation": sys.implementation.name,
            "python_version": sys.version,
            "seed": SEED,
            "calibration_count": CALIBRATION_COUNT,
            "formal_count": FORMAL_COUNT,
            "calibration_source_indices": calibration_indices,
            "formal_source_indices": formal_indices,
            "overlap_count": 0,
        },
        "request_contract": {
            "system_prompt": None,
            "prompt_suffix": PROMPT_SUFFIX,
            "generation": {
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 512,
                "chat_template_kwargs": {
                    "enable_thinking": False,
                },
            },
            "sequential": True,
        },
        "calibration": calibration,
        "formal": formal,
    }
    core_hash = hashlib.sha256(canonical_bytes(core)).hexdigest()
    envelope = {
        **core,
        "created_at": utc_now(),
        "content_sha256": core_hash,
        "cache_root": str(CACHE_ROOT),
    }
    scratch_manifest = SCRATCH_ROOT / args.output.name
    scratch_manifest.write_bytes(canonical_bytes(envelope))
    final_hash = hashlib.sha256(scratch_manifest.read_bytes()).hexdigest()
    scratch_hash = SCRATCH_ROOT / f"{args.output.name}.sha256"
    scratch_hash.write_text(
        f"{final_hash}  {args.output.name}\n",
        encoding="utf-8",
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    temporary = args.output.with_name(f".{args.output.name}.tmp.{os.getpid()}")
    shutil.copyfile(scratch_manifest, temporary)
    os.replace(temporary, args.output)
    final_hash_path = args.output.with_suffix(
        f"{args.output.suffix}.sha256"
    )
    hash_temporary = final_hash_path.with_name(
        f".{final_hash_path.name}.tmp.{os.getpid()}"
    )
    shutil.copyfile(scratch_hash, hash_temporary)
    os.replace(hash_temporary, final_hash_path)
    print(
        "GSM8K_SPLIT_PASS "
        f"fingerprint={dataset._fingerprint} "
        f"content_sha256={core_hash} file_sha256={final_hash} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"GSM8K split error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
