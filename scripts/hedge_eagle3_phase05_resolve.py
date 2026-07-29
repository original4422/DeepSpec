#!/usr/bin/env python3
"""Resolve Phase 05 native by wrapping the frozen Phase 04 native resolver."""

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

ACCEPTED_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-native-formal.complete.json"
)


def resolve_native(
    attempt_id: str,
    *,
    require_worker_hostname: bool,
) -> dict[str, object]:
    if not (
        len(attempt_id) >= 36
        and attempt_id[8] == "T"
        and attempt_id[15:25] == "Z-phase-05"
        and "-native-formal-" in attempt_id
    ):
        raise ValueError("invalid Phase 05 native formal attempt ID")
    value = phase04.resolve(
        "native",
        attempt_id,
        gate=None,
        require_worker_hostname=require_worker_hostname,
    )
    value["phase"] = "05"
    value["formal_protocol"] = {
        "mode": "native",
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
    if environment.get("SGLANG_EAGLE3_HEDGE_MODE") != "disabled":
        raise RuntimeError("Phase 05 native resolver did not disable HEDGE")
    if "SGLANG_EAGLE3_HEDGE_CONFIG_JSON" in environment:
        raise RuntimeError("Phase 05 native resolver retained HEDGE config")
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
        raise RuntimeError("an accepted native formal result already exists")
    value = resolve_native(
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
            os.write(
                sys.stdout.fileno(),
                f"{name}={content}".encode() + b"\0",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
