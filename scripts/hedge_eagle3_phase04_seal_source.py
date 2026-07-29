#!/usr/bin/env python3
"""Publish the reviewed post-recovery Phase 04 SGLang source identity."""

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
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
SGLANG_BASE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PHASE03_FINAL_SHA = "90c8558721de37ed0dc12802f29253ba52b873bc"
PHASE04_FINAL_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
PHASE03_PATCH_SHA256 = (
    "13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945"
)
PHASE04_PATCH_SHA256 = (
    "73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf"
)
PHASE04_DELTA_SHA256 = (
    "e08b3ab919cc6f9088b5b578765c6af547ef12c40f1da4ce99c55d405ff4b668"
)
RECOVERY_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T042500Z-phase-04-eagle-worker-recovery-01"
)
PHASE03_HDFS_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T030500Z-phase-03-hedge-adapter-01"
)
CANONICAL_ROOT = REPO_ROOT / "patches/hedge_eagle3_phase04"
EXPECTED_FILES = (
    "python/sglang/srt/arg_groups/deepseek_v4_hook.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/models/deepseek_v4.py",
    "python/sglang/srt/speculative/eagle3_hedge.py",
    "python/sglang/srt/speculative/eagle_utils.py",
    "python/sglang/srt/speculative/eagle_worker_common.py",
    "python/sglang/srt/speculative/eagle_worker_v2.py",
    "python/sglang/srt/speculative/hedge_spec/__init__.py",
    "python/sglang/srt/speculative/hedge_spec/budget.py",
    "python/sglang/srt/speculative/hedge_spec/config.py",
    "python/sglang/srt/speculative/hedge_spec/torch_rule.py",
    "python/sglang/srt/speculative/multi_layer_eagle_worker_v2.py",
    "test/registered/unit/models/test_deepseek_v4_eagle3_aux.py",
    "test/registered/unit/speculative/test_eagle3_hedge.py",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: Sequence[str],
    *,
    cwd: Path = SGLANG_ROOT,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        tuple(command),
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=300,
    )


def git_text(*args: str) -> str:
    return run(("git", *args)).stdout.decode("utf-8").strip()


