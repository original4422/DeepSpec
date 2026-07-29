#!/usr/bin/env python3
"""Read-only progress snapshot for one active D6 B+ formal attempt."""

from __future__ import annotations

import argparse
import collections
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FATAL_PATTERNS = {
    "traceback": r"Traceback \(most recent call last\):",
    "cuda_error": r"(?:CUDA error|CUDA out of memory)",
    "nccl_error": r"(?:NCCL WARN|NCCL ERROR|ncclUnhandledCudaError)",
    "worker_crash": r"(?:Scheduler hit an exception|Worker crashed)",
}


def inspect_jsonl(path: Path) -> dict[str, Any]:
    rows = []
    invalid = []
    if path.is_file():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                invalid.append({"line": number, "error": str(error)})
                continue
            if isinstance(row, dict):
                rows.append(row)
            else:
                invalid.append({"line": number, "error": "row is not an object"})
    terminal = collections.Counter(str(row.get("terminal_state")) for row in rows)
    return {
        "path": str(path),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "complete_json_rows": len(rows),
        "invalid_json_lines": invalid,
        "terminal_states": dict(sorted(terminal.items())),
        "retry_count": sum(int(row.get("retry_count", 0)) for row in rows),
        "completion_tokens": sum(
            int((row.get("usage") or {}).get("completion_tokens", 0))
            for row in rows
        ),
        "match": sum(row.get("answer_status") == "match" for row in rows),
        "mismatch": sum(row.get("answer_status") == "mismatch" for row in rows),
        "parse_failure": sum(
            row.get("answer_status") == "parse_failure" for row in rows
        ),
    }


def snapshot(scratch: Path) -> dict[str, Any]:
    server_log = (
        (scratch / "server.log").read_text(errors="replace")
        if (scratch / "server.log").is_file()
        else ""
    )
    formal_path = (
        scratch / "formal_outputs.jsonl"
        if (scratch / "formal_outputs.jsonl").is_file()
        else scratch / "formal_outputs.raw.jsonl"
    )
    return {
        "schema_version": 1,
        "attempt_id": scratch.name,
        "captured_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "phase": (
            "formal"
            if (scratch / "formal.active").is_file()
            else "warmup"
            if (scratch / "warmup.active").is_file()
            else "lifecycle"
        ),
        "warmup": inspect_jsonl(scratch / "warmup_outputs.jsonl"),
        "formal": inspect_jsonl(formal_path),
        "startup": (
            json.loads((scratch / "startup.json").read_text())
            if (scratch / "startup.json").is_file()
            else None
        ),
        "server_fatal_pattern_counts": {
            name: len(re.findall(pattern, server_log, flags=re.IGNORECASE))
            for name, pattern in FATAL_PATTERNS.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    if not args.scratch.is_dir():
        raise ValueError("B+ attempt scratch does not exist")
    document = snapshot(args.scratch)
    print(json.dumps(document, indent=2, sort_keys=True))
    invalid = (
        document["warmup"]["invalid_json_lines"]
        + document["formal"]["invalid_json_lines"]
    )
    return 0 if not invalid else 1


if __name__ == "__main__":
    raise SystemExit(main())
