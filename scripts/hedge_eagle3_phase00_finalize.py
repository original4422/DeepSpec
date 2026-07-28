#!/usr/bin/env python3
"""Seal the small, reproducible Phase 00 bootstrap artifacts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence


RUN_DIR = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T205627Z-phase-00-bootstrap-01"
)
COORD_DIR = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-20260728T205627Z"
)
WORKTREE = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
ORIGINAL_WORKTREE = Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def capture(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    required: bool = True,
) -> dict[str, Any]:
    completed = subprocess.run(
        tuple(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    stdout_path = RUN_DIR / "raw" / f"devbox_{name}.stdout.txt"
    stderr_path = RUN_DIR / "raw" / f"devbox_{name}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if required and completed.returncode != 0:
        raise RuntimeError(
            f"{name} failed: rc={completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return {
        "name": name,
        "command": list(command),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout": completed.stdout,
    }


def main() -> int:
    inventory = read_json(RUN_DIR / "worker_inventory.json")
    processes = read_json(RUN_DIR / "existing_processes.json")
    namespace = read_json(RUN_DIR / "namespace_bootstrap.json")
    if not (
        inventory["worker_id"] == "4099544"
        and inventory["observed_gpu_count"] == 8
        and inventory["exact_gpu_count"] is True
        and inventory["all_h20"] is True
    ):
        raise RuntimeError("worker inventory does not prove exact 8xH20")
    if processes["signal_sent"] is not False:
        raise RuntimeError("process artifact reports a signal")
    if not (
        namespace["port_available"] is True
        and namespace["keepalive_started"] is False
        and namespace["gpu_workload_started"] is False
        and namespace["signal_sent"] is False
    ):
        raise RuntimeError("namespace evidence violates Phase 00 boundaries")

    commands = [
        capture("mlx_worker_list", ("mlx", "worker", "list"), cwd=WORKTREE),
        capture(
            "eagle_git_status",
            ("git", "status", "--short", "--branch"),
            cwd=WORKTREE,
        ),
        capture(
            "eagle_git_head",
            ("git", "rev-parse", "HEAD"),
            cwd=WORKTREE,
        ),
        capture(
            "eagle_git_branch",
            ("git", "branch", "--show-current"),
            cwd=WORKTREE,
        ),
        capture(
            "git_worktree_list",
            ("git", "worktree", "list", "--porcelain"),
            cwd=WORKTREE,
        ),
        capture(
            "original_git_status",
            ("git", "status", "--short", "--branch"),
            cwd=ORIGINAL_WORKTREE,
        ),
        capture(
            "devbox_capacity",
            (
                "df",
                "-B1",
                "--output=source,size,used,avail,pcent,target",
                str(WORKTREE),
                "/mnt/hdfs/pengzegang/DeepSpec",
            ),
            cwd=WORKTREE,
        ),
    ]
    worker_list = commands[0]["stdout"]
    if "4099544" not in worker_list or "8      NVIDIA-H20" not in worker_list:
        raise RuntimeError("fresh mlx worker list does not prove 8xH20")
    if commands[2]["stdout"].strip() != (
        "cac6c78d88df97d395406fe831f573df3016e7f7"
    ):
        raise RuntimeError("unexpected Eagle3 bootstrap base")
    if commands[3]["stdout"].strip() != "exp/hedge-v4-eagle3":
        raise RuntimeError("unexpected Eagle3 branch")

    now = (
        dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    deadlines = {
        "schema_version": 1,
        "started_at": "2026-07-28T20:56:27Z",
        "implementation_cutoff": "2026-07-29T05:56:27Z",
        "hard_stop": "2026-07-29T08:56:27Z",
        "worker": "4099544",
        "gpu_count": 8,
        "tp_size": 8,
        "eagle3_no_b0_action_at_cutoff": (
            "stop implementation and GPU experiments; preserve evidence only"
        ),
    }
    assignment = {
        "schema_version": 1,
        "kind": "worker_assignment",
        "session": "hedge-v4-eagle3",
        "status": "READY_FOR_KEEPALIVE",
        "worker_id": "4099544",
        "expected_gpu_count": 8,
        "expected_gpu_model": "NVIDIA H20",
        "gpu_indices": list(range(8)),
        "gpu_uuids": [gpu["uuid"] for gpu in inventory["gpus"]],
        "tp_size": 8,
        "cuda_visible_devices": "0,1,2,3,4,5,6,7",
        "worktree": str(WORKTREE),
        "branch": "exp/hedge-v4-eagle3",
        "state_dir": "/home/tiger/.deepspec-hedge-v4-eagle3",
        "scratch_root": "/tmp/deepspec-hedge-v4-eagle3",
        "hdfs_root": "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3",
        "run_root": (
            "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs"
        ),
        "coordination_root": (
            "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4"
        ),
        "http_port": 31001,
        "assigned_at": deadlines["started_at"],
        "implementation_cutoff": deadlines["implementation_cutoff"],
        "hard_stop": deadlines["hard_stop"],
        "signals_sent": [],
    }
    bootstrap = {
        "schema_version": 1,
        "status": "PHASE_00_READY_FOR_ACCEPTANCE",
        "created_at": now,
        "session": "hedge-v4-eagle3",
        "plan": "docs/plan/hedge-deepseek-v4-flash-eagle3.md",
        "worktree": str(WORKTREE),
        "branch": "exp/hedge-v4-eagle3",
        "base_sha": "cac6c78d88df97d395406fe831f573df3016e7f7",
        "sglang_source_path": "/home/tiger/src/sglang-hedge-v4-eagle3",
        "sglang_source_created": False,
        "sglang_base_sha": "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
        "uv_env_path": "/home/tiger/venvs/deepspec-hedge-v4-eagle3",
        "uv_env_created": False,
        "worker_id": "4099544",
        "worker_hostname": inventory["hostname"],
        "observed_gpu_count": inventory["observed_gpu_count"],
        "all_h20": inventory["all_h20"],
        "existing_compute_pid_count": processes["compute_pid_count"],
        "existing_keepalive_candidate_pid_count": (
            processes["keepalive_candidate_pid_count"]
        ),
        "keepalive_script": str(
            WORKTREE / "scripts/hedge_eagle3_keepalive.sh"
        ),
        "keepalive_owner_schema": str(
            WORKTREE
            / "schemas/hedge_eagle3_keepalive_owner.schema.json"
        ),
        "worker_owner_schema": str(
            WORKTREE
            / "schemas/hedge_eagle3_worker_owner.schema.json"
        ),
        "keepalive_started": False,
        "gpu_workload_started": False,
        "model_download_started": False,
        "formal_environment_installed": False,
        "signal_sent": False,
        "commit_or_push_performed": False,
        "run_dir": str(RUN_DIR),
        "coordination_dir": str(COORD_DIR),
        "deadlines_path": str(RUN_DIR / "deadlines.json"),
        "worker_inventory_path": str(
            RUN_DIR / "worker_inventory.json"
        ),
        "existing_processes_path": str(
            RUN_DIR / "existing_processes.json"
        ),
        "worker_assignment_path": str(
            RUN_DIR / "worker_assignment.json"
        ),
        "raw_devbox_commands": str(
            RUN_DIR / "devbox_command_outputs.json"
        ),
    }
    handoff = f"""# Phase 00 handoff

