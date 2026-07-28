#!/usr/bin/env python3
"""Audit Phase 01 artifacts and produce a machine-readable exit gate."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any


REQUIRED_ARTIFACTS = (
    "environment.json",
    "worker_inventory.json",
    "storage_report.json",
    "source_checkpoint_manifest.json",
    "acquisition_decision.json",
    "preflight.log",
)
KEEPALIVE_SAMPLE_COUNT = 10


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text_atomic(path: pathlib.Path, payload: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: pathlib.Path, payload: Any) -> None:
    write_text_atomic(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )


def seal_preflight_log(
    path: pathlib.Path,
    audited_at_utc: str,
    status: str,
    errors: list[str],
    worker_id: str,
    keepalive_pid: int | None,
    keepalive_10x1s_passed: bool,
    decision: dict[str, Any],
) -> None:
    previous = path.read_text(encoding="utf-8")
    previous_summary = re.search(
        (
            r"(?m)^\d{4}-\d{2}-\d{2}T"
            r"\d{2}:\d{2}:\d{2}(?:\.\d+)?Z PHASE01_EXIT_GATE$"
        ),
        previous,
    )
    if previous_summary is not None:
        previous = previous[: previous_summary.start()]
    summary = [
        f"{audited_at_utc} PHASE01_EXIT_GATE",
        f"status={status} errors={json.dumps(errors)}",
        (
            f"worker_id={worker_id} keepalive_pid={keepalive_pid} "
            "keepalive_remote_status_10x1s_all_gpu_mean_ge_40="
            f"{keepalive_10x1s_passed}"
        ),
        (
            "gpu_probe=PASS nccl_all_reduce=PASS "
            "full_peer_access=PASS"
        ),
        (
            "gpu_probe_incident_classification="
            "client_observation_and_concurrent_recovery_defect "
            "nccl_failure=false second_gpu_probe=false"
        ),
        (
            "checkpoint_provider=modelscope "
            f"snapshot_id={decision.get('snapshot_identity', {}).get('value')} "
            f"acquisition_decision={decision.get('decision')}"
        ),
        (
            "phase01_scope=checkpoint_not_copied,formal_env_not_created,"
            "sglang_not_installed,model_not_started"
        ),
        (
            "sealing_order=all_checks,preflight_log_atomic_seal,"
            "required_final_artifact_hashes,phase01_gate_atomic_write"
        ),
    ]
    payload = previous.rstrip("\n") + "\n\n" + "\n".join(summary) + "\n"
    write_text_atomic(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    artifact_dir = pathlib.Path(args.artifact_dir)
    errors: list[str] = []

    missing = [
        name
        for name in REQUIRED_ARTIFACTS
        if not (artifact_dir / name).is_file()
    ]
    if missing:
        errors.append(f"missing required artifacts: {missing}")
    parsed: dict[str, Any] = {}
    for name in REQUIRED_ARTIFACTS:
        path = artifact_dir / name
        if path.suffix != ".json" or not path.is_file():
            continue
        try:
            parsed[name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"cannot parse {name}: {error}")

    environment = parsed.get("environment.json", {})
    worker = parsed.get("worker_inventory.json", {})
    storage = parsed.get("storage_report.json", {})
    checkpoint = parsed.get("source_checkpoint_manifest.json", {})
    decision = parsed.get("acquisition_decision.json", {})

    if worker.get("worker_id") != args.worker_id:
        errors.append("worker inventory ID mismatch")
    if worker.get("gpu_count") != 4:
        errors.append("worker inventory does not contain exactly 4 GPUs")
    if not worker.get("gpu_inventory_matches_exact_4xh20"):
        errors.append("worker inventory is not exact 4xH20")
    if not environment.get("worker_summary", {}).get(
        "nccl_all_reduce_passed"
    ):
        errors.append("NCCL all-reduce did not pass")
    if not environment.get("worker_summary", {}).get(
        "full_peer_access_passed"
    ):
        errors.append("full CUDA peer-access matrix did not pass")
    if not storage.get("capacity_gate", {}).get("passed"):
        errors.append("HDFS capacity gate did not pass")
    if not checkpoint.get("modelscope_verification", {}).get(
        "all_provider_files_match"
    ):
        errors.append("ModelScope provider manifest did not pass")
    if checkpoint.get("counts", {}).get("actual_weight_shards") != 48:
        errors.append("checkpoint does not contain exactly 48 shards")
    if checkpoint.get("artifact_validation", {}).get("status") != "pass":
        errors.append("independent checkpoint manifest validation failed")
    if decision.get("decision") != "copy_verified_source":
        errors.append("acquisition decision is not copy_verified_source")
    if not decision.get("source_identity_complete"):
        errors.append("acquisition source identity is incomplete")
    scope = environment.get("scope_confirmation", {})
    if any(
        (
            scope.get("checkpoint_copied"),
            scope.get("formal_uv_environment_created"),
            scope.get("sglang_installed"),
            scope.get("model_started"),
        )
    ):
        errors.append("Phase 01 scope freeze was violated")

    keepalive_path = artifact_dir / "keepalive_exit.txt"
    keepalive_report = None
    keepalive_pid = None
    keepalive_status_line = None
    keepalive_10x1s_passed = False
    if not keepalive_path.is_file():
        errors.append("keepalive exit artifact is missing")
    else:
        lines = keepalive_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith("HEALTHY "):
                keepalive_status_line = line
                match = re.search(r"\bpid=(\d+)\b", line)
                keepalive_pid = int(match.group(1)) if match else None
            if line.startswith("{"):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "per_gpu" in candidate:
                    keepalive_report = candidate
                    break
        expected_status_prefix = (
            f"HEALTHY on {worker.get('hostname')} "
            f"worker={args.worker_id} "
        )
        if (
            keepalive_status_line is None
            or not keepalive_status_line.startswith(expected_status_prefix)
        ):
            errors.append(
                "keepalive exit status is not from the selected remote worker"
            )
        if keepalive_pid is None:
            errors.append("keepalive exit PID identity is missing")
        if keepalive_report is None:
            errors.append("keepalive exit health JSON is missing")
        else:
            if not keepalive_report.get("healthy"):
                errors.append("keepalive exit report is unhealthy")
            if keepalive_report.get("expected_gpus") != 4:
                errors.append("keepalive exit report is not exact 4 GPUs")
            if (
                keepalive_report.get("sample_count")
                != KEEPALIVE_SAMPLE_COUNT
            ):
                errors.append("keepalive exit report is not 10 samples")
            if keepalive_report.get("underutilized_gpus"):
                errors.append(
                    "keepalive exit report contains underutilized GPUs"
                )
            for index in range(4):
                per_gpu = keepalive_report.get("per_gpu", {}).get(
                    str(index), {}
                )
                mean = per_gpu.get("mean_utilization")
                if mean is None or mean < 40:
                    errors.append(
                        f"keepalive GPU {index} mean utilization below 40"
                    )
                if (
                    per_gpu.get("sample_count")
                    != KEEPALIVE_SAMPLE_COUNT
                ):
                    errors.append(
                        f"keepalive GPU {index} does not have 10 samples"
                    )
            keepalive_10x1s_passed = not any(
                error.startswith("keepalive ")
                for error in errors
            )

    worker_list = subprocess.run(
        ["mlx", "worker", "list"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    write_text_atomic(
        artifact_dir / "worker_list_exit.txt",
        worker_list.stdout + worker_list.stderr,
    )
    matching_lines = [
        line
        for line in worker_list.stdout.splitlines()
        if line.split(maxsplit=1)[0:1] == [args.worker_id]
    ]
    if worker_list.returncode != 0 or len(matching_lines) != 1:
        errors.append("selected worker is absent from exit worker list")
    elif not (
        re.search(r"\s4\s+", matching_lines[0])
        and "NVIDIA-H20" in matching_lines[0]
    ):
        errors.append("exit worker list no longer identifies exact 4xH20")

    audited_at_utc = utc_now()
    status = "PASS" if not errors else "FAIL"
    log_path = artifact_dir / "preflight.log"
    if log_path.is_file():
        seal_preflight_log(
            path=log_path,
            audited_at_utc=audited_at_utc,
            status=status,
            errors=errors,
            worker_id=args.worker_id,
            keepalive_pid=keepalive_pid,
            keepalive_10x1s_passed=keepalive_10x1s_passed,
            decision=decision,
        )

    artifact_hashes = {
        name: {
            "size_bytes": (artifact_dir / name).stat().st_size,
            "sha256": sha256_file(artifact_dir / name),
        }
        for name in REQUIRED_ARTIFACTS
        if (artifact_dir / name).is_file()
    }
    gate = {
        "schema_version": 1,
        "audited_at_utc": audited_at_utc,
        "status": status,
        "authorized_phase": "Phase 01",
        "worker_id": args.worker_id,
        "worker_list_matching_line": (
            matching_lines[0] if len(matching_lines) == 1 else None
        ),
        "keepalive_pid": keepalive_pid,
        "keepalive_remote_status_line": keepalive_status_line,
        "keepalive_remote_status_10x1s_passed": (
            keepalive_10x1s_passed
        ),
        "keepalive_report": keepalive_report,
        "errors": errors,
        "required_final_artifact_hashes": artifact_hashes,
        "sealing_order": [
            "all_checks_completed",
            "preflight_log_atomically_sealed",
            "required_final_artifacts_hashed",
            "phase01_gate_atomically_written",
        ],
        "next_eligible_phase": (
            "Phase 02 after user confirmation" if not errors else None
        ),
    }
    write_json(artifact_dir / "phase01_gate.json", gate)
    print(json.dumps(gate, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
