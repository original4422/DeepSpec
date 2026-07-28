#!/usr/bin/env python3
"""Pin and materialize openai/gsm8k main/test first ten examples."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset
from huggingface_hub import HfApi

REPO_ID = "openai/gsm8k"
CONFIG = "main"
SPLIT = "test"
REVISION = "740312add88f781978c0658806c59bc2815b9866"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    resolved = HfApi().dataset_info(REPO_ID, revision=REVISION).sha
    if resolved != REVISION:
        raise RuntimeError(f"dataset revision mismatch: {resolved}")
    dataset = load_dataset(
        REPO_ID,
        CONFIG,
        split=f"{SPLIT}[:10]",
        revision=REVISION,
        cache_dir=str(args.cache_dir),
    )
    if len(dataset) != 10 or set(dataset.column_names) != {"question", "answer"}:
        raise RuntimeError("unexpected GSM8K schema or row count")
    payload = "".join(
        json.dumps(
            {
                "sample_index": index,
                "question": row["question"],
                "answer": row["answer"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for index, row in enumerate(dataset)
    )
    args.output.write_text(payload)
    manifest = {
        "schema_version": 1,
        "provider": "Hugging Face",
        "repo_id": REPO_ID,
        "config": CONFIG,
        "split": SPLIT,
        "selection": "first 10 rows in dataset order",
        "revision": REVISION,
        "resolved_revision": resolved,
        "datasets_fingerprint": dataset._fingerprint,
        "row_count": len(dataset),
        "columns": dataset.column_names,
        "jsonl_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
