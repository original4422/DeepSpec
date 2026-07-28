#!/usr/bin/env python3
"""Validate and publish the authoritative Phase 01B handoff artifacts."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

import sglang
import torch


REPO_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
VENV = Path("/home/tiger/venvs/deepspec-hedge-v4-eagle3")
SOURCE_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
DATASET_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T230100Z-phase-01b-dataset-revision-12"
)
FIXTURE_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T231700Z-phase-01b-fixtures-proxy-bypass-15"
)
ENV_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T224800Z-phase-01b-full-env-protoc-09"
)
LINK_LAYOUT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T225800Z-phase-01b-link-layout-10/"
    "cuda_link_layout.json"
)
KEEPALIVE_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "eagle3-20260728T205627Z/keepalive-active.json"
)
KEEPALIVE_STATUS_ROOT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260728T232400Z-phase-01b-final-keepalive-status-16"
)
CORE_MARKER = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/"
    "hedge-core.json"
)
COMPAT_ROOT = Path(
    "/home/tiger/toolchains/"
    "deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat"
)
CUDA_ROOT = (
    VENV / "lib/python3.11/site-packages/nvidia/cu13"
)
UV = Path("/home/tiger/.local/bin/uv")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def command(*args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    ).stdout.strip()


def publish_bytes(
    path: Path,
    payload: bytes,
    *,
    replace_existing: bool = False,
) -> str:
    """Atomically publish one small artifact after fsync/size/hash gates."""

    if path.exists() != replace_existing:
        state = "absent" if replace_existing else "already exists"
        raise RuntimeError(f"publish target is unexpectedly {state}: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if temporary.exists():
        raise RuntimeError(f"publish temporary already exists: {temporary}")
    expected_size = len(payload)
    expected_hash = hashlib.sha256(payload).hexdigest()
    with temporary.open("xb") as stream:
        written = stream.write(payload)
        if written != expected_size:
            raise RuntimeError(f"short artifact write: {temporary}")
        stream.flush()
        os.fsync(stream.fileno())
    if (
        temporary.stat().st_size != expected_size
        or sha256(temporary) != expected_hash
    ):
        raise RuntimeError(f"temporary artifact identity differs: {temporary}")
    os.replace(temporary, path)
    if path.stat().st_size != expected_size or sha256(path) != expected_hash:
        raise RuntimeError(f"published artifact identity differs: {path}")
    return expected_hash


def write_json(
    path: Path,
    value: object,
    *,
    replace_existing: bool = False,
) -> str:
    return publish_bytes(
        path,
        (
            json.dumps(
                value,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        replace_existing=replace_existing,
    )


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def validate_inputs() -> dict[str, Any]:
    required = (
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "uv.lock",
        SOURCE_ROOT / "python/pyproject.toml",
        DATASET_ROOT / "gsm8k_split_manifest.json",
        DATASET_ROOT / "gsm8k_split_manifest.json.sha256",
        FIXTURE_ROOT / "runner_fixture_summary.json",
        FIXTURE_ROOT / "process_fixture_summary.json",
        FIXTURE_ROOT / "mock_runner_diagnostic.json",
        ENV_ROOT / "environment_sync.log",
        ENV_ROOT / "import_identity.json",
        ENV_ROOT / "uv_pip_check.log",
        LINK_LAYOUT,
        KEEPALIVE_MARKER,
        KEEPALIVE_STATUS_ROOT / "status.stdout.txt",
        KEEPALIVE_STATUS_ROOT / "status.stderr.txt",
        CORE_MARKER,
    )
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"required Phase 01B input is absent: {path}")

    dataset = json.loads(
        (DATASET_ROOT / "gsm8k_split_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    runner = json.loads(
        (FIXTURE_ROOT / "runner_fixture_summary.json").read_text(
            encoding="utf-8"
        )
    )
    process = json.loads(
        (FIXTURE_ROOT / "process_fixture_summary.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostic = json.loads(
        (FIXTURE_ROOT / "mock_runner_diagnostic.json").read_text(
            encoding="utf-8"
        )
    )
    keepalive = json.loads(KEEPALIVE_MARKER.read_text(encoding="utf-8"))
    core = json.loads(CORE_MARKER.read_text(encoding="utf-8"))

    if dataset["dataset"]["resolved_revision"] != (
        "740312add88f781978c0658806c59bc2815b9866"
    ):
        raise RuntimeError("dataset revision differs")
    if (
        len(dataset["calibration"]) != 32
        or len(dataset["formal"]) != 500
        or dataset["selection"]["overlap_count"] != 0
    ):
        raise RuntimeError("dataset split contract differs")
    if (
        runner["status"] != "PASS"
        or runner["mock_api"]["warmup_count"] != 10
        or runner["mock_api"]["formal_count"] != 500
        or runner["mock_api"]["maximum_runner_in_flight"] != 1
        or runner["mock_api"]["summary"]["formal_terminal"] != 500
        or diagnostic["differing_fields"]
    ):
        raise RuntimeError("runner fixture contract differs")
    if (
        process["status"] != "PASS"
        or process["broad_kill_used"]
        or not process["mismatched_identity_refused"]
        or process["signal_sent_to_unregistered_process"]
    ):
        raise RuntimeError("process cleanup fixture contract differs")
    if (
        keepalive["status"] != "active"
        or keepalive["worker_id"] != "4099544"
        or keepalive["expected_gpu_count"] != 8
        or not keepalive["health_gate"]["healthy"]
    ):
        raise RuntimeError("operational keepalive marker differs")
    status_text = (
        KEEPALIVE_STATUS_ROOT / "status.stdout.txt"
    ).read_text(encoding="utf-8")
    if (
        "HEALTHY" not in status_text
        or '"healthy": true' not in status_text
        or status_text.count('"mean_utilization": 100.0') != 8
    ):
        raise RuntimeError("final keepalive status gate differs")
    if (
        core["status"] != "READY"
        or core["commit_sha"]
        != "4d96f44065c07030ede67484a262006ec149626a"
        or core["tests"]["result"] != "PASS"
        or core["tests"]["test_count"] != 33
    ):
        raise RuntimeError("pure-core dependency marker differs")
    return {
        "dataset": dataset,
        "runner": runner,
        "process": process,
        "keepalive": keepalive,
        "core": core,
    }


def environment_lock() -> dict[str, Any]:
    lock_check = command(
        str(UV),
        "lock",
        "--check",
        "--project",
        str(REPO_ROOT),
    )
    pip_check = command(
        str(UV),
        "pip",
        "check",
        "--python",
        str(VENV / "bin/python"),
    )
    packages = json.loads(
        command(
            str(UV),
            "pip",
            "list",
            "--python",
            str(VENV / "bin/python"),
            "--format=json",
        )
    )
    key_versions = {
        name: package_version(name)
        for name in (
            "torch",
            "nvidia-nccl-cu13",
            "flashinfer-python",
            "triton",
            "sglang-kernel",
            "sglang",
            "numpy",
        )
    }
    link_layout = json.loads(LINK_LAYOUT.read_text(encoding="utf-8"))
    rust_env = {
        **os.environ,
        "RUSTUP_HOME": (
            "/home/tiger/toolchains/deepspec-rust-1.90.0/rustup"
        ),
        "CARGO_HOME": (
            "/home/tiger/toolchains/deepspec-rust-1.90.0/cargo"
        ),
    }
    if torch.cuda.is_initialized():
        raise RuntimeError("torch unexpectedly initialized CUDA")
    if Path(sglang.__file__).resolve().parent != (
        SOURCE_ROOT / "python/sglang"
    ).resolve():
        raise RuntimeError("SGLang import does not point to lane source")
    return {
        "schema_version": 1,
        "status": "PASS",
        "created_at": utc_now(),
        "phase": "01B",
        "lane": "eagle3",
        "repository_root": str(REPO_ROOT),
        "venv": str(VENV),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "implementation": sys.implementation.name,
        },
        "uv": {
            "version": command(str(UV), "--version"),
            "lock_check": "PASS",
            "lock_check_output": lock_check,
            "pip_check": "PASS",
            "pip_check_output": pip_check,
            "rebuild_commands": [
                (
                    f"UV_PROJECT_ENVIRONMENT={VENV} "
                    f"{UV} sync --project {REPO_ROOT} --frozen "
                    f"--no-install-project --python {VENV / 'bin/python'}"
                ),
                (
                    f"{UV} pip install --python {VENV / 'bin/python'} "
                    f"--no-deps --editable {SOURCE_ROOT / 'python'}"
                ),
            ],
        },
        "lock_identity": {
            "project_name": "deepspec-hedge-v4-eagle3-runtime",
            "pyproject": str(REPO_ROOT / "pyproject.toml"),
            "pyproject_sha256": sha256(REPO_ROOT / "pyproject.toml"),
            "uv_lock": str(REPO_ROOT / "uv.lock"),
            "uv_lock_sha256": sha256(REPO_ROOT / "uv.lock"),
            "installed_package_count": len(packages),
            "installed_packages": packages,
        },
        "versions": {
            **key_versions,
            "torch_cuda_runtime": torch.version.cuda,
        },
        "sglang_import": {
            "version": sglang.__version__,
            "path": str(Path(sglang.__file__).resolve()),
            "editable_source": str(SOURCE_ROOT / "python"),
        },
        "cuda_13_toolchain": {
            "cuda_root": str(CUDA_ROOT),
            "compat_root": str(COMPAT_ROOT),
            "compat_libcuda_sha256": sha256(COMPAT_ROOT / "libcuda.so.1"),
            "link_layout_evidence": str(LINK_LAYOUT),
            "link_layout_sha256": sha256(LINK_LAYOUT),
            "link_layout": link_layout,
            "rustc": command(
                "/home/tiger/toolchains/deepspec-rust-1.90.0/"
                "cargo/bin/rustc",
                "--version",
                env=rust_env,
            ),
            "cargo": command(
                "/home/tiger/toolchains/deepspec-rust-1.90.0/"
                "cargo/bin/cargo",
                "--version",
                env=rust_env,
            ),
            "protoc": command(
                "/home/tiger/toolchains/deepspec-protoc-35.0/bin/protoc",
                "--version",
            ),
        },
        "attempt_evidence": {
            "rust_missing": (
                "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
                "20260728T224200Z-phase-01b-full-env-07"
            ),
            "protoc_missing": (
                "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
                "20260728T224500Z-phase-01b-full-env-rust-08"
            ),
            "full_environment_pass": str(ENV_ROOT),
        },
        "model_or_fixture_cuda_operation_performed": False,
        "torch_cuda_initialized": torch.cuda.is_initialized(),
        "operational_keepalive_is_separate": True,
    }


def source_identity(core: dict[str, Any]) -> dict[str, Any]:
    head = command("git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD")
    branch = command(
        "git", "-C", str(SOURCE_ROOT), "branch", "--show-current"
    )
    status = command(
        "git", "-C", str(SOURCE_ROOT), "status", "--porcelain=v1"
    )
    distance = int(
        command(
            "git",
            "-C",
            str(SOURCE_ROOT),
            "rev-list",
            "--count",
            f"{SGLANG_BASE}..{head}",
        )
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(SOURCE_ROOT),
            "merge-base",
            "--is-ancestor",
            SGLANG_BASE,
            head,
        ),
        check=True,
        timeout=30,
    )
    if head != SGLANG_BASE or distance != 0 or status:
        raise RuntimeError("Phase 01B SGLang source identity differs")
    direct_url = json.loads(
        (
            VENV
            / "lib/python3.11/site-packages/"
            "sglang-0.5.16.dist-info/direct_url.json"
        ).read_text(encoding="utf-8")
    )
    if direct_url != {
        "url": f"file://{SOURCE_ROOT / 'python'}",
        "dir_info": {"editable": True},
    }:
        raise RuntimeError("editable SGLang direct URL differs")
    return {
        "schema_version": 1,
        "status": "PASS",
        "created_at": utc_now(),
        "source_root": str(SOURCE_ROOT),
        "branch": branch,
        "origin": command(
            "git", "-C", str(SOURCE_ROOT), "remote", "get-url", "origin"
        ),
        "release_tag": command(
            "git",
            "-C",
            str(SOURCE_ROOT),
            "describe",
            "--tags",
            "--exact-match",
            "HEAD",
        ),
        "required_base_commit": SGLANG_BASE,
        "head_commit": head,
        "head_equals_required_base": True,
        "required_base_is_ancestor": True,
        "commits_after_required_base": distance,
        "worktree_clean": True,
        "source_parent_gate": (
            "PASS: the independent worktree was created directly at the "
            "required fdebc938 base; Phase 01B HEAD still equals that base"
        ),
        "source_pyproject": str(SOURCE_ROOT / "python/pyproject.toml"),
        "source_pyproject_sha256": sha256(
            SOURCE_ROOT / "python/pyproject.toml"
        ),
        "sglang_version": package_version("sglang"),
        "import_path": str(Path(sglang.__file__).resolve()),
        "editable_direct_url": direct_url,
        "pure_core_dependency": {
            "status": "READY_NOT_CHERRY_PICKED",
            "marker": str(CORE_MARKER),
            "marker_sha256": sha256(CORE_MARKER),
            "commit_sha": core["commit_sha"],
            "parent_sha": core["parent_sha"],
            "hedge_source_sha": core["hedge_source_sha"],
            "test_result": core["tests"]["result"],
            "test_count": core["tests"]["test_count"],
            "phase_for_cherry_pick": "03",
        },
        "model_or_fixture_cuda_operation_performed": False,
    }


def handoff_text(
    output_dir: Path,
    hashes: dict[str, str],
    validated: dict[str, Any],
) -> str:
    keepalive = validated["keepalive"]
    runner = validated["runner"]
    dataset = validated["dataset"]
    summary = runner["mock_api"]["summary"]
    lines = [
        "# Eagle3 Phase 01B handoff",
        "",
        "## 结论",
        "",
        "`PASS`。独立 uv/SGLang 环境、固定数据 split、顺序 runner、",
        "B0/q25/report fixture 与定向 process cleanup 均满足 Phase 01B",
        "退出门禁；可以交由主 Agent 做只读验收。此 executor 未进入 Phase 02、",
        "未启动模型服务、未 cherry-pick pure HEDGE core、未 commit/push。",
        "",
        "Phase 01B 的 import、data 和 fixture 均为 CPU-only；唯一 GPU workload 是",
        "独立的 operational keepalive（不是模型/实验结果），交接时仍健康运行。",
        "",
        "## 退出门禁",
        "",
        f"- uv lock check 与 `uv pip check` 均 PASS；venv 为 `{VENV}`。",
        f"- SGLang import 来自 `{SOURCE_ROOT}/python/sglang/__init__.py`；",
        f"  clean HEAD/固定 base 均为 `{SGLANG_BASE}`，tag `v0.5.16`。",
        "- Python/Torch/CUDA/NCCL/FlashInfer/Triton/sglang-kernel 版本、",
        "  CUDA 13.0 link layout、Rust 1.90 和 protoc 35.0 已写入",
        "  `environment_lock.json`。",
        f"- GSM8K revision `{dataset['dataset']['resolved_revision']}`，",
        f"  fingerprint `{dataset['dataset']['fingerprint']}`，seed ",
        f"  `{dataset['selection']['seed']}`；32 calibration 与 500 formal",
        "  重叠为 0，prompt/generation contract 已固化。",
        "- native/B0/B+ resolved config 具有同一 schema；TP=8、EAGLE3",
        "  proposal width=3 与所有公共 decode 字段保持一致。",
        f"- mock API 完成 10 warmup + 500 formal；formal terminal",
        f"  `{summary['formal_terminal']}`，success `{summary['successes']}`，",
        f"  retry `{summary['retries']}`，runner/server maximum active 均为 1。",
        "- q25 fixture 使用 linear method 得到 `B=g=1.75`、`m=1`；",
        "  B0 PASS 与首个 token-ID mismatch 反例两条路径均已验证。",
        "- cleanup fixture 先拒绝 start-ticks 不符的登记身份，只向完全匹配的",
        "  PID/PGID/SID process group 发送 SIGTERM；没有 broad kill，child",
        "  return code 为 0。",
        "",
        "## Token-ID runtime gate（Phase 02 必须保留）",
        "",
        "runner 对完整 output token IDs **fail-closed**：固定 OpenAI chat response",
        "找不到完整整数 token-ID 数组时，本请求作为 transport failure 进入有界",
        "retry，最终仍缺失则记为失败。Phase 02 必须实测固定 SGLang OpenAI chat",
        "path 是否实际返回 token IDs；若没有，只能增加可审计、可 fixture 覆盖的",
        "API adapter/runtime 输出字段。禁止把 response text 静默重新 tokenize，",
        "因为这不能证明生成时的真实 token IDs，也会破坏 B0 等价审计。",
        "",
        "## Required artifacts",
        "",
    ]
    for name in (
        "environment_lock.json",
        "sglang_source_identity.json",
        "gsm8k_split_manifest.json",
        "runner_fixture_summary.json",
        "process_fixture_summary.json",
    ):
        lines.append(f"- `{output_dir / name}` — SHA-256 `{hashes[name]}`")
    lines += [
        f"- `{output_dir / 'phase-01b-handoff.md'}` — 本文件；",
        "  自身 hash 由 `artifact_manifest.json` 在写入后记录。",
        "",
        "完整 10+500 mock responses 位于",
        f"`{FIXTURE_ROOT / 'mock_runner_outputs.json'}`；resolved configs、",
        "diagnostic 与 experiment table 同目录保留。",
        "",
        "## Attempt / blocker 迁移",
        "",
        "- direct-torch attempt 04：按 lock 补齐 ELF closure 和 lane-local",
        "  NCCL，torch CPU import PASS。",
        "- keepalive attempt 05：错误 compat prefix 导致失败且前后 0 context；",
        "  attempt 06 仅切换到已验证的私有 CUDA 13 compat prefix 后 8 卡 PASS。",
        "- full-env attempts 07→08→09：blocker 依次从缺 Rust 迁移到缺 protoc，",
        "  固定 Rust 1.90/protoc 35.0 后 frozen sync、editable import 与 pip",
        "  check PASS。",
        "- dataset attempt 11：本地 revision 常量多一个尾字符，provider",
        "  fail-closed；attempt 12 仅修正常量后 pinned revision/split PASS。",
        "- fixture attempt 13：早期汇总断言失败但缺少实际差异；attempt 14",
        "  新增 diagnostic，证明 inherited `HTTP_PROXY` 劫持 loopback 并返回",
        "  403；attempt 15 仅让 lane-local transport 显式 bypass proxy 后完整",
        "  10+500 PASS。",
        "",
        "## 当前进程与依赖",
        "",
        f"- operational keepalive marker：`{KEEPALIVE_MARKER}`；owner",
        f"  PID/PGID/SID `{keepalive['owner_pid']}/",
        f"{keepalive['owner_pgid']}/{keepalive['owner_sid']}`，worker",
        f"  `{keepalive['worker_id']}`，8×10 样本 gate healthy；最终复核见",
        f"  `{KEEPALIVE_STATUS_ROOT}`。不要向它发送 signal，直至主 Agent",
        "  紧邻 Phase 02 模型 attempt 按 lifecycle 明确暂停。",
        "- fixture child 已正常终止，mock server 已 shutdown；本 executor",
        "  没有遗留模型服务或 fixture process。",
        f"- pure-core marker `{CORE_MARKER}` 为 READY：commit",
        f"  `{validated['core']['commit_sha']}`、33 tests PASS；当前",
        "  **not cherry-picked**，按计划留给 Phase 03。",
        "",
        "## 下一步条件",
        "",
        "主 Agent 对上述 6 个 required artifacts、hash 和原始 attempt 做只读",
        "验收后，Phase 01B 可标记完成。Phase 02 仍须遵守独立前置门禁：确认",
        "01A/01C 已验收；紧邻 attempt 暂停并验证 keepalive 8 个 CUDA context",
        "全部退出；使用登记命令进入 target diagnostic/native Eagle3，并首先",
        "验证 OpenAI chat token-ID runtime gate。这里不声称任何模型结果。",
        "",
    ]
    return "\n".join(lines)


REQUIRED_ARTIFACTS = (
    "environment_lock.json",
    "sglang_source_identity.json",
    "gsm8k_split_manifest.json",
    "runner_fixture_summary.json",
    "process_fixture_summary.json",
    "phase-01b-handoff.md",
)


def audit_sealed_artifacts(output_dir: Path) -> dict[str, str]:
    manifest_path = output_dir / "artifact_manifest.json"
    companion_path = output_dir / "artifact_manifest.sha256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "PASS"
        or manifest.get("required_artifact_count")
        != len(REQUIRED_ARTIFACTS)
        or len(manifest.get("files", [])) != len(REQUIRED_ARTIFACTS)
    ):
        raise RuntimeError("artifact manifest cardinality/status differs")
    records = {
        record["name"]: record for record in manifest["files"]
    }
    if set(records) != set(REQUIRED_ARTIFACTS):
        raise RuntimeError("artifact manifest file set differs")
    hashes: dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = output_dir / name
        record = records[name]
        actual_hash = sha256(path)
        if (
            record["path"] != str(path)
            or record["size"] != path.stat().st_size
            or record["sha256"] != actual_hash
        ):
            raise RuntimeError(f"sealed artifact identity differs: {name}")
        hashes[name] = actual_hash
    handoff = (output_dir / "phase-01b-handoff.md").read_text(
        encoding="utf-8"
    )
    for name in REQUIRED_ARTIFACTS[:-1]:
        expected = (
            f"`{output_dir / name}` — SHA-256 `{hashes[name]}`"
        )
        if expected not in handoff:
            raise RuntimeError(f"handoff hash differs: {name}")
    expected_companion = (
        f"{sha256(manifest_path)}  artifact_manifest.json\n"
    )
    if companion_path.read_text(encoding="utf-8") != expected_companion:
        raise RuntimeError("artifact manifest companion hash differs")
    return hashes


def repair_existing_handoff_hash(output_dir: Path) -> dict[str, str]:
    expected_root = Path(
        "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
        "20260728T232000Z-phase-01b-final-17"
    )
    if output_dir != expected_root:
        raise RuntimeError("repair is restricted to the audited final-17")
    manifest_path = output_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {
        record["name"]: record for record in manifest["files"]
    }
    if set(records) != set(REQUIRED_ARTIFACTS):
        raise RuntimeError("pre-repair artifact file set differs")
    for name in REQUIRED_ARTIFACTS[:-1]:
        path = output_dir / name
        actual_hash = sha256(path)
        if (
            records[name]["size"] != path.stat().st_size
            or records[name]["sha256"] != actual_hash
        ):
            raise RuntimeError(
                f"non-handoff identity differs before repair: {name}"
            )

    runner_name = "runner_fixture_summary.json"
    runner_hash = sha256(output_dir / runner_name)
    old_hash = hashlib.sha256(b"").hexdigest()
    handoff_path = output_dir / "phase-01b-handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    old_fragment = (
        f"`{output_dir / runner_name}` — SHA-256 `{old_hash}`"
    )
    new_fragment = (
        f"`{output_dir / runner_name}` — SHA-256 `{runner_hash}`"
    )
    if handoff.count(old_fragment) != 1:
        raise RuntimeError("audited empty-file hash fragment is not unique")
    corrected = handoff.replace(old_fragment, new_fragment)
    publish_bytes(
        handoff_path,
        corrected.encode("utf-8"),
        replace_existing=True,
    )

    handoff_record = records["phase-01b-handoff.md"]
    handoff_record["size"] = handoff_path.stat().st_size
    handoff_record["sha256"] = sha256(handoff_path)
    write_json(manifest_path, manifest, replace_existing=True)
    companion = (
        f"{sha256(manifest_path)}  artifact_manifest.json\n"
    ).encode("utf-8")
    publish_bytes(
        output_dir / "artifact_manifest.sha256",
        companion,
        replace_existing=True,
    )
    return audit_sealed_artifacts(output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repair-existing-handoff-hash", action="store_true")
    args = parser.parse_args(argv)
    if args.repair_existing_handoff_hash:
        repaired = repair_existing_handoff_hash(args.output_dir)
        print(
            "PHASE01B_FINAL_HASH_REPAIR_PASS "
            + " ".join(
                f"{name}={repaired[name]}"
                for name in REQUIRED_ARTIFACTS
            )
        )
        return 0
    if args.output_dir.exists():
        raise RuntimeError("refusing to overwrite Phase 01B final artifacts")
    validated = validate_inputs()
    args.output_dir.mkdir(parents=True)

    write_json(args.output_dir / "environment_lock.json", environment_lock())
    write_json(
        args.output_dir / "sglang_source_identity.json",
        source_identity(validated["core"]),
    )
    publish_bytes(
        args.output_dir / "gsm8k_split_manifest.json",
        (DATASET_ROOT / "gsm8k_split_manifest.json").read_bytes(),
    )
    publish_bytes(
        args.output_dir / "runner_fixture_summary.json",
        (FIXTURE_ROOT / "runner_fixture_summary.json").read_bytes(),
    )
    publish_bytes(
        args.output_dir / "process_fixture_summary.json",
        (FIXTURE_ROOT / "process_fixture_summary.json").read_bytes(),
    )
    required_without_handoff = REQUIRED_ARTIFACTS[:-1]
    hashes = {
        name: sha256(args.output_dir / name)
        for name in required_without_handoff
    }
    publish_bytes(
        args.output_dir / "phase-01b-handoff.md",
        handoff_text(args.output_dir, hashes, validated).encode("utf-8"),
    )
    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "created_at": utc_now(),
        "phase": "01B",
        "files": [
            {
                "name": name,
                "path": str(args.output_dir / name),
                "size": (args.output_dir / name).stat().st_size,
                "sha256": sha256(args.output_dir / name),
            }
            for name in REQUIRED_ARTIFACTS
        ],
        "required_artifact_count": len(REQUIRED_ARTIFACTS),
    }
    write_json(args.output_dir / "artifact_manifest.json", manifest)
    publish_bytes(
        args.output_dir / "artifact_manifest.sha256",
        (
            f"{sha256(args.output_dir / 'artifact_manifest.json')}  "
            "artifact_manifest.json\n"
        ).encode("utf-8"),
    )
    audit_sealed_artifacts(args.output_dir)
    print(
        "PHASE01B_FINAL_PASS "
        f"required={len(REQUIRED_ARTIFACTS)} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Phase 01B finalize error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
