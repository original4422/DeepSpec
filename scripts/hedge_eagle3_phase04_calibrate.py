#!/usr/bin/env python3
"""Compare Phase 04 B0 outputs and freeze the protocol q25 configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_eagle3_phase01b.tools import (
    build_resolved_config,
    calibrate_q25,
    canonical_sha256,
    compare_b0_token_ids,
)


DATASET_MANIFEST = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12/"
    "gsm8k_split_manifest.json"
)
DATASET_SHA256 = (
    "5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5"
)
FINAL_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
PATCH_SHA256 = "73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: Sequence[object]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--b0", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        raise RuntimeError("refusing to overwrite Phase 04 calibration artifact")
    args.output_dir.mkdir(parents=True)
    native = read_jsonl(args.native)
    b0 = read_jsonl(args.b0)
    if any(row.get("terminal_status") != "success" for row in [*native, *b0]):
        raise RuntimeError("native or B0 calibration contains a failed record")
    comparison = compare_b0_token_ids(native, b0)
    write_json(args.output_dir / "b0_comparison.json", comparison)
    if comparison["first_mismatch"] is not None:
        write_json(
            args.output_dir / "b0_first_counterexample.json",
            comparison["first_mismatch"],
        )
    enriched = []
    for calibration_index, record in enumerate(b0):
        for barrier in record["strict_rejection_barriers"]:
            value = float(barrier["regret_over_value"])
            if not math.isfinite(value):
                raise RuntimeError("B0 barrier has a non-finite regret/value")
            if value > 0:
                enriched.append(
                    {
                        "calibration_index": calibration_index,
                        "source_index": record["source_index"],
                        **barrier,
                        "regret_over_value": value,
                    }
                )
    q25 = calibrate_q25(enriched)
    bplus = build_resolved_config("B+", gate=q25["g"])
    calibration = {
        **q25,
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": DATASET_SHA256,
        "native_outputs_sha256": sha256(args.native),
        "b0_outputs_sha256": sha256(args.b0),
        "b0_status": comparison["status"],
        "sglang_final_sha": FINAL_SHA,
        "sglang_patch_sha256": PATCH_SHA256,
        "formal_bplus_resolved_config": bplus,
        "formal_bplus_config_sha256": bplus["config_sha256"],
    }
    calibration["frozen_calibration_sha256"] = canonical_sha256(calibration)
    shutil.copy2(args.native, args.output_dir / "native_calibration_outputs.jsonl")
    shutil.copy2(args.b0, args.output_dir / "b0_calibration_outputs.jsonl")
    write_jsonl(args.output_dir / "positive_values.jsonl", enriched)
    write_json(args.output_dir / "calibration.json", calibration)
    write_json(args.output_dir / "resolved_config_Bplus.json", bplus)
    write_json(
        args.output_dir / "phase04_status.json",
        {
            "schema_version": 1,
            "status": "CALIBRATION_FROZEN",
            "b0_status": comparison["status"],
            "exploratory_only": comparison["status"] == "B0_FAIL",
            "positive_value_count": len(enriched),
            "g": q25["g"],
            "B": q25["B"],
            "m": q25["m"],
            "frozen_calibration_sha256": calibration[
                "frozen_calibration_sha256"
            ],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
