#!/usr/bin/env python3
"""Owned TP=8 lifecycle for the DFlash D6 native formal arm."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


WORKER_ID = "4099543"
EXPECTED_HOST = "g340-cd51-4b00-4d69-9088-7ae6-6253"
REPO = Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
SOURCE = Path("/home/tiger/src/deepspec-sglang-hedge-dflash")
SOURCE_SHA = "9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1"
SOURCE_TREE = "53fc45b1b04963736254dc7ed582047313b8075a"
SOURCE_PARENT = "1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5"
SOURCE_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PYTHON = Path("/home/tiger/venvs/deepspec-hedge-dflash/bin/python")
KEEPALIVE = REPO / "scripts/dflash_keepalive.sh"
API = REPO / "scripts/dflash_d6_api.py"
CUDA_VIEW_HELPER = REPO / "scripts/dflash_d3_cuda_view.sh"
CUDA_VIEW = Path("/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0")
CU13_PAYLOAD = Path(
    "/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13"
)
CUDA_COMPAT_DIR = Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/"
    "cuda-13.0/compat"
)
PORT = 31457
MODEL_NAME = "deepseek-v4-flash"
TARGET_REV = "60d8d70770c6776ff598c94bb586a859a38244f1"
DRAFT_REV = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
DATASET_REV = "740312add88f781978c0658806c59bc2815b9866"
DATASET_SEED = 980406
TARGET = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash/"
    f"snapshots/huggingface-{TARGET_REV}"
)
DRAFT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft/"
    f"RedHatAI--DeepSeek-V4-Flash-speculator.dflash/{DRAFT_REV}"
)
TARGET_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    f"target-deepseek-v4-flash-{TARGET_REV}.complete.json"
)
DRAFT_POINTER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft_pointer.json"
)
D1C = (
    REPO
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1c"
)
CALIBRATION = D1C / "dflash_d1c_gsm8k_calibration_32.jsonl"
WARMUP = D1C / "dflash_d1c_gsm8k_warmup_10.jsonl"
FORMAL = D1C / "dflash_d1c_gsm8k_formal_500.jsonl"
DATASET_MANIFEST = D1C / "dflash_d1c_dataset_manifest.json"
DATASET_IDENTITY = D1C / "dflash_d1c_dataset_identity.json"
FORMAL_INDICES = D1C / "dflash_d1c_formal_indices.json"
PROMPT_MANIFEST = D1C / "dflash_d1c_prompt_manifest.json"
KEEPALIVE_STATE = Path("/tmp/deepspec-hedge-dflash/keepalive")
RUN_ROOT = Path("/tmp/deepspec-hedge-dflash/runs")
HDFS_RUN_ROOT = Path("/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs")
BASE_URL = f"http://127.0.0.1:{PORT}"
MINIMUM_LIVE_SECONDS = 12_000
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    command: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env=env,
        timeout=timeout,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def hard_stop(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("hard stop must use exact YYYY-MM-DDTHH:MM:SSZ")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError("hard stop is not canonical UTC")
    return parsed


def paths(attempt_id: str) -> tuple[Path, Path]:
    if not re.fullmatch(
        r"dflash-d6-native-\d{8}T\d{6}Z-a\d{2}", attempt_id
    ):
        raise ValueError("invalid D6 native attempt ID")
    return RUN_ROOT / attempt_id, HDFS_RUN_ROOT / attempt_id


def server_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VIEW": str(CUDA_VIEW),
            "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
            "CUDA_HOME": str(CUDA_VIEW),
            "LD_LIBRARY_PATH": f"{CUDA_COMPAT_DIR}:{CU13_PAYLOAD / 'lib'}",
            "PATH": (
                f"{PYTHON.parent}:{CUDA_VIEW / 'bin'}:/usr/bin:/bin"
            ),
            "FLASHINFER_WORKSPACE_BASE": (
                "/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
            ),
            "FLASHINFER_CUDA_ARCH_LIST": "9.0",
            "PYTHONNOUSERSITE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "SGLANG_RAGGED_VERIFY_MODE": "static",
            "SGLANG_DSV4_FP4_EXPERTS": "1",
            "SGLANG_CACHE_DIR": "/tmp/deepspec-hedge-dflash/cache/sglang",
            "SGLANG_DG_CACHE_DIR": (
                "/tmp/deepspec-hedge-dflash/cache/deep_gemm"
            ),
            "TRITON_CACHE_DIR": "/tmp/deepspec-hedge-dflash/cache/triton",
            "TORCH_EXTENSIONS_DIR": (
                "/tmp/deepspec-hedge-dflash/cache/torch_extensions"
            ),
            "HEDGE_ENABLED": "0",
            "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE": "0",
        }
    )
    for name in (
        "SGLANG_DSV4_FP4_DEQUANT",
        "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
        "SGLANG_DFLASH_HEDGE_CONFIG_JSON",
    ):
        environment.pop(name, None)
    return environment


def server_command() -> list[str]:
    return [
        str(PYTHON),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(TARGET),
        "--served-model-name",
        MODEL_NAME,
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--tp-size",
        "8",
        "--speculative-algorithm",
        "DFLASH",
        "--speculative-draft-model-path",
        str(DRAFT),
        "--speculative-dflash-block-size",
        "8",
        "--speculative-num-steps",
        "1",
        "--speculative-eagle-topk",
        "1",
        "--moe-runner-backend",
        "flashinfer_mxfp4",
        "--context-length",
        "4096",
        "--max-running-requests",
        "1",
        "--mem-fraction-static",
        "0.80",
        "--disable-cuda-graph",
        "--disable-overlap-schedule",
        "--disable-radix-cache",
    ]


def contract(hard_stop_utc: str) -> dict[str, Any]:
    hard_stop(hard_stop_utc)
    environment = server_environment()
    return {
        "schema_version": 1,
        "phase": "D6",
        "arm": "native",
        "source_sha": SOURCE_SHA,
        "source_tree": SOURCE_TREE,
        "source_base": SOURCE_BASE,
        "worker_id": WORKER_ID,
        "port": PORT,
        "tp_size": 8,
        "dflash_block_size": 8,
        "proposal_width": 7,
        "target_revision": TARGET_REV,
        "draft_revision": DRAFT_REV,
        "dataset_revision": DATASET_REV,
        "dataset_seed": DATASET_SEED,
        "warmup_count": 10,
        "warmup_source": "exact first 10 calibration rows",
        "formal_count": 500,
        "formal_source": "fixed non-overlapping shuffled rows 32:532",
        "timing_boundary": (
            "first formal request dispatch through 500th formal terminal state; "
            "includes HTTP, generation, queueing, retries, and retry backoff; "
            "excludes startup and warmup"
        ),
        "hedge_enabled": False,
        "calibration_trace": False,
        "hedge_config": None,
        "hard_stop_utc": hard_stop_utc,
        "minimum_live_seconds": MINIMUM_LIVE_SECONDS,
        "environment": {
            key: environment[key]
            for key in (
                "CUDA_VISIBLE_DEVICES",
                "CUDA_HOME",
                "LD_LIBRARY_PATH",
                "FLASHINFER_WORKSPACE_BASE",
                "FLASHINFER_CUDA_ARCH_LIST",
                "SGLANG_RAGGED_VERIFY_MODE",
                "SGLANG_DSV4_FP4_EXPERTS",
                "HEDGE_ENABLED",
                "SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE",
            )
        },
        "unset_environment": [
            "SGLANG_DSV4_FP4_DEQUANT",
            "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
            "SGLANG_DFLASH_HEDGE_CONFIG_JSON",
        ],
        "command": server_command(),
        "gpu_action": False,
    }


def gpu_rows(query: str) -> list[list[str]]:
    output = run(
        [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ]
    ).stdout
    return [
        [item.strip() for item in row]
        for row in csv.reader(io.StringIO(output))
    ]


def compute_rows() -> list[list[str]]:
    completed = run(
        [
            "nvidia-smi",
            (
                "--query-compute-apps="
                "gpu_uuid,pid,process_name,used_gpu_memory"
            ),
            "--format=csv,noheader,nounits",
        ]
    )
    return [
        [item.strip() for item in row]
        for row in csv.reader(io.StringIO(completed.stdout))
        if row
    ]


def require_worker() -> list[dict[str, Any]]:
    if socket.gethostname() != EXPECTED_HOST:
        raise RuntimeError("assigned worker hostname changed")
    rows = gpu_rows("index,uuid,name,memory.total,memory.used,utilization.gpu")
    if len(rows) != 8:
        raise RuntimeError("assigned worker does not expose exactly eight GPUs")
    gpus = []
    for expected, row in enumerate(rows):
        index, uuid, name, total, used, utilization = row
        if int(index) != expected or name != "NVIDIA H20":
            raise RuntimeError("assigned GPU identity changed")
        gpus.append(
            {
                "index": expected,
                "tp_rank": expected,
                "uuid": uuid,
                "name": name,
                "memory_total_mib": int(total),
                "memory_used_mib": int(used),
                "utilization_percent": int(utilization),
            }
        )
    return gpus


def proc_start_ticks(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat").read_text()
    return int(stat[stat.rfind(")") + 2 :].split()[19])


def proc_argv(pid: int) -> list[str]:
    return [
        item.decode(errors="replace")
        for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if item
    ]


def validate_keepalive(*, collect_gate: bool) -> dict[str, Any]:
    if collect_gate:
        completed = run(
            ["bash", str(KEEPALIVE), "status", WORKER_ID],
            timeout=30,
        )
        status_output = completed.stdout
    else:
        status_output = ""
    identity = json.loads(
        (KEEPALIVE_STATE / "process_identity.json").read_text()
    )
    gate = json.loads((KEEPALIVE_STATE / "keepalive_gate.json").read_text())
    pid = int(identity["pid"])
    if (
        identity["worker_id"] != WORKER_ID
        or identity["hostname"] != EXPECTED_HOST
        or int(identity["pgid"]) != pid
        or int(identity["sid"]) != pid
        or proc_argv(pid) != identity["argv"]
        or os.getpgid(pid) != pid
        or os.getsid(pid) != pid
        or not gate.get("healthy")
    ):
        raise RuntimeError("owned keepalive identity or gate is invalid")
    contexts = compute_rows()
    gpu_uuids = {row["uuid"] for row in identity["physical_gpus"]}
    if (
        len(contexts) != 8
        or {row[0] for row in contexts} != gpu_uuids
        or any(int(row[3]) <= 0 or int(row[3]) >= 4096 for row in contexts)
    ):
        raise RuntimeError("compute context inventory is not keepalive-only")
    return {
        "identity": identity,
        "gate": gate,
        "compute_applications": contexts,
        "status_output": status_output,
    }


def port_free() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", PORT)) != 0


def require_source() -> None:
    if not PYTHON.is_file() or not os.access(PYTHON, os.X_OK):
        raise RuntimeError("pinned uv Python is unavailable")
    for path in (
        API,
        CUDA_VIEW_HELPER,
        CALIBRATION,
        WARMUP,
        FORMAL,
        DATASET_MANIFEST,
        DATASET_IDENTITY,
        FORMAL_INDICES,
        PROMPT_MANIFEST,
    ):
        if not path.is_file():
            raise RuntimeError(f"required file is missing: {path}")
    run(["bash", str(CUDA_VIEW_HELPER), "verify"], timeout=60)
    if run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).stdout.strip() != SOURCE_SHA:
        raise RuntimeError("SGLang HEAD changed")
    if run(["git", "-C", str(SOURCE), "rev-parse", "HEAD^"]).stdout.strip() != SOURCE_PARENT:
        raise RuntimeError("SGLang parent changed")
    if run(["git", "-C", str(SOURCE), "write-tree"]).stdout.strip() != SOURCE_TREE:
        raise RuntimeError("SGLang source tree changed")
    if run(["git", "-C", str(SOURCE), "status", "--porcelain"]).stdout:
        raise RuntimeError("SGLang source is dirty")
    run(
        ["git", "-C", str(SOURCE), "merge-base", "--is-ancestor", SOURCE_BASE, SOURCE_SHA]
    )
    probe = (
        "import pathlib,sglang;"
        f"p=pathlib.Path({str(SOURCE)!r}).resolve();"
        "m=pathlib.Path(sglang.__file__).resolve();"
        "assert m.is_relative_to(p/'python');"
        "assert sglang.__version__=='0.5.16'"
    )
    run([str(PYTHON), "-c", probe], env=server_environment(), timeout=180)


def checkpoint_identity() -> dict[str, Any]:
    marker = json.loads(TARGET_MARKER.read_text())
    pointer = json.loads(DRAFT_POINTER.read_text())
    draft_complete_path = Path(pointer["complete_path"])
    draft_complete = json.loads(draft_complete_path.read_text())
    if (
        marker["status"].lower() != "complete"
        or marker["immutable"] is not True
        or marker["repo_id"] != "deepseek-ai/DeepSeek-V4-Flash"
        or marker["revision"] != TARGET_REV
        or Path(marker["snapshot_path"]) != TARGET
        or marker["weight_shard_count"] != 46
        or marker["file_count"] != 73
        or marker["total_bytes"] != 159630041626
    ):
        raise RuntimeError("target checkpoint marker identity changed")
    manifest_path = Path(marker["manifest_path"])
    if sha256(manifest_path) != marker["manifest_sha256"]:
        raise RuntimeError("target checkpoint manifest hash changed")
    if (
        pointer["status"] != "COMPLETE"
        or pointer["repo_id"]
        != "RedHatAI/DeepSeek-V4-Flash-speculator.dflash"
        or pointer["revision"] != DRAFT_REV
        or Path(pointer["formal_path"]) != DRAFT
        or pointer["file_count"] != 6
        or pointer["total_size_bytes"] != 3607606957
        or draft_complete["status"] != "COMPLETE"
        or draft_complete["revision"] != DRAFT_REV
    ):
        raise RuntimeError("draft checkpoint identity changed")
    config = json.loads((DRAFT / "config.json").read_text())
    if (
        config["speculators_config"]["algorithm"] != "dflash"
        or config["block_size"] != 8
        or config["aux_hidden_state_layer_ids"] != [3, 13, 23, 32, 42]
    ):
        raise RuntimeError("draft config identity changed")
    return {
        "schema_version": 1,
        "phase": "D6",
        "target": {
            "repo_id": marker["repo_id"],
            "revision": TARGET_REV,
            "formal_path": str(TARGET),
            "completion_marker": str(TARGET_MARKER),
            "manifest_path": str(manifest_path),
            "manifest_sha256": marker["manifest_sha256"],
            "file_count": marker["file_count"],
            "total_bytes": marker["total_bytes"],
            "weight_shard_count": marker["weight_shard_count"],
        },
        "draft": {
            "repo_id": pointer["repo_id"],
            "revision": DRAFT_REV,
            "formal_path": str(DRAFT),
            "pointer": str(DRAFT_POINTER),
            "completion_marker": str(draft_complete_path),
            "file_count": pointer["file_count"],
            "total_bytes": pointer["total_size_bytes"],
            "algorithm": "dflash",
            "block_size": 8,
            "proposal_candidates": 7,
            "aux_hidden_state_layer_ids": config["aux_hidden_state_layer_ids"],
        },
        "pass": True,
    }


def validate_dataset() -> dict[str, Any]:
    manifest = json.loads(DATASET_MANIFEST.read_text())
    identity = json.loads(DATASET_IDENTITY.read_text())
    indices = json.loads(FORMAL_INDICES.read_text())
    prompt = json.loads(PROMPT_MANIFEST.read_text())
    selection = manifest["selection"]
    if (
        manifest["source"]["revision"] != DATASET_REV
        or selection["seed"] != DATASET_SEED
        or selection["calibration_count"] != 32
        or selection["warmup_count"] != 10
        or selection["formal_count"] != 500
        or selection["cohorts_disjoint"] is not True
        or indices["dataset_indices"] != selection["formal_indices"]
        or selection["warmup_indices"] != selection["calibration_indices"][:10]
        or identity["dataset"]["datasets_fingerprint"] != "59ec1b7f9357c7a2"
    ):
        raise RuntimeError("pinned dataset protocol identity changed")
    expected_files = {
        CALIBRATION.name: CALIBRATION,
        WARMUP.name: WARMUP,
        FORMAL.name: FORMAL,
    }
    for name, path in expected_files.items():
        entry = manifest["artifacts"][name]
        if sha256(path) != entry["sha256"]:
            raise RuntimeError(f"dataset artifact hash changed: {name}")
    if (
        prompt["generation"]
        != {
            "temperature": 0,
            "top_p": 1,
            "max_tokens": 512,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        or prompt["prompt"]["system_prompt"] is not None
        or prompt["execution"]["max_concurrency"] != 1
    ):
        raise RuntimeError("prompt or generation protocol identity changed")
    return {
        "schema_version": 1,
        "phase": "D6",
        "repo": "openai/gsm8k",
        "config": "main",
        "split": "test",
        "revision": DATASET_REV,
        "seed": DATASET_SEED,
        "fingerprint": identity["dataset"]["datasets_fingerprint"],
        "calibration_count": 32,
        "warmup_count": 10,
        "formal_count": 500,
        "cohorts_disjoint": True,
        "warmup_indices": selection["warmup_indices"],
        "formal_indices_sha256": indices["indices_sha256"],
        "artifact_sha256": {
            name: manifest["artifacts"][name]["sha256"]
            for name in expected_files
        },
        "prompt_manifest_sha256": sha256(PROMPT_MANIFEST),
        "pass": True,
    }


def preflight(attempt_id: str, hard_stop_utc: str) -> dict[str, Any]:
    deadline = hard_stop(hard_stop_utc)
    scratch, hdfs_run = paths(attempt_id)
    if scratch.exists() or hdfs_run.exists():
        raise RuntimeError("attempt scratch or HDFS run already exists")
    scratch.mkdir(parents=True)
    for name in (
        "sglang",
        "deep_gemm",
        "triton",
        "torch_extensions",
        "flashinfer-workspace",
    ):
        Path("/tmp/deepspec-hedge-dflash/cache", name).mkdir(
            parents=True, exist_ok=True
        )
    try:
        ensure = run(["bash", str(CUDA_VIEW_HELPER), "ensure"], timeout=120)
        (scratch / "cuda_view_ensure.json").write_text(ensure.stdout)
        verify = run(["bash", str(CUDA_VIEW_HELPER), "verify"], timeout=60)
        (scratch / "cuda_view_verify.json").write_text(verify.stdout)
        gpus = require_worker()
        require_source()
        checkpoint = checkpoint_identity()
        dataset = validate_dataset()
        if not port_free():
            raise RuntimeError(f"port {PORT} is occupied")
        keepalive = validate_keepalive(collect_gate=True)
        (scratch / "keepalive_before.txt").write_text(keepalive["status_output"])
        write_json(
            scratch / "keepalive_identity_before.json", keepalive["identity"]
        )
        resolved = {
            **contract(hard_stop_utc),
            "attempt_id": attempt_id,
            "hostname": EXPECTED_HOST,
            "preflight_at_utc": utc_now(),
        }
        write_json(scratch / "resolved_config.json", resolved)
        write_json(
            scratch / "environment.json",
            {
                "schema_version": 1,
                "captured_at_utc": utc_now(),
                "worker_id": WORKER_ID,
                "hostname": EXPECTED_HOST,
                "gpus": gpus,
                "keepalive": keepalive,
                "resolved_environment": resolved["environment"],
            },
        )
        write_json(
            scratch / "source_identity.json",
            {
                "schema_version": 1,
                "checkout": str(SOURCE),
                "head": SOURCE_SHA,
                "tree": SOURCE_TREE,
                "parent": SOURCE_PARENT,
                "fixed_base": SOURCE_BASE,
                "fixed_base_is_ancestor": True,
                "status_porcelain": "",
                "hedge_enabled": False,
                "calibration_trace": False,
                "hedge_config": None,
            },
        )
        write_json(scratch / "checkpoint_identity.json", checkpoint)
        write_json(scratch / "dataset_identity.json", dataset)
        shutil.copy2(FORMAL_INDICES, scratch / "formal_indices.json")
        shutil.copy2(PROMPT_MANIFEST, scratch / "prompt_manifest.json")
        (scratch / "command.txt").write_text(
            subprocess.list2cmdline(server_command()) + "\n"
        )
        (scratch / "requests.jsonl").touch()
        write_json(
            scratch / "hedge_counters.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "status": "NOT_RUN",
                "hedge_enabled": False,
                "config": None,
            },
        )
        document = {
            "schema_version": 1,
            "phase": "D6",
            "attempt_id": attempt_id,
            "status": "PASS",
            "captured_at_utc": utc_now(),
            "worker_id": WORKER_ID,
            "hostname": EXPECTED_HOST,
            "gpu_count": 8,
            "port": PORT,
            "port_free": True,
            "keepalive_pid": keepalive["identity"]["pid"],
            "source_sha": SOURCE_SHA,
            "source_tree": SOURCE_TREE,
            "dataset_revision": DATASET_REV,
            "dataset_fingerprint": dataset["fingerprint"],
            "hard_stop_utc": hard_stop_utc,
            "seconds_until_hard_stop": (
                deadline - datetime.now(timezone.utc)
            ).total_seconds(),
            "live_attempt_consumed": False,
        }
        write_json(scratch / "preflight.json", document)
        return document
    except BaseException as error:
        write_json(
            scratch / "preflight.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "attempt_id": attempt_id,
                "status": "FAIL",
                "captured_at_utc": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
                "live_attempt_consumed": False,
            },
        )
        raise


def wait_no_contexts(path: Path, seconds: int = 60) -> bool:
    with path.open("w") as output:
        for attempt in range(1, seconds + 1):
            rows = compute_rows()
            output.write(
                f"{utc_now()} attempt={attempt} contexts="
                f"{canonical(rows) if rows else 'none'}\n"
            )
            output.flush()
            if not rows:
                return True
            if attempt < seconds:
                time.sleep(1)
    return False


def process_matches(pid: int, ticks: int, command: Sequence[str]) -> bool:
    try:
        return (
            proc_start_ticks(pid) == ticks
            and os.getpgid(pid) == pid
            and os.getsid(pid) == pid
            and proc_argv(pid) == list(command)
        )
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def health() -> bool:
    try:
        request = urllib.request.Request(BASE_URL + "/health", method="GET")
        with OPENER.open(request, timeout=5) as response:
            response.read()
        return True
    except (OSError, urllib.error.URLError):
        return False


class GpuSampler(threading.Thread):
    def __init__(
        self,
        scratch: Path,
        server: subprocess.Popen[Any],
        ticks: int,
        command: Sequence[str],
    ) -> None:
        super().__init__(daemon=True)
        self.scratch = scratch
        self.server = server
        self.ticks = ticks
        self.command = list(command)
        self.stop_event = threading.Event()
        self.error: str | None = None

    def phase(self) -> str:
        if (self.scratch / "formal.active").exists():
            return "formal"
        if (self.scratch / "warmup.active").exists():
            return "warmup"
        return "lifecycle"

    def run(self) -> None:
        try:
            path = self.scratch / "gpu_samples.csv"
            with path.open("w", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(
                    [
                        "timestamp_utc",
                        "phase",
                        "gpu_index",
                        "gpu_uuid",
                        "utilization_percent",
                        "memory_used_mib",
                        "memory_total_mib",
                        "server_alive",
                    ]
                )
                while (
                    not self.stop_event.is_set()
                    and self.server.poll() is None
                    and process_matches(
                        self.server.pid, self.ticks, self.command
                    )
                ):
                    phase = self.phase()
                    for row in gpu_rows(
                        "index,uuid,utilization.gpu,memory.used,memory.total"
                    ):
                        writer.writerow([utc_now(), phase, *row, "true"])
                    output.flush()
                    self.stop_event.wait(0.5 if phase in {"warmup", "formal"} else 1)
        except BaseException as error:
            self.error = repr(error)

    def stop(self) -> None:
        self.stop_event.set()
        self.join(timeout=10)


def write_gpu_snapshot(path: Path) -> None:
    rows = gpu_rows("index,uuid,utilization.gpu,memory.used,memory.total")
    with path.open("w", newline="") as output:
        csv.writer(output).writerows(rows)


def gpu_evidence(scratch: Path, server_log: str) -> dict[str, Any]:
    by_gpu: dict[int, list[dict[str, int]]] = {index: [] for index in range(8)}
    with (scratch / "gpu_samples.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["phase"] != "formal":
                continue
            by_gpu[int(row["gpu_index"])].append(
                {
                    "utilization": int(row["utilization_percent"]),
                    "memory": int(row["memory_used_mib"]),
                }
            )
    tp_counts = {str(rank): server_log.count(f"TP{rank}") for rank in range(8)}
    document = {
        "schema_version": 1,
        "tp_rank_log_counts": tp_counts,
        "tp_ranks_initialized": sum(count > 0 for count in tp_counts.values()),
        "formal_samples_per_gpu": {
            str(index): len(values) for index, values in by_gpu.items()
        },
        "formal_peak_utilization_percent": {
            str(index): max((row["utilization"] for row in values), default=0)
            for index, values in by_gpu.items()
        },
        "formal_minimum_memory_used_mib": {
            str(index): min((row["memory"] for row in values), default=0)
            for index, values in by_gpu.items()
        },
    }
    document["pass"] = (
        document["tp_ranks_initialized"] == 8
        and all(by_gpu.values())
        and all(
            value > 80_000
            for value in document["formal_minimum_memory_used_mib"].values()
        )
        and all(
            value > 0
            for value in document["formal_peak_utilization_percent"].values()
        )
    )
    return document


def fatal_scan(server_log: str) -> dict[str, Any]:
    patterns = {
        "python_traceback": r"Traceback \(most recent call last\):",
        "cuda_error": r"(?:CUDA error|CUDA out of memory)",
        "nccl_error": r"(?:NCCL WARN|NCCL ERROR|ncclUnhandledCudaError)",
        "worker_crash": r"(?:Scheduler hit an exception|Worker crashed)",
    }
    counts = {
        name: len(re.findall(pattern, server_log, flags=re.IGNORECASE))
        for name, pattern in patterns.items()
    }
    return {
        "schema_version": 1,
        "scanned_before_owned_shutdown": True,
        "counts": counts,
        "unhandled_fatal": any(counts.values()),
    }


def stop_server(
    server: subprocess.Popen[Any] | None,
    *,
    ticks: int | None,
    command: Sequence[str],
) -> bool:
    if server is None or server.poll() is not None:
        return True
    if ticks is None or not process_matches(server.pid, ticks, command):
        return False
    os.killpg(server.pid, signal.SIGTERM)
    try:
        server.wait(timeout=90)
        return True
    except subprocess.TimeoutExpired:
        if not process_matches(server.pid, ticks, command):
            return False
        os.killpg(server.pid, signal.SIGKILL)
        try:
            server.wait(timeout=30)
            return True
        except subprocess.TimeoutExpired:
            return False


def seal(
    scratch: Path,
    hdfs_run: Path,
    *,
    attempt_id: str,
    hard_stop_utc: str,
    cleanup_status: str,
    contexts_clear: bool,
    resume_rc: int,
    gpu: dict[str, Any] | None,
    fatal: dict[str, Any] | None,
) -> str:
    api = (
        json.loads((scratch / "api_smoke.json").read_text())
        if (scratch / "api_smoke.json").exists()
        else {}
    )
    startup = (
        json.loads((scratch / "startup.json").read_text())
        if (scratch / "startup.json").exists()
        else {}
    )
    counters = (
        json.loads((scratch / "hedge_counters.json").read_text())
        if (scratch / "hedge_counters.json").exists()
        else {}
    )
    write_json(
        scratch / "cleanup.json",
        {
            "schema_version": 1,
            "phase": "D6",
            "attempt_id": attempt_id,
            "status": cleanup_status,
            "contexts_clear": contexts_clear,
            "keepalive_resume_returncode": resume_rc,
            "hard_stop_utc": hard_stop_utc,
            "finished_at_utc": utc_now(),
        },
    )
    status = (
        "PASS"
        if cleanup_status == "PASS"
        and contexts_clear
        and resume_rc == 0
        and startup.get("status") == "ready"
        and api.get("status") == "PASS"
        and api.get("arm_pass") is True
        and counters.get("status") == "PASS"
        and gpu is not None
        and gpu.get("pass") is True
        and fatal is not None
        and fatal.get("unhandled_fatal") is False
        else "FAIL"
    )
    formal = api.get("formal_summary", {})
    acceptance = api.get("acceptance_summary", {})
    summary = {
        "schema_version": 1,
        "phase": "D6",
        "attempt_id": attempt_id,
        "arm": "native",
        "status": status,
        "startup_status": startup.get("status", "NOT_READY"),
        "api_status": api.get("status", "NOT_RUN"),
        "arm_pass": api.get("arm_pass", False),
        "cleanup_status": cleanup_status,
        "hedge_enabled": False,
        "calibration_trace": False,
        "hedge_config": None,
        "source_sha": SOURCE_SHA,
        "source_tree": SOURCE_TREE,
        "hard_stop_utc": hard_stop_utc,
        "benchmark": True,
        "warmup_count": api.get("warmup_count", 0),
        "formal_request_count": formal.get("request_count", 0),
        "formal_all_terminal": formal.get("all_terminal", False),
        "formal_terminal_counts": formal.get("terminal_counts"),
        "formal_retry_count": formal.get("retry_count"),
        "formal_completion_tokens": formal.get("completion_tokens"),
        "formal_wall_time_seconds": formal.get("wall_time_seconds"),
        "formal_e2e_output_tps": formal.get("e2e_output_tps"),
        "mean_accepted_drafts_per_proposal": acceptance.get(
            "mean_accepted_drafts_per_proposal"
        ),
        "mean_accept_length_including_current": acceptance.get(
            "mean_accept_length_including_current"
        ),
        "acceptance_length_histogram_0_to_7": acceptance.get(
            "acceptance_length_histogram_0_to_7"
        ),
        "accepted_draft_tokens_by_position_1_to_7": acceptance.get(
            "accepted_draft_tokens_by_position_1_to_7"
        ),
        "acceptance_rate_by_position_1_to_7": acceptance.get(
            "acceptance_rate_by_position_1_to_7"
        ),
        "gpu_evidence": gpu,
        "fatal_scan_before_cleanup": fatal,
        "finished_at_utc": utc_now(),
    }
    write_json(scratch / "summary.json", summary)
    files = sorted(
        path
        for path in scratch.iterdir()
        if path.is_file() and path.name != "artifact_manifest.sha256"
    )
    manifest = "\n".join(f"{sha256(path)}  {path.name}" for path in files) + "\n"
    (scratch / "artifact_manifest.sha256").write_text(manifest)
    if hdfs_run.exists():
        raise RuntimeError(f"refusing to overwrite HDFS run: {hdfs_run}")
    staging = hdfs_run.with_name(f".{hdfs_run.name}.staging-{os.getpid()}")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for path in sorted(p for p in scratch.iterdir() if p.is_file()):
            shutil.copy2(path, staging / path.name)
        for path in sorted(p for p in scratch.iterdir() if p.is_file()):
            if sha256(path) != sha256(staging / path.name):
                raise RuntimeError(f"HDFS copy hash mismatch: {path.name}")
        write_json(
            staging / ".complete.json",
            {
                "schema_version": 1,
                "attempt_id": attempt_id,
                "status": status,
                "manifest_sha256": sha256(
                    scratch / "artifact_manifest.sha256"
                ),
                "published_at_utc": utc_now(),
            },
        )
        staging.rename(hdfs_run)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return status


def live(attempt_id: str, hard_stop_utc: str) -> int:
    deadline = hard_stop(hard_stop_utc)
    scratch, hdfs_run = paths(attempt_id)
    if hdfs_run.exists():
        raise RuntimeError("HDFS attempt already exists")
    preflight_document = json.loads((scratch / "preflight.json").read_text())
    if preflight_document.get("status") != "PASS":
        raise RuntimeError("preflight is not PASS")
    if (deadline - datetime.now(timezone.utc)).total_seconds() < MINIMUM_LIVE_SECONDS:
        raise RuntimeError("insufficient time remains for a fresh formal live attempt")
    if not port_free():
        raise RuntimeError(f"port {PORT} became occupied")
    require_worker()
    require_source()
    immediate = validate_keepalive(collect_gate=True)
    before = json.loads((scratch / "keepalive_identity_before.json").read_text())
    for key in ("worker_id", "hostname", "pid", "pgid", "sid", "argv", "physical_gpus"):
        if before[key] != immediate["identity"][key]:
            raise RuntimeError(f"keepalive identity changed before pause: {key}")
    write_json(
        scratch / "keepalive_identity_immediate_before_pause.json",
        immediate["identity"],
    )
    (scratch / "keepalive_immediate_before_pause.txt").write_text(
        immediate["status_output"]
    )
    command = server_command()
    environment = server_environment()
    server: subprocess.Popen[Any] | None = None
    server_log_handle: Any = None
    ticks: int | None = None
    sampler: GpuSampler | None = None
    contexts_clear = False
    resume_rc = 1
    cleanup_status = "FAIL"
    gpu: dict[str, Any] | None = None
    fatal: dict[str, Any] | None = None
    live_error: BaseException | None = None
    pause_started = False
    try:
        pause_started = True
        paused = run(["bash", str(KEEPALIVE), "pause", WORKER_ID], timeout=120)
        (scratch / "keepalive_pause.txt").write_text(paused.stdout)
        if not wait_no_contexts(scratch / "cuda_contexts_after_pause.txt"):
            raise RuntimeError("GPU contexts did not clear after keepalive pause")
        server_log_handle = (scratch / "server.log").open("wb")
        server = subprocess.Popen(
            command,
            env=environment,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        (scratch / "server.pid").write_text(f"{server.pid}\n")
        for _ in range(100):
            if Path(f"/proc/{server.pid}/stat").is_file():
                ticks = proc_start_ticks(server.pid)
                break
            time.sleep(0.1)
        if ticks is None or not process_matches(server.pid, ticks, command):
            raise RuntimeError("owned server identity could not be established")
        (scratch / "server.start_ticks").write_text(f"{ticks}\n")
        gpus = require_worker()
        write_json(
            scratch / "process_identity.json",
            {
                "schema_version": 1,
                "phase": "D6",
                "attempt_id": attempt_id,
                "worker_id": WORKER_ID,
                "hostname": EXPECTED_HOST,
                "pid": server.pid,
                "pgid": os.getpgid(server.pid),
                "sid": os.getsid(server.pid),
                "start_ticks": ticks,
                "argv": command,
                "port": PORT,
                "cuda_visible_devices": "0,1,2,3,4,5,6,7",
                "rank_to_physical_gpu": [
                    {
                        "tp_rank": gpu_row["index"],
                        "physical_index": gpu_row["index"],
                        "gpu_uuid": gpu_row["uuid"],
                        "gpu_name": gpu_row["name"],
                    }
                    for gpu_row in gpus
                ],
                "started_at_utc": utc_now(),
            },
        )
        sampler = GpuSampler(scratch, server, ticks, command)
        sampler.start()
        ready_started = utc_now()
        ready = False
        with (scratch / "readiness_checks.log").open("w") as checks:
            for _ in range(720):
                if datetime.now(timezone.utc) >= deadline:
                    raise RuntimeError("hard stop reached while waiting for readiness")
                if server.poll() is not None:
                    raise RuntimeError(
                        f"server exited before readiness: rc={server.returncode}"
                    )
                if not process_matches(server.pid, ticks, command):
                    raise RuntimeError("owned server identity changed")
                if health():
                    ready = True
                    break
                checks.write(f"{utc_now()} not-ready\n")
                checks.flush()
                time.sleep(5)
        write_json(
            scratch / "startup.json",
            {
                "schema_version": 1,
                "status": "ready" if ready else "timeout",
                "started_at_utc": ready_started,
                "finished_at_utc": utc_now(),
                "timeout_seconds": 3600,
                "hard_stop_utc": hard_stop_utc,
            },
        )
        if not ready:
            raise RuntimeError("server readiness timed out")
        write_gpu_snapshot(scratch / "gpu_after_ready.csv")
        api_command = [
            str(PYTHON),
            str(API),
            "run",
            "--base-url",
            BASE_URL,
            "--model",
            MODEL_NAME,
            "--calibration",
            str(CALIBRATION),
            "--warmup",
            str(WARMUP),
            "--formal",
            str(FORMAL),
            "--scratch",
            str(scratch),
            "--hard-stop-utc",
            hard_stop_utc,
            "--timeout",
            "300",
        ]
        api_result = run(
            api_command,
            env=environment,
            timeout=max(
                1,
                (deadline - datetime.now(timezone.utc)).total_seconds() + 30,
            ),
            check=False,
        )
        (scratch / "api_client.log").write_text(api_result.stdout)
        if api_result.returncode != 0:
            raise RuntimeError(f"D6 API client failed: rc={api_result.returncode}")
        write_gpu_snapshot(scratch / "gpu_after_formal.csv")
        if sampler.error is not None:
            raise RuntimeError(f"GPU sampler failed: {sampler.error}")
        server_log_handle.flush()
        server_log = (scratch / "server.log").read_text(errors="replace")
        gpu = gpu_evidence(scratch, server_log)
        write_json(scratch / "gpu_evidence.json", gpu)
        if not gpu["pass"]:
            raise RuntimeError("eight-rank/eight-GPU formal participation gate failed")
        fatal = fatal_scan(server_log)
        write_json(scratch / "fatal_scan_before_cleanup.json", fatal)
        if fatal["unhandled_fatal"]:
            raise RuntimeError("unhandled server fatal pattern detected before cleanup")
        (scratch / "formal.complete").touch()
    except BaseException as error:
        live_error = error
        if not (scratch / "api_smoke.json").exists():
            write_json(
                scratch / "api_smoke.json",
                {
                    "schema_version": 1,
                    "phase": "D6",
                    "arm": "native",
                    "status": "FAIL",
                    "arm_pass": False,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "finished_at_utc": utc_now(),
                },
            )
    finally:
        if sampler is not None:
            sampler.stop()
        server_stopped = stop_server(server, ticks=ticks, command=command)
        if server_log_handle is not None:
            server_log_handle.close()
        contexts_clear = (
            server_stopped
            and wait_no_contexts(scratch / "cuda_contexts_after_server.txt")
        )
        if contexts_clear and pause_started:
            resumed = run(
                ["bash", str(KEEPALIVE), "resume", WORKER_ID],
                timeout=180,
                check=False,
            )
            resume_rc = resumed.returncode
            (scratch / "keepalive_resume.txt").write_text(resumed.stdout)
            if resume_rc == 0:
                shutil.copy2(
                    KEEPALIVE_STATE / "process_identity.json",
                    scratch / "keepalive_identity_after.json",
                )
                shutil.copy2(
                    KEEPALIVE_STATE / "keepalive_gpu_samples.csv",
                    scratch / "keepalive_resume_gpu_samples.csv",
                )
                shutil.copy2(
                    KEEPALIVE_STATE / "keepalive_gate.json",
                    scratch / "keepalive_resume_gate.json",
                )
        cleanup_status = (
            "PASS"
            if server_stopped and contexts_clear and resume_rc == 0
            else "FAIL"
        )
        sealed_status = seal(
            scratch,
            hdfs_run,
            attempt_id=attempt_id,
            hard_stop_utc=hard_stop_utc,
            cleanup_status=cleanup_status,
            contexts_clear=contexts_clear,
            resume_rc=resume_rc,
            gpu=gpu,
            fatal=fatal,
        )
    if live_error is not None:
        raise live_error
    return 0 if sealed_status == "PASS" else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("action", choices=("contract", "preflight", "live"))
    root.add_argument("attempt_id")
    root.add_argument("hard_stop_utc")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.action == "contract":
        print(json.dumps(contract(args.hard_stop_utc), indent=2, sort_keys=True))
        return 0
    if args.action == "preflight":
        print(
            json.dumps(
                preflight(args.attempt_id, args.hard_stop_utc),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    return live(args.attempt_id, args.hard_stop_utc)


if __name__ == "__main__":
    raise SystemExit(main())
