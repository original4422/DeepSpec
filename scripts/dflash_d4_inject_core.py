#!/usr/bin/env python3
"""Inject the canonical DeepSpec HEDGE core into one pinned SGLang checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = REPO_ROOT / "deepspec" / "hedge_spec"
TARGET_RELATIVE_ROOT = Path("python/sglang/srt/speculative/hedge_spec")
CORE_FILES = (
    "__init__.py",
    "budget.py",
    "config.py",
    "hedge_core_identity.json",
    "torch_rule.py",
)
UPSTREAM_CORE_COMMIT = "4d96f44065c07030ede67484a262006ec149626a"
SGLANG_BASE_COMMIT = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_output(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *args],
        text=True,
    ).strip()


def content_hash(entries: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def inject(*, sglang_root: Path, check_only: bool) -> dict[str, object]:
    sglang_root = sglang_root.resolve()
    if not (sglang_root / ".git").exists():
        raise SystemExit(f"not a Git checkout: {sglang_root}")
    git_output(sglang_root, "cat-file", "-e", f"{SGLANG_BASE_COMMIT}^{{commit}}")

    canonical_commit = git_output(
        REPO_ROOT,
        "log",
        "-1",
        "--format=%H",
        "--",
        "deepspec/hedge_spec",
    )
    sglang_before = git_output(sglang_root, "rev-parse", "HEAD")
    target_root = sglang_root / TARGET_RELATIVE_ROOT
    entries: list[dict[str, str]] = []
    mismatches: list[str] = []

    if not check_only:
        target_root.mkdir(parents=True, exist_ok=True)

    for filename in CORE_FILES:
        source = CANONICAL_ROOT / filename
        target = target_root / filename
        payload = source.read_bytes()
        expected = sha256_bytes(payload)
        if check_only:
            if not target.is_file() or sha256_bytes(target.read_bytes()) != expected:
                mismatches.append(filename)
        else:
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{filename}.",
                dir=target_root,
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, target)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        entries.append(
            {
                "path": filename,
                "sha256": expected,
            }
        )

    if mismatches:
        raise SystemExit(
            "injected core differs from canonical files: " + ", ".join(mismatches)
        )

    return {
        "schema_version": 1,
        "status": "PASS",
        "mode": "check" if check_only else "inject",
        "canonical_repository": str(REPO_ROOT),
        "canonical_commit": canonical_commit,
        "upstream_pure_core_commit": UPSTREAM_CORE_COMMIT,
        "sglang_repository": str(sglang_root),
        "sglang_base_commit": SGLANG_BASE_COMMIT,
        "sglang_head_before": sglang_before,
        "target_root": str(TARGET_RELATIVE_ROOT),
        "files": entries,
        "content_hash": content_hash(entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--manifest-out", type=Path)
    args = parser.parse_args()

    manifest = inject(sglang_root=args.sglang_root, check_only=args.check)
    serialized = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.manifest_out is not None:
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_out.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
