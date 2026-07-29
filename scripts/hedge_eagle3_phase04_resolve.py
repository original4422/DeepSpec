#!/usr/bin/env python3
"""Resolve one frozen-source Phase 04 Eagle3 calibration arm."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_eagle3_phase01b.tools import build_resolved_config


WORKER_ID = "4099544"
EXPECTED_HOSTNAME = "g340-cd51-4b00-adb3-18a1-dd47-fb"
SOURCE = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
BASE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
FINAL_SHA = "2600c7b16c648d281be060b33ffadc7ae320f7e3"
PATCH = REPO_ROOT / "patches/hedge_eagle3_phase04/sglang-final-candidate.patch"
PATCH_SHA256 = "73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf"
VENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
PYTHON = VENV / "bin/python"
CUDA_ROOT = VENV / "lib/python3.11/site-packages/nvidia/cu13"
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
    "usr/local/cuda-13.0/compat"
)
PORT = 31001
CHANGED_FILES = (
    "python/sglang/srt/arg_groups/deepseek_v4_hook.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/models/deepseek_v4.py",
    "python/sglang/srt/speculative/eagle3_hedge.py",
    "python/sglang/srt/speculative/eagle_utils.py",
    "python/sglang/srt/speculative/eagle_worker_common.py",
    "python/sglang/srt/speculative/eagle_worker_v2.py",
    "python/sglang/srt/speculative/hedge_spec/__init__.py",
    "python/sglang/srt/speculative/hedge_spec/budget.py",
    "python/sglang/srt/speculative/hedge_spec/config.py",
    "python/sglang/srt/speculative/hedge_spec/torch_rule.py",
    "python/sglang/srt/speculative/multi_layer_eagle_worker_v2.py",
    "test/registered/unit/models/test_deepseek_v4_eagle3_aux.py",
    "test/registered/unit/speculative/test_eagle3_hedge.py",
)


def run(*command: str) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity() -> dict[str, object]:
    head = run("git", "-C", str(SOURCE), "rev-parse", "HEAD")
    status = run("git", "-C", str(SOURCE), "status", "--short")
    changed = run(
        "git", "-C", str(SOURCE), "diff", "--name-only", BASE_SHA, "HEAD", "--"
    ).splitlines()
    if head != FINAL_SHA:
        raise RuntimeError(f"SGLang final SHA differs: {head}")
    if status:
        raise RuntimeError("SGLang final source is not clean")
    subprocess.run(
        ("git", "-C", str(SOURCE), "merge-base", "--is-ancestor", BASE_SHA, head),
        check=True,
        timeout=60,
    )
    if changed != list(CHANGED_FILES):
        raise RuntimeError("SGLang base-to-final file set differs")
    if sha256(PATCH) != PATCH_SHA256:
        raise RuntimeError("reviewed SGLang patch hash differs")
    subprocess.run(
        ("git", "-C", str(SOURCE), "apply", "--check", "--reverse", str(PATCH)),
        check=True,
        timeout=60,
    )
    return {
        "source_root": str(SOURCE),
        "base_sha": BASE_SHA,
        "final_sha": head,
        "worktree_clean": True,
        "changed_files": changed,
        "reviewed_patch": str(PATCH),
        "reviewed_patch_sha256": PATCH_SHA256,
        "reviewed_patch_reverse_check": "PASS",
        "uv_lock_sha256": sha256(REPO_ROOT / "uv.lock"),
        "import_path": str(SOURCE / "python/sglang/__init__.py"),
    }


def environment(config: dict[str, object]) -> dict[str, str]:
    nvidia_libs = sorted(
        path
        for path in (VENV / "lib/python3.11/site-packages/nvidia").glob("*/lib")
        if path.is_dir()
    )
    if not nvidia_libs:
        raise RuntimeError("lane-local NVIDIA library closure is absent")
    if not (COMPAT_ROOT / "libcuda.so.1").is_file():
        raise RuntimeError("fixed CUDA 13 forward-compat libcuda is absent")
    if not PYTHON.is_file():
        raise RuntimeError("lane Python is absent")
    resolved_env = config["environment"]
    assert isinstance(resolved_env, dict)
    result = {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "CUDA_HOME": str(CUDA_ROOT),
        "PATH": ":".join(
            [
                str(CUDA_ROOT / "bin"),
                str(VENV / "bin"),
                "/home/tiger/.cargo/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
            ]
        ),
        "LD_LIBRARY_PATH": ":".join(
            [
                str(COMPAT_ROOT),
                *(str(path) for path in nvidia_libs),
                str(CUDA_ROOT / "lib64"),
                "/usr/local/cuda/lib64",
            ]
        ),
        "LIBRARY_PATH": str(CUDA_ROOT / "lib64"),
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "SGLANG_EAGLE3_V4_AUX_TRACE": "1",
        "SGLANG_EAGLE3_HEDGE_MODE": str(
            resolved_env["SGLANG_EAGLE3_HEDGE_MODE"]
        ),
        "SGLANG_EAGLE3_HEDGE_TRACE_CAPACITY": "1024",
        "PYTHONUNBUFFERED": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }
    hedge_json = resolved_env["SGLANG_EAGLE3_HEDGE_CONFIG_JSON"]
    if hedge_json is not None:
        result["SGLANG_EAGLE3_HEDGE_CONFIG_JSON"] = str(hedge_json)
    return result


def command(config: dict[str, object]) -> list[str]:
    models = config["models"]
    assert isinstance(models, dict)
    target = models["target"]
    draft = models["draft"]
    assert isinstance(target, dict) and isinstance(draft, dict)
    target_path = Path(str(target["path"]))
    draft_path = Path(str(draft["path"]))
    if not (target_path / "config.json").is_file():
        raise RuntimeError("fixed target snapshot is absent")
    if not (draft_path / "pytorch_model.bin").is_file():
        raise RuntimeError("fixed draft snapshot is absent")
    return [
        str(PYTHON),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(target_path),
        "--served-model-name",
        "deepseek-v4-flash-eagle3",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--tp-size",
        "8",
        "--moe-runner-backend",
        "flashinfer_mxfp4",
        "--context-length",
        "4096",
        "--max-running-requests",
        "1",
        "--mem-fraction-static",
        "0.60",
        "--disable-cuda-graph",
        "--disable-overlap-schedule",
        "--disable-radix-cache",
        "--speculative-algorithm",
        "EAGLE3",
        "--speculative-draft-model-path",
        str(draft_path),
        "--speculative-draft-attention-backend",
        "flashinfer",
        "--speculative-num-steps",
        "3",
        "--speculative-eagle-topk",
        "1",
        "--speculative-num-draft-tokens",
        "4",
    ]


def resolve(
    mode: str,
    attempt_id: str,
    *,
    gate: float | None,
    require_worker_hostname: bool,
) -> dict[str, object]:
    config = build_resolved_config(mode, gate=gate)
    observed = socket.gethostname()
    if require_worker_hostname and observed != EXPECTED_HOSTNAME:
        raise RuntimeError(
            f"worker hostname differs: expected={EXPECTED_HOSTNAME} observed={observed}"
        )
    return {
        "schema_version": 1,
        "phase": "04",
        "mode": mode,
        "attempt_id": attempt_id,
        "worker_id": WORKER_ID,
        "hostname_expected": EXPECTED_HOSTNAME,
        "hostname_observed": observed,
        "hostname_asserted": require_worker_hostname,
        "gpu_count": 8,
        "tp_size": 8,
        "port": PORT,
        "proposal_tokens": 3,
        "internal_verify_width": 4,
        "source": source_identity(),
        "experiment_config": config,
        "environment": environment(config),
        "command": command(config),
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_evidence(directory: Path, value: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    config = value["experiment_config"]
    assert isinstance(config, dict)
    models = config["models"]
    assert isinstance(models, dict)
    write_json(
        directory / "checkpoint_identity.json",
        {
            "schema_version": 1,
            "target": models["target"],
            "draft": models["draft"],
        },
    )
    write_json(
        directory / "environment.json",
        {
            "schema_version": 1,
            "worker_id": value["worker_id"],
            "hostname": value["hostname_observed"],
            "gpu_count": value["gpu_count"],
            "tp_size": value["tp_size"],
            "source": value["source"],
            "environment": value["environment"],
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("native", "B0", "B+"), required=True)
    parser.add_argument("--gate", type=float)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--print-command-null", action="store_true")
    parser.add_argument("--print-environment-null", action="store_true")
    parser.add_argument("--assert-worker-hostname", action="store_true")
    args = parser.parse_args(argv)
    value = resolve(
        args.mode,
        args.attempt_id,
        gate=args.gate,
        require_worker_hostname=args.assert_worker_hostname,
    )
    if args.output is not None:
        write_json(args.output, value)
    if args.evidence_dir is not None:
        write_evidence(args.evidence_dir, value)
    if args.print_command_null:
        for item in value["command"]:
            os.write(sys.stdout.fileno(), str(item).encode() + b"\0")
    if args.print_environment_null:
        for name, content in value["environment"].items():
            os.write(
                sys.stdout.fileno(),
                f"{name}={content}".encode() + b"\0",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
