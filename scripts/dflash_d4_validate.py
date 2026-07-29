#!/usr/bin/env python3
"""Run and seal the bounded D4 CPU acceptance suite."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SGLANG_ROOT = Path("/home/tiger/src/deepspec-sglang-hedge-dflash")
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-dflash/bin/python")
SOURCE_MANIFEST = (
    REPO_ROOT
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4"
    / "dflash_d4_source_manifest.json"
)
D4C_ATTEMPT_ID = "dflash-d4-b0-20260729T000000Z-a01"
D4C_FILES = (
    Path("scripts/dflash_d4_b0_attempt.sh"),
    Path("scripts/dflash_d4_b0_api.py"),
    Path("tests/hedge_dflash_integration/test_dflash_d4c_tooling.py"),
)


def run_case(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
) -> tuple[dict[str, object], str]:
    started = dt.datetime.now(dt.timezone.utc)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    finished = dt.datetime.now(dt.timezone.utc)
    output = completed.stdout
    counts = [
        int(match)
        for match in re.findall(r"Ran ([0-9]+) tests?", output)
    ]
    record = {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "test_counts": counts,
    }
    return record, f"===== {name} =====\n{output.rstrip()}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--log-out", required=True, type=Path)
    args = parser.parse_args()

    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "999",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
        }
    )
    cases = (
        (
            "canonical_core",
            [
                str(PYTHON),
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests/hedge_spec",
                "-v",
            ],
            REPO_ROOT,
        ),
        (
            "dflash_hedge_integration",
            [
                str(PYTHON),
                "-m",
                "unittest",
                "tests.hedge_dflash_integration.test_dflash_hedge_integration",
                "-v",
            ],
            REPO_ROOT,
        ),
        (
            "dflash_d4c_tooling",
            [
                str(PYTHON),
                "-m",
                "unittest",
                "tests.hedge_dflash_integration.test_dflash_d4c_tooling",
                "-v",
            ],
            REPO_ROOT,
        ),
        (
            "dflash_d4_source_capture_tooling",
            [
                str(PYTHON),
                "-m",
                "unittest",
                "tests.hedge_dflash_integration.test_dflash_d4_source_capture",
                "-v",
            ],
            REPO_ROOT,
        ),
        (
            "dflash_primary_regression",
            [
                str(PYTHON),
                "test/registered/unit/spec/test_dflash_deepseek_v4_primary.py",
                "-v",
            ],
            SGLANG_ROOT,
        ),
        (
            "dflash_overlap_regression",
            [
                str(PYTHON),
                "test/registered/unit/spec/test_dflash_overlap_hostsync.py",
                "-v",
            ],
            SGLANG_ROOT,
        ),
        (
            "injected_core_check",
            [
                str(PYTHON),
                "scripts/dflash_d4_inject_core.py",
                "--sglang-root",
                str(SGLANG_ROOT),
                "--check",
            ],
            REPO_ROOT,
        ),
        (
            "source_syntax",
            [
                str(PYTHON),
                "-c",
                (
                    "from pathlib import Path; "
                    "paths=["
                    "Path('python/sglang/srt/speculative/dflash_hedge.py'),"
                    "Path('python/sglang/srt/speculative/dflash_worker_v2.py'),"
                    "Path('python/sglang/srt/managers/scheduler.py')]; "
                    "[compile(path.read_text(), str(path), 'exec') "
                    "for path in paths]; print('syntax=PASS files=3')"
                ),
            ],
            SGLANG_ROOT,
        ),
    )

    records = []
    logs = []
    for name, command, cwd in cases:
        record, log = run_case(
            name=name,
            command=command,
            cwd=cwd,
            environment=environment,
        )
        records.append(record)
        logs.append(log)

    status = (
        "PASS"
        if all(record["status"] == "PASS" for record in records)
        else "FAIL"
    )
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    contract = json.loads(
        subprocess.check_output(
            [
                "bash",
                str(REPO_ROOT / D4C_FILES[0]),
                "contract",
                D4C_ATTEMPT_ID,
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
        )
    )
    summary = {
        "schema_version": 1,
        "status": status,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gpu_used": False,
        "environment": {
            key: environment[key]
            for key in (
                "CUDA_VISIBLE_DEVICES",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONHASHSEED",
                "PYTHONNOUSERSITE",
            )
        },
        "python": str(PYTHON),
        "cases": records,
        "d4c_readiness": {
            "status": "PASS",
            "gpu_used": False,
            "contract": contract,
            "files": [
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(
                        (REPO_ROOT / path).read_bytes()
                    ).hexdigest(),
                }
                for path in D4C_FILES
            ],
        },
        "source_identity": {
            "pre_integration_head": source_manifest["pre_integration_head"],
            "final_source_commit": source_manifest["final_source_commit"],
            "final_source_tree": source_manifest["final_source_tree"],
            "observed_head": source_manifest["observed_head"],
            "integration_patch_sha256": source_manifest["integration_patch"][
                "sha256"
            ],
            "integration_patch_format": source_manifest["integration_patch"][
                "format"
            ],
            "integration_patch_apply_args": source_manifest[
                "integration_patch"
            ]["apply_args"],
            "integration_patch_artifact_git_diff_check": source_manifest[
                "integration_patch"
            ]["artifact_git_diff_check"],
            "patch_plus_injected_core_matches_final_tree": source_manifest[
                "integration_patch"
            ]["patch_plus_injected_core_matches_final_tree"],
            "integration_content_hash": source_manifest[
                "integration_content_hash"
            ],
            "injected_core_content_hash": source_manifest[
                "injected_core_content_hash"
            ],
            "upstream_pure_core_commit": source_manifest[
                "upstream_pure_core_commit"
            ],
            "dflash_canonical_core_commit": source_manifest[
                "dflash_canonical_core_commit"
            ],
        },
    }
    json_out = args.json_out.resolve()
    log_out = args.log_out.resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    log_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log_out.write_text("\n".join(logs), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
