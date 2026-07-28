#!/usr/bin/env python3
"""Assemble Phase 01 environment, storage, and acquisition artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import urllib.request
from typing import Any, Sequence


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: Sequence[str], timeout: float = 60.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "argv": list(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(command),
            "returncode": None,
            "stdout": getattr(error, "stdout", "") or "",
            "stderr": getattr(error, "stderr", "") or str(error),
            "exception": type(error).__name__,
        }


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def statvfs(path: pathlib.Path) -> dict[str, Any]:
    stats = os.statvfs(path)
    return {
        "path": str(path),
        "block_size": stats.f_frsize,
        "total_bytes": stats.f_blocks * stats.f_frsize,
        "free_bytes": stats.f_bfree * stats.f_frsize,
        "available_bytes": stats.f_bavail * stats.f_frsize,
    }


def os_release() -> dict[str, str]:
    path = pathlib.Path("/etc/os-release")
    result: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                result[key] = value.strip().strip('"')
    return result


def tool(name: str, arguments: Sequence[str]) -> dict[str, Any]:
    resolved = shutil.which(name)
    return {
        "name": name,
        "path": resolved,
        "available": resolved is not None,
        "probe": run([resolved, *arguments]) if resolved else None,
    }


def connectivity(url: str) -> dict[str, Any]:
    started = utc_now()
    try:
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "DeepSpec-Phase01-Preflight/1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return {
                "url": url,
                "started_at_utc": started,
                "finished_at_utc": utc_now(),
                "reachable": True,
                "status": response.status,
                "final_url": response.url,
            }
    except Exception as error:
        return {
            "url": url,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "reachable": False,
            "error_type": type(error).__name__,
            "error": str(error),
        }


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--hdfs-root", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--hf-reference-revision", required=True)
    parser.add_argument("--sglang-commit", required=True)
    args = parser.parse_args()

    artifact_dir = pathlib.Path(args.artifact_dir)
    repo_root = pathlib.Path(args.repo_root)
    hdfs_root = pathlib.Path(args.hdfs_root)
    source = pathlib.Path(args.source)
    worker = json.loads(
        (artifact_dir / "worker_inventory.json").read_text(encoding="utf-8")
    )
    worker_storage = json.loads(
        (artifact_dir / "storage_report_worker.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint = json.loads(
        (artifact_dir / "source_checkpoint_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    gpu_probe = json.loads(
        (artifact_dir / "gpu_probe.json").read_text(encoding="utf-8")
    )
    worker_connectivity = json.loads(
        (artifact_dir / "worker_connectivity.json").read_text(
            encoding="utf-8"
        )
    )
    process_inventory = json.loads(
        (artifact_dir / "process_inventory_after_incident.json").read_text(
            encoding="utf-8"
        )
    )
    cuda_toolchain = json.loads(
        (artifact_dir / "cuda_toolchain_discovery.json").read_text(
            encoding="utf-8"
        )
    )

    git_status = run(["git", "-C", str(repo_root), "status", "--porcelain=v2"])
    environment = {
        "schema_version": 1,
        "authorized_phase": "Phase 01",
        "attempt_id": args.attempt_id,
        "observed_at_utc": utc_now(),
        "fixed_inputs": {
            "model_repository": (
                "deepseek-ai/DeepSeek-V4-Flash-DSpark"
            ),
            "checkpoint_provider": "modelscope",
            "modelscope_provider_reference": "master",
            "modelscope_snapshot_id": checkpoint["provider_identity"][
                "immutable_local_payload_snapshot_id"
            ],
            "hf_cross_provider_reference_revision": (
                args.hf_reference_revision
            ),
            "sglang_source_commit": args.sglang_commit,
        },
        "git": {
            "branch": run(
                ["git", "-C", str(repo_root), "branch", "--show-current"]
            ),
            "head": run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"]
            ),
            "status_porcelain_v2": git_status,
        },
        "devbox": {
            "hostname": platform.node(),
            "os_release": os_release(),
            "uname": platform.uname()._asdict(),
            "python": {
                "executable": sys.executable,
                "version": sys.version,
            },
            "tools": [
                tool("uv", ["--version"]),
                tool("python3", ["--version"]),
                tool("git", ["--version"]),
                tool("gcc", ["--version"]),
                tool("g++", ["--version"]),
                tool("cmake", ["--version"]),
                tool("ninja", ["--version"]),
                tool("rustc", ["--version"]),
                tool("cargo", ["--version"]),
            ],
            "connectivity": {
                "github": connectivity("https://github.com"),
                "huggingface": connectivity("https://huggingface.co"),
                "modelscope": connectivity(
                    "https://www.modelscope.cn"
                ),
            },
        },
        "worker_summary": {
            "worker_id": args.worker_id,
            "hostname": worker["hostname"],
            "gpu_count": worker["gpu_count"],
            "gpu_inventory_matches_exact_4xh20": worker[
                "gpu_inventory_matches_exact_4xh20"
            ],
            "gpus": worker["gpus"],
            "os": worker["os"],
            "tools": worker["tools"],
            "nccl_ldconfig_entries": worker["nccl_ldconfig_entries"],
            "gpu_probe_status": gpu_probe["status"],
            "nccl_all_reduce_passed": gpu_probe[
                "nccl_all_reduce_passed"
            ],
            "full_peer_access_passed": gpu_probe[
                "full_peer_access_passed"
            ],
            "nccl_version": gpu_probe["ranks"][0]["nccl_version"],
            "probe_torch_version": gpu_probe["ranks"][0][
                "torch_version"
            ],
            "probe_torch_cuda_version": gpu_probe["ranks"][0][
                "torch_cuda_version"
            ],
            "topology": worker["topology"],
            "nvidia_smi_p2p_read_capability": worker[
                "p2p_read_capability"
            ],
            "nvidia_smi_p2p_write_capability": worker[
                "p2p_write_capability"
            ],
            "connectivity": worker_connectivity,
            "cuda_toolchain_discovery": cuda_toolchain,
        },
        "gpu_probe_incident": {
            "classification": (
                "client_observation_and_concurrent_recovery_defect"
            ),
            "nccl_or_p2p_failure": False,
            "facts": [
                (
                    "mlx worker login returned before the original remote "
                    "wrapper completed"
                ),
                (
                    "manual keepalive resume occurred after client return "
                    "and before the original wrapper's residual-context "
                    "observation"
                ),
                (
                    "all four rank records show successful NCCL all-reduce "
                    "and rank 0 records a full true peer-access matrix"
                ),
                (
                    "post-incident process inventory found no active "
                    "Phase 01 probe process"
                ),
            ],
            "active_probe_process_count_after_incident": (
                process_inventory["active_probe_process_count"]
            ),
            "wrapper_repairs_written_but_not_gpu_retested": [
                "bounded registered PID/PGID/SID",
                "periodic client-visible heartbeat",
                "ERR/HUP/INT/TERM/EXIT recovery traps",
                "targeted process-group cleanup",
                "pre-pause torchrun import/help identity check",
            ],
            "second_gpu_probe_executed": False,
            "reason_second_probe_not_executed": (
                "Existing rank evidence was complete; main Agent cancelled "
                "a redundant second GPU lifecycle to avoid additional risk."
            ),
        },
        "scope_confirmation": {
            "checkpoint_copied": False,
            "formal_uv_environment_created": False,
            "formal_uv_environment_path": (
                "/home/tiger/venvs/deepspec-dspark"
            ),
            "formal_uv_environment_path_exists": pathlib.Path(
                "/home/tiger/venvs/deepspec-dspark"
            ).exists(),
            "sglang_installed": False,
            "model_started": False,
        },
    }
    write_json(artifact_dir / "environment.json", environment)

    devbox_root = statvfs(pathlib.Path("/"))
    hdfs = statvfs(hdfs_root)
    source_size = checkpoint["bytes"]["local_all_regular_files_total_bytes"]
    required_free = source_size + 50 * 1024**3
    storage_report = {
        "schema_version": 1,
        "observed_at_utc": utc_now(),
        "devbox_shared_root": devbox_root,
        "hdfs_root": hdfs,
        "source_checkpoint": {
            "path": str(source),
            "size_bytes": source_size,
        },
        "worker_tmp": worker_storage["worker_tmp"],
        "capacity_gate": {
            "required_hdfs_available_bytes": required_free,
            "policy": (
                "one independent checkpoint-sized destination plus "
                "50 GiB run-artifact reserve"
            ),
            "hdfs_available_bytes": hdfs["available_bytes"],
            "passed": hdfs["available_bytes"] >= required_free,
        },
    }
    write_json(artifact_dir / "storage_report.json", storage_report)

    verification = checkpoint["modelscope_verification"]
    structure = checkpoint["checkpoint_structure"]
    checkpoint_config = checkpoint["checkpoint_config"]
    validation = checkpoint.get("artifact_validation", {})
    identity_complete = bool(
        checkpoint["provider_identity"]["provider"] == "modelscope"
        and checkpoint["provider_identity"]["repository"]
        == "deepseek-ai/DeepSeek-V4-Flash-DSpark"
        and verification["all_provider_files_match"]
        and verification["source_snapshot_unchanged"]
        and validation.get("status") == "pass"
        and structure["actual_shards_exact"]
        and structure["index_shards_exact"]
        and structure["required_tokenizer_files_present"]
        and structure["config_present"]
        and structure["weight_index_present"]
        and structure["complete_marker_present"]
        and checkpoint_config["dspark_block_size"] == 5
        and checkpoint_config["expert_dtype"] == "fp4"
        and checkpoint_config["dspark_target_layer_ids"] == [40, 41, 42]
        and checkpoint_config["num_nextn_predict_layers"] == 1
    )
    gaps: list[str] = []
    if verification["missing"]:
        gaps.append(f"missing provider files: {verification['missing']}")
    if verification["content_or_size_mismatches"]:
        gaps.append(
            "content/size mismatches against ModelScope provider metadata: "
            f"{verification['content_or_size_mismatches']}"
        )
    if verification["symlinks"]:
        gaps.append(f"source symlinks: {verification['symlinks']}")
    if not verification["source_snapshot_unchanged"]:
        gaps.append("source changed during read-only verification")
    if not structure["actual_shards_exact"]:
        gaps.append("weight shard names/count are not exact")
    if not structure["index_shards_exact"]:
        gaps.append("weight index does not reference exact 48 shards")
    if not structure["complete_marker_present"]:
        gaps.append("local acquisition .complete marker is missing")
    if checkpoint_config["dspark_block_size"] != 5:
        gaps.append("dspark_block_size is not 5")
    if checkpoint_config["expert_dtype"] != "fp4":
        gaps.append("expert_dtype is not packed fp4")
    if checkpoint_config["dspark_target_layer_ids"] != [40, 41, 42]:
        gaps.append("DSpark target layer configuration is unexpected")
    if checkpoint_config["num_nextn_predict_layers"] != 1:
        gaps.append("DSpark draft architecture layer count is unexpected")
    if validation.get("status") != "pass":
        gaps.append(
            f"independent manifest validation failed: "
            f"{validation.get('errors')}"
        )
    snapshot_id = checkpoint["provider_identity"][
        "immutable_local_payload_snapshot_id"
    ]["value"]
    snapshot_path = (
        "/mnt/hdfs/pengzegang/DeepSpec/models/"
        "deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/"
        f"modelscope-{snapshot_id}"
    )
    hf_reference = checkpoint["hf_fixed_revision_reference"]
    decision = {
        "schema_version": 2,
        "attempt_id": args.attempt_id,
        "decided_at_utc": utc_now(),
        "provider": "modelscope",
        "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
        "provider_reference": "master",
        "resolved_immutable_provider_commit": None,
        "snapshot_identity": checkpoint["provider_identity"][
            "immutable_local_payload_snapshot_id"
        ],
        "local_tree_snapshot_identity": checkpoint["provider_identity"][
            "immutable_local_tree_snapshot_id"
        ],
        "provider_file_revisions": checkpoint["provider_identity"][
            "provider_file_revisions"
        ],
        "hf_cross_provider_reference": {
            "revision": args.hf_reference_revision,
            "weight_shard_matches": hf_reference[
                "matches_by_category"
            ]["weight_shard"],
            "model_config_tokenizer_index_matches": hf_reference[
                "matches_by_category"
            ]["model_config_tokenizer_index"],
            "weight_shard_mismatches": [
                entry["path"]
                for entry in hf_reference["mismatches_by_category"][
                    "weight_shard"
                ]
            ],
            "model_config_tokenizer_index_mismatches": [
                entry["path"]
                for entry in hf_reference["mismatches_by_category"][
                    "model_config_tokenizer_index"
                ]
            ],
            "ancillary_mismatches": [
                entry["path"]
                for entry in hf_reference["mismatches_by_category"][
                    "ancillary"
                ]
            ],
        },
        "source_path": str(source),
        "decision": (
            "copy_verified_source"
            if identity_complete
            else "download_pinned_snapshot"
        ),
        "source_identity_complete": identity_complete,
        "gaps": gaps,
        "non_blocking_limitations": [
            (
                "ModelScope API exposes the symbolic master reference and "
                "per-file revisions but no single immutable resolved "
                "snapshot commit; the complete provider payload manifest "
                "SHA-256 is therefore the canonical snapshot ID."
            )
        ],
        "reason": (
            "All 75 ModelScope provider files match official size and "
            "SHA-256 metadata; the complete local payload manifest fixes "
            "an immutable snapshot identity."
            if identity_complete
            else "The existing source lacks complete official-provider "
            "identity or content evidence; Phase 02 must download a pinned "
            "snapshot rather than infer identity from the directory name."
        ),
        "phase02_recommendation": {
            "action": (
                "physically_copy_verified_modelscope_source"
                if identity_complete
                else "download_pinned_snapshot"
            ),
            "recommended_snapshot_path": snapshot_path,
            "publication_authorized": False,
            "copy_started": False,
            "requirements": [
                "copy into a unique staging directory on the same HDFS",
                "preserve the source unchanged",
                "reject symlinks, hardlinks, reflinks, and cache references",
                "recompute and match the Phase 01 complete manifest",
                "publish only after Phase 02 user confirmation and gate",
            ],
        },
        "evidence": {
            "source_checkpoint_manifest": str(
                artifact_dir / "source_checkpoint_manifest.json"
            ),
            "modelscope_repository_metadata": str(
                artifact_dir / "modelscope_repository_metadata.json"
            ),
            "modelscope_file_metadata": str(
                artifact_dir / "modelscope_file_metadata.json"
            ),
            "hf_revision_metadata": str(
                artifact_dir / "hf_revision_metadata.json"
            ),
            "checkpoint_manifest_validation": str(
                artifact_dir / "checkpoint_manifest_validation.json"
            ),
            "manifest_sha256": file_sha256(
                artifact_dir / "source_checkpoint_manifest.json"
            ),
        },
    }
    write_json(artifact_dir / "acquisition_decision.json", decision)
    print(
        json.dumps(
            {
                "environment": str(artifact_dir / "environment.json"),
                "storage": str(artifact_dir / "storage_report.json"),
                "acquisition_decision": decision["decision"],
                "gaps": gaps,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
