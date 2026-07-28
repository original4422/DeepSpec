#!/usr/bin/env python3
"""Remove redirected signed URLs from completed D1A curl event evidence."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import urllib.parse


REVISION = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
WORKTREE = pathlib.Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
NVME_ATTEMPTS = pathlib.Path(
    "/tmp/deepspec-hedge-dflash/d1a/attempts"
)
HDFS_EVIDENCE = pathlib.Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/evidence/d1a"
)
REPO_EVIDENCE = (
    WORKTREE
    / "docs"
    / "experiment"
    / "artifacts"
    / "hedge-deepseek-v4-flash-dflash"
    / "d1a"
)


def sanitize_curl_stdout(raw: str) -> tuple[str, bool]:
    if not raw:
        return raw, False
    value = json.loads(raw)
    effective = value.pop("url_effective", None)
    if effective is None:
        return json.dumps(value, sort_keys=True), False
    parsed = urllib.parse.urlsplit(effective)
    value["effective_endpoint"] = parsed.hostname
    value["effective_url_redacted"] = True
    return json.dumps(value, sort_keys=True), True


def sanitize(path: pathlib.Path) -> dict[str, object]:
    rows = []
    changed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if "curl_stdout" in row:
            row["curl_stdout"], row_changed = sanitize_curl_stdout(
                row["curl_stdout"]
            )
            changed += int(row_changed)
        rows.append(row)
    temporary = path.with_name(f".{path.name}.sanitize-{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(temporary, path)
    red_flags = (
        "X-Amz-",
        "Signature=",
        "Policy=",
        "Key-Pair-Id=",
        "url_effective",
    )
    payload = path.read_text(encoding="utf-8")
    hits = [needle for needle in red_flags if needle in payload]
    if hits:
        raise RuntimeError(f"signed URL material remains in {path}: {hits}")
    return {
        "path": str(path),
        "rows": len(rows),
        "redirected_urls_redacted": changed,
        "signed_url_scan_passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_id")
    args = parser.parse_args()
    if not re.fullmatch(
        r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", args.attempt_id
    ):
        raise SystemExit("invalid attempt id")
    roots = [
        NVME_ATTEMPTS / args.attempt_id,
        HDFS_EVIDENCE / args.attempt_id,
        REPO_EVIDENCE / args.attempt_id,
    ]
    paths = [root / "download_events.jsonl" for root in roots]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"completed evidence files are missing: {missing}")
    result = [sanitize(path) for path in paths]
    print(json.dumps({"sanitized": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
