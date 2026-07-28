#!/usr/bin/env python3
"""Finalize canonical P00 session and keepalive artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


AUTONOMY_START = "2026-07-28T20:54:41Z"
AUTONOMY_DEADLINE = "2026-07-29T08:54:41Z"
EXPECTED_HEAD = "cac6c78d88df97d395406fe831f573df3016e7f7"
EXPECTED_SGLANG = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PINNED_HEDGE = "9fb903d676254ea5f5d171051fb15c54f331111c"


def atomic_json(path: Path, payload: Any) -> None:
    if path.exists():
        raise RuntimeError(f"refusing existing canonical artifact: {path}")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip())
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--base-repo", type=Path, required=True)
    args = parser.parse_args()

    migration_path = (
        args.artifact_dir / "keepalive-migration" / "keepalive_migration.json"
    )
    checkpoint_path = args.artifact_dir / "checkpoint_identity.json"
    environment_path = args.artifact_dir / "environment_identity.json"
    sglang_path = args.artifact_dir / "sglang_base_identity.json"
    cuda_path = args.artifact_dir / "cuda_link_probe.json"
    final_worker_path = (
        args.artifact_dir / "final-state" / "worker_inventory.json"
    )
    paths = (
        migration_path,
        checkpoint_path,
        environment_path,
        sglang_path,
        cuda_path,
        final_worker_path,
    )
    records = {
        path.name if path.parent == args.artifact_dir else str(
            path.relative_to(args.artifact_dir)
        ): json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    }
    migration = records["keepalive-migration/keepalive_migration.json"]
    checkpoint = records["checkpoint_identity.json"]
    environment = records["environment_identity.json"]
    sglang = records["sglang_base_identity.json"]
    cuda = records["cuda_link_probe.json"]
    final_worker = records["final-state/worker_inventory.json"]

    bootstrap_path = args.artifact_dir / "keepalive_initial.json"
    preserved_bootstrap = args.artifact_dir / "keepalive_bootstrap_initial.json"
    if bootstrap_path.exists() and not preserved_bootstrap.exists():
        os.replace(bootstrap_path, preserved_bootstrap)
    canonical_keepalive = {
        "schema_version": 1,
        "authorized_phase": "P00",
        "status": migration["status"],
        "worker_id": migration["worker_id"],
        "runtime_python": migration["new_runtime_python"],
        "supervisor_pid": migration["new"]["pid"],
        "supervisor_pgid": migration["new"]["pgid"],
        "supervisor_sid": migration["new"]["sid"],
        "health": migration["new"]["health"],
        "migration_evidence": str(migration_path),
        "bootstrap_evidence": str(preserved_bootstrap),
        "resolved_environment": migration["new_resolved_environment"],
    }
    if bootstrap_path.exists():
        existing_keepalive = json.loads(
            bootstrap_path.read_text(encoding="utf-8")
        )
        if existing_keepalive != canonical_keepalive:
            raise RuntimeError("conflicting canonical keepalive artifact")
    else:
        atomic_json(bootstrap_path, canonical_keepalive)

    hedge_source = Path(
        "/mlx_devbox/users/pengzegang/playground/github/HEDGE"
    )
    hedge_head = git(hedge_source, "rev-parse", "HEAD")
    pinned_present = (
        subprocess.run(
            [
                "git",
                "-C",
                str(hedge_source),
                "cat-file",
                "-e",
                f"{PINNED_HEDGE}^{{commit}}",
            ],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    process_text = final_worker["process_inventory"]["stdout"]
    forbidden_server_markers = (
        "sglang.launch_server",
        "python -m sglang",
        "vllm.entrypoints",
        "torchrun",
    )
    server_processes = [
        line
        for line in process_text.splitlines()
        if any(marker in line.lower() for marker in forbidden_server_markers)
    ]

    current_head = git(args.worktree, "rev-parse", "HEAD")
    initial_head_is_ancestor = (
        subprocess.run(
            [
                "git",
                "-C",
                str(args.worktree),
                "merge-base",
                "--is-ancestor",
                EXPECTED_HEAD,
                current_head,
            ],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    checks = {
        "initial_worktree_head_is_ancestor": initial_head_is_ancestor,
        "worktree_branch": git(
            args.worktree, "branch", "--show-current"
        )
        == "exp/hedge-v4-dspark",
        "checkpoint": checkpoint["status"] == "PASS",
        "environment_versions": (
            environment["packages"]["sglang"] == "0.5.16"
            and environment["packages"]["torch"] == "2.11.0+cu130"
        ),
        "sglang_base": (
            sglang["status"] == "PASS"
            and sglang["source_commit"] == EXPECTED_SGLANG
        ),
        "cuda_link": cuda["status"] == "PASS",
        "keepalive": (
            migration["status"] == "PASS"
            and migration["new_runtime_python"]
            == "/home/tiger/venvs/hedge-v4-dspark/bin/python"
        ),
        "worker": (
            final_worker["inventory_passed"]
            and final_worker["expected_gpu_count"] == 8
        ),
        "no_model_server": not server_processes,
        "pinned_hedge_object_present": pinned_present,
    }
    session = {
        "schema_version": 1,
        "authorized_phase": "P00",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "attempt_id": "20260728T205441Z-p00-bootstrap",
        "autonomy_start_utc": AUTONOMY_START,
        "autonomy_deadline_utc": AUTONOMY_DEADLINE,
        "finalized_at_utc": dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "worker": {
            "id": "4106666",
            "hostname": final_worker["hostname"],
            "gpu_count": 8,
            "gpu_uuids": [gpu["uuid"] for gpu in final_worker["gpus"]],
            "model_server_started": False,
            "model_server_processes": server_processes,
            "operational_keepalive_pid": migration["new"]["pid"],
            "operational_keepalive_pgid": migration["new"]["pgid"],
            "operational_keepalive_sid": migration["new"]["sid"],
        },
        "git": {
            "worktree": str(args.worktree),
            "branch": git(args.worktree, "branch", "--show-current"),
            "initial_head": EXPECTED_HEAD,
            "head": current_head,
            "remote": git(args.worktree, "remote", "get-url", "origin"),
            "dirty_paths_at_handoff": git(
                args.worktree, "status", "--short"
            ).splitlines(),
            "base_worktree": str(args.base_repo),
            "base_head": git(args.base_repo, "rev-parse", "HEAD"),
            "base_dirty_paths_preserved": git(
                args.base_repo, "status", "--short"
            ).splitlines(),
        },
        "identity": {
            "checkpoint_snapshot": checkpoint["snapshot_identity"],
            "checkpoint_file_count": checkpoint["file_count"],
            "checkpoint_shard_count": checkpoint["shard_count"],
            "checkpoint_payload_bytes": checkpoint["total_bytes"],
            "full_checkpoint_hash_performed": False,
            "sglang_base_commit": sglang["source_commit"],
            "sglang_source": sglang["target_source"],
            "venv": environment["venv"],
            "hedge_source_current_head": hedge_head,
            "hedge_source_required_commit": PINNED_HEDGE,
            "hedge_required_commit_present": pinned_present,
            "hedge_source_current_dirty_paths": git(
                hedge_source, "status", "--short"
            ).splitlines(),
            "hedge_p00_note": (
                "P00 recorded the current source HEAD only. P02 must read "
                "tracked core/tests from the pinned commit object and must "
                "not modify the HEDGE worktree."
            ),
        },
        "artifacts": {
            str(path.relative_to(args.artifact_dir)): {
                "path": str(path),
                "sha256": sha256(path),
            }
            for path in (*paths, bootstrap_path, preserved_bootstrap)
        },
        "checks": checks,
        "next_eligible_phase": "P03 after main-Agent P00 acceptance",
        "executor_scope_ended": True,
    }
    atomic_json(args.artifact_dir / "session.json", session)
    print(
        json.dumps(
            {
                "status": session["status"],
                "keepalive_pid": migration["new"]["pid"],
                "server_processes": server_processes,
            },
            sort_keys=True,
        )
    )
    return 0 if session["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
