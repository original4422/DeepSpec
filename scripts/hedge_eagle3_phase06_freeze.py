#!/usr/bin/env python3
"""Create or verify the reviewed Phase 06 B+-formal tool freeze."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python")
SGLANG_FINAL_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
DATASET = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12/"
    "gsm8k_split_manifest.json"
)
DATASET_SHA256 = (
    "5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5"
)
CALIBRATION = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T052000Z-phase-04-calibration-01/calibration.json"
)
CALIBRATION_SHA256 = (
    "9af2cff0cc176ef16c7552c54817b2cfb66f5224463ac15730e6eae04a837474"
)
TOOL_PATHS = (
    "deepspec/hedge_eagle3_phase01b/tools.py",
    "patches/hedge_eagle3_phase04/sglang-final-candidate.patch",
    "scripts/hedge_eagle3_keepalive.sh",
    "scripts/hedge_eagle3_phase02_gpu_sampler.py",
    "scripts/hedge_eagle3_phase02_runtime.py",
    "scripts/hedge_eagle3_phase02_watchdog.py",
    "scripts/hedge_eagle3_phase04_resolve.py",
    "scripts/hedge_eagle3_phase05_run.py",
    "scripts/hedge_eagle3_phase06_attempt.sh",
    "scripts/hedge_eagle3_phase06_freeze.py",
    "scripts/hedge_eagle3_phase06_resolve.py",
    "scripts/hedge_eagle3_phase06_run.py",
    "scripts/phase05_wait_ready.py",
    "tests/test_hedge_eagle3_phase06.py",
    "uv.lock",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: Sequence[str], *, binary: bool = False):
    return subprocess.run(
        tuple(command),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=not binary,
        timeout=300,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def source_identity() -> dict[str, Any]:
    head = run(("git", "-C", str(SGLANG_ROOT), "rev-parse", "HEAD")).stdout.strip()
    status = run(("git", "-C", str(SGLANG_ROOT), "status", "--short")).stdout
    if head != SGLANG_FINAL_SHA or status:
        raise RuntimeError("frozen SGLang source identity differs")
    return {
        "sglang_final_sha": head,
        "sglang_clean": True,
        "deepspec_head": run(("git", "rev-parse", "HEAD")).stdout.strip(),
        "deepspec_status": run(("git", "status", "--short")).stdout.splitlines(),
    }


def file_records() -> list[dict[str, Any]]:
    records = []
    for relative in TOOL_PATHS:
        path = REPO_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"Phase 06 tool is absent: {relative}")
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return records


def regression() -> dict[str, Any]:
    commands = (
        (
            "bash_syntax",
            ("bash", "-n", "scripts/hedge_eagle3_phase06_attempt.sh"),
        ),
        (
            "python_compile",
            (
                str(PYTHON),
                "-m",
                "py_compile",
                "scripts/hedge_eagle3_phase06_resolve.py",
                "scripts/hedge_eagle3_phase06_run.py",
                "scripts/hedge_eagle3_phase06_freeze.py",
            ),
        ),
        (
            "unit_tests",
            (
                str(PYTHON),
                "-m",
                "unittest",
                "tests.test_hedge_eagle3_phase06",
            ),
        ),
    )
    results = []
    for name, command in commands:
        completed = run(command)
        results.append(
            {
                "name": name,
                "command": list(command),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
    attempt = "20260729T080000Z-phase-06-bplus-formal-freeze"
    phase06_command = run(
        (
            str(PYTHON),
            "scripts/hedge_eagle3_phase06_resolve.py",
            "--attempt-id",
            attempt,
            "--print-command-null",
        ),
        binary=True,
    ).stdout
    phase04_command = run(
        (
            str(PYTHON),
            "scripts/hedge_eagle3_phase04_resolve.py",
            "--mode",
            "B+",
            "--gate",
            "6.75",
            "--attempt-id",
            attempt,
            "--print-command-null",
        ),
        binary=True,
    ).stdout
    phase06_environment = run(
        (
            str(PYTHON),
            "scripts/hedge_eagle3_phase06_resolve.py",
            "--attempt-id",
            attempt,
            "--print-environment-null",
        ),
        binary=True,
    ).stdout
    phase04_environment = run(
        (
            str(PYTHON),
            "scripts/hedge_eagle3_phase04_resolve.py",
            "--mode",
            "B+",
            "--gate",
            "6.75",
            "--attempt-id",
            attempt,
            "--print-environment-null",
        ),
        binary=True,
    ).stdout
    if phase06_command != phase04_command:
        raise RuntimeError("Phase 06 server command differs from Phase 04 B+")
    if phase06_environment != phase04_environment:
        raise RuntimeError("Phase 06 environment differs from Phase 04 B+")
    return {
        "status": "PASS",
        "commands": results,
        "phase04_bplus_server_command_identical": True,
        "phase04_bplus_environment_identical": True,
        "gate": 6.75,
        "risk_budget": 6.75,
        "max_relaxed_mismatches_per_block": 1,
        "value_scheme": "normalized_suffix",
    }


def write_atomic(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite freeze output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f"{path.name}.staging-{os.getpid()}")
    with staging.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path)


def create(output: Path) -> None:
    if sha256(DATASET) != DATASET_SHA256:
        raise RuntimeError("fixed dataset manifest differs")
    if sha256(CALIBRATION) != CALIBRATION_SHA256:
        raise RuntimeError("fixed Phase 04 calibration differs")
    write_atomic(
        output,
        {
            "schema_version": 1,
            "status": "PASS",
            "created_at": utc_now(),
            "source": source_identity(),
            "dataset_manifest": str(DATASET),
            "dataset_manifest_sha256": DATASET_SHA256,
            "calibration_artifact": str(CALIBRATION),
            "calibration_artifact_sha256": CALIBRATION_SHA256,
            "formal_bplus_config_sha256": (
                "87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a"
            ),
            "regression": regression(),
            "files": file_records(),
            "immutability_rule": (
                "Do not modify listed files during the Phase 06 formal attempt."
            ),
        },
    )


def verify(manifest_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    differences = []
    for expected in manifest["files"]:
        path = REPO_ROOT / expected["path"]
        observed = {
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None,
        }
        if observed != {
            "bytes": expected["bytes"],
            "sha256": expected["sha256"],
        }:
            differences.append(
                {
                    "path": expected["path"],
                    "expected": expected,
                    "observed": observed,
                }
            )
    identity = source_identity()
    if differences:
        raise RuntimeError(f"Phase 06 tooling differs: {differences!r}")
    write_atomic(
        output,
        {
            "schema_version": 1,
            "status": "PASS",
            "verified_at": utc_now(),
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "file_count": len(manifest["files"]),
            "file_differences": [],
            "sglang_final_sha": identity["sglang_final_sha"],
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "create":
        create(args.output)
    else:
        verify(args.manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
