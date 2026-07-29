#!/usr/bin/env python3
"""Resolve the one allowed Phase 06 HEDGE B+ formal arm."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE04_PATH = REPO_ROOT / "scripts/hedge_eagle3_phase04_resolve.py"
SPEC = importlib.util.spec_from_file_location(
    "hedge_eagle3_phase04_resolve", PHASE04_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen Phase 04 resolver")
phase04 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase04)

GATE = 6.75
ACCEPTED_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-bplus-formal.complete.json"
)


def resolve_bplus(
    attempt_id: str,
    *,
    require_worker_hostname: bool,
) -> dict[str, object]:
    if not (
        len(attempt_id) >= 36
        and attempt_id[8] == "T"
        and attempt_id[15:25] == "Z-phase-06"
        and "-bplus-formal-" in attempt_id
    ):
        raise ValueError("invalid Phase 06 B+ formal attempt ID")
    value = phase04.resolve(
        "B+",
        attempt_id,
        gate=GATE,
        require_worker_hostname=require_worker_hostname,
    )
    value["phase"] = "06"
    value["formal_protocol"] = {
        "mode": "B+",
        "warmup_partition": "calibration",
        "warmup_indices": list(range(10)),
        "formal_partition": "formal",
        "formal_count": 500,
        "sequential": True,
        "formal_result_once": True,
        "accepted_result_marker": str(ACCEPTED_MARKER),
    }
    environment = value["environment"]
    assert isinstance(environment, dict)
    if environment.get("SGLANG_EAGLE3_HEDGE_MODE") != "enabled":
        raise RuntimeError("Phase 06 resolver did not enable HEDGE")
    expected = phase04.build_resolved_config("B+", gate=GATE)["environment"][
        "SGLANG_EAGLE3_HEDGE_CONFIG_JSON"
    ]
    if environment.get("SGLANG_EAGLE3_HEDGE_CONFIG_JSON") != expected:
        raise RuntimeError("Phase 06 resolver changed the frozen B+ config")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--print-command-null", action="store_true")
    parser.add_argument("--print-environment-null", action="store_true")
    parser.add_argument("--assert-worker-hostname", action="store_true")
    parser.add_argument("--assert-no-complete-result", action="store_true")
    args = parser.parse_args(argv)
    if args.assert_no_complete_result and ACCEPTED_MARKER.exists():
        raise RuntimeError("an accepted B+ formal result already exists")
    value = resolve_bplus(
        args.attempt_id,
        require_worker_hostname=args.assert_worker_hostname,
    )
    if args.output is not None:
        phase04.write_json(args.output, value)
    if args.evidence_dir is not None:
        phase04.write_evidence(args.evidence_dir, value)
        phase04.write_json(args.evidence_dir / "source_identity.json", value["source"])
    if args.print_command_null:
        for item in value["command"]:
            os.write(sys.stdout.fileno(), str(item).encode() + b"\0")
    if args.print_environment_null:
        for name, content in value["environment"].items():
            os.write(sys.stdout.fileno(), f"{name}={content}".encode() + b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
