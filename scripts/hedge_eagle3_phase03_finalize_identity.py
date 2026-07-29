#!/usr/bin/env python3
"""Freeze the committed Eagle3 SGLang identity across Phase 03 records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


DEFAULT_DEEPSPEC_ROOT = Path(
    "/mlx_devbox/users/pengzegang/playground/github/"
    "DeepSpec-hedge-v4-eagle3"
)
DEFAULT_SGLANG_ROOT = Path("/home/tiger/src/sglang-hedge-v4-eagle3")
DEFAULT_HDFS_ARTIFACT = Path(
    "/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/"
    "20260729T030500Z-phase-03-hedge-adapter-01"
)
PLACEHOLDER = "PENDING_MAIN_AGENT_SGLANG_FINAL_SHA"
SGLANG_BASE = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
PATCH_DIR = Path("patches/hedge_eagle3_phase03")
PLAIN_FILES = (
    Path("deepspec/hedge_eagle3_phase01b/tools.py"),
    PATCH_DIR / "README.md",
    PATCH_DIR / "phase-03-handoff.md",
    Path("docs/experiment/hedge-deepseek-v4-flash-eagle3.md"),
    Path("docs/progress/hedge-deepseek-v4-flash-eagle3.md"),
)
HDFS_SYNC_FILES = (
    "README.md",
    "manifest.json",
    "phase-03-handoff.md",
    "regression-summary.json",
)
HDFS_CONFIG_FILES = (
    "resolved_config_native.json",
    "resolved_config_B0.json",
    "resolved_config_B+.json",
)
STATUS_REPLACEMENTS = {
    "FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT": "FINAL_CANDIDATE_FROZEN",
    (
        "PHASE_03_FINAL_CANDIDATE_PASS_PENDING_MAIN_SOURCE_COMMIT"
    ): "PHASE_03_COMPLETE_SOURCE_FROZEN",
    (
        "PHASE_03_EXECUTOR_COMPLETE_PENDING_MAIN_SOURCE_COMMIT"
    ): "PHASE_03_COMPLETE_SOURCE_FROZEN",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def run_git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout


def validate_sha(value: str) -> str:
    if SHA_RE.fullmatch(value) is None:
        raise ValueError("SGLang final SHA must be 40 lowercase hex digits")
    return value


def injected_core_aggregate(
    sglang_root: Path,
    final_sha: str,
    records: list[dict[str, object]],
) -> str:
    aggregate = hashlib.sha256()
    for record in records:
        relative = str(record["path"])
        payload = run_git(sglang_root, "show", f"{final_sha}:{relative}")
        digest = sha256_bytes(payload)
        if digest != record["sha256"]:
            raise RuntimeError(
                f"committed injected core differs at {relative}"
            )
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return aggregate.hexdigest()


def verify_committed_source(
    *,
    deepspec_root: Path,
    sglang_root: Path,
    final_sha: str,
) -> dict[str, object]:
    manifest = json.loads(
        (deepspec_root / PATCH_DIR / "manifest.json").read_text()
    )
    head = run_git(sglang_root, "rev-parse", "HEAD").decode().strip()
    if head != final_sha:
        raise RuntimeError(
            f"SGLang HEAD differs from requested final SHA: {head}"
        )
    status = run_git(
        sglang_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    ).decode()
    if status:
        raise RuntimeError("SGLang worktree is not clean after final commit")
    subprocess.run(
        (
            "git",
            "-C",
            str(sglang_root),
            "merge-base",
            "--is-ancestor",
            SGLANG_BASE,
            final_sha,
        ),
        check=True,
        capture_output=True,
        timeout=60,
    )
    patch = run_git(
        sglang_root,
        "diff",
        "--binary",
        "--full-index",
        SGLANG_BASE,
        final_sha,
        "--",
    )
    expected_patch = manifest["sglang_candidate"]["patch_sha256"]
    if sha256_bytes(patch) != expected_patch:
        raise RuntimeError("committed SGLang diff differs from frozen patch")
    changed_files = (
        run_git(
            sglang_root,
            "diff",
            "--name-only",
            SGLANG_BASE,
            final_sha,
            "--",
        )
        .decode()
        .splitlines()
    )
    if changed_files != manifest["sglang_candidate"]["changed_files"]:
        raise RuntimeError("committed SGLang file set differs from manifest")
    injection = injected_core_aggregate(
        sglang_root,
        final_sha,
        manifest["injection"]["files"],
    )
    if injection != manifest["injection"]["aggregate_sha256"]:
        raise RuntimeError("committed injected-core aggregate differs")
    uv_lock = deepspec_root / "uv.lock"
    if (
        sha256_bytes(uv_lock.read_bytes())
        != manifest["uv_lock"]["sha256"]
    ):
        raise RuntimeError("uv.lock differs from Phase 03 manifest")
    return {
        "final_sha": final_sha,
        "patch_sha256": expected_patch,
        "changed_files": changed_files,
        "injection_aggregate_sha256": injection,
        "uv_lock_sha256": manifest["uv_lock"]["sha256"],
    }


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def replace_required(
    text: str,
    old: str,
    new: str,
    *,
    label: str,
) -> str:
    if old not in text:
        raise RuntimeError(f"current Phase 03 {label} block differs")
    return text.replace(old, new, 1)


def finalized_text(
    text: str,
    final_sha: str,
    *,
    relative: Path,
) -> str:
    if PLACEHOLDER not in text:
        if final_sha not in text:
            raise RuntimeError("authority file has another SGLang final SHA")
        frozen_markers = {
            PATCH_DIR / "README.md": ("manifest status are frozen",),
            PATCH_DIR / "phase-03-handoff.md": (
                "FINAL_CANDIDATE_FROZEN",
                "Phase 03 source is frozen and PASS",
            ),
            Path(
                "docs/experiment/hedge-deepseek-v4-flash-eagle3.md"
            ): (
                "PHASE_03_COMPLETE_SOURCE_FROZEN",
                "Phase 03 source freeze PASS",
            ),
            Path(
                "docs/progress/hedge-deepseek-v4-flash-eagle3.md"
            ): (
                "PHASE_03_COMPLETE_SOURCE_FROZEN",
                "source gate frozen/PASS",
            ),
        }
        missing = [
            marker
            for marker in frozen_markers.get(relative, ())
            if marker not in text
        ]
        if missing:
            raise RuntimeError(
                f"frozen Phase 03 authority file is inconsistent: {missing}"
            )
        return text
    result = text.replace(PLACEHOLDER, final_sha)
    for pending, frozen in STATUS_REPLACEMENTS.items():
        result = result.replace(pending, frozen)
    if relative == Path(
        "docs/experiment/hedge-deepseek-v4-flash-eagle3.md"
    ):
        result = replace_required(
            result,
            (
                "> clean fixed-base replay 与联合回归均 PASS。由于 phase executor 不提交，\n"
                f"> `sglang_final_sha` 为 `{final_sha}`，仍待主 Agent\n"
                "> 对这份精确候选 commit 后由 finalizer 回填；该动作完成前\n"
                "> 不得进入 Phase 04。"
            ),
            (
                "> clean fixed-base replay 与联合回归均 PASS。主 Agent 已提交精确\n"
                f"> candidate，并由 identity finalizer 冻结 `sglang_final_sha` 为 `{final_sha}`；\n"
                "> committed tree、patch、core 与 uv lock identity 均 PASS。Phase 03 source\n"
                "> gate 已完成，主 Agent 验收后 Phase 04 gate 可开放。"
            ),
            label="experiment quick-read",
        )
        result = replace_required(
            result,
            (
                "结论。operational keepalive 未被暂停或替换。manifest 状态为\n"
                "`FINAL_CANDIDATE_FROZEN`；主 Agent 必须先提交精确 SGLang\n"
                "candidate、回填 `sglang_final_sha` 并把 marker 标为 frozen，再验收进入 Phase 04。"
            ),
            (
                "结论。operational keepalive 未被暂停或替换。manifest 状态为\n"
                f"`FINAL_CANDIDATE_FROZEN`，final SHA `{final_sha}` 已通过确定性 identity\n"
                "核验；Phase 03 source freeze PASS，主 Agent 验收后可进入 Phase 04。"
            ),
            label="experiment body gate",
        )
        result = result.replace(
            "FINAL CANDIDATE PASS；final source commit pending main Agent",
            f"FINAL SOURCE FROZEN PASS；final commit {final_sha}",
            1,
        )
        next_heading = "## 下一步\n"
        if next_heading not in result:
            raise RuntimeError("current Phase 03 experiment next block differs")
        result = result.partition(next_heading)[0] + (
            next_heading
            + "\nPhase 03 source identity 已冻结为 `"
            + final_sha
            + "` 并通过全部门禁。主 Agent 完成最终 diff/artifact/worker/keepalive\n"
            "复核后可派发独立 Phase 04 executor，运行 native 32、B0 32 和 q25\n"
            "calibration；不得把既有 3-request smoke 复用为 baseline。\n"
        )
    elif relative == Path(
        "docs/progress/hedge-deepseek-v4-flash-eagle3.md"
    ):
        result = replace_required(
            result,
            (
                f"executor 不 commit，final SHA `{final_sha}`；等待主 Agent提交精确 "
                "candidate、运行 identity finalizer 并提交/push DeepSpec，验收后才可派 Phase 04"
            ),
            (
                f"executor handoff 时未 commit；主 Agent 后续提交的 final SHA `{final_sha}` "
                "已通过 identity finalizer，source gate frozen/PASS；最终复核后可派 Phase 04"
            ),
            label="progress current row",
        )
    elif relative == PATCH_DIR / "README.md":
        start = "`manifest.json` records every changed file"
        end = "Replay:\n"
        if start not in result or end not in result:
            raise RuntimeError("current Phase 03 README gate block differs")
        prefix, _, tail = result.partition(start)
        _, _, replay = tail.partition(end)
        result = prefix + (
            "`manifest.json` records every changed file, the uv lock identity, "
            "and the\nclean-base replay evidence. The committed SGLang tree was "
            "verified against\nall recorded identities; the final SHA above "
            "and manifest status are frozen.\n\n"
            "Identity finalizer invocation used for this commit:\n\n"
            "```bash\n"
            "/home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python \\\n"
            "  scripts/hedge_eagle3_phase03_finalize_identity.py \\\n"
            f"  --sglang-final-sha {final_sha}\n"
            "```\n\nReplay:\n"
            + replay
        )
    elif relative == PATCH_DIR / "phase-03-handoff.md":
        heading = "## Main-Agent completion required\n"
        if heading not in result:
            raise RuntimeError("current Phase 03 handoff gate block differs")
        result = result.partition(heading)[0] + (
            "## Finalization result\n\n"
            f"SGLang final SHA `{final_sha}` is committed and clean. The "
            "identity finalizer verified the\n13-file patch hash, file set, "
            "injected core aggregate, and uv lock, then updated\nall local and "
            "HDFS authority fields. Phase 03 source is frozen and PASS; after\n"
            "the main Agent's final review, the Phase 04 gate is open. The "
            "Phase 02 three-request\nsmoke remains bring-up evidence and is "
            "not a native baseline.\n"
        )
    return result


def finalize_repository_files(
    *,
    deepspec_root: Path,
    final_sha: str,
    finalized_at: str,
) -> str:
    final_sha = validate_sha(final_sha)
    manifest_path = deepspec_root / PATCH_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prior = manifest.get("sglang_final_sha")
    if prior not in (PLACEHOLDER, final_sha):
        raise RuntimeError("manifest has another SGLang final SHA")
    regression_path = deepspec_root / PATCH_DIR / "regression-summary.json"
    regression = json.loads(regression_path.read_text(encoding="utf-8"))
    regression_prior = regression.get("sglang_final_sha")
    if regression_prior not in (PLACEHOLDER, final_sha):
        raise RuntimeError("regression summary has another final SHA")
    if prior != regression_prior:
        raise RuntimeError("authority files disagree on SGLang final SHA")
    if prior == PLACEHOLDER:
        if (
            manifest.get("status")
            != "FINAL_CANDIDATE_PASS_PENDING_MAIN_COMMIT"
            or manifest.get("sglang_final_sha_status")
            != "PENDING_MAIN_AGENT_COMMIT"
            or regression.get("sglang_final_sha_status")
            != "PENDING_MAIN_AGENT_COMMIT"
        ):
            raise RuntimeError("pending final-SHA authority state is invalid")
        effective_finalized_at = finalized_at
    else:
        if (
            manifest.get("status") != "FINAL_CANDIDATE_FROZEN"
            or manifest.get("sglang_final_sha_status") != "FROZEN"
            or regression.get("sglang_final_sha_status") != "FROZEN"
        ):
            raise RuntimeError("frozen final-SHA authority state is invalid")
        effective_finalized_at = manifest.get("finalized_at_utc")
        if (
            not isinstance(effective_finalized_at, str)
            or not effective_finalized_at
            or regression.get("finalized_at_utc")
            != effective_finalized_at
        ):
            raise RuntimeError("frozen finalization timestamps disagree")

    rendered: dict[Path, bytes] = {}
    for relative in PLAIN_FILES:
        path = deepspec_root / relative
        rendered[path] = finalized_text(
            path.read_text(encoding="utf-8"),
            final_sha,
            relative=relative,
        ).encode("utf-8")

    manifest["status"] = "FINAL_CANDIDATE_FROZEN"
    manifest["sglang_final_sha"] = final_sha
    manifest["sglang_final_sha_status"] = "FROZEN"
    manifest["finalized_at_utc"] = effective_finalized_at
    rendered[manifest_path] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    regression["sglang_final_sha"] = final_sha
    regression["sglang_final_sha_status"] = "FROZEN"
    regression["finalized_at_utc"] = effective_finalized_at
    rendered[regression_path] = (
        json.dumps(regression, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    for path, payload in rendered.items():
        if path.read_bytes() != payload:
            atomic_write(path, payload)
    return effective_finalized_at


def sync_hdfs_artifact(
    *,
    deepspec_root: Path,
    hdfs_artifact: Path,
    final_sha: str,
) -> None:
    if not hdfs_artifact.is_dir():
        raise RuntimeError(f"Phase 03 HDFS artifact is absent: {hdfs_artifact}")
    local = deepspec_root / PATCH_DIR
    for name in HDFS_SYNC_FILES:
        atomic_write(hdfs_artifact / name, (local / name).read_bytes())
    resolved_hashes = {}
    for name in HDFS_CONFIG_FILES:
        path = hdfs_artifact / name
        config = json.loads(path.read_text(encoding="utf-8"))
        prior = config["source"].get("final_commit")
        if prior not in (PLACEHOLDER, final_sha):
            raise RuntimeError(f"{name} has another SGLang final SHA")
        config["source"]["final_commit"] = final_sha
        config.pop("config_sha256", None)
        config["config_sha256"] = sha256_bytes(
            (
                json.dumps(
                    config,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        )
        resolved_hashes[config["mode"]] = config["config_sha256"]
        atomic_write(
            path,
            (
                json.dumps(config, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        )
    runner_summary_path = hdfs_artifact / "runner_fixture_summary.json"
    runner_summary = json.loads(
        runner_summary_path.read_text(encoding="utf-8")
    )
    runner_summary["resolved_config_hashes"] = resolved_hashes
    atomic_write(
        runner_summary_path,
        (
            json.dumps(runner_summary, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-final-sha", required=True)
    parser.add_argument(
        "--deepspec-root",
        type=Path,
        default=DEFAULT_DEEPSPEC_ROOT,
    )
    parser.add_argument(
        "--sglang-root",
        type=Path,
        default=DEFAULT_SGLANG_ROOT,
    )
    parser.add_argument(
        "--hdfs-artifact",
        type=Path,
        default=DEFAULT_HDFS_ARTIFACT,
    )
    args = parser.parse_args()
    final_sha = validate_sha(args.sglang_final_sha)
    evidence = verify_committed_source(
        deepspec_root=args.deepspec_root,
        sglang_root=args.sglang_root,
        final_sha=final_sha,
    )
    finalized_at = datetime.now(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )
    finalized_at = finalize_repository_files(
        deepspec_root=args.deepspec_root,
        final_sha=final_sha,
        finalized_at=finalized_at,
    )
    sync_hdfs_artifact(
        deepspec_root=args.deepspec_root,
        hdfs_artifact=args.hdfs_artifact,
        final_sha=final_sha,
    )
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "finalized_at_utc": finalized_at,
                **evidence,
                "hdfs_artifact": str(args.hdfs_artifact),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
