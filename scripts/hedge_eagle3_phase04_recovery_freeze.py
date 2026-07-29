#!/usr/bin/env python3
"""Freeze the Phase 04 EAGLEWorkerV2 recovery without mutating Phase 03 authority."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from hedge_eagle3_phase03_freeze import (
    SGLANG_BASE,
    clean_replay,
    complete_patch,
    injection_identity,
    sha256_bytes,
    sha256_file,
)


DEEPSPEC_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python")
PHASE03_FINAL_SHA = "90c8558721de37ed0dc12802f29253ba52b873bc"
PHASE03_LOCAL_PATCH = (
    DEEPSPEC_ROOT
    / "patches/hedge_eagle3_phase03/sglang-final-candidate.patch"
)
PHASE03_HDFS_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T030500Z-phase-03-hedge-adapter-01"
)
EXPECTED_RECOVERY_FILES = (
    "python/sglang/srt/speculative/eagle_worker_v2.py",
    "test/registered/unit/speculative/test_eagle3_hedge.py",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        timeout=timeout,
    )


def git_text(*args: str, cwd: Path = SGLANG_ROOT) -> str:
    return run(("git", *args), cwd=cwd).stdout.decode("utf-8").strip()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def phase03_authority() -> dict[str, object]:
    paths = {
        "local_patch": PHASE03_LOCAL_PATCH,
        "hdfs_patch": PHASE03_HDFS_ROOT / "sglang-final-candidate.patch",
        "hdfs_manifest": PHASE03_HDFS_ROOT / "manifest.json",
    }
    records = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"Phase 03 authority file is absent: {path}")
        records[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    if (
        records["local_patch"]["sha256"]
        != records["hdfs_patch"]["sha256"]
    ):
        raise RuntimeError("Phase 03 local/HDFS patch identity differs")
    return records


def source_identity() -> dict[str, object]:
    head = git_text("rev-parse", "HEAD")
    if head != PHASE03_FINAL_SHA:
        raise RuntimeError(f"unexpected Phase 03 SGLang HEAD: {head}")
    status = (
        run(("git", "status", "--short"), cwd=SGLANG_ROOT)
        .stdout.decode("utf-8")
        .splitlines()
    )
    changed = tuple(
        line[3:] for line in status if len(line) >= 4
    )
    if tuple(sorted(changed)) != tuple(sorted(EXPECTED_RECOVERY_FILES)):
        raise RuntimeError(f"unexpected recovery source status: {status}")
    if any(not line.startswith(" M ") for line in status):
        raise RuntimeError(f"recovery must only modify tracked files: {status}")
    return {
        "head": head,
        "status": status,
        "recovery_files": list(EXPECTED_RECOVERY_FILES),
        "final_sha": "PENDING_MAIN_AGENT_SGLANG_COMMIT",
        "final_sha_status": "PENDING_MAIN_AGENT_REVIEW_AND_COMMIT",
    }


def in_place_regression(output: Path) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = str(SGLANG_ROOT / "python")
    commands = (
        (
            str(PYTHON),
            "test/registered/unit/models/test_deepseek_v4_eagle3_aux.py",
            "-v",
        ),
        (
            str(PYTHON),
            "test/registered/unit/speculative/test_eagle3_hedge.py",
            "-v",
        ),
        (
            str(PYTHON),
            "-m",
            "py_compile",
            "python/sglang/srt/speculative/eagle_worker_v2.py",
            "test/registered/unit/speculative/test_eagle3_hedge.py",
        ),
        ("git", "diff", "--check"),
    )
    logs = []
    records = []
    for command in commands:
        completed = run(command, cwd=SGLANG_ROOT, env=env)
        stdout = completed.stdout.decode("utf-8")
        stderr = completed.stderr.decode("utf-8")
        logs.extend(
            (
                f"$ {' '.join(command)}\n",
                stdout,
                stderr,
                "\n",
            )
        )
        records.append(
            {
                "command": list(command),
                "returncode": completed.returncode,
            }
        )
    output.write_text("".join(logs), encoding="utf-8")
    return {
        "status": "PASS",
        "commands": records,
        "expected_counts": {
            "deepseek_v4_eagle3_aux": 11,
            "eagle3_hedge": 25,
        },
        "log": output.name,
        "log_sha256": sha256_file(output),
    }


def tdd_cycles() -> list[dict[str, object]]:
    prefix = [
        str(PYTHON),
        "test/registered/unit/speculative/test_eagle3_hedge.py",
    ]
    return [
        {
            "seam": "registry-selected concrete worker lifecycle",
            "test": (
                "TestEagleWorkerV2HedgeIntegration."
                "test_registry_selected_worker_exposes_hedge_lifecycle"
            ),
            "red": "AttributeError: EAGLEWorkerV2 has no dump_info_records",
            "green": "PASS",
            "command_prefix": prefix,
        },
        {
            "seam": "EAGLE3-only adapter construction",
            "test": (
                "TestEagleWorkerV2HedgeIntegration."
                "test_worker_constructs_adapter_only_for_eagle3"
            ),
            "red": "AttributeError: EAGLEWorkerV2 has no _hedge_adapter",
            "green": "PASS",
            "command_prefix": prefix,
        },
        {
            "seam": "prefill request-state binding order",
            "test": (
                "TestEagleWorkerV2HedgeIntegration."
                "test_prefill_binds_request_state_before_target_forward"
            ),
            "red": "events [target, draft] != [bind, target, draft]",
            "green": "PASS",
            "command_prefix": prefix,
        },
        {
            "seam": "shared verifier adapter routing",
            "test": (
                "TestEagleWorkerV2HedgeIntegration."
                "test_verify_passes_same_adapter_to_shared_verifier"
            ),
            "red": "run_eagle_verify kwargs missing hedge_adapter",
            "green": "PASS",
            "command_prefix": prefix,
        },
    ]


def file_manifest(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        records.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def publish(local_dir: Path, output_dir: Path) -> None:
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite recovery artifact: {output_dir}")
    staging = output_dir.with_name(
        f"{output_dir.name}.staging-{os.getpid()}"
    )
    if staging.exists():
        raise RuntimeError(f"unexpected recovery staging path: {staging}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(local_dir, staging)
    if file_manifest(local_dir) != file_manifest(staging):
        raise RuntimeError("recovery artifact staging verification differs")
    os.replace(staging, output_dir)
    if file_manifest(local_dir) != file_manifest(output_dir):
        raise RuntimeError("published recovery artifact verification differs")


def freeze(output_dir: Path) -> dict[str, object]:
    before_authority = phase03_authority()
    source = source_identity()
    with tempfile.TemporaryDirectory(
        prefix="deepspec-eagle3-phase04-recovery-",
        dir="/tmp",
    ) as temporary:
        local_dir = Path(temporary) / "artifact"
        local_dir.mkdir()

        full_patch, full_names = complete_patch(SGLANG_ROOT)
        full_patch_path = local_dir / "sglang-fixed-base-candidate.patch"
        full_patch_path.write_bytes(full_patch)

        delta_patch = run(
            (
                "git",
                "diff",
                "--binary",
                "--full-index",
                PHASE03_FINAL_SHA,
                "--",
            ),
            cwd=SGLANG_ROOT,
        ).stdout
        delta_names = git_text(
            "diff",
            "--name-only",
            PHASE03_FINAL_SHA,
            "--",
        ).splitlines()
        if tuple(delta_names) != EXPECTED_RECOVERY_FILES:
            raise RuntimeError(f"unexpected recovery delta: {delta_names}")
        delta_path = local_dir / "sglang-phase04-recovery.patch"
        delta_path.write_bytes(delta_patch)

        in_place = in_place_regression(
            local_dir / "in-place-tests.log"
        )
        clean, clean_log = clean_replay(
            sglang_root=SGLANG_ROOT,
            patch_path=full_patch_path,
        )
        clean_log_path = local_dir / "clean-replay-tests.log"
        clean_log_path.write_text(clean_log, encoding="utf-8")
        clean["log"] = clean_log_path.name
        clean["log_sha256"] = sha256_file(clean_log_path)

        after_authority = phase03_authority()
        if before_authority != after_authority:
            raise RuntimeError("Phase 03 authority changed during recovery freeze")

        manifest = {
            "schema_version": 1,
            "status": "RECOVERY_CANDIDATE_PASS_PENDING_MAIN_COMMIT",
            "created_at": utc_now(),
            "blocker_attempt": (
                "20260729T040000Z-phase-04-native-calibration-02"
            ),
            "blocker_signature": (
                "enable_multi_layer_eagle=false selected EAGLEWorkerV2 "
                "without HEDGE bind/verify/lifecycle hooks"
            ),
            "single_variable_recovery": (
                "wire the existing Eagle3 HEDGE adapter into the concrete "
                "EAGLEWorkerV2 selected by the fixed server config"
            ),
            "sglang_base_sha": SGLANG_BASE,
            "source": source,
            "phase03_authority_unchanged": {
                "status": "PASS",
                "before": before_authority,
                "after": after_authority,
            },
            "full_candidate": {
                "path": full_patch_path.name,
                "bytes": len(full_patch),
                "sha256": sha256_bytes(full_patch),
                "changed_file_count": len(full_names),
                "changed_files": full_names,
            },
            "phase04_delta": {
                "path": delta_path.name,
                "bytes": len(delta_patch),
                "sha256": sha256_bytes(delta_patch),
                "changed_file_count": len(delta_names),
                "changed_files": delta_names,
            },
            "tdd_cycles": tdd_cycles(),
            "in_place_regression": in_place,
            "clean_replay": clean,
            "injection": injection_identity(SGLANG_ROOT),
            "gpu_actions": "NONE",
            "review_gate": (
                "No GPU launch until the main Agent reviews this manifest, "
                "commits SGLang, and seals a new Phase 04 source identity."
            ),
        }
        manifest_path = local_dir / "manifest.json"
        write_json(manifest_path, manifest)
        (local_dir / "manifest.sha256").write_text(
            f"{sha256_file(manifest_path)}  manifest.json\n",
            encoding="utf-8",
        )
        publish(local_dir, output_dir)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = freeze(args.output_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
