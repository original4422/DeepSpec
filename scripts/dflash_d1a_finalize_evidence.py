#!/usr/bin/env python3
"""Audit and mirror supplemental D1A evidence after successful publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
from typing import Any

import dflash_d1a_acquire_publish as base


MANDATORY_SUPPLEMENTS = {
    "retry_monitor.jsonl",
    "retry_reset_diagnostic.json",
    "reset_observation.json",
}
OPTIONAL_SUPPLEMENTS = {
    "error.json",
    "recovery_events.jsonl",
    "recovery_preflight.json",
}
SIGNED_URL_MARKERS = (
    "X-Amz-Signature",
    "X-Amz-Credential",
    "X-Xet-Cas-Uid",
    "Key-Pair-Id=",
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def copy_new_or_match(source: pathlib.Path, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if (
            destination.stat().st_size != source.stat().st_size
            or sha256(destination) != sha256(source)
        ):
            raise RuntimeError(
                f"existing evidence differs; overwrite refused: {destination}"
            )
        return
    temporary = destination.with_name(
        f".{destination.name}.staging-{os.getpid()}"
    )
    shutil.copyfile(source, temporary)
    os.rename(temporary, destination)


def copy_authoritative(source: pathlib.Path, destination: pathlib.Path) -> None:
    """Atomically refresh a known mutable evidence file from worker NVMe."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.refresh-{os.getpid()}"
    )
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def records(root: pathlib.Path, exclude: set[str]) -> list[dict[str, Any]]:
    output = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name in exclude:
            continue
        output.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_id")
    args = parser.parse_args()
    if not re.fullmatch(
        r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", args.attempt_id
    ):
        raise SystemExit("invalid attempt id")

    acquisition = base.Acquisition(args.attempt_id)
    attempt = acquisition.attempt_root
    repo = acquisition.repo_evidence
    hdfs = acquisition.hdfs_evidence
    for root in (attempt, repo, hdfs):
        if not root.is_dir():
            raise RuntimeError(f"completed evidence root missing: {root}")
        summary = json.loads((root / "summary.json").read_text())
        if summary.get("status") != "PASS":
            raise RuntimeError(f"evidence root is not PASS: {root}")

    final_keepalive = subprocess.run(
        [
            "bash",
            str(base.WORKTREE / "scripts" / "dflash_keepalive.sh"),
            "status",
            base.WORKER_ID,
        ],
        check=True,
        text=True,
        capture_output=True,
        timeout=75,
    )
    keepalive_gate = json.loads(
        (
            pathlib.Path("/tmp/deepspec-hedge-dflash/keepalive")
            / "keepalive_gate.json"
        ).read_text()
    )
    keepalive_identity = json.loads(
        (
            pathlib.Path("/tmp/deepspec-hedge-dflash/keepalive")
            / "process_identity.json"
        ).read_text()
    )
    if (
        keepalive_gate.get("healthy") is not True
        or keepalive_identity.get("worker_id") != base.WORKER_ID
        or keepalive_identity.get("pid") != acquisition.verify_keepalive()
    ):
        raise RuntimeError("final D1A keepalive gate failed")
    keepalive_record = {
        "schema_version": 1,
        "worker_id": base.WORKER_ID,
        "hostname": socket.gethostname(),
        "keepalive_identity": keepalive_identity,
        "gate": keepalive_gate,
        "status_stdout": final_keepalive.stdout,
        "status_stderr": final_keepalive.stderr,
        "keepalive_was_paused_or_stopped": False,
        "model_process_started": False,
        "checked_at_utc": base.utc_now(),
    }
    base.write_json(attempt / "keepalive_final_status.json", keepalive_record)

    reset_source = (
        base.REPO_EVIDENCE_PARENT / "reset_observation.json"
    )
    if not reset_source.is_file():
        raise RuntimeError("repo reset_observation.json is missing")
    copy_new_or_match(reset_source, attempt / "reset_observation.json")

    available = {
        name
        for name in MANDATORY_SUPPLEMENTS | OPTIONAL_SUPPLEMENTS
        if (attempt / name).is_file()
    }
    missing = MANDATORY_SUPPLEMENTS - available
    if missing:
        raise RuntimeError(f"mandatory supplemental evidence missing: {missing}")
    available.add("keepalive_final_status.json")
    for name in sorted(available):
        copy_new_or_match(attempt / name, repo / name)
        copy_new_or_match(attempt / name, hdfs / name)
    # The acquisition writes its final "evidence export PASS" line only after
    # the initial bundle copy. Refresh this known mutable log from the retained
    # NVMe source before demanding byte-identical evidence mirrors.
    for name in ("download.log", "heartbeat.json"):
        for destination_root in (repo, hdfs):
            copy_authoritative(
                attempt / name, destination_root / name
            )

    for root in (attempt, repo, hdfs):
        for path in root.iterdir():
            if not path.is_file():
                continue
            if path.stat().st_size > 4 * 1024 * 1024:
                raise RuntimeError(f"unexpected large repo evidence: {path}")
            payload = path.read_bytes()
            hits = [
                marker
                for marker in SIGNED_URL_MARKERS
                if marker.encode() in payload
            ]
            if hits:
                raise RuntimeError(
                    f"signed URL material found in {path}: {hits}"
                )

    pointer = json.loads(base.HDFS_POINTER.read_text())
    complete = json.loads((base.HDFS_FORMAL / ".complete").read_text())
    provider = json.loads((attempt / "provider_metadata.json").read_text())
    if (
        pointer.get("repo_id") != base.REPO_ID
        or pointer.get("revision") != base.REVISION
        or pointer.get("formal_path") != str(base.HDFS_FORMAL)
        or pointer.get("complete_path") != str(base.HDFS_FORMAL / ".complete")
        or complete.get("repo_id") != base.REPO_ID
        or complete.get("revision") != base.REVISION
        or pointer.get("provider_manifest_sha256")
        != provider.get("manifest_sha256")
        or complete.get("provider_manifest_sha256")
        != provider.get("manifest_sha256")
    ):
        raise RuntimeError("final pointer/.complete/provider identity mismatch")
    formal_files = base.relative_regular_files(base.HDFS_FORMAL)
    if set(formal_files) != base.EXPECTED_PROVIDER_FILES | {".complete"}:
        raise RuntimeError("formal checkpoint file set mismatch")
    formal_payload_bytes = sum(
        formal_files[name].stat().st_size
        for name in base.EXPECTED_PROVIDER_FILES
    )
    if formal_payload_bytes != provider["total_size_bytes"]:
        raise RuntimeError("formal checkpoint payload byte total mismatch")

    exclude = {
        "evidence_audit.json",
        "evidence_manifest.json",
    }
    repo_records = records(repo, exclude)
    repo_by_name = {item["name"]: item for item in repo_records}
    for other in (attempt, hdfs):
        other_by_name = {
            item["name"]: item for item in records(other, exclude)
        }
        if other_by_name != repo_by_name:
            raise RuntimeError(
                f"evidence mirror mismatch between repo and {other}"
            )
    manifest = {
        "schema_version": 1,
        "attempt_id": args.attempt_id,
        "files": repo_records,
        "manifest_sha256": base.canonical_json_sha256(repo_records),
    }
    audit = {
        "schema_version": 1,
        "status": "PASS",
        "phase": "D1A",
        "attempt_id": args.attempt_id,
        "provider": "huggingface",
        "repo_id": base.REPO_ID,
        "revision": base.REVISION,
        "provider_manifest_sha256": provider["manifest_sha256"],
        "provider_file_count": provider["file_count"],
        "provider_total_size_bytes": provider["total_size_bytes"],
        "formal_path": str(base.HDFS_FORMAL),
        "complete_path": str(base.HDFS_FORMAL / ".complete"),
        "draft_pointer_path": str(base.HDFS_POINTER),
        "complete_sha256": sha256(base.HDFS_FORMAL / ".complete"),
        "draft_pointer_sha256": sha256(base.HDFS_POINTER),
        "formal_file_set_match": True,
        "formal_payload_bytes_match": True,
        "evidence_manifest_sha256": manifest["manifest_sha256"],
        "evidence_mirrors_match": True,
        "signed_url_scan_passed": True,
        "keepalive_final_gate_passed": True,
        "keepalive_pid": keepalive_identity["pid"],
        "keepalive_was_paused_or_stopped": False,
        "model_process_started": False,
        "fallback_checkpoint_enabled": False,
        "full_weight_sha256_recomputed": False,
        "audited_at_utc": base.utc_now(),
    }
    for root in (attempt, repo, hdfs):
        base.write_json(root / "evidence_manifest.json", manifest)
        base.write_json(root / "evidence_audit.json", audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
