#!/usr/bin/env python3
"""Acquire, minimally validate, and publish the pinned DFlash draft.

This tool is intentionally self-contained and uses only the Python standard
library plus curl. Active files and logs live on the assigned worker's NVMe.
The HDFS payload is copied as independent regular files and is made visible by
an atomic same-parent directory rename that already contains its .complete
marker.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, BinaryIO


REPO_ID = "RedHatAI/DeepSeek-V4-Flash-speculator.dflash"
REVISION = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
EXPECTED_PROVIDER_FILES = {
    ".gitattributes",
    "README.md",
    "config.json",
    "config.py",
    "model.safetensors",
    "val_metrics.json",
}
WORKER_ID = "4099543"
EXPECTED_HOSTNAME = "g340-cd51-4b00-4d69-9088-7ae6-6253"
EXPECTED_GPU_COUNT = 8
WORKTREE = pathlib.Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
NVME_ROOT = pathlib.Path("/tmp/deepspec-hedge-dflash/d1a")
KEEPALIVE_ROOT = pathlib.Path("/tmp/deepspec-hedge-dflash/keepalive")
HDFS_LANE_ROOT = pathlib.Path("/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash")
HDFS_DRAFT_PARENT = (
    HDFS_LANE_ROOT
    / "draft"
    / "RedHatAI--DeepSeek-V4-Flash-speculator.dflash"
)
HDFS_FORMAL = HDFS_DRAFT_PARENT / REVISION
HDFS_POINTER = HDFS_LANE_ROOT / "draft_pointer.json"
REPO_EVIDENCE_PARENT = (
    WORKTREE
    / "docs"
    / "experiment"
    / "artifacts"
    / "hedge-deepseek-v4-flash-dflash"
    / "d1a"
)
TIMEBOX_PATH = (
    WORKTREE
    / "docs"
    / "experiment"
    / "artifacts"
    / "hedge-deepseek-v4-flash-dflash"
    / "d0"
    / "timebox.json"
)
LANE_IDENTITY_PATH = TIMEBOX_PATH.with_name("lane_identity.json")
USER_AGENT = "DeepSpec-DFlash-D1A/1.0"
SMALL_HASH_LIMIT_BYTES = 64 * 1024 * 1024
COPY_CHUNK_BYTES = 16 * 1024 * 1024
HEARTBEAT_INTERVAL_SECONDS = 30

DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "I64": 8,
    "U64": 8,
    "F64": 8,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"refusing to replace temporary file: {temporary}")
    payload = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8") + b"\n"
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        with contextlib.suppress(OSError):
            os.fsync(handle.fileno())
    os.rename(temporary, path)


def sha256_file(path: pathlib.Path, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    consumed = 0
    with path.open("rb") as handle:
        while True:
            remaining = None if limit is None else limit - consumed
            if remaining is not None and remaining <= 0:
                break
            block = handle.read(
                8 * 1024 * 1024
                if remaining is None
                else min(8 * 1024 * 1024, remaining)
            )
            if not block:
                break
            digest.update(block)
            consumed += len(block)
    return digest.hexdigest()


def git_blob_sha1(path: pathlib.Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def relative_regular_files(root: pathlib.Path) -> dict[str, pathlib.Path]:
    files: dict[str, pathlib.Path] = {}
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            raise RuntimeError(f"symlink is forbidden in snapshot: {relative}")
        if candidate.is_file():
            files[relative] = candidate
        elif not candidate.is_dir():
            raise RuntimeError(f"non-regular snapshot entry: {relative}")
    return files


def safe_provider_path(raw: str) -> str:
    candidate = pathlib.PurePosixPath(raw)
    if (
        not raw
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != raw
    ):
        raise RuntimeError(f"unsafe provider path: {raw!r}")
    return raw


def provider_oid(entry: dict[str, Any]) -> dict[str, Any]:
    lfs = entry.get("lfs") or {}
    return {
        "git_blob_id": entry.get("blobId"),
        "lfs_sha256": lfs.get("sha256"),
        "lfs_size": lfs.get("size"),
        "lfs_pointer_size": lfs.get("pointerSize"),
        "xet_hash": entry.get("xetHash") or lfs.get("xetHash"),
    }


def parse_safetensors_header(path: pathlib.Path) -> dict[str, Any]:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise RuntimeError(f"truncated safetensors prefix: {path}")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 2 or header_length > 128 * 1024 * 1024:
            raise RuntimeError(
                f"implausible safetensors header length {header_length}: {path}"
            )
        raw_header = handle.read(header_length)
    if len(raw_header) != header_length:
        raise RuntimeError(f"truncated safetensors header: {path}")
    try:
        header = json.loads(raw_header)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid safetensors header JSON: {path}") from error
    if not isinstance(header, dict):
        raise RuntimeError("safetensors header must be a JSON object")

    data_bytes = file_size - 8 - header_length
    if data_bytes < 0:
        raise RuntimeError("safetensors header exceeds file size")

    tensors: list[dict[str, Any]] = []
    dtype_counts: collections.Counter[str] = collections.Counter()
    rank_counts: collections.Counter[str] = collections.Counter()
    parameter_count = 0
    intervals: list[tuple[int, int, str]] = []
    for name, value in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(value, dict):
            raise RuntimeError(f"tensor metadata is not an object: {name}")
        dtype = value.get("dtype")
        shape = value.get("shape")
        offsets = value.get("data_offsets")
        if dtype not in DTYPE_BYTES:
            raise RuntimeError(f"unsupported tensor dtype {dtype!r}: {name}")
        if (
            not isinstance(shape, list)
            or not all(isinstance(item, int) and item >= 0 for item in shape)
        ):
            raise RuntimeError(f"invalid tensor shape: {name}")
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(isinstance(item, int) for item in offsets)
        ):
            raise RuntimeError(f"invalid tensor data offsets: {name}")
        start, end = offsets
        if start < 0 or end < start or end > data_bytes:
            raise RuntimeError(f"out-of-range tensor data offsets: {name}")
        elements = math.prod(shape)
        expected_bytes = elements * DTYPE_BYTES[dtype]
        if end - start != expected_bytes:
            raise RuntimeError(
                f"tensor byte span disagrees with dtype/shape: {name}"
            )
        intervals.append((start, end, name))
        parameter_count += elements
        dtype_counts[dtype] += 1
        rank_counts[str(len(shape))] += 1
        tensors.append(
            {
                "name": name,
                "dtype": dtype,
                "shape": shape,
                "data_offsets": offsets,
                "parameter_count": elements,
                "data_bytes": expected_bytes,
            }
        )

    intervals.sort()
    cursor = 0
    for start, end, name in intervals:
        if start != cursor:
            raise RuntimeError(
                f"safetensors data is not contiguous at {name}: "
                f"expected {cursor}, got {start}"
            )
        cursor = end
    if cursor != data_bytes:
        raise RuntimeError(
            f"safetensors final offset {cursor} != payload bytes {data_bytes}"
        )

    tensors.sort(key=lambda item: item["name"])
    layer_indices = sorted(
        {
            int(match.group(1))
            for item in tensors
            if (
                match := re.search(
                    r"(?:^|\.)layers\.(\d+)\.", str(item["name"])
                )
            )
        }
    )
    target_width_matches = [
        item["name"] for item in tensors if 16384 in item["shape"]
    ]
    hidden_size_matches = [
        item["name"] for item in tensors if 4096 in item["shape"]
    ]
    draft_vocab_matches = [
        item["name"] for item in tensors if 32000 in item["shape"]
    ]
    if layer_indices != [0, 1, 2, 3, 4]:
        raise RuntimeError(
            f"weight layer indices do not match 5-layer config: {layer_indices}"
        )
    if not target_width_matches:
        raise RuntimeError("no tensor dimension matches hc_mult width 16384")
    if not hidden_size_matches:
        raise RuntimeError("no tensor dimension matches hidden_size 4096")
    if not draft_vocab_matches:
        raise RuntimeError("no tensor dimension matches draft_vocab_size 32000")

    return {
        "schema_version": 1,
        "path": path.name,
        "file_size_bytes": file_size,
        "header_length_bytes": header_length,
        "header_sha256": hashlib.sha256(raw_header).hexdigest(),
        "data_bytes": data_bytes,
        "metadata": header.get("__metadata__"),
        "tensor_count": len(tensors),
        "parameter_count": parameter_count,
        "dtype_tensor_counts": dict(sorted(dtype_counts.items())),
        "rank_tensor_counts": dict(sorted(rank_counts.items())),
        "layer_indices": layer_indices,
        "shape_contract": {
            "configured_hidden_size_dimension": 4096,
            "configured_hc_mult": 4,
            "derived_target_feature_width_dimension": 16384,
            "configured_draft_vocab_size_dimension": 32000,
            "target_feature_width_tensor_names": target_width_matches,
            "hidden_size_tensor_count": len(hidden_size_matches),
            "draft_vocab_tensor_names": draft_vocab_matches,
            "all_tensor_byte_spans_match_dtype_and_shape": True,
            "all_data_offsets_contiguous_and_cover_payload": True,
        },
        "tensors": tensors,
    }


def config_summary(path: pathlib.Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    transformer = config.get("transformer_layer_config")
    speculators = config.get("speculators_config")
    if not isinstance(transformer, dict) or not isinstance(speculators, dict):
        raise RuntimeError("required nested DFlash config objects are missing")
    proposals = speculators.get("proposal_methods")
    proposal_tokens = [
        item.get("speculative_tokens")
        for item in proposals
        if isinstance(item, dict)
    ] if isinstance(proposals, list) else []
    checks = {
        "architecture": config.get("architectures") == ["DFlashDraftModel"],
        "algorithm": speculators.get("algorithm") == "dflash",
        "block_size": config.get("block_size") == 8,
        "proposal_width": proposal_tokens == [7],
        "aux_hidden_state_layer_ids": config.get(
            "aux_hidden_state_layer_ids"
        )
        == [3, 13, 23, 32, 42],
        "hc_mult": transformer.get("hc_mult") == 4,
        "hidden_size": transformer.get("hidden_size") == 4096,
        "derived_target_feature_width": (
            transformer.get("hc_mult") * transformer.get("hidden_size")
            if isinstance(transformer.get("hc_mult"), int)
            and isinstance(transformer.get("hidden_size"), int)
            else None
        )
        == 16384,
        "draft_layer_count": transformer.get("num_hidden_layers") == 5,
        "draft_vocab_size": config.get("draft_vocab_size") == 32000,
        "target_vocab_size": transformer.get("vocab_size") == 129280,
        "all_sliding_attention_layers": transformer.get("layer_types")
        == ["sliding_attention"] * 5,
        "sliding_window": transformer.get("sliding_window") == 2048,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"fixed DFlash config contract failed: {failed}")
    return {
        "schema_version": 1,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "config_sha256": sha256_file(path),
        "checks": checks,
        "selected": {
            "architectures": config.get("architectures"),
            "auto_map": config.get("auto_map"),
            "aux_hidden_state_layer_ids": config.get(
                "aux_hidden_state_layer_ids"
            ),
            "block_size": config.get("block_size"),
            "draft_vocab_size": config.get("draft_vocab_size"),
            "dtype": config.get("dtype"),
            "mask_token_id": config.get("mask_token_id"),
            "max_anchors": config.get("max_anchors"),
            "speculators_config": speculators,
            "target_hidden_size": config.get("target_hidden_size"),
            "transformer_layer_config": transformer,
        },
        "derived": {
            "proposal_candidate_count": 7,
            "target_feature_width": 16384,
            "draft_layer_indices": [0, 1, 2, 3, 4],
        },
    }


class Acquisition:
    def __init__(self, attempt_id: str) -> None:
        if not re.fullmatch(
            r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", attempt_id
        ):
            raise ValueError(f"invalid D1A attempt id: {attempt_id}")
        self.attempt_id = attempt_id
        self.attempt_root = NVME_ROOT / "attempts" / attempt_id
        self.nvme_staging = (
            NVME_ROOT
            / f".staging-primary-{REVISION}-{attempt_id}"
        )
        self.hdfs_staging = (
            HDFS_DRAFT_PARENT / f".staging-{REVISION}-{attempt_id}"
        )
        self.hdfs_evidence = (
            HDFS_LANE_ROOT / "evidence" / "d1a" / attempt_id
        )
        self.repo_evidence = REPO_EVIDENCE_PARENT / attempt_id
        self.log_path = self.attempt_root / "download.log"
        self.heartbeat_path = self.attempt_root / "heartbeat.json"
        self.events_path = self.attempt_root / "download_events.jsonl"
        self.started_at = utc_now()
        self.current_stage = "initializing"
        self.current_path: pathlib.Path | None = None
        self.timebox: dict[str, Any] = {}
        self.provider: dict[str, Any] = {}
        self.keepalive_pid: int | None = None

    def log(self, message: str) -> None:
        line = f"{utc_now()} {message}"
        print(line, flush=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()

    def event(self, value: dict[str, Any]) -> None:
        value = {"timestamp_utc": utc_now(), **value}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
            handle.flush()

    def heartbeat(self, *, bytes_done: int | None = None) -> None:
        payload = {
            "schema_version": 1,
            "attempt_id": self.attempt_id,
            "worker_id": WORKER_ID,
            "hostname": socket.gethostname(),
            "stage": self.current_stage,
            "current_path": (
                str(self.current_path) if self.current_path is not None else None
            ),
            "current_path_bytes": (
                self.current_path.stat().st_size
                if self.current_path is not None and self.current_path.exists()
                else None
            ),
            "bytes_done": bytes_done,
            "keepalive_pid": self.keepalive_pid,
            "updated_at_utc": utc_now(),
        }
        write_json(self.heartbeat_path, payload)

    def require_timebox(self, *, implementation_phase: bool = True) -> None:
        now = datetime.now(timezone.utc)
        hard_stop = parse_utc(self.timebox["hard_stop_utc"])
        implementation_stop = parse_utc(
            self.timebox["implementation_stop_if_b0_incomplete_utc"]
        )
        if now >= hard_stop:
            raise RuntimeError("DFlash T+12h hard stop has been reached")
        if implementation_phase and now >= implementation_stop:
            raise RuntimeError(
                "DFlash T+9h implementation stop has been reached"
            )

    def verify_keepalive(self) -> int:
        if (KEEPALIVE_ROOT / "paused").exists():
            raise RuntimeError("DFlash keepalive is unexpectedly paused")
        raw_pid = (KEEPALIVE_ROOT / "supervisor.pid").read_text().strip()
        if not re.fullmatch(r"[1-9][0-9]*", raw_pid):
            raise RuntimeError("invalid registered keepalive PID")
        pid = int(raw_pid)
        proc = pathlib.Path("/proc") / str(pid)
        raw_argv = (proc / "cmdline").read_bytes()
        argv = [
            part.decode(errors="replace")
            for part in raw_argv.split(b"\0")
            if part
        ]
        required = [
            str(WORKTREE / "scripts" / "keepalive_load.py"),
            "load",
            "--expected-gpus",
            "8",
            "--matrix-size",
            "8192",
        ]
        if len(argv) != 7 or argv[1:] != required:
            raise RuntimeError(
                f"registered keepalive command mismatch for PID {pid}: {argv}"
            )
        pgid = os.getpgid(pid)
        sid = os.getsid(pid)
        if pgid != pid or sid != pid:
            raise RuntimeError("registered keepalive PID/PGID/SID mismatch")
        gate = json.loads(
            (KEEPALIVE_ROOT / "keepalive_gate.json").read_text()
        )
        means = gate.get("per_gpu_mean_utilization_percent") or {}
        if (
            gate.get("healthy") is not True
            or set(means) != {str(index) for index in range(8)}
            or any(float(value) < 40.0 for value in means.values())
        ):
            raise RuntimeError("registered keepalive utilization gate is not healthy")
        self.keepalive_pid = pid
        return pid

    def preflight(self) -> None:
        self.attempt_root.mkdir(parents=True, exist_ok=False)
        self.log("D1A preflight started; no model process will be launched")
        self.timebox = json.loads(TIMEBOX_PATH.read_text())
        lane = json.loads(LANE_IDENTITY_PATH.read_text())
        if lane.get("worker_id") != WORKER_ID:
            raise RuntimeError("lane identity worker mismatch")
        if lane.get("worktree") != str(WORKTREE):
            raise RuntimeError("lane identity worktree mismatch")
        if socket.gethostname() != EXPECTED_HOSTNAME:
            raise RuntimeError(
                f"unexpected hostname: {socket.gethostname()}"
            )
        self.require_timebox()

        query = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            text=True,
            capture_output=True,
            timeout=30,
        )
        actual_gpus = []
        for raw_line in query.stdout.splitlines():
            raw_index, raw_uuid, raw_name = raw_line.split(",", 2)
            actual_gpus.append(
                {
                    "index": int(raw_index.strip()),
                    "uuid": raw_uuid.strip(),
                    "name": raw_name.strip(),
                }
            )
        expected_uuids = json.loads(
            (TIMEBOX_PATH.parent / "keepalive_identity.json").read_text()
        )["physical_gpu_uuids"]
        if (
            len(actual_gpus) != EXPECTED_GPU_COUNT
            or [item["index"] for item in actual_gpus] != list(range(8))
            or any(item["name"] != "NVIDIA H20" for item in actual_gpus)
            or [item["uuid"] for item in actual_gpus] != expected_uuids
        ):
            raise RuntimeError(f"worker GPU identity mismatch: {actual_gpus}")
        pid = self.verify_keepalive()
        preflight = {
            "schema_version": 1,
            "attempt_id": self.attempt_id,
            "worker_id": WORKER_ID,
            "hostname": socket.gethostname(),
            "physical_gpus": actual_gpus,
            "keepalive_pid": pid,
            "keepalive_status": "HEALTHY",
            "keepalive_was_paused_or_stopped": False,
            "model_process_started": False,
            "timebox": self.timebox,
            "checked_at_utc": utc_now(),
        }
        write_json(self.attempt_root / "preflight.json", preflight)
        self.heartbeat()
        self.log(
            f"preflight PASS worker={WORKER_ID} gpus=8 "
            f"keepalive_pid={pid}"
        )

    def request_provider_metadata(self) -> None:
        self.current_stage = "provider_metadata"
        self.heartbeat()
        api_url = (
            "https://huggingface.co/api/models/"
            f"{REPO_ID}/revision/{REVISION}?blobs=true"
        )
        response: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, 6):
            self.require_timebox()
            self.verify_keepalive()
            request = urllib.request.Request(
                api_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as handle:
                    response = json.load(handle)
                break
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
                last_error = error
                self.log(
                    f"provider metadata attempt={attempt} failed: "
                    f"{type(error).__name__}: {error}"
                )
                if attempt < 5:
                    time.sleep(min(30, 2**attempt))
        if response is None:
            raise RuntimeError(
                f"provider metadata unavailable after retries: {last_error}"
            )
        write_json(self.attempt_root / "provider_response.json", response)
        if response.get("sha") != REVISION:
            raise RuntimeError(
                f"provider resolved sha {response.get('sha')} != {REVISION}"
            )
        if response.get("id") != REPO_ID:
            raise RuntimeError(
                f"provider repo id {response.get('id')} != {REPO_ID}"
            )

        siblings = response.get("siblings")
        if not isinstance(siblings, list):
            raise RuntimeError("provider response is missing siblings")
        files = []
        for sibling in siblings:
            if not isinstance(sibling, dict):
                raise RuntimeError("invalid provider sibling entry")
            path = safe_provider_path(str(sibling.get("rfilename", "")))
            size = sibling.get("size")
            lfs = sibling.get("lfs") or {}
            if size is None:
                size = lfs.get("size")
            if not isinstance(size, int) or size < 0:
                raise RuntimeError(
                    f"provider did not return an exact size for {path}: {size}"
                )
            if lfs.get("size") is not None and lfs.get("size") != size:
                raise RuntimeError(f"provider size/LFS size mismatch for {path}")
            files.append(
                {
                    "path": path,
                    "size_bytes": size,
                    "provider_oid": provider_oid(sibling),
                }
            )
        files.sort(key=lambda item: item["path"])
        paths = {item["path"] for item in files}
        if paths != EXPECTED_PROVIDER_FILES:
            raise RuntimeError(
                "pinned provider file set changed or API response is incomplete: "
                f"expected={sorted(EXPECTED_PROVIDER_FILES)} actual={sorted(paths)}"
            )
        weight = next(
            item for item in files if item["path"] == "model.safetensors"
        )
        if not weight["provider_oid"].get("lfs_sha256"):
            raise RuntimeError("provider did not expose weight SHA-256/OID")
        self.provider = {
            "schema_version": 1,
            "provider": "huggingface",
            "repo_id": REPO_ID,
            "requested_revision": REVISION,
            "resolved_revision": response["sha"],
            "api_url": api_url,
            "provider_commit_verified": True,
            "file_count": len(files),
            "total_size_bytes": sum(item["size_bytes"] for item in files),
            "files": files,
            "manifest_sha256": canonical_json_sha256(files),
            "retrieved_at_utc": utc_now(),
            "full_payload_sha256_policy": (
                "not recomputed: no corruption evidence; provider OID, exact "
                "file set/size, safetensors header, and copy validation used"
            ),
        }
        write_json(
            self.attempt_root / "provider_metadata.json", self.provider
        )
        self.log(
            f"provider identity PASS revision={REVISION} "
            f"files={len(files)} bytes={self.provider['total_size_bytes']} "
            f"manifest_sha256={self.provider['manifest_sha256']}"
        )

    def capacity_gate(self) -> None:
        total = int(self.provider["total_size_bytes"])
        reserve = 2 * 1024 * 1024 * 1024
        NVME_ROOT.mkdir(parents=True, exist_ok=True)
        HDFS_DRAFT_PARENT.mkdir(parents=True, exist_ok=True)
        nvme_usage = shutil.disk_usage(NVME_ROOT)
        hdfs_usage = shutil.disk_usage(HDFS_DRAFT_PARENT)
        capacity = {
            "schema_version": 1,
            "required_payload_bytes": total,
            "required_reserve_bytes": reserve,
            "nvme": {
                "path": str(NVME_ROOT),
                "total_bytes": nvme_usage.total,
                "used_bytes": nvme_usage.used,
                "free_bytes": nvme_usage.free,
                "passed": nvme_usage.free >= total + reserve,
            },
            "hdfs": {
                "path": str(HDFS_DRAFT_PARENT),
                "total_bytes": hdfs_usage.total,
                "used_bytes": hdfs_usage.used,
                "free_bytes": hdfs_usage.free,
                "passed": hdfs_usage.free >= total + reserve,
            },
            "checked_at_utc": utc_now(),
        }
        write_json(self.attempt_root / "capacity.json", capacity)
        if not capacity["nvme"]["passed"] or not capacity["hdfs"]["passed"]:
            raise RuntimeError(f"capacity gate failed: {capacity}")
        if self.nvme_staging.exists():
            raise FileExistsError(
                f"unique NVMe staging already exists: {self.nvme_staging}"
            )
        if self.hdfs_staging.exists():
            raise FileExistsError(
                f"unique HDFS staging already exists: {self.hdfs_staging}"
            )
        if HDFS_FORMAL.exists():
            raise FileExistsError(
                f"formal draft path already exists; overwrite refused: {HDFS_FORMAL}"
            )
        if HDFS_POINTER.exists():
            raise FileExistsError(
                f"draft pointer already exists; overwrite refused: {HDFS_POINTER}"
            )
        self.log(
            f"capacity PASS nvme_free={nvme_usage.free} "
            f"hdfs_free={hdfs_usage.free}"
        )

    def run_curl(self, url: str, partial: pathlib.Path, expected: int) -> None:
        command = [
            "curl",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "8",
            "--retry-all-errors",
            "--retry-delay",
            "5",
            "--connect-timeout",
            "30",
            "--speed-limit",
            "1024",
            "--speed-time",
            "300",
            "--max-time",
            "7200",
            "--continue-at",
            "-",
            "--output",
            str(partial),
            "--write-out",
            (
                '{"http_code":%{http_code},"size_download":%{size_download},'
                '"speed_download":%{speed_download},"time_total":%{time_total},'
                '"content_type":"%{content_type}"}'
            ),
            "--user-agent",
            USER_AGENT,
            url,
        ]
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        last_heartbeat = 0.0
        try:
            while process.poll() is None:
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    self.require_timebox()
                    self.verify_keepalive()
                    self.heartbeat()
                    last_heartbeat = now
                time.sleep(2)
            stdout, stderr = process.communicate(timeout=30)
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=30)
            raise
        duration = time.monotonic() - started
        event = {
            "event": "curl_complete",
            "path": str(partial),
            "expected_size_bytes": expected,
            "actual_size_bytes": (
                partial.stat().st_size if partial.exists() else None
            ),
            "returncode": process.returncode,
            "duration_seconds": duration,
            "curl_stdout": stdout.strip(),
            "curl_stderr": stderr.strip(),
        }
        self.event(event)
        if process.returncode != 0:
            raise RuntimeError(
                f"curl failed rc={process.returncode}: {stderr.strip()}"
            )

    def download(self) -> None:
        self.current_stage = "nvme_download"
        self.nvme_staging.mkdir(parents=True, exist_ok=False)
        self.log(f"created unique NVMe staging {self.nvme_staging}")
        for entry in self.provider["files"]:
            self.require_timebox()
            self.verify_keepalive()
            relative = entry["path"]
            destination = self.nvme_staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_name(destination.name + ".partial")
            self.current_path = partial
            self.heartbeat()
            encoded = "/".join(
                urllib.parse.quote(part, safe="")
                for part in pathlib.PurePosixPath(relative).parts
            )
            url = (
                f"https://huggingface.co/{REPO_ID}/resolve/"
                f"{REVISION}/{encoded}?download=true"
            )
            self.log(
                f"download start path={relative} "
                f"expected_bytes={entry['size_bytes']}"
            )
            self.run_curl(url, partial, int(entry["size_bytes"]))
            actual = partial.stat().st_size
            if actual != entry["size_bytes"]:
                raise RuntimeError(
                    f"download size mismatch {relative}: "
                    f"expected={entry['size_bytes']} actual={actual}"
                )
            os.rename(partial, destination)
            self.current_path = destination
            self.heartbeat()
            self.log(f"download PASS path={relative} bytes={actual}")
        self.current_path = None

    def validate_payload(
        self, root: pathlib.Path, *, location: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        self.current_stage = f"{location}_validation"
        self.heartbeat()
        actual = relative_regular_files(root)
        expected = {
            entry["path"]: entry for entry in self.provider["files"]
        }
        if set(actual) != set(expected):
            raise RuntimeError(
                f"{location} file set mismatch expected={sorted(expected)} "
                f"actual={sorted(actual)}"
            )
        records = []
        for relative in sorted(actual):
            path = actual[relative]
            stat = path.stat()
            entry = expected[relative]
            if stat.st_size != entry["size_bytes"]:
                raise RuntimeError(
                    f"{location} size mismatch {relative}: "
                    f"{stat.st_size} != {entry['size_bytes']}"
                )
            record = {
                "path": relative,
                "size_bytes": stat.st_size,
                "is_regular_file": path.is_file(),
                "is_symlink": path.is_symlink(),
                "link_count": stat.st_nlink,
                "device": stat.st_dev,
                "inode": stat.st_ino,
                "provider_oid": entry["provider_oid"],
            }
            if stat.st_size <= SMALL_HASH_LIMIT_BYTES:
                record["local_sha256"] = sha256_file(path)
                record["local_git_blob_sha1"] = git_blob_sha1(path)
                provider_blob = entry["provider_oid"].get("git_blob_id")
                record["provider_git_blob_match"] = (
                    provider_blob == record["local_git_blob_sha1"]
                )
                if provider_blob and not record["provider_git_blob_match"]:
                    raise RuntimeError(
                        f"{location} provider Git blob mismatch: {relative}"
                    )
            else:
                record["local_full_sha256"] = None
                record["full_sha256_omission_reason"] = (
                    "no corruption evidence; provider SHA-256/OID retained "
                    "and exact size/header validated"
                )
            records.append(record)
        total = sum(item["size_bytes"] for item in records)
        if total != self.provider["total_size_bytes"]:
            raise RuntimeError(f"{location} total payload size mismatch")

        config = config_summary(root / "config.json")
        header = parse_safetensors_header(root / "model.safetensors")
        manifest = {
            "schema_version": 1,
            "attempt_id": self.attempt_id,
            "location": location,
            "path": str(root),
            "repo_id": REPO_ID,
            "revision": REVISION,
            "provider_manifest_sha256": self.provider["manifest_sha256"],
            "file_count": len(records),
            "total_size_bytes": total,
            "file_set_matches_provider": True,
            "all_sizes_match_provider": True,
            "contains_symlinks": False,
            "files": records,
            "config_summary_sha256": canonical_json_sha256(config),
            "safetensors_header_summary_sha256": canonical_json_sha256(header),
            "validated_at_utc": utc_now(),
        }
        return manifest, config, header

    def validate_nvme(self) -> None:
        manifest, config, header = self.validate_payload(
            self.nvme_staging, location="nvme"
        )
        write_json(self.attempt_root / "nvme_manifest.json", manifest)
        write_json(self.attempt_root / "config_summary.json", config)
        write_json(
            self.attempt_root / "safetensors_header_summary.json", header
        )
        self.log(
            "NVMe validation PASS "
            f"files={manifest['file_count']} "
            f"bytes={manifest['total_size_bytes']} "
            f"tensors={header['tensor_count']}"
        )

    def copy_file(self, source: pathlib.Path, destination: pathlib.Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        copied = 0
        last_heartbeat = time.monotonic()
        with source.open("rb") as read_handle, destination.open("xb") as write_handle:
            while block := read_handle.read(COPY_CHUNK_BYTES):
                write_handle.write(block)
                copied += len(block)
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    self.require_timebox()
                    self.verify_keepalive()
                    self.heartbeat(bytes_done=copied)
                    last_heartbeat = now
            write_handle.flush()
            with contextlib.suppress(OSError):
                os.fsync(write_handle.fileno())
        if copied != source.stat().st_size:
            raise RuntimeError(
                f"copy byte count mismatch {source}: "
                f"{copied} != {source.stat().st_size}"
            )

    def copy_to_hdfs(self) -> None:
        self.current_stage = "hdfs_copy"
        self.hdfs_staging.mkdir(parents=True, exist_ok=False)
        self.log(f"created unique HDFS staging {self.hdfs_staging}")
        for entry in self.provider["files"]:
            relative = entry["path"]
            source = self.nvme_staging / relative
            destination = self.hdfs_staging / relative
            self.current_path = destination
            self.heartbeat(bytes_done=0)
            self.log(
                f"HDFS copy start path={relative} bytes={entry['size_bytes']}"
            )
            self.copy_file(source, destination)
            self.log(
                f"HDFS copy complete path={relative} "
                f"bytes={destination.stat().st_size}"
            )
        self.current_path = None

    def validate_hdfs(self) -> dict[str, Any]:
        manifest, config, header = self.validate_payload(
            self.hdfs_staging, location="hdfs_staging"
        )
        source_manifest = json.loads(
            (self.attempt_root / "nvme_manifest.json").read_text()
        )
        source_records = {
            entry["path"]: entry for entry in source_manifest["files"]
        }
        independent = []
        for entry in manifest["files"]:
            source = source_records[entry["path"]]
            same_identity = (
                source["device"] == entry["device"]
                and source["inode"] == entry["inode"]
            )
            if same_identity:
                raise RuntimeError(
                    f"HDFS payload is not an independent entity: {entry['path']}"
                )
            item = {
                "path": entry["path"],
                "source_device": source["device"],
                "source_inode": source["inode"],
                "destination_device": entry["device"],
                "destination_inode": entry["inode"],
                "different_file_identity": True,
                "size_match": source["size_bytes"] == entry["size_bytes"],
            }
            if "local_sha256" in source:
                item["small_file_sha256_match"] = (
                    source["local_sha256"] == entry.get("local_sha256")
                )
                if not item["small_file_sha256_match"]:
                    raise RuntimeError(
                        f"HDFS small-file hash mismatch: {entry['path']}"
                    )
            independent.append(item)
        nvme_header = json.loads(
            (
                self.attempt_root / "safetensors_header_summary.json"
            ).read_text()
        )
        if (
            header["header_sha256"] != nvme_header["header_sha256"]
            or header["tensor_count"] != nvme_header["tensor_count"]
            or header["file_size_bytes"] != nvme_header["file_size_bytes"]
        ):
            raise RuntimeError("HDFS safetensors header/size mismatch")
        config_source = json.loads(
            (self.attempt_root / "config_summary.json").read_text()
        )
        if config != config_source:
            raise RuntimeError("HDFS config summary mismatch")
        manifest["independent_entity_checks"] = independent
        manifest["all_payload_files_are_independent_entities"] = True
        manifest["small_file_hashes_match_nvme"] = True
        manifest["safetensors_header_matches_nvme"] = True
        manifest["full_weight_sha256_recomputed"] = False
        manifest["full_weight_sha256_omission_reason"] = (
            "no transfer corruption evidence; exact provider/NVMe/HDFS size, "
            "independent streaming copy, and matching safetensors header used"
        )
        write_json(self.attempt_root / "hdfs_validation.json", manifest)
        self.log(
            "HDFS staging validation PASS "
            f"files={manifest['file_count']} "
            f"bytes={manifest['total_size_bytes']}"
        )
        return manifest

    def publish(self, hdfs_manifest: dict[str, Any]) -> None:
        self.current_stage = "atomic_publication"
        self.require_timebox()
        self.verify_keepalive()
        nvme_manifest = json.loads(
            (self.attempt_root / "nvme_manifest.json").read_text()
        )
        config = json.loads(
            (self.attempt_root / "config_summary.json").read_text()
        )
        header = json.loads(
            (
                self.attempt_root / "safetensors_header_summary.json"
            ).read_text()
        )
        complete = {
            "schema_version": 1,
            "status": "COMPLETE",
            "lane": "dflash",
            "phase": "D1A",
            "attempt_id": self.attempt_id,
            "provider": "huggingface",
            "repo_id": REPO_ID,
            "revision": REVISION,
            "formal_path": str(HDFS_FORMAL),
            "file_count": hdfs_manifest["file_count"],
            "total_size_bytes": hdfs_manifest["total_size_bytes"],
            "provider_manifest_sha256": self.provider["manifest_sha256"],
            "nvme_manifest_sha256": canonical_json_sha256(nvme_manifest),
            "hdfs_validation_sha256": canonical_json_sha256(hdfs_manifest),
            "config_summary_sha256": canonical_json_sha256(config),
            "safetensors_header_summary_sha256": canonical_json_sha256(header),
            "full_weight_sha256_recomputed": False,
            "publication_semantics": (
                "marker written and read back in unique same-parent HDFS "
                "staging before atomic directory rename"
            ),
            "published_at_utc": utc_now(),
        }
        complete_path = self.hdfs_staging / ".complete"
        write_json(complete_path, complete)
        if json.loads(complete_path.read_text()) != complete:
            raise RuntimeError("HDFS .complete readback mismatch")
        if HDFS_FORMAL.exists():
            raise FileExistsError(
                f"formal path appeared before publication: {HDFS_FORMAL}"
            )
        os.rename(self.hdfs_staging, HDFS_FORMAL)
        if self.hdfs_staging.exists() or not HDFS_FORMAL.is_dir():
            raise RuntimeError("atomic HDFS staging-to-formal rename failed")
        final_files = relative_regular_files(HDFS_FORMAL)
        if set(final_files) != EXPECTED_PROVIDER_FILES | {".complete"}:
            raise RuntimeError("formal HDFS file set mismatch after publication")
        if json.loads((HDFS_FORMAL / ".complete").read_text()) != complete:
            raise RuntimeError("formal HDFS .complete mismatch after rename")

        pointer = {
            "schema_version": 1,
            "status": "COMPLETE",
            "lane": "dflash",
            "phase": "D1A",
            "provider": "huggingface",
            "repo_id": REPO_ID,
            "revision": REVISION,
            "formal_path": str(HDFS_FORMAL),
            "complete_path": str(HDFS_FORMAL / ".complete"),
            "provider_manifest_sha256": self.provider["manifest_sha256"],
            "file_count": self.provider["file_count"],
            "total_size_bytes": self.provider["total_size_bytes"],
            "attempt_id": self.attempt_id,
            "published_at_utc": complete["published_at_utc"],
        }
        HDFS_POINTER.parent.mkdir(parents=True, exist_ok=True)
        temporary_pointer = HDFS_POINTER.with_name(
            f".draft_pointer.staging-{self.attempt_id}.json"
        )
        if HDFS_POINTER.exists() or temporary_pointer.exists():
            raise FileExistsError("draft pointer path already exists")
        write_json(temporary_pointer, pointer)
        os.rename(temporary_pointer, HDFS_POINTER)
        if json.loads(HDFS_POINTER.read_text()) != pointer:
            raise RuntimeError("draft pointer readback mismatch")
        write_json(self.attempt_root / "draft_pointer.json", pointer)
        publication = {
            "schema_version": 1,
            "attempt_id": self.attempt_id,
            "formal_path": str(HDFS_FORMAL),
            "complete_path": str(HDFS_FORMAL / ".complete"),
            "draft_pointer_path": str(HDFS_POINTER),
            "staging_absent_after_atomic_rename": not self.hdfs_staging.exists(),
            "formal_directory_present": HDFS_FORMAL.is_dir(),
            "complete_marker_present": (HDFS_FORMAL / ".complete").is_file(),
            "pointer_present": HDFS_POINTER.is_file(),
            "formal_file_set": sorted(final_files),
            "published_at_utc": complete["published_at_utc"],
            "validated_at_utc": utc_now(),
        }
        write_json(self.attempt_root / "complete_marker.json", complete)
        write_json(self.attempt_root / "publication.json", publication)
        self.log(
            f"atomic publication PASS formal={HDFS_FORMAL} "
            f"pointer={HDFS_POINTER}"
        )

    def export_evidence(self) -> None:
        self.current_stage = "evidence_export"
        self.heartbeat()
        names = {
            "capacity.json",
            "complete_marker.json",
            "config_summary.json",
            "download.log",
            "download_events.jsonl",
            "draft_pointer.json",
            "heartbeat.json",
            "hdfs_validation.json",
            "nvme_manifest.json",
            "preflight.json",
            "provider_metadata.json",
            "provider_response.json",
            "publication.json",
            "safetensors_header_summary.json",
            "summary.json",
        }
        missing = sorted(
            name for name in names if not (self.attempt_root / name).is_file()
        )
        if missing:
            raise RuntimeError(f"evidence export inputs missing: {missing}")

        hdfs_parent = self.hdfs_evidence.parent
        hdfs_parent.mkdir(parents=True, exist_ok=True)
        hdfs_staging = hdfs_parent / f".staging-{self.attempt_id}"
        if hdfs_staging.exists() or self.hdfs_evidence.exists():
            raise FileExistsError("HDFS evidence target already exists")
        hdfs_staging.mkdir(parents=False)
        for name in sorted(names):
            shutil.copyfile(
                self.attempt_root / name, hdfs_staging / name
            )
        os.rename(hdfs_staging, self.hdfs_evidence)

        REPO_EVIDENCE_PARENT.mkdir(parents=True, exist_ok=True)
        repo_staging = REPO_EVIDENCE_PARENT / f".staging-{self.attempt_id}"
        if repo_staging.exists() or self.repo_evidence.exists():
            raise FileExistsError("repo evidence target already exists")
        repo_staging.mkdir(parents=False)
        for name in sorted(names):
            shutil.copyfile(
                self.attempt_root / name, repo_staging / name
            )
        os.rename(repo_staging, self.repo_evidence)
        self.log(
            f"evidence export PASS hdfs={self.hdfs_evidence} "
            f"repo={self.repo_evidence}"
        )

    def success_summary(self) -> None:
        self.current_stage = "complete"
        self.verify_keepalive()
        summary = {
            "schema_version": 1,
            "status": "PASS",
            "phase": "D1A",
            "attempt_id": self.attempt_id,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "provider_file_count": self.provider["file_count"],
            "provider_total_size_bytes": self.provider["total_size_bytes"],
            "provider_manifest_sha256": self.provider["manifest_sha256"],
            "nvme_staging": str(self.nvme_staging),
            "hdfs_formal": str(HDFS_FORMAL),
            "hdfs_complete": str(HDFS_FORMAL / ".complete"),
            "draft_pointer": str(HDFS_POINTER),
            "keepalive_pid": self.keepalive_pid,
            "keepalive_status": "HEALTHY",
            "keepalive_was_paused_or_stopped": False,
            "model_process_started": False,
            "fallback_enabled": False,
            "full_weight_sha256_recomputed": False,
            "started_at_utc": self.started_at,
            "completed_at_utc": utc_now(),
            "exit_gates": {
                "exact_revision": "PASS",
                "provider_identity_and_oid": "PASS",
                "nvme_file_set_and_size": "PASS",
                "config_contract": "PASS",
                "safetensors_header_and_shapes": "PASS",
                "independent_hdfs_copy": "PASS",
                "hdfs_file_set_and_size": "PASS",
                "atomic_formal_and_complete_publication": "PASS",
                "draft_pointer": "PASS",
                "keepalive_continuity": "PASS",
            },
        }
        write_json(self.attempt_root / "summary.json", summary)
        self.heartbeat()
        self.log("D1A PASS")

    def failure_summary(self, error: BaseException) -> None:
        self.current_stage = "failed"
        failure = {
            "schema_version": 1,
            "status": "FAIL",
            "phase": "D1A",
            "attempt_id": self.attempt_id,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
            "nvme_staging": str(self.nvme_staging),
            "hdfs_staging": str(self.hdfs_staging),
            "hdfs_formal": str(HDFS_FORMAL),
            "draft_pointer": str(HDFS_POINTER),
            "fallback_enabled": False,
            "checkpoint_specific_failure_proven": False,
            "keepalive_was_paused_or_stopped": False,
            "model_process_started": False,
            "started_at_utc": self.started_at,
            "failed_at_utc": utc_now(),
        }
        with contextlib.suppress(Exception):
            write_json(self.attempt_root / "error.json", failure)
            write_json(self.attempt_root / "summary.json", failure)
            self.heartbeat()
            self.log(
                f"D1A FAIL {type(error).__name__}: {error}; "
                "all staging retained and fallback remains disabled"
            )

    def run(self) -> None:
        self.preflight()
        self.request_provider_metadata()
        self.capacity_gate()
        self.download()
        self.validate_nvme()
        self.copy_to_hdfs()
        hdfs_manifest = self.validate_hdfs()
        self.publish(hdfs_manifest)
        self.success_summary()
        self.export_evidence()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args()
    acquisition: Acquisition | None = None
    try:
        acquisition = Acquisition(args.attempt_id)
        acquisition.run()
        return 0
    except BaseException as error:
        if acquisition is not None:
            acquisition.failure_summary(error)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
