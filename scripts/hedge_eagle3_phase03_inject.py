#!/usr/bin/env python3
"""Inject the canonical HEDGE core into the lane-local SGLang package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


DEFAULT_DEEPSPEC_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
DEFAULT_SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
HEDGE_SOURCE_SHA = "9fb903d676254ea5f5d171051fb15c54f331111c"
PURE_CORE_PUBLISH_SHA = "4d96f44065c07030ede67484a262006ec149626a"
EAGLE3_IMPORT_SHA = "4cefd0a36ea254e4c14a83f35dc8db15b37a3384"
CORE_FILES = ("__init__.py", "budget.py", "config.py", "torch_rule.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def git_blob(root: Path, revision: str, path: str) -> bytes:
    return subprocess.run(
        ("git", "-C", str(root), "show", f"{revision}:{path}"),
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout


def inject(
    *,
    deepspec_root: Path = DEFAULT_DEEPSPEC_ROOT,
    sglang_root: Path = DEFAULT_SGLANG_ROOT,
) -> dict[str, object]:
    deepspec_root = deepspec_root.resolve()
    sglang_root = sglang_root.resolve()
    head = git(sglang_root, "rev-parse", "HEAD")
    if head != SGLANG_BASE:
        raise RuntimeError(
            f"SGLang HEAD {head} differs from fixed base {SGLANG_BASE}"
        )
    deepspec_head = git(deepspec_root, "rev-parse", "HEAD")
    ancestry = subprocess.run(
        (
            "git",
            "-C",
            str(deepspec_root),
            "merge-base",
            "--is-ancestor",
            EAGLE3_IMPORT_SHA,
            deepspec_head,
        ),
        check=False,
        timeout=60,
    )
    if ancestry.returncode != 0:
        raise RuntimeError(
            "Eagle3 pure-core import commit is not an ancestor of DeepSpec HEAD"
        )
    source = deepspec_root / "deepspec/hedge_spec"
    destination = (
        sglang_root / "python/sglang/srt/speculative/hedge_spec"
    )
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for filename in CORE_FILES:
        source_file = source / filename
        destination_file = destination / filename
        source_hash = sha256(source_file)
        canonical_path = f"deepspec/hedge_spec/{filename}"
        publisher_blob = git_blob(
            deepspec_root,
            PURE_CORE_PUBLISH_SHA,
            canonical_path,
        )
        import_blob = git_blob(
            deepspec_root,
            EAGLE3_IMPORT_SHA,
            canonical_path,
        )
        if publisher_blob != import_blob or import_blob != source_file.read_bytes():
            raise RuntimeError(
                "publisher/import/worktree pure-core bytes differ: "
                f"{filename}"
            )
        shutil.copyfile(source_file, destination_file)
        destination_hash = sha256(destination_file)
        if destination_hash != source_hash:
            raise RuntimeError(f"injected core differs: {filename}")
        records.append(
            {
                "source": str(source_file.relative_to(deepspec_root)),
                "destination": str(
                    destination_file.relative_to(sglang_root)
                ),
                "sha256": source_hash,
                "bytes": source_file.stat().st_size,
                "dspark_publish_sha256": hashlib.sha256(
                    publisher_blob
                ).hexdigest(),
                "eagle3_import_sha256": hashlib.sha256(
                    import_blob
                ).hexdigest(),
            }
        )
    aggregate = hashlib.sha256()
    for record in records:
        aggregate.update(str(record["destination"]).encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(record["sha256"]).encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": 1,
        "status": "PASS",
        "hedge_source_sha": HEDGE_SOURCE_SHA,
        "dspark_pure_core_publish_sha": PURE_CORE_PUBLISH_SHA,
        "eagle3_pure_core_import_sha": EAGLE3_IMPORT_SHA,
        "deepspec_head": deepspec_head,
        "deepspec_root": str(deepspec_root),
        "sglang_base": SGLANG_BASE,
        "sglang_head": head,
        "sglang_root": str(sglang_root),
        "files": records,
        "injected_file_count": len(records),
        "aggregate_sha256": aggregate.hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
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
    args = parser.parse_args()
    manifest = inject(
        deepspec_root=args.deepspec_root,
        sglang_root=args.sglang_root,
    )
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
