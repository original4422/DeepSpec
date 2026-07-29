#!/usr/bin/env python3
"""Seal the reproducible DFlash HEDGE integration patch and source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SGLANG_ROOT = Path("/home/tiger/src/deepspec-sglang-hedge-dflash")
SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PRE_INTEGRATION_HEAD = "1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5"
FINAL_SOURCE_COMMIT = "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
UPSTREAM_CORE_COMMIT = "4d96f44065c07030ede67484a262006ec149626a"
INTEGRATION_FILES = (
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/speculative/dflash_worker_v2.py",
    "python/sglang/srt/speculative/dflash_hedge.py",
)
CORE_FILES = (
    "python/sglang/srt/speculative/hedge_spec/__init__.py",
    "python/sglang/srt/speculative/hedge_spec/budget.py",
    "python/sglang/srt/speculative/hedge_spec/config.py",
    "python/sglang/srt/speculative/hedge_spec/hedge_core_identity.json",
    "python/sglang/srt/speculative/hedge_spec/torch_rule.py",
)


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_records(paths: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "sha256": sha256((SGLANG_ROOT / path).read_bytes()),
        }
        for path in paths
    ]


def combined_hash(records: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_patch() -> bytes:
    tracked = run(
        [
            "git",
            "diff",
            "--binary",
            "--unified=0",
            PRE_INTEGRATION_HEAD,
            "--",
            INTEGRATION_FILES[0],
            INTEGRATION_FILES[1],
        ],
        cwd=SGLANG_ROOT,
    ).stdout
    added = run(
        [
            "git",
            "diff",
            "--no-index",
            "--binary",
            "--unified=0",
            "/dev/null",
            INTEGRATION_FILES[2],
        ],
        cwd=SGLANG_ROOT,
        check=False,
    )
    if added.returncode not in {0, 1}:
        raise RuntimeError(added.stderr.decode("utf-8", errors="replace"))
    patch = tracked + added.stdout
    if not patch:
        raise RuntimeError("integration patch is unexpectedly empty")
    return patch


def check_patch_artifact_whitespace(patch: bytes) -> None:
    """Prove the serialized patch is clean when stored as a Git artifact."""

    with tempfile.TemporaryDirectory(
        prefix="dflash-d4-patch-artifact-check-"
    ) as temp:
        repository = Path(temp)
        run(["git", "init", "--quiet"], cwd=repository)
        patch_path = repository / "integration.patch"
        patch_path.write_bytes(patch)
        run(["git", "add", "integration.patch"], cwd=repository)
        run(["git", "diff", "--cached", "--check"], cwd=repository)


def check_patch(patch: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="dflash-d4-patch-check-") as temp:
        temporary = Path(temp)
        patch_path = temporary / "integration.patch"
        patch_path.write_bytes(patch)
        index_path = temporary / "index"
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(index_path)
        run(
            ["git", "read-tree", PRE_INTEGRATION_HEAD],
            cwd=SGLANG_ROOT,
            env=env,
        )
        run(
            [
                "git",
                "apply",
                "--cached",
                "--unidiff-zero",
                "--check",
                str(patch_path),
            ],
            cwd=SGLANG_ROOT,
            env=env,
        )
        run(
            [
                "git",
                "apply",
                "--cached",
                "--unidiff-zero",
                str(patch_path),
            ],
            cwd=SGLANG_ROOT,
            env=env,
        )
        for path in CORE_FILES:
            blob = run(
                ["git", "rev-parse", f"{FINAL_SOURCE_COMMIT}:{path}"],
                cwd=SGLANG_ROOT,
            ).stdout.decode().strip()
            run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob},{path}",
                ],
                cwd=SGLANG_ROOT,
                env=env,
            )
        rebuilt_tree = run(
            ["git", "write-tree"],
            cwd=SGLANG_ROOT,
            env=env,
        ).stdout.decode().strip()
        final_tree = run(
            ["git", "rev-parse", f"{FINAL_SOURCE_COMMIT}^{{tree}}"],
            cwd=SGLANG_ROOT,
        ).stdout.decode().strip()
        if rebuilt_tree != final_tree:
            raise RuntimeError(
                f"rebuilt tree {rebuilt_tree} != final tree {final_tree}"
            )
        return rebuilt_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch-out", required=True, type=Path)
    parser.add_argument("--manifest-out", required=True, type=Path)
    args = parser.parse_args()
    patch_out = args.patch_out.resolve()
    manifest_out = args.manifest_out.resolve()

    observed_head = run(
        ["git", "rev-parse", "HEAD"],
        cwd=SGLANG_ROOT,
    ).stdout.decode().strip()
    if observed_head not in {PRE_INTEGRATION_HEAD, FINAL_SOURCE_COMMIT}:
        raise SystemExit(
            f"expected HEAD {PRE_INTEGRATION_HEAD} or {FINAL_SOURCE_COMMIT}, "
            f"got {observed_head}"
        )
    run(
        ["git", "cat-file", "-e", f"{SGLANG_BASE}^{{commit}}"],
        cwd=SGLANG_ROOT,
    )
    patch = build_patch()
    check_patch_artifact_whitespace(patch)
    rebuilt_tree = check_patch(patch)

    patch_out.parent.mkdir(parents=True, exist_ok=True)
    patch_out.write_bytes(patch)
    integration = file_records(INTEGRATION_FILES)
    core = file_records(CORE_FILES)
    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "sglang_repository": str(SGLANG_ROOT),
        "sglang_base_commit": SGLANG_BASE,
        "pre_integration_head": PRE_INTEGRATION_HEAD,
        "final_source_commit": FINAL_SOURCE_COMMIT,
        "final_source_tree": rebuilt_tree,
        "observed_head": observed_head,
        "upstream_pure_core_commit": UPSTREAM_CORE_COMMIT,
        "dflash_canonical_core_commit": run(
            [
                "git",
                "log",
                "-1",
                "--format=%H",
                "--",
                "deepspec/hedge_spec",
            ],
            cwd=REPO_ROOT,
        ).stdout.decode().strip(),
        "integration_patch": {
            "path": str(patch_out.relative_to(REPO_ROOT)),
            "sha256": sha256(patch),
            "bytes": len(patch),
            "format": "unified-zero",
            "apply_args": ["--unidiff-zero"],
            "artifact_git_diff_check": "PASS",
            "temporary_index_apply_check": "PASS",
            "patch_plus_injected_core_matches_final_tree": "PASS",
        },
        "integration_files": integration,
        "integration_content_hash": combined_hash(integration),
        "injected_core_files": core,
        "injected_core_content_hash": combined_hash(core),
        "rebuild_order": [
            "checkout pre_integration_head",
            "run scripts/dflash_d4_inject_core.py",
            "git apply --unidiff-zero integration_patch",
        ],
    }
    serialized = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