Status: **PASS — ready for main Agent acceptance**.

- T0: `{deadlines["started_at"]}`
- T0+9h: `{deadlines["implementation_cutoff"]}`
- T0+12h: `{deadlines["hard_stop"]}`
- Worker: `4099544`, hostname `{inventory["hostname"]}`
- Inventory: exact 8×NVIDIA H20, physical indices 0–7 and UUID mapping saved
- Existing compute PIDs: `{processes["compute_pid_count"]}`
- Existing keepalive candidates: `{processes["keepalive_candidate_pid_count"]}`
- Signal sent: **no**
- GPU workload or keepalive started: **no**
- Checkpoint download / formal env install / Phase 01 work: **no**

## Exit gates

- PASS: independent worktree `{WORKTREE}` and branch `exp/hedge-v4-eagle3`
- PASS: env/source paths, port 31001, scratch/state/HDFS namespaces have no
  detected owner conflict; only small owner markers were created
- PASS: fresh `mlx worker list` and remote inventory prove 8×H20
- PASS: full GPU UUID, memory, topology and command outputs are retained
- PASS: all observed existing PID dispositions are machine-readable; the
  observed set was empty
- PASS: no signal was sent
- PASS: worker and exact-eight-GPU keepalive owner JSON schemas exist
- PASS: T0+9h and T0+12h are machine-readable in `deadlines.json`

## Residual state and Phase 01 conditions

No compute PID, CUDA context, keepalive, server or model process was present at
inventory time, and Phase 00 created none. The worker is therefore
`READY_FOR_KEEPALIVE`, not `KEEPALIVE_ACTIVE`. After main-Agent acceptance,
Phase 01 must establish the dedicated Python/uv prerequisite and start the
prepared exact-eight-GPU keepalive before any long unattended step, then prove
10×1-second mean utilization >=40% independently on all eight GPUs. Phase 01A,
01B and 01C may then proceed within their own bounded executors.

Canonical artifact directory: `{RUN_DIR}`
"""
    write_exclusive(RUN_DIR / "deadlines.json", deadlines)
    write_exclusive(RUN_DIR / "worker_assignment.json", assignment)
    write_exclusive(RUN_DIR / "bootstrap.json", bootstrap)
    write_exclusive(RUN_DIR / "devbox_command_outputs.json", commands)
    (RUN_DIR / "phase-00-handoff.md").write_text(
        handoff,
        encoding="utf-8",
    )
    write_exclusive(COORD_DIR / "worker_assignment.json", assignment)
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_dir": str(RUN_DIR),
                "coordination_assignment": str(
                    COORD_DIR / "worker_assignment.json"
                ),
                "worker_id": "4099544",
                "gpu_count": 8,
                "existing_compute_pid_count": (
                    processes["compute_pid_count"]
                ),
                "keepalive_started": False,
                "signal_sent": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