def phase03_authority() -> dict[str, dict[str, Any]]:
    paths = {
        "local_patch": (
            REPO_ROOT
            / "patches/hedge_eagle3_phase03/sglang-final-candidate.patch"
        ),
        "hdfs_patch": PHASE03_HDFS_ROOT / "sglang-final-candidate.patch",
        "hdfs_manifest": PHASE03_HDFS_ROOT / "manifest.json",
    }
    records = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"Phase 03 authority is absent: {path}")
        records[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    if (
        records["local_patch"]["sha256"] != PHASE03_PATCH_SHA256
        or records["hdfs_patch"]["sha256"] != PHASE03_PATCH_SHA256
    ):
        raise RuntimeError("Phase 03 frozen patch identity differs")
    return records


def recovery_identity() -> dict[str, Any]:
    manifest_path = RECOVERY_ROOT / "manifest.json"
    companion_path = RECOVERY_ROOT / "manifest.sha256"
    patch_path = RECOVERY_ROOT / "sglang-fixed-base-candidate.patch"
    delta_path = RECOVERY_ROOT / "sglang-phase04-recovery.patch"
    for path in (manifest_path, companion_path, patch_path, delta_path):
        if not path.is_file():
            raise RuntimeError(f"recovery artifact is absent: {path}")
    expected_companion = companion_path.read_text(encoding="utf-8").split()[0]
    if sha256(manifest_path) != expected_companion:
        raise RuntimeError("recovery manifest companion hash differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "RECOVERY_CANDIDATE_PASS_PENDING_MAIN_COMMIT":
        raise RuntimeError("recovery manifest status differs")
    if sha256(patch_path) != PHASE04_PATCH_SHA256:
        raise RuntimeError("recovery full patch identity differs")
    if sha256(delta_path) != PHASE04_DELTA_SHA256:
        raise RuntimeError("recovery delta identity differs")
    return {
        "root": str(RECOVERY_ROOT),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "full_patch_sha256": PHASE04_PATCH_SHA256,
        "delta_sha256": PHASE04_DELTA_SHA256,
        "clean_replay_status": manifest["clean_replay"]["status"],
        "clean_replay_log_sha256": manifest["clean_replay"]["log_sha256"],
    }


def source_candidate() -> tuple[bytes, list[str]]:
    head = git_text("rev-parse", "HEAD")
    status = git_text("status", "--short")
    if head != PHASE04_FINAL_SHA or status:
        raise RuntimeError(
            f"post-recovery SGLang source differs: head={head} status={status!r}"
        )
    patch = run(
        (
            "git",
            "diff",
            "--binary",
            "--full-index",
            SGLANG_BASE_SHA,
            PHASE04_FINAL_SHA,
            "--",
        )
    ).stdout
    names = git_text(
        "diff",
        "--name-only",
        SGLANG_BASE_SHA,
        PHASE04_FINAL_SHA,
        "--",
    ).splitlines()
    if names != list(EXPECTED_FILES):
        raise RuntimeError(f"post-recovery changed file set differs: {names}")
    if sha256_bytes(patch) != PHASE04_PATCH_SHA256:
        raise RuntimeError("post-recovery fixed-base patch identity differs")
    recovery_patch = RECOVERY_ROOT / "sglang-fixed-base-candidate.patch"
    if patch != recovery_patch.read_bytes():
        raise RuntimeError("post-commit patch differs from reviewed recovery patch")
    run(
        (
            "git",
            "apply",
            "--check",
            "--reverse",
            str(recovery_patch),
        )
    )
    return patch, names


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def records(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(item for item in root.iterdir() if item.is_file())
    ]


def publish_hdfs(local: Path, output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite source identity: {output}")
    staging = output.with_name(f"{output.name}.staging-{os.getpid()}")
    if staging.exists():
        raise RuntimeError(f"unexpected source identity staging: {staging}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(local, staging)
    if records(local) != records(staging):
        raise RuntimeError("source identity HDFS staging differs")
    os.replace(staging, output)
    if records(local) != records(output):
        raise RuntimeError("published source identity differs")


def seal(output: Path) -> dict[str, Any]:
    before = phase03_authority()
    recovery = recovery_identity()
    patch, changed_files = source_candidate()
    manifest = {
        "schema_version": 1,
        "status": "FINAL_SOURCE_IDENTITY_PASS",
        "created_at": utc_now(),
        "sglang": {
            "base_sha": SGLANG_BASE_SHA,
            "phase03_parent_sha": PHASE03_FINAL_SHA,
            "final_sha": PHASE04_FINAL_SHA,
            "worktree_clean": True,
            "patch": "sglang-final-candidate.patch",
            "patch_bytes": len(patch),
            "patch_sha256": PHASE04_PATCH_SHA256,
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
        },
        "recovery": recovery,
        "phase03_authority_before": before,
        "phase03_authority_immutability": "MUST_REMAIN_UNCHANGED",
    }
    if CANONICAL_ROOT.exists():
        raise RuntimeError(
            f"refusing to overwrite Phase 04 canonical authority: {CANONICAL_ROOT}"
        )
    canonical_staging = CANONICAL_ROOT.with_name(
        f"{CANONICAL_ROOT.name}.staging-{os.getpid()}"
    )
    if canonical_staging.exists():
        raise RuntimeError(f"unexpected canonical staging: {canonical_staging}")
    canonical_staging.mkdir(parents=True)
    (canonical_staging / "sglang-final-candidate.patch").write_bytes(patch)
    write_json(canonical_staging / "manifest.json", manifest)
    (canonical_staging / "README.md").write_text(
        "# Eagle3 Phase 04 source authority\n\n"
        "本目录固定 live retry 02 暴露 concrete `EAGLEWorkerV2` seam 后的"
        "最小 recovery source。完整 patch 始于固定 SGLang base，"
        "Phase 03 authority 保持只读不变。SGLang final SHA 为 "
        f"`{PHASE04_FINAL_SHA}`，patch SHA-256 为 "
        f"`{PHASE04_PATCH_SHA256}`。\n",
        encoding="utf-8",
    )
    os.replace(canonical_staging, CANONICAL_ROOT)

    canonical_records = records(CANONICAL_ROOT)
    canonical = {
        **manifest,
        "canonical_root": str(CANONICAL_ROOT),
        "canonical_files": canonical_records,
        "canonical_manifest_sha256": sha256(
            CANONICAL_ROOT / "manifest.json"
        ),
    }
    with tempfile.TemporaryDirectory(
        prefix="deepspec-eagle3-phase04-source-",
        dir="/tmp",
    ) as temporary:
        local = Path(temporary) / "artifact"
        local.mkdir()
        write_json(local / "source_identity.json", canonical)
        (local / "sglang-final-candidate.patch").write_bytes(patch)
        artifact_manifest = {
            "schema_version": 1,
            "status": "PASS",
            "files": records(local),
        }
        write_json(local / "artifact_manifest.json", artifact_manifest)
        publish_hdfs(local, output)

    after = phase03_authority()
    if before != after:
        raise RuntimeError("Phase 03 authority changed while sealing Phase 04")
    return {
        "status": "PASS",
        "canonical_root": str(CANONICAL_ROOT),
        "canonical_manifest_sha256": canonical[
            "canonical_manifest_sha256"
        ],
        "hdfs_source_identity": str(output),
        "phase03_authority_unchanged": True,
        "sglang_final_sha": PHASE04_FINAL_SHA,
        "sglang_patch_sha256": PHASE04_PATCH_SHA256,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seal(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
