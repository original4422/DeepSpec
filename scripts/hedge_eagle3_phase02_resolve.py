#!/usr/bin/env python3
"""Resolve the fixed Phase 02 target/native launch without touching CUDA."""

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


WORKER_ID = "4099544"
SOURCE = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
BASE_SHA = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
VENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
PYTHON = VENV / "bin/python"
TARGET = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash/"
    "snapshots/huggingface-60d8d70770c6776ff598c94bb586a859a38244f1"
)
DRAFT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/models/"
    "SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/snapshots/"
    "huggingface-4c68aa4689d59cb1064f20abec7708174ee4613d"
)
TARGET_REVISION = "60d8d70770c6776ff598c94bb586a859a38244f1"
DRAFT_REVISION = "4c68aa4689d59cb1064f20abec7708174ee4613d"
CUDA_ROOT = VENV / "lib/python3.11/site-packages/nvidia/cu13"
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
    "usr/local/cuda-13.0/compat"
)
PORT = 31001
EXPECTED_HOSTNAME = "g340-cd51-4b00-adb3-18a1-dd47-fb"
TARGET_ATTENTION_BACKEND = "dsv4"
NATIVE_DRAFT_ATTENTION_BACKEND = "flashinfer"
NATIVE_RUNTIME_PATCH_SHA256 = (
    "64ce797b2a4ac5f668557fb481f9577c4a72baf601c5350eee03dd4ad7e60fe2"
)
NATIVE_RUNTIME_TRACKED_FILES = (
    "python/sglang/srt/arg_groups/deepseek_v4_hook.py",
    "python/sglang/srt/models/deepseek_v4.py",
)
NATIVE_SOURCE_TEST = (
    "test/registered/unit/models/test_deepseek_v4_eagle3_aux.py"
)
NATIVE_SOURCE_TEST_SHA256 = (
    "2f32eecbe96c104352b9e9793da519abd339408044bc15b9a3c4994f3af5232b"
)


