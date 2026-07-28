#!/usr/bin/env python3
"""Create the small Phase 04 exit gate from already-produced artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    required = [
        "resolved_config.json",
        "resolved_command.txt",
        "dataset_manifest.json",
        "gsm8k_first10.jsonl",
        "tooling_test.log",
        "process_lifecycle_test.log",
        "mock_api_smoke.json",
        "mock_gsm8k_outputs.jsonl",
        "mock_summary.json",
    ]
    for name in required:
        if not (args.artifact_dir / name).is_file():
            raise FileNotFoundError(name)
    manifest = json.loads((args.artifact_dir / "dataset_manifest.json").read_text())
    summary = json.loads((args.artifact_dir / "mock_summary.json").read_text())
    api = json.loads((args.artifact_dir / "mock_api_smoke.json").read_text())
    data = args.artifact_dir / "gsm8k_first10.jsonl"
    checks = {
        "dataset_revision_pinned": manifest["revision"]
        == "740312add88f781978c0658806c59bc2815b9866",
        "dataset_rows_10": len(data.read_text().splitlines()) == 10,
        "dataset_sha256": sha256(data) == manifest["jsonl_sha256"],
        "api_mock_pass": api["status"] == "PASS",
        "gsm8k_all_terminal": summary["all_terminal"] is True,
        "gsm8k_success_10": summary["success_requests"] == 10,
        "gsm8k_failed_0": summary["failed_requests"] == 0,
        "parser_and_retry_test_pass": "PASS api_smoke gsm8k_retry parser summary"
        in (args.artifact_dir / "tooling_test.log").read_text(),
    }
    gate = {
        "schema_version": 1,
        "phase": "Phase 04",
        "attempt_id": args.artifact_dir.name,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "artifacts": {
            name: {
                "bytes": (args.artifact_dir / name).stat().st_size,
                "sha256": sha256(args.artifact_dir / name),
            }
            for name in required
        },
    }
    output = args.artifact_dir / "phase04_gate.json"
    output.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")
    if gate["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
