#!/usr/bin/env python3
"""Apply the fixed DSpark integration patch and inject canonical HEDGE core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


SGLANG_BASE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
DEEPSPEC_CORE_SHA = "4d96f44065c07030ede67484a262006ec149626a"
CORE_FILES = (
    "__init__.py",
    "budget.py",
    "config.py",
    "torch_rule.py",
    "hedge_core_identity.json",
)
PATCHED_FILES = (
    "python/sglang/srt/entrypoints/openai/serving_chat.py",
    "python/sglang/srt/speculative/dspark_components/dspark_verify.py",
    "python/sglang/srt/speculative/dspark_components/dspark_worker_v2.py",
    "python/sglang/srt/speculative/dspark_components/hedge_dspark.py",
)
CORE_TARGET_ROOT = Path("python/sglang/srt/speculative/hedge_spec")


def _run(
    args: list[str], *, cwd: Path, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_record(root: Path, relative: Path) -> dict[str, str | int]:
    data = (root / relative).read_bytes()
    return {
        "path": relative.as_posix(),
        "sha256": _sha256(data),
        "size_bytes": len(data),
    }


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("ascii")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _tree_digest(records: list[dict[str, str | int]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(item["path"])):
        digest.update(str(record["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def apply(*, source: Path, repo: Path, patch: Path) -> dict:
    source = source.resolve()
    repo = repo.resolve()
    patch = patch.resolve()
    if not (source / ".git").exists():
        # Linked worktrees have a .git file rather than a directory.
        if not (source / ".git").is_file():
            raise RuntimeError(f"not a Git source tree: {source}")

    head = _run(["git", "rev-parse", "HEAD"], cwd=source).stdout.strip()
    if head != SGLANG_BASE_SHA:
        raise RuntimeError(
            f"SGLang HEAD must be {SGLANG_BASE_SHA}, got {head}"
        )
    tracked_status = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=source,
    ).stdout
    if tracked_status:
        raise RuntimeError(
            "SGLang tracked source is not clean before patch application:\n"
            + tracked_status
        )
    full_status = _run(
        ["git", "status", "--porcelain=v1"], cwd=source
    ).stdout
    if full_status:
        raise RuntimeError(
            "SGLang source has untracked files before patch application:\n"
            + full_status
        )

    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            DEEPSPEC_CORE_SHA,
            "HEAD",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise RuntimeError(
            f"DeepSpec HEAD does not contain pure-core commit {DEEPSPEC_CORE_SHA}"
        )

    canonical_root = repo / "deepspec/hedge_spec"
    canonical: dict[str, bytes] = {}
    for name in CORE_FILES:
        relative = Path("deepspec/hedge_spec") / name
        data = (repo / relative).read_bytes()
        committed = _run(
            ["git", "show", f"{DEEPSPEC_CORE_SHA}:{relative.as_posix()}"],
            cwd=repo,
        ).stdout.encode("utf-8")
        if data != committed:
            raise RuntimeError(
                f"canonical core differs from {DEEPSPEC_CORE_SHA}: {relative}"
            )
        canonical[name] = data
    if not patch.is_file():
        raise RuntimeError(f"integration patch does not exist: {patch}")

    target_root = source / CORE_TARGET_ROOT
    if target_root.exists():
        raise RuntimeError(f"core injection target already exists: {target_root}")
    _run(
        ["git", "apply", "--unidiff-zero", "--check", str(patch)],
        cwd=source,
    )
    _run(["git", "apply", "--unidiff-zero", str(patch)], cwd=source)

    target_root.mkdir(parents=True, exist_ok=False)
    core_records = []
    for name, data in canonical.items():
        target = target_root / name
        target.write_bytes(data)
        if target.read_bytes() != data:
            raise RuntimeError(f"core injection changed bytes: {target}")
        core_records.append(
            {
                "canonical_path": str((canonical_root / name).relative_to(repo)),
                "target_path": str(target.relative_to(source)),
                "sha256": _sha256(data),
                "size_bytes": len(data),
                "byte_identical": True,
            }
        )

    _run(["git", "diff", "--check"], cwd=source)
    final_files = [
        _file_record(source, Path(relative)) for relative in PATCHED_FILES
    ]
    final_files.extend(
        _file_record(source, CORE_TARGET_ROOT / name) for name in CORE_FILES
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "sglang_base_sha": SGLANG_BASE_SHA,
        "sglang_head_after_apply": _run(
            ["git", "rev-parse", "HEAD"], cwd=source
        ).stdout.strip(),
        "deepspec_core_sha": DEEPSPEC_CORE_SHA,
        "patch_path": str(patch),
        "patch_sha256": _sha256(patch.read_bytes()),
        "core_files": core_records,
        "final_files": final_files,
        "final_tree_sha256": _tree_digest(final_files),
        "source_status": _run(
            ["git", "status", "--porcelain=v1"], cwd=source
        ).stdout.splitlines(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path)
    args = parser.parse_args()
    result = apply(source=args.source, repo=args.repo, patch=args.patch)
    if args.manifest_out is not None:
        _atomic_json(args.manifest_out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
