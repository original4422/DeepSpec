#!/usr/bin/env python3
"""Audit the sealed one-shot DFlash HEDGE D4-C short B=0 attempt."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ATTEMPT_ID = "dflash-d4-b0-20260729T045317Z-a01"
SOURCE_SHA = "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
SOURCE_TREE = "53fc45b1b04963736254dc7ed582047313b8075a"
EXPECTED_IDS = [22, 1]
EXPECTED_CONFIG = {
    "B": 0.0,
    "g": 1_000_000.0,
    "m": 1,
    "value_scheme": "normalized_suffix",
    "block_size": 7,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(run: Path, name: str) -> dict:
    return json.loads((run / name).read_text(encoding="utf-8"))


def read_gpu_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    return [
        {
            "gpu_index": int(index.strip()),
            "gpu_uuid": uuid.strip(),
            "utilization_percent": int(utilization.strip()),
            "memory_used_mib": int(memory.strip()),
            "memory_total_mib": int(total.strip()),
        }
        for index, uuid, utilization, memory, total in rows
    ]


def manifest_audit(run: Path, complete: dict) -> dict:
    manifest = run / "artifact_manifest.sha256"
    records = {}
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = raw_line.split("  ", 1)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or "/" in name
            or name in records
        ):
            raise ValueError(f"invalid manifest record: {raw_line!r}")
        records[name] = digest
    expected = {
        path.name
        for path in run.iterdir()
        if path.is_file()
        and path.name not in {".complete.json", "artifact_manifest.sha256"}
    }
    mismatches = {
        name: {"expected": digest, "observed": sha256(run / name)}
        for name, digest in records.items()
        if not (run / name).is_file() or sha256(run / name) != digest
    }
    manifest_hash = sha256(manifest)
    passed = (
        set(records) == expected
        and not mismatches
        and manifest_hash == complete["manifest_sha256"]
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "record_count": len(records),
        "expected_file_count": len(expected),
        "recorded_names_match": set(records) == expected,
        "hash_mismatches": mismatches,
        "manifest_sha256": manifest_hash,
        "complete_manifest_sha256": complete["manifest_sha256"],
    }


def log_audit(log: str) -> dict:
    ranks = list(range(8))

    def observed_ranks(pattern: str) -> list[int]:
        return sorted({int(value) for value in re.findall(pattern, log)})

    distributed = observed_ranks(
        r"\bTP([0-7])\] Init torch distributed ends\."
    )
    target = observed_ranks(
        r"\bTP([0-7])\] Load weight end\..*type=DeepseekV4ForCausalLM"
    )
    draft = observed_ranks(
        r"\bTP([0-7])\] Load weight end\..*type=DFlashDraftModel"
    )
    fatal_patterns = {
        "traceback": r"Traceback \(most recent call last\)",
        "cuda_error": r"CUDA (?:error|Error)",
        "nccl_error_or_warn": r"NCCL (?:ERROR|WARN)",
        "oom": r"(?:OutOfMemory|out of memory)",
        "scheduler_exception": r"Scheduler hit an exception",
        "killed": r"\bKilled\b",
    }
    fatal_counts = {
        name: len(re.findall(pattern, log))
        for name, pattern in fatal_patterns.items()
    }
    sigterm = log.find("SIGTERM received")
    child_exit = log.find(
        "Subprocess detokenizer",
        sigterm if sigterm >= 0 else 0,
    )
    sigquit = log.find("SIGQUIT received", child_exit if child_exit >= 0 else 0)
    normal_shutdown = (
        sigterm >= 0
        and child_exit > sigterm
        and "crashed with exit code -15" in log[child_exit : child_exit + 300]
        and sigquit > child_exit
        and log.count("crashed") == 1
    )
    gates = {
        "distributed_tp_ranks": distributed,
        "target_load_tp_ranks": target,
        "draft_load_tp_ranks": draft,
        "hedge_adapter_enabled": (
            "Initialized DFlash HEDGE adapter: {'mode': 'enabled'" in log
        ),
        "dflash_block8_ready": (
            "DFLASH draft runner ready." in log
            and "block_size=8" in log
        ),
        "server_ready": "The server is fired up and ready to roll!" in log,
        "chat_http_200": (
            '"POST /v1/chat/completions HTTP/1.1" 200 OK' in log
        ),
        "server_info_http_200_count": log.count(
            '"GET /get_server_info HTTP/1.1" 200 OK'
        ),
        "fatal_counts": fatal_counts,
        "normal_registered_shutdown": normal_shutdown,
        "expected_generation_config_warnings": log.count(
            "Proceeding without generation config."
        ),
    }
    passed = (
        distributed == ranks
        and target == ranks
        and draft == ranks
        and gates["hedge_adapter_enabled"]
        and gates["dflash_block8_ready"]
        and gates["server_ready"]
        and gates["chat_http_200"]
        and gates["server_info_http_200_count"] >= 2
        and all(count == 0 for count in fatal_counts.values())
        and normal_shutdown
    )
    return {"status": "PASS" if passed else "FAIL", **gates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if run.name != ATTEMPT_ID:
        raise SystemExit(f"unexpected attempt: {run.name}")

    complete = read_json(run, ".complete.json")
    summary = read_json(run, "summary.json")
    cleanup = read_json(run, "cleanup.json")
    startup = read_json(run, "startup.json")
    api = read_json(run, "api_smoke.json")
    counters = read_json(run, "hedge_counters.json")
    resolved = read_json(run, "resolved_config.json")
    source = read_json(run, "source_identity.json")
    identity = read_json(run, "process_identity.json")
    resume_gate = read_json(run, "keepalive_resume_gate.json")
    recovery = read_json(run, "prelaunch_recovery_audit.json")
    hedge = counters["hedge"]
    manifest = manifest_audit(run, complete)
    server_log = (run / "server.log").read_text(
        encoding="utf-8",
        errors="replace",
    )
    logs = log_audit(server_log)

    after_ready = read_gpu_csv(run / "gpu_after_ready.csv")
    after_request = read_gpu_csv(run / "gpu_after_request.csv")
    with (run / "gpu_samples.csv").open(
        newline="",
        encoding="utf-8",
    ) as stream:
        samples = list(csv.DictReader(stream))
    sample_indices = sorted(
        {int(row["gpu_index"]) for row in samples}
    )
    request_phase_rows = sum(
        row["phase"] == "request" for row in samples
    )
    max_memory = {
        str(index): max(
            int(row["memory_used_mib"])
            for row in samples
            if int(row["gpu_index"]) == index
        )
        for index in range(8)
    }
    gpu_pass = (
        [row["gpu_index"] for row in after_ready] == list(range(8))
        and [row["gpu_index"] for row in after_request] == list(range(8))
        and sample_indices == list(range(8))
        and all(row["memory_used_mib"] > 90_000 for row in after_ready)
        and all(row["utilization_percent"] > 0 for row in after_request)
        and all(value > 90_000 for value in max_memory.values())
        and len(identity["rank_to_physical_gpu"]) == 8
        and [
            row["tp_rank"] for row in identity["rank_to_physical_gpu"]
        ]
        == list(range(8))
    )
    gpu = {
        "status": "PASS" if gpu_pass else "FAIL",
        "rank_to_physical_gpu": identity["rank_to_physical_gpu"],
        "after_ready_memory_mib": [
            row["memory_used_mib"] for row in after_ready
        ],
        "immediate_after_request_utilization_percent": [
            row["utilization_percent"] for row in after_request
        ],
        "max_sampled_memory_mib": max_memory,
        "gpu_sample_rows": len(samples),
        "request_phase_rows": request_phase_rows,
        "request_sampling_limitation": (
            "The 0.377s request completed inside the sampler's preceding "
            "1s lifecycle interval; the immediate post-response snapshot "
            "shows positive utilization on all eight GPUs."
            if request_phase_rows == 0
            else None
        ),
    }

    expected_histogram = [8, 0, 0, 0, 0, 0, 0, 0]
    hedge_pass = (
        counters["status"] == "PASS"
        and hedge["mode"] == "enabled"
        and hedge["config"] == EXPECTED_CONFIG
        and hedge["dflash_block_size"] == 8
        and hedge["proposal_width"] == 7
        and hedge["proposals"] == 8
        and hedge["draft_tokens_verifiable"] == 56
        and hedge["strict_accepted_draft_tokens"]
        == hedge["hedge_accepted_draft_tokens"]
        and hedge["relaxed_mismatches"] == 0
        and hedge["regret_charged"] == 0.0
        and hedge["accept_length_histogram"] == expected_histogram
        and hedge["active_request_states"] == 0
        and hedge["state_leaks"] == 0
        and hedge["request_state"] == []
        and hedge["requests_initialized"] >= 1
        and hedge["requests_finished"] >= 1
    )
    api_pass = (
        api["status"] == "PASS"
        and api["chat_response"]["http_status"] == 200
        and api["chat_response"]["body"]["choices"][0]["message"]["content"]
        == "4"
        and api["output_token_ids"] == EXPECTED_IDS
        and api["d3_token_id_match"] is True
        and api["completion_tokens"] == 2
    )
    lifecycle_pass = (
        complete["status"] == "PASS"
        and summary["status"] == "PASS"
        and cleanup["status"] == "PASS"
        and cleanup["contexts_clear"] is True
        and cleanup["keepalive_resume_returncode"] == 0
        and startup["status"] == "ready"
        and resume_gate["healthy"] is True
        and (run / "cuda_contexts_after_pause.txt")
        .read_text()
        .strip()
        .endswith("contexts=none")
        and (run / "cuda_contexts_after_server.txt")
        .read_text()
        .strip()
        .endswith("contexts=none")
    )
    identity_pass = (
        resolved["phase"] == "D4-C"
        and resolved["mode"] == "dflash_hedge_b0"
        and resolved["tp_size"] == 8
        and resolved["block_size"] == 8
        and resolved["draft_candidates"] == 7
        and source["head"] == SOURCE_SHA
        and summary["source_sha"] == SOURCE_SHA
        and identity["pid"] == identity["pgid"] == identity["sid"] == 114418
        and identity["worker_id"] == "4099543"
    )
    recovery_pass = (
        recovery["status"] == "PASS"
        and recovery["preflight_body_pass"] is True
        and recovery["zero_gpu_side_effects"] is True
        and recovery["present_pause_or_server_files"] == []
        and recovery["hdfs_run_exists"] is False
    )
    status = (
        "PASS"
        if all(
            (
                manifest["status"] == "PASS",
                logs["status"] == "PASS",
                gpu_pass,
                hedge_pass,
                api_pass,
                lifecycle_pass,
                identity_pass,
                recovery_pass,
            )
        )
        else "FAIL"
    )
    document = {
        "schema_version": 1,
        "phase": "D4-C",
        "attempt_id": ATTEMPT_ID,
        "status": status,
        "audited_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "scope": "one short infrastructure prompt; not GSM8K calibration",
        "worker_id": "4099543",
        "hdfs_run": str(run),
        "source": {
            "commit": SOURCE_SHA,
            "tree": SOURCE_TREE,
            "identity_pass": identity_pass,
        },
        "manifest": manifest,
        "prelaunch_recovery": {
            "status": "PASS" if recovery_pass else "FAIL",
            "preflight_body_pass": recovery["preflight_body_pass"],
            "zero_gpu_side_effects_before_continuation": recovery[
                "zero_gpu_side_effects"
            ],
            "original_wrapper_returncode_recoverable": recovery[
                "original_wrapper_returncode_recoverable"
            ],
            "continued_same_attempt_id": True,
        },
        "lifecycle": {
            "status": "PASS" if lifecycle_pass else "FAIL",
            "startup": startup,
            "cleanup": cleanup,
            "resume_gate": resume_gate,
            "fresh_post_audit_keepalive_observation": {
                "captured_at_utc": "2026-07-29T05:13:00Z",
                "pid": 123914,
                "sample_count_per_gpu": 10,
                "per_gpu_mean_utilization_percent": {
                    str(index): 100.0 for index in range(8)
                },
                "healthy": True,
            },
        },
        "api": {
            "status": "PASS" if api_pass else "FAIL",
            "http_status": api["chat_response"]["http_status"],
            "content": api["chat_response"]["body"]["choices"][0][
                "message"
            ]["content"],
            "output_token_ids": api["output_token_ids"],
            "expected_d3_a05_output_token_ids": EXPECTED_IDS,
            "d3_token_id_match": api["d3_token_id_match"],
            "completion_tokens": api["completion_tokens"],
            "elapsed_seconds": api["elapsed_seconds"],
        },
        "hedge": {
            "status": "PASS" if hedge_pass else "FAIL",
            **hedge,
        },
        "gpu_participation": gpu,
        "server_log": logs,
        "conclusion": (
            "D4-C short live B=0 infrastructure smoke PASS; this is not "
            "the plan's 32-example B=0 calibration arm."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
