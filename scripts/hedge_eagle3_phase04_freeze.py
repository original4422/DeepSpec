#!/usr/bin/env python3
"""Create or verify the immutable Phase 04 execution-tool manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python")
SGLANG_FINAL_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
DATASET_MANIFEST = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12/"
    "gsm8k_split_manifest.json"
)
DATASET_SHA256 = (
    "5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5"
)
TOOL_PATHS = (
    "deepspec/hedge_eagle3_phase01b/tools.py",
    "patches/hedge_eagle3_phase04/manifest.json",
    "patches/hedge_eagle3_phase04/sglang-final-candidate.patch",
    "scripts/hedge_eagle3_keepalive.sh",
    "scripts/hedge_eagle3_phase02_gpu_sampler.py",
    "scripts/hedge_eagle3_phase02_runtime.py",
    "scripts/hedge_eagle3_phase02_watchdog.py",
    "scripts/hedge_eagle3_phase04_attempt.sh",
    "scripts/hedge_eagle3_phase04_calibrate.py",
    "scripts/hedge_eagle3_phase04_freeze.py",
    "scripts/hedge_eagle3_phase04_probe.sh",
    "scripts/hedge_eagle3_phase04_resolve.py",
    "scripts/hedge_eagle3_phase04_run.py",
    "scripts/phase05_wait_ready.py",
    "tests/test_hedge_eagle3_phase03.py",
    "tests/test_hedge_eagle3_phase04.py",
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


def file_records() -> list[dict[str, Any]]:
    result = []
    for relative in TOOL_PATHS:
        path = REPO_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"frozen tool is absent: {relative}")
        result.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return result


def run(
    command: Sequence[str],
    *,
    binary: bool = False,
) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        tuple(command),
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=not binary,
        timeout=300,
    )


def git_identity() -> dict[str, Any]:
    branch = run(("git", "branch", "--show-current")).stdout.strip()
    head = run(("git", "rev-parse", "HEAD")).stdout.strip()
    status = run(("git", "status", "--short")).stdout.splitlines()
    sglang_head = run(
        ("git", "-C", str(SGLANG_ROOT), "rev-parse", "HEAD")
    ).stdout.strip()
    sglang_status = run(
        ("git", "-C", str(SGLANG_ROOT), "status", "--short")
    ).stdout.splitlines()
    if sglang_head != SGLANG_FINAL_SHA or sglang_status:
        raise RuntimeError("frozen SGLang identity differs")
    return {
        "deepspec_branch": branch,
        "deepspec_head": head,
        "deepspec_status_at_freeze": status,
        "sglang_final_sha": sglang_head,
        "sglang_clean": True,
    }


def regression() -> dict[str, Any]:
    commands = (
        (
            "bash_syntax",
            (
                "bash",
                "-n",
                "scripts/hedge_eagle3_phase04_attempt.sh",
                "scripts/hedge_eagle3_phase04_probe.sh",
            ),
        ),
        (
            "python_compile",
            (
                str(PYTHON),
                "-m",
                "py_compile",
                "scripts/hedge_eagle3_phase04_resolve.py",
                "scripts/hedge_eagle3_phase04_run.py",
                "scripts/hedge_eagle3_phase04_calibrate.py",
                "scripts/hedge_eagle3_phase04_freeze.py",
            ),
        ),
        (
            "unit_tests",
            (
                str(PYTHON),
                "-m",
                "unittest",
                "tests.test_hedge_eagle3_phase04",
                "tests.test_hedge_eagle3_phase03",
            ),
        ),
        (
            "source_aux_tests",
            (
                str(PYTHON),
                str(
                    SGLANG_ROOT
                    / "test/registered/unit/models/"
                    "test_deepseek_v4_eagle3_aux.py"
                ),
                "-v",
            ),
        ),
        (
            "source_hedge_tests",
            (
                str(PYTHON),
                str(
                    SGLANG_ROOT
                    / "test/registered/unit/speculative/"
                    "test_eagle3_hedge.py"
                ),
                "-v",
            ),
        ),
        (
            "diff_check",
            (
                "git",
                "diff",
                "--check",
                "--",
                "scripts/hedge_eagle3_phase04_attempt.sh",
                "scripts/hedge_eagle3_phase04_calibrate.py",
                "scripts/hedge_eagle3_phase04_freeze.py",
                "scripts/hedge_eagle3_phase04_probe.sh",
                "scripts/hedge_eagle3_phase04_resolve.py",
                "scripts/hedge_eagle3_phase04_run.py",
                "tests/test_hedge_eagle3_phase04.py",
                "docs/experiment/hedge-deepseek-v4-flash-eagle3.md",
                "docs/progress/hedge-deepseek-v4-flash-eagle3.md",
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
    resolver_commands = {}
    for mode, gate in (("native", None), ("B0", None), ("B+", "0.25")):
        command = [
            str(PYTHON),
            "scripts/hedge_eagle3_phase04_resolve.py",
            "--mode",
            mode,
            "--attempt-id",
            f"20260729T040000Z-phase-04-{mode}-freeze-01",
            "--print-command-null",
        ]
        if gate is not None:
            command[4:4] = ["--gate", gate]
        completed = run(command, binary=True)
        resolver_commands[mode] = [
            item.decode("utf-8")
            for item in completed.stdout.rstrip(b"\0").split(b"\0")
        ]
    if not all(
        command == resolver_commands["native"]
        for command in resolver_commands.values()
    ):
        raise RuntimeError("three frozen arms do not share one server command")
    return {
        "status": "PASS",
        "commands": results,
        "three_arm_server_command_identical": True,
        "server_command": resolver_commands["native"],
    }


def write_atomic(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite freeze output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f"{path.name}.staging-{os.getpid()}")
    if staging.exists():
        raise RuntimeError(f"unexpected freeze staging path: {staging}")
    with staging.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path)


def create(output: Path) -> None:
    if sha256(DATASET_MANIFEST) != DATASET_SHA256:
        raise RuntimeError("fixed dataset manifest differs")
    result = {
        "schema_version": 1,
        "status": "PASS",
        "created_at": utc_now(),
        "git": git_identity(),
        "dataset_manifest": str(DATASET_MANIFEST),
        "dataset_manifest_sha256": DATASET_SHA256,
        "regression": regression(),
        "files": file_records(),
        "immutability_rule": (
            "Do not modify any listed file during a live Phase 04 attempt."
        ),
    }
    write_atomic(output, result)


def verify(manifest_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    differences = []
    for record in manifest.get("files", []):
        path = REPO_ROOT / record["path"]
        observed = {
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None,
        }
        if (
            observed["bytes"] != record["bytes"]
            or observed["sha256"] != record["sha256"]
        ):
            differences.append(
                {
                    "path": record["path"],
                    "expected": {
                        "bytes": record["bytes"],
                        "sha256": record["sha256"],
                    },
                    "observed": observed,
                }
            )
    identity = git_identity()
    if differences:
        raise RuntimeError(
            "Phase 04 tooling differs: "
            + json.dumps(differences, sort_keys=True)
        )
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