def run(*command: str) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def source_identity() -> dict[str, object]:
    head = run("git", "-C", str(SOURCE), "rev-parse", "HEAD")
    if head != BASE_SHA:
        raise RuntimeError(f"SGLang HEAD differs from fixed base: {head}")
    status = subprocess.run(
        ("git", "-C", str(SOURCE), "status", "--short"),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.rstrip("\n")
    diff = subprocess.run(
        ("git", "-C", str(SOURCE), "diff", "--binary", BASE_SHA, "--"),
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    tracked_diff_files = subprocess.run(
        (
            "git",
            "-C",
            str(SOURCE),
            "diff",
            "--name-only",
            BASE_SHA,
            "--",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.splitlines()
    untracked_files = subprocess.run(
        (
            "git",
            "-C",
            str(SOURCE),
            "ls-files",
            "--others",
            "--exclude-standard",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.splitlines()
    source_test = SOURCE / NATIVE_SOURCE_TEST
    return {
        "source_root": str(SOURCE),
        "base_sha": BASE_SHA,
        "head_sha": head,
        "worktree_status": status.splitlines(),
        "diff_sha256": sha256_bytes(diff),
        "diff_bytes": len(diff),
        "tracked_diff_files": tracked_diff_files,
        "untracked_files": untracked_files,
        "source_test_sha256": (
            sha256_bytes(source_test.read_bytes())
            if source_test.is_file()
            else None
        ),
        "import_path": str(SOURCE / "python/sglang/__init__.py"),
    }


def environment(mode: str) -> dict[str, str]:
    if mode not in {"target", "native"}:
        raise ValueError(f"unknown Phase 02 mode: {mode}")
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
    if not TARGET.is_dir() or not (TARGET / "config.json").is_file():
        raise RuntimeError("fixed target snapshot is absent")
    ld_library_path = ":".join(
        [
            str(COMPAT_ROOT),
            *(str(path) for path in nvidia_libs),
            str(CUDA_ROOT / "lib64"),
            "/usr/local/cuda/lib64",
        ]
    )
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
        "LD_LIBRARY_PATH": ld_library_path,
        "LIBRARY_PATH": str(CUDA_ROOT / "lib64"),
        "SGLANG_DSV4_FP4_EXPERTS": "1",
        "SGLANG_RAGGED_VERIFY_MODE": "static",
        "SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH": "1",
        "PYTHONUNBUFFERED": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }
    if mode == "native":
        result["SGLANG_EAGLE3_V4_AUX_TRACE"] = "1"
    return result


def command(mode: str) -> list[str]:
    served_model = (
        "deepseek-v4-flash-target-diagnostic"
        if mode == "target"
        else "deepseek-v4-flash-eagle3-native"
    )
    result = [
        str(PYTHON),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(TARGET),
        "--served-model-name",
        served_model,
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
    ]
    if mode == "native":
        if not DRAFT.is_dir() or not (DRAFT / "pytorch_model.bin").is_file():
            raise RuntimeError("fixed draft snapshot is absent")
        result.extend(
            [
                "--speculative-algorithm",
                "EAGLE3",
                "--speculative-draft-model-path",
                str(DRAFT),
                "--speculative-draft-attention-backend",
                NATIVE_DRAFT_ATTENTION_BACKEND,
                "--speculative-num-steps",
                "3",
                "--speculative-eagle-topk",
                "1",
                "--speculative-num-draft-tokens",
                "4",
            ]
        )
    return result


def validate_worker_hostname(observed: str) -> str:
    if observed != EXPECTED_HOSTNAME:
        raise RuntimeError(
            f"worker hostname differs: expected={EXPECTED_HOSTNAME} "
            f"observed={observed}"
        )
    return observed


def assert_worker_hostname() -> str:
    return validate_worker_hostname(socket.gethostname())


def assert_source_state(
    mode: str, identity: dict[str, object]
) -> None:
    if mode == "native":
        if identity.get("tracked_diff_files") != list(
            NATIVE_RUNTIME_TRACKED_FILES
        ):
            raise RuntimeError(
                "native SGLang tracked file set differs from the review"
            )
        if identity.get("diff_sha256") != NATIVE_RUNTIME_PATCH_SHA256:
            raise RuntimeError(
                "native SGLang differs from the reviewed runtime patch"
            )
        if identity.get("untracked_files") != [NATIVE_SOURCE_TEST]:
            raise RuntimeError(
                "native SGLang untracked file set differs from the review"
            )
        if identity.get("source_test_sha256") != NATIVE_SOURCE_TEST_SHA256:
            raise RuntimeError(
                "native SGLang source test identity differs from the review"
            )
        return
    if mode != "target":
        raise ValueError(f"unknown Phase 02 mode: {mode}")
    if identity["worktree_status"] or identity["diff_bytes"] != 0:
        raise RuntimeError(
            "target diagnostic requires the clean fixed SGLang base"
        )


def resolve(
    mode: str, attempt_id: str, require_worker_hostname: bool = False
) -> dict[str, object]:
    env = environment(mode)
    launch = command(mode)
    identity = source_identity()
    assert_source_state(mode, identity)
    hostname_observed = (
        assert_worker_hostname()
        if require_worker_hostname
        else socket.gethostname()
    )
    return {
        "schema_version": 1,
        "phase": "02",
        "mode": mode,
        "attempt_id": attempt_id,
        "worker_id": WORKER_ID,
        "hostname_expected": EXPECTED_HOSTNAME,
        "hostname_observed": hostname_observed,
        "hostname_asserted": require_worker_hostname,
        "gpu_count": 8,
        "tp_size": 8,
        "port": PORT,
        "proposal_tokens": None if mode == "target" else 3,
        "internal_verify_width": None if mode == "target" else 4,
        "target": {
            "path": str(TARGET),
            "repo_id": "deepseek-ai/DeepSeek-V4-Flash",
            "revision": TARGET_REVISION,
        },
        "draft": (
            None
            if mode == "target"
            else {
                "path": str(DRAFT),
                "repo_id": "SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1",
                "revision": DRAFT_REVISION,
            }
        ),
        "packed_fp4": {
            "enabled": True,
            "moe_runner_backend": "flashinfer_mxfp4",
            "SGLANG_DSV4_FP4_DEQUANT": "explicitly_unset",
        },
        "attention_backends": {
            "target": TARGET_ATTENTION_BACKEND,
            "draft": (
                None
                if mode == "target"
                else NATIVE_DRAFT_ATTENTION_BACKEND
            ),
            "draft_override_only": mode == "native",
        },
        "graphs": {
            "target_decode": "disabled",
            "target_prefill": "disabled",
            "draft_extend": "disabled_by_env",
        },
        "source": identity,
        "environment": env,
        "command": launch,
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("target", "native"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-command-null", action="store_true")
    parser.add_argument("--print-environment-null", action="store_true")
    parser.add_argument("--assert-worker-hostname", action="store_true")
    args = parser.parse_args(argv)
    value = resolve(
        args.mode,
        args.attempt_id,
        require_worker_hostname=args.assert_worker_hostname,
    )
    if args.output is not None:
        write_json(args.output, value)
    if args.print_command_null:
        for item in value["command"]:
            os.write(sys.stdout.fileno(), item.encode() + b"\0")
    if args.print_environment_null:
        for name, content in value["environment"].items():
            os.write(
                sys.stdout.fileno(),
                f"{name}={content}".encode() + b"\0",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
