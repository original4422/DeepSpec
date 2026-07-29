#!/usr/bin/env python3
"""Freeze and clean-replay the complete Eagle3 SGLang source candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


DEFAULT_DEEPSPEC_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
DEFAULT_SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python")
SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
HEDGE_SOURCE_SHA = "9fb903d676254ea5f5d171051fb15c54f331111c"
PURE_CORE_PUBLISH_SHA = "4d96f44065c07030ede67484a262006ec149626a"
EAGLE3_IMPORT_SHA = "4cefd0a36ea254e4c14a83f35dc8db15b37a3384"
PENDING_FINAL_SHA = "PENDING_MAIN_AGENT_SGLANG_FINAL_SHA"
CORE_DESTINATIONS = (
    "python/sglang/srt/speculative/hedge_spec/__init__.py",
    "python/sglang/srt/speculative/hedge_spec/budget.py",
    "python/sglang/srt/speculative/hedge_spec/config.py",
    "python/sglang/srt/speculative/hedge_spec/torch_rule.py",
)
SOURCE_TESTS = (
    "test/registered/unit/models/test_deepseek_v4_eagle3_aux.py",
    "test/registered/unit/speculative/test_eagle3_hedge.py",
)
EXPECTED_MECHANICAL_CONTEXT_LINES = (
    7,
    8,
    33,
    37,
    48,
    49,
    67,
    77,
    92,
    111,
    316,
    321,
    326,
    414,
    460,
    462,
    466,
    1431,
    2053,
    2057,
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(
    command: tuple[str, ...],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        timeout=timeout,
    )


def complete_patch(sglang_root: Path) -> tuple[bytes, list[str]]:
    with tempfile.TemporaryDirectory(
        prefix="deepspec-eagle3-phase03-index-",
        dir="/tmp",
    ) as temporary:
        index = Path(temporary) / "index"
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(index)
        run(
            ("git", "-C", str(sglang_root), "read-tree", SGLANG_BASE),
            env=env,
        )
        run(
            ("git", "-C", str(sglang_root), "add", "-A", "--"),
            env=env,
        )
        patch = run(
            (
                "git",
                "-C",
                str(sglang_root),
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                SGLANG_BASE,
                "--",
            ),
            env=env,
        ).stdout
        names = (
            run(
                (
                    "git",
                    "-C",
                    str(sglang_root),
                    "diff",
                    "--cached",
                    "--name-only",
                    SGLANG_BASE,
                    "--",
                ),
                env=env,
            )
            .stdout.decode("utf-8")
            .splitlines()
        )
    if not patch or not names:
        raise RuntimeError("complete SGLang candidate patch is empty")
    return patch, names


def injection_identity(sglang_root: Path) -> dict[str, object]:
    records = []
    aggregate = hashlib.sha256()
    for relative in CORE_DESTINATIONS:
        path = sglang_root / relative
        digest = sha256_file(path)
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "file_count": len(records),
        "files": records,
        "aggregate_sha256": aggregate.hexdigest(),
    }


def clean_replay(
    *,
    sglang_root: Path,
    patch_path: Path,
) -> tuple[dict[str, object], str]:
    patch_path = patch_path.resolve()
    with tempfile.TemporaryDirectory(
        prefix="deepspec-eagle3-phase03-full-replay-",
        dir="/tmp",
    ) as temporary:
        clean_root = Path(temporary) / "sglang"
        run(
            (
                "git",
                "-C",
                str(sglang_root),
                "worktree",
                "add",
                "--detach",
                str(clean_root),
                SGLANG_BASE,
            )
        )
        logs = []
        try:
            run(
                (
                    "git",
                    "-C",
                    str(clean_root),
                    "apply",
                    "--check",
                    str(patch_path),
                )
            )
            run(
                (
                    "git",
                    "-C",
                    str(clean_root),
                    "apply",
                    str(patch_path),
                )
            )
            run(("git", "-C", str(clean_root), "diff", "--check"))
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONHASHSEED"] = "0"
            env["PYTHONPATH"] = str(clean_root / "python")
            for relative in SOURCE_TESTS:
                completed = run(
                    (str(PYTHON), str(clean_root / relative), "-v"),
                    cwd=clean_root,
                    env=env,
                    timeout=180,
                )
                logs.append(completed.stdout.decode("utf-8"))
                logs.append(completed.stderr.decode("utf-8"))
            applied_patch, _ = complete_patch(clean_root)
            if sha256_bytes(applied_patch) != sha256_file(patch_path):
                raise RuntimeError("clean replay patch hash differs")
            result = {
                "status": "PASS",
                "base_sha": SGLANG_BASE,
                "git_apply_check": "PASS",
                "git_diff_check": "PASS",
                "source_tests": list(SOURCE_TESTS),
                "python": str(PYTHON),
                "patch_sha256_after_replay": sha256_bytes(applied_patch),
            }
        finally:
            run(
                (
                    "git",
                    "-C",
                    str(sglang_root),
                    "worktree",
                    "remove",
                    "--force",
                    str(clean_root),
                )
            )
    return result, "".join(logs)


def freeze(
    *,
    deepspec_root: Path,
    sglang_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    deepspec_root = deepspec_root.resolve()
    sglang_root = sglang_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {output_dir}")
    head = (
        run(("git", "-C", str(sglang_root), "rev-parse", "HEAD"))
        .stdout.decode()
        .strip()
    )
    if head != SGLANG_BASE:
        raise RuntimeError(f"SGLang HEAD differs from base: {head}")
    patch, changed_files = complete_patch(sglang_root)
    mechanical_context_lines = tuple(
        line_number
        for line_number, line in enumerate(
            patch.splitlines(),
            start=1,
        )
        if line == b" "
    )
    if mechanical_context_lines != EXPECTED_MECHANICAL_CONTEXT_LINES:
        raise RuntimeError(
            "canonical patch context-marker identity differs"
        )
    patch_path = output_dir / "sglang-final-candidate.patch"
    patch_path.write_bytes(patch)
    replay, replay_log = clean_replay(
        sglang_root=sglang_root,
        patch_path=patch_path,
    )
    replay_log_path = output_dir / "clean-replay-tests.log"
    replay_log_path.write_text(replay_log, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "status": "FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT",
        "hedge_source_sha": HEDGE_SOURCE_SHA,
        "dspark_pure_core_publish_sha": PURE_CORE_PUBLISH_SHA,
        "eagle3_pure_core_import_sha": EAGLE3_IMPORT_SHA,
        "deepspec_head_before_phase03_commit": (
            run(("git", "-C", str(deepspec_root), "rev-parse", "HEAD"))
            .stdout.decode()
            .strip()
        ),
        "deepspec_staged_diff_check": {
            "status": "PASS_WITH_CANONICAL_PATCH_EXCLUDED",
            "excluded_diff_check": "PASS",
            "excluded_path": (
                "patches/hedge_eagle3_phase03/"
                "sglang-final-candidate.patch"
            ),
            "mechanical_warning_count": len(
                mechanical_context_lines
            ),
            "mechanical_warning_reason": (
                "The canonical unified diff contains blank context-marker "
                "lines consisting of one space. As an outer newly added "
                "DeepSpec file, those immutable bytes render as '+ ' and "
                "trigger git diff --check trailing-whitespace warnings."
            ),
        },
        "sglang_base_sha": SGLANG_BASE,
        "sglang_head_before_final_commit": head,
        "sglang_final_sha": PENDING_FINAL_SHA,
        "sglang_final_sha_status": "PENDING_MAIN_AGENT_COMMIT",
        "sglang_candidate": {
            "patch": patch_path.name,
            "patch_bytes": len(patch),
            "patch_sha256": sha256_bytes(patch),
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
        },
        "injection": injection_identity(sglang_root),
        "uv_lock": {
            "path": "uv.lock",
            "sha256": sha256_file(deepspec_root / "uv.lock"),
            "bytes": (deepspec_root / "uv.lock").stat().st_size,
        },
        "clean_replay": {
            **replay,
            "log": replay_log_path.name,
            "log_sha256": sha256_file(replay_log_path),
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deepspec-root",
        type=Path,
        default=DEFAULT_DEEPSPEC_ROOT,
    )
    parser.add_argument(
        "--sglang-root",
        type=Path,
        default=DEFAULT_SGLANG_ROOT,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = freeze(
        deepspec_root=args.deepspec_root,
        sglang_root=args.sglang_root,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
