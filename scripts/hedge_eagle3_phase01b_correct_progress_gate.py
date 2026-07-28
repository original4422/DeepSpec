#!/usr/bin/env python3
"""Record why the install progress gate produced a false STALL verdict."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


REQUIRED_LOG_PATTERNS = (
    "Found fresh response for: https://download.pytorch.org/whl/cu130/torch/",
    "Adding transitive dependency for torch==2.11.0+cu130: "
    "cuda-toolkit[cublas]",
    "Selecting: cuda-toolkit==13.0.2",
    "Sending fresh GET request for: "
    "https://download.pytorch.org/whl/cu130/nvidia-cublas/",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--verbose-log", type=Path, required=True)
    parser.add_argument("--termination", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite: {args.output}")
    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    termination = json.loads(args.termination.read_text(encoding="utf-8"))
    verbose_log = args.verbose_log.read_text(encoding="utf-8")
    if gate.get("verdict") != "STALL":
        raise RuntimeError("input gate is not the STALL verdict being corrected")
    if termination.get("status") != "TARGETED_STOP_COMPLETE":
        raise RuntimeError("attempt termination evidence is incomplete")
    missing = [
        pattern for pattern in REQUIRED_LOG_PATTERNS if pattern not in verbose_log
    ]
    if missing:
        raise RuntimeError(f"verbose log lacks correction evidence: {missing}")
    fresh_get_count = verbose_log.count("Sending fresh GET request")
    fresh_response_count = verbose_log.count("Found fresh response")
    payload = {
        "schema_version": 1,
        "status": "GATE_FALSE_POSITIVE_RECORDED",
        "recorded_at": utc_now(),
        "supersedes_verdict": str(args.gate),
        "supersedes_inference": str(
            args.gate.parent.parent
            / "20260728T213900Z-phase-01b-bootstrap-system-certs-02"
            / "thread_probe_inference.json"
        ),
        "corrected_verdict": "ONLINE_RESOLUTION_WAS_PROGRESSING",
        "blocker_migration": (
            "The issue is expensive online resolution and CUDA-toolkit "
            "dependency expansion, not an unavailable proxy or dead resolver."
        ),
        "gate_defect": {
            "summary": (
                "The 15-second gate observed proc file I/O, uv-cache tree "
                "changes and venv changes, but omitted socket recv/send, "
                "resolver in-memory state and buffered verbose logs."
            ),
            "why_false_red": (
                "uv made and consumed fresh HTTP metadata requests while all "
                "three observed filesystem-oriented signals remained flat."
            ),
            "future_fix": (
                "Treat network byte counters or monotonically growing "
                "line-buffered resolver events as progress; never infer a "
                "network stall from /proc/<pid>/io alone."
            ),
        },
        "verbose_log": str(args.verbose_log),
        "verbose_log_sha256": sha256(args.verbose_log),
        "verbose_log_bytes": args.verbose_log.stat().st_size,
        "fresh_get_count": fresh_get_count,
        "fresh_response_count": fresh_response_count,
        "required_evidence_patterns": list(REQUIRED_LOG_PATTERNS),
        "termination": str(args.termination),
        "termination_was_based_on_false_positive": True,
        "network_or_uv_failure_proven": False,
        "next_strategy": (
            "Use the lock-pinned torch wheel URL/hash as a tight no-deps "
            "probe to bypass expensive online resolution and establish the "
            "keepalive prerequisite sooner; react only to actual import errors."
        ),
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PROGRESS_GATE_CORRECTED output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"gate correction error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
