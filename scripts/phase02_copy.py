#!/usr/bin/env python3
"""Create and validate the Phase 02 DeepSpec-owned checkpoint copy.

The source manifest is the authority for the 75 provider payload files.  This
program intentionally copies bytes through userspace; it never creates links,
reflinks, or cache references.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import threading
import time
import traceback
from typing import Any


BUFFER_BYTES = 16 * 1024 * 1024
COPY_WORKERS = 4
PROGRESS_INTERVAL_SECONDS = 30
WORKER_LIST_INTERVAL_SECONDS = 60
KEEPALIVE_INTERVAL_SECONDS = 600
EXPECTED_FILES = 75
EXPECTED_SHARDS = 48
EXPECTED_BYTES = 166_898_666_759
EXPECTED_SNAPSHOT_ID = (
    "bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "186d562ff6b1ebda2051cd12725acf5d230ed55a078106de95137630434806e9"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=BUFFER_BYTES) as handle:
        while chunk := handle.read(BUFFER_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: pathlib.Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(payload)
    os.replace(temporary, path)


def write_json(path: pathlib.Path, payload: Any) -> None:
    write_atomic(path, json_bytes(payload))


def file_record(path: pathlib.Path, relative: str) -> dict[str, Any]:
    metadata = path.lstat()
    return {
        "path": relative,
        "size_bytes": metadata.st_size,
        "mode": stat.S_IMODE(metadata.st_mode),
        "mtime_ns": metadata.st_mtime_ns,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "is_regular": stat.S_ISREG(metadata.st_mode),
        "is_symlink": stat.S_ISLNK(metadata.st_mode),
    }


def disk_record(path: pathlib.Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


class Phase02:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.source = pathlib.Path(args.source)
        self.source_manifest_path = pathlib.Path(args.source_manifest)
        self.staging = pathlib.Path(args.staging)
        self.formal = pathlib.Path(args.formal)
        self.run_dir = pathlib.Path(args.run_dir)
        self.scratch = pathlib.Path(args.scratch)
        self.copy_log = self.scratch / "copy.log"
        self.progress_path = self.scratch / "progress.json"
        self.worker_monitor_path = self.scratch / "worker_monitor.json"
        self.stop_monitor = threading.Event()
        self.abort_copy = threading.Event()
        self.progress_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.monitor_lock = threading.Lock()
        self.bytes_copied = 0
        self.files_copied = 0
        self.copy_started_monotonic = 0.0
        self.copy_results: list[dict[str, Any]] = []
        self.worker_checks: list[dict[str, Any]] = []
        self.monitor_errors: list[str] = []
        self.published = False
        self.provider_records: list[dict[str, Any]] = []
        self.source_before: list[dict[str, Any]] = []
        self.source_after: list[dict[str, Any]] = []

    def log(self, message: str) -> None:
        line = f"{utc_now()} {message}"
        with self.log_lock:
            with self.copy_log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        try:
            print(line, flush=True)
        except BrokenPipeError:
            pass

    def run_command(
        self, command: list[str], timeout: int
    ) -> tuple[int, str, str]:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    def check_worker(self, full_keepalive: bool) -> dict[str, Any]:
        check: dict[str, Any] = {
            "checked_at_utc": utc_now(),
            "full_keepalive_check": full_keepalive,
            "worker_id": self.args.worker_id,
        }
        try:
            rc, stdout, stderr = self.run_command(["mlx", "worker", "list"], 90)
            matching = [
                line
                for line in stdout.splitlines()
                if re.match(rf"^{re.escape(self.args.worker_id)}\s+", line)
            ]
            fields = matching[0].split() if len(matching) == 1 else []
            inventory_ok = (
                rc == 0
                and len(matching) == 1
                and len(fields) >= 5
                and fields[3] == "4"
                and fields[4] == "NVIDIA-H20"
            )
            check.update(
                {
                    "worker_list_returncode": rc,
                    "worker_list_matching_lines": matching,
                    "worker_inventory_ok": inventory_ok,
                    "worker_list_stderr": stderr,
                }
            )
            if not inventory_ok:
                raise RuntimeError("4xH20 worker is absent or changed")

            if full_keepalive:
                command = [
                    "mlx",
                    "worker",
                    "login",
                    self.args.worker_id,
                    "--",
                    "bash",
                    self.args.keepalive_script,
                    "status",
                    self.args.worker_id,
                ]
                rc, stdout, stderr = self.run_command(command, 180)
                report = None
                for line in stdout.splitlines():
                    if line.startswith("{") and '"healthy"' in line:
                        report = json.loads(line)
                keepalive_ok = (
                    rc == 0
                    and "HEALTHY on " in stdout
                    and isinstance(report, dict)
                    and report.get("healthy") is True
                    and report.get("expected_gpus") == 4
                    and report.get("sample_count") == 10
                    and not report.get("underutilized_gpus")
                    and all(
                        item.get("mean_utilization", 0) >= 40
                        for item in report.get("per_gpu", {}).values()
                    )
                    and len(report.get("per_gpu", {})) == 4
                )
                check.update(
                    {
                        "keepalive_returncode": rc,
                        "keepalive_stdout": stdout,
                        "keepalive_stderr": stderr,
                        "keepalive_report": report,
                        "keepalive_ok": keepalive_ok,
                    }
                )
                if not keepalive_ok:
                    raise RuntimeError("remote keepalive 10x1s gate failed")
            check["status"] = "PASS"
        except Exception as error:
            check["status"] = "FAIL"
            check["error"] = f"{type(error).__name__}: {error}"
            with self.monitor_lock:
                self.monitor_errors.append(check["error"])
            self.abort_copy.set()
        finally:
            with self.monitor_lock:
                self.worker_checks.append(check)
                write_json(
                    self.worker_monitor_path,
                    {
                        "schema_version": 1,
                        "attempt_id": self.args.attempt_id,
                        "worker_id": self.args.worker_id,
                        "checks": self.worker_checks,
                        "errors": self.monitor_errors,
                        "status": (
                            "PASS" if not self.monitor_errors else "FAIL"
                        ),
                    },
                )
        return check

    def worker_monitor_loop(self) -> None:
        next_keepalive = time.monotonic() + KEEPALIVE_INTERVAL_SECONDS
        while not self.stop_monitor.wait(WORKER_LIST_INTERVAL_SECONDS):
            full = time.monotonic() >= next_keepalive
            check = self.check_worker(full)
            self.log(
                "WORKER_HEARTBEAT "
                f"status={check['status']} full_keepalive={full}"
            )
            if full:
                next_keepalive = time.monotonic() + KEEPALIVE_INTERVAL_SECONDS
            if check["status"] != "PASS":
                return

    def load_manifest(self) -> dict[str, Any]:
        actual_sha = sha256_file(self.source_manifest_path)
        if actual_sha != EXPECTED_SOURCE_MANIFEST_SHA256:
            raise RuntimeError(
                f"source manifest hash mismatch: {actual_sha}"
            )
        manifest = json.loads(self.source_manifest_path.read_text())
        if manifest.get("source_path") != str(self.source):
            raise RuntimeError("source path differs from Phase 01 manifest")
        verification = manifest["modelscope_verification"]
        records = [
            {
                "path": item["path"],
                "size_bytes": item["expected_size_bytes"],
                "sha256": item["expected_sha256"],
            }
            for item in verification["files"]
        ]
        records.sort(key=lambda item: item["path"])
        if len(records) != EXPECTED_FILES:
            raise RuntimeError(f"provider file count is {len(records)}")
        if sum(item["size_bytes"] for item in records) != EXPECTED_BYTES:
            raise RuntimeError("provider payload byte count mismatch")
        if canonical_sha256(records) != EXPECTED_SNAPSHOT_ID:
            raise RuntimeError("provider payload snapshot ID mismatch")
        if any(item["path"] == ".complete" for item in records):
            raise RuntimeError("source .complete unexpectedly in payload")
        self.provider_records = records
        return manifest

    def stat_source(self) -> list[dict[str, Any]]:
        records = []
        for expected in self.provider_records:
            path = self.source / expected["path"]
            observed = file_record(path, expected["path"])
            if not observed["is_regular"] or observed["is_symlink"]:
                raise RuntimeError(
                    f"source payload is not a regular entity: {expected['path']}"
                )
            if observed["size_bytes"] != expected["size_bytes"]:
                raise RuntimeError(
                    f"source size changed: {expected['path']}"
                )
            records.append(observed)
        return records

    def write_progress(self, status: str) -> None:
        with self.progress_lock:
            elapsed = max(
                time.monotonic() - self.copy_started_monotonic, 0.001
            )
            rate = self.bytes_copied / elapsed
            remaining = max(EXPECTED_BYTES - self.bytes_copied, 0)
            payload = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "status": status,
                "updated_at_utc": utc_now(),
                "bytes_copied": self.bytes_copied,
                "expected_bytes": EXPECTED_BYTES,
                "files_completed": self.files_copied,
                "expected_files": EXPECTED_FILES,
                "throughput_bytes_per_second": rate,
                "eta_seconds": remaining / rate if rate > 0 else None,
            }
        write_json(self.progress_path, payload)

    def progress_loop(self) -> None:
        while not self.stop_monitor.wait(PROGRESS_INTERVAL_SECONDS):
            self.write_progress("copying")
            progress = json.loads(self.progress_path.read_text())
            self.log(
                "COPY_PROGRESS "
                f"bytes={progress['bytes_copied']}/{EXPECTED_BYTES} "
                f"files={progress['files_completed']}/{EXPECTED_FILES} "
                f"throughput_Bps={progress['throughput_bytes_per_second']:.0f} "
                f"eta_s={progress['eta_seconds']:.0f}"
            )

    def copy_one(self, expected: dict[str, Any]) -> dict[str, Any]:
        if self.abort_copy.is_set():
            raise RuntimeError("copy aborted by worker watchdog")
        relative = expected["path"]
        source = self.source / relative
        destination = self.staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.phase02-part-{self.args.attempt_id}"
        )
        if destination.exists() or temporary.exists():
            raise FileExistsError(
                f"unexpected pre-existing destination path: {relative}"
            )
        started = time.monotonic()
        bytes_written = 0
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o640,
        )
        try:
            with source.open("rb", buffering=BUFFER_BYTES) as reader:
                with os.fdopen(
                    descriptor, "wb", buffering=BUFFER_BYTES
                ) as writer:
                    descriptor = -1
                    while chunk := reader.read(BUFFER_BYTES):
                        if self.abort_copy.is_set():
                            raise RuntimeError(
                                "copy aborted by worker watchdog"
                            )
                        writer.write(chunk)
                        bytes_written += len(chunk)
                        with self.progress_lock:
                            self.bytes_copied += len(chunk)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if bytes_written != expected["size_bytes"]:
            raise RuntimeError(
                f"copy byte count mismatch for {relative}: {bytes_written}"
            )
        if temporary.stat().st_size != expected["size_bytes"]:
            raise RuntimeError(f"staging size mismatch for {relative}")
        os.replace(temporary, destination)
        result = {
            "path": relative,
            "size_bytes": bytes_written,
            "elapsed_seconds": time.monotonic() - started,
            "method": "python-buffered-userspace-read-write",
            "temporary_then_atomic_rename": True,
        }
        with self.progress_lock:
            self.files_copied += 1
            self.copy_results.append(result)
        return result

    def copy_payload(self) -> None:
        order = sorted(
            self.provider_records,
            key=lambda item: item["size_bytes"],
            reverse=True,
        )
        self.copy_started_monotonic = time.monotonic()
        self.write_progress("copying")
        progress_thread = threading.Thread(
            target=self.progress_loop,
            name="phase02-progress",
            daemon=True,
        )
        progress_thread.start()
        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=COPY_WORKERS
            ) as executor:
                futures = {
                    executor.submit(self.copy_one, item): item["path"]
                    for item in order
                }
                for future in concurrent.futures.as_completed(futures):
                    relative = futures[future]
                    result = future.result()
                    self.log(
                        "COPY_FILE_DONE "
                        f"path={relative} bytes={result['size_bytes']} "
                        f"elapsed_s={result['elapsed_seconds']:.3f}"
                    )
        finally:
            self.write_progress(
                "copied"
                if (
                    self.bytes_copied == EXPECTED_BYTES
                    and self.files_copied == EXPECTED_FILES
                )
                else "incomplete"
            )
        if self.abort_copy.is_set():
            raise RuntimeError("copy aborted because worker watchdog failed")
        if (
            self.bytes_copied != EXPECTED_BYTES
            or self.files_copied != EXPECTED_FILES
        ):
            raise RuntimeError("aggregate copy count mismatch")

    def hash_one_target(
        self, expected: dict[str, Any]
    ) -> dict[str, Any]:
        path = self.staging / expected["path"]
        observed = file_record(path, expected["path"])
        actual_sha = sha256_file(path)
        return {
            **observed,
            "sha256": actual_sha,
            "expected_size_bytes": expected["size_bytes"],
            "expected_sha256": expected["sha256"],
            "size_match": observed["size_bytes"] == expected["size_bytes"],
            "sha256_match": actual_sha == expected["sha256"],
        }

    def validate_target(self) -> dict[str, Any]:
        expected_paths = {item["path"] for item in self.provider_records}
        observed_paths: set[str] = set()
        symlinks: list[str] = []
        for candidate in self.staging.rglob("*"):
            relative = candidate.relative_to(self.staging).as_posix()
            if candidate.is_symlink():
                symlinks.append(relative)
            elif candidate.is_file():
                observed_paths.add(relative)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=COPY_WORKERS
        ) as executor:
            records = list(executor.map(self.hash_one_target, self.provider_records))
        records.sort(key=lambda item: item["path"])
        snapshot_records = [
            {
                "path": item["path"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in records
        ]
        actual_shards = sorted(
            path
            for path in observed_paths
            if re.fullmatch(r"model-\d{5}-of-00048\.safetensors", path)
        )
        index = json.loads(
            (self.staging / "model.safetensors.index.json").read_text()
        )
        index_shards = sorted(set(index["weight_map"].values()))
        config = json.loads((self.staging / "config.json").read_text())
        entity_records = []
        for expected in self.provider_records:
            source_stat = (self.source / expected["path"]).stat()
            target_stat = (self.staging / expected["path"]).stat()
            entity_records.append(
                {
                    "path": expected["path"],
                    "source_device": source_stat.st_dev,
                    "source_inode": source_stat.st_ino,
                    "target_device": target_stat.st_dev,
                    "target_inode": target_stat.st_ino,
                    "same_device_and_inode": (
                        source_stat.st_dev == target_stat.st_dev
                        and source_stat.st_ino == target_stat.st_ino
                    ),
                    "os_path_samefile": os.path.samefile(
                        self.source / expected["path"],
                        self.staging / expected["path"],
                    ),
                }
            )
        errors = []
        if observed_paths != expected_paths:
            errors.append("target file set differs from provider manifest")
        if symlinks:
            errors.append("target contains symlinks")
        if any(
            not item["is_regular"]
            or item["is_symlink"]
            or not item["size_match"]
            or not item["sha256_match"]
            for item in records
        ):
            errors.append("one or more target payload files failed validation")
        snapshot_id = canonical_sha256(snapshot_records)
        if snapshot_id != EXPECTED_SNAPSHOT_ID:
            errors.append("target payload snapshot ID mismatch")
        expected_shards = [
            f"model-{number:05d}-of-00048.safetensors"
            for number in range(1, EXPECTED_SHARDS + 1)
        ]
        if actual_shards != expected_shards:
            errors.append("actual shard set is not exactly 48 shards")
        if index_shards != expected_shards:
            errors.append("weight index does not reference exactly 48 shards")
        if config.get("dspark_block_size") != 5:
            errors.append("dspark_block_size is not 5")
        if config.get("expert_dtype") != "fp4":
            errors.append("expert_dtype is not fp4")
        if any(
            item["same_device_and_inode"] or item["os_path_samefile"]
            for item in entity_records
        ):
            errors.append("source and target share a file identity")
        required = {
            "config.json",
            "configuration.json",
            "generation_config.json",
            "model.safetensors.index.json",
            "tokenizer.json",
            "tokenizer_config.json",
        }
        if not required.issubset(observed_paths):
            errors.append("required config/tokenizer/index files are missing")
        return {
            "schema_version": 1,
            "attempt_id": self.args.attempt_id,
            "validated_at_utc": utc_now(),
            "validation_path": str(self.staging),
            "expected_file_count": EXPECTED_FILES,
            "actual_file_count": len(observed_paths),
            "expected_total_bytes": EXPECTED_BYTES,
            "actual_total_bytes": sum(item["size_bytes"] for item in records),
            "expected_snapshot_id": EXPECTED_SNAPSHOT_ID,
            "actual_snapshot_id": snapshot_id,
            "missing_paths": sorted(expected_paths - observed_paths),
            "extra_paths": sorted(observed_paths - expected_paths),
            "symlinks": symlinks,
            "actual_weight_shards": actual_shards,
            "index_weight_shards": index_shards,
            "checkpoint_config": {
                "architectures": config.get("architectures"),
                "model_type": config.get("model_type"),
                "expert_dtype": config.get("expert_dtype"),
                "dspark_block_size": config.get("dspark_block_size"),
                "dspark_target_layer_ids": config.get(
                    "dspark_target_layer_ids"
                ),
                "num_nextn_predict_layers": config.get(
                    "num_nextn_predict_layers"
                ),
            },
            "copy_method": {
                "name": "python-buffered-userspace-read-write",
                "workers": COPY_WORKERS,
                "buffer_bytes": BUFFER_BYTES,
                "links_or_reflinks_used": False,
                "cache_reference_used": False,
                "per_file_temporary_then_atomic_rename": True,
            },
            "entity_independence": {
                "all_source_target_file_identities_distinct": not any(
                    item["same_device_and_inode"] or item["os_path_samefile"]
                    for item in entity_records
                ),
                "records": entity_records,
            },
            "files": records,
            "errors": errors,
            "status": "PASS" if not errors else "FAIL",
        }

    def publish_small_artifact(
        self, name: str, payload: bytes
    ) -> dict[str, Any]:
        path = self.run_dir / name
        write_atomic(path, payload)
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    def rollback_publication(self) -> str | None:
        if not self.published:
            return None
        try:
            marker = self.formal / ".complete"
            if marker.exists():
                marker.unlink()
            if self.staging.exists():
                return "formal and staging both exist; rollback refused"
            os.rename(self.formal, self.staging)
            self.published = False
            return None
        except Exception as error:
            return f"{type(error).__name__}: {error}"

    def execute(self) -> int:
        started_at = utc_now()
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.copy_log.touch(exist_ok=False)
        try:
            if self.run_dir.exists():
                raise FileExistsError(f"run dir already exists: {self.run_dir}")
            self.run_dir.mkdir(parents=True, exist_ok=False)
            if self.formal.exists():
                raise FileExistsError(
                    f"formal target already exists: {self.formal}"
                )
            if self.staging.exists():
                raise FileExistsError(
                    f"staging target already exists: {self.staging}"
                )
            if self.staging.parent != self.formal.parent:
                raise RuntimeError(
                    "staging and formal target must have the same parent"
                )
            self.staging.parent.mkdir(parents=True, exist_ok=True)

            manifest = self.load_manifest()
            initial_worker = self.check_worker(full_keepalive=True)
            if initial_worker["status"] != "PASS":
                raise RuntimeError("initial worker/keepalive gate failed")
            self.source_before = self.stat_source()
            write_json(
                self.scratch / "source_stat_before.json",
                {
                    "schema_version": 1,
                    "observed_at_utc": utc_now(),
                    "source": str(self.source),
                    "files": self.source_before,
                },
            )
            self.staging.mkdir(parents=False, exist_ok=False)

            attempt_record = {
                "schema_version": 1,
                "authorized_phase": "Phase 02",
                "attempt_id": self.args.attempt_id,
                "started_at_utc": started_at,
                "pid": os.getpid(),
                "pgid": os.getpgid(0),
                "sid": os.getsid(0),
                "hostname": os.uname().nodename,
                "worker_id": self.args.worker_id,
                "source": str(self.source),
                "source_manifest": str(self.source_manifest_path),
                "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
                "staging": str(self.staging),
                "formal_target": str(self.formal),
                "run_dir": str(self.run_dir),
                "scratch": str(self.scratch),
                "copy_method": "4-worker userspace buffered byte copy",
                "formal_target_preexisting": False,
                "staging_preexisting": False,
            }
            write_json(self.scratch / "attempt.json", attempt_record)
            self.publish_small_artifact(
                "attempt.json", json_bytes(attempt_record)
            )
            self.log(
                "PHASE02_START "
                f"attempt={self.args.attempt_id} pid={os.getpid()} "
                f"pgid={os.getpgid(0)} source={self.source} "
                f"staging={self.staging} formal={self.formal}"
            )

            monitor_thread = threading.Thread(
                target=self.worker_monitor_loop,
                name="phase02-worker-monitor",
                daemon=True,
            )
            monitor_thread.start()
            self.copy_payload()
            copy_finished = time.monotonic()
            self.log("COPY_PAYLOAD_COMPLETE; starting full target SHA256")
            target_validation = self.validate_target()
            if target_validation["status"] != "PASS":
                raise RuntimeError(
                    "target validation failed: "
                    + "; ".join(target_validation["errors"])
                )
            self.log(
                "TARGET_HASH_VALIDATION_PASS "
                f"files={target_validation['actual_file_count']} "
                f"bytes={target_validation['actual_total_bytes']} "
                f"snapshot_id={target_validation['actual_snapshot_id']}"
            )

            self.source_after = self.stat_source()
            source_unchanged = self.source_before == self.source_after
            source_unchanged_record = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "checked_at_utc": utc_now(),
                "source": str(self.source),
                "file_count": len(self.source_after),
                "before": self.source_before,
                "after": self.source_after,
                "unchanged": source_unchanged,
                "source_was_read_only": True,
            }
            if not source_unchanged:
                raise RuntimeError("source stat snapshot changed")

            final_worker = self.check_worker(full_keepalive=True)
            if final_worker["status"] != "PASS":
                raise RuntimeError("final worker/keepalive gate failed")
            self.stop_monitor.set()
            monitor_thread.join(timeout=5)
            if self.monitor_errors:
                raise RuntimeError("worker monitor recorded a failure")

            copy_elapsed = max(
                copy_finished - self.copy_started_monotonic, 0.001
            )
            copy_manifest = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "source": str(self.source),
                "staging": str(self.staging),
                "formal_target": str(self.formal),
                "provider": "modelscope",
                "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
                "provider_payload_snapshot_id": EXPECTED_SNAPSHOT_ID,
                "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
                "copy_started_at_utc": started_at,
                "copy_completed_at_utc": utc_now(),
                "copy_elapsed_seconds": copy_elapsed,
                "copy_throughput_bytes_per_second": (
                    EXPECTED_BYTES / copy_elapsed
                ),
                "copy_method": {
                    "name": "python-buffered-userspace-read-write",
                    "workers": COPY_WORKERS,
                    "buffer_bytes": BUFFER_BYTES,
                    "links_or_reflinks_used": False,
                    "cache_reference_used": False,
                },
                "provider_payload_file_count": EXPECTED_FILES,
                "provider_payload_bytes": EXPECTED_BYTES,
                "files": sorted(
                    self.copy_results, key=lambda item: item["path"]
                ),
                "status": "PASS",
            }
            destination_manifest = {
                "schema_version": 1,
                "provider": "modelscope",
                "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
                "provider_payload_snapshot_id": EXPECTED_SNAPSHOT_ID,
                "file_count": EXPECTED_FILES,
                "total_bytes": EXPECTED_BYTES,
                "files": [
                    {
                        "path": item["path"],
                        "size_bytes": item["size_bytes"],
                        "sha256": item["sha256"],
                    }
                    for item in target_validation["files"]
                ],
            }
            provenance = {
                "schema_version": 1,
                "provider": "modelscope",
                "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
                "provider_revision": None,
                "snapshot_identity": {
                    "algorithm": "sha256_canonical_json_path_size_sha256",
                    "scope": "75 ModelScope provider payload files",
                    "value": EXPECTED_SNAPSHOT_ID,
                },
                "source": str(self.source),
                "source_manifest": str(self.source_manifest_path),
                "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
                "attempt_id": self.args.attempt_id,
                "copy_method": copy_manifest["copy_method"],
            }

            self.log(
                "PREPUBLICATION_GATE_PASS source_unchanged=true "
                "target_validation=true keepalive=true"
            )
            os.rename(self.staging, self.formal)
            self.published = True
            if self.staging.exists() or not self.formal.is_dir():
                raise RuntimeError("atomic staging-to-formal rename failed")

            complete_record = {
                "schema_version": 1,
                "status": "complete",
                "provider": "modelscope",
                "repository": "deepseek-ai/DeepSeek-V4-Flash-DSpark",
                "provider_revision": None,
                "provider_payload_snapshot_id": EXPECTED_SNAPSHOT_ID,
                "provider_payload_file_count": EXPECTED_FILES,
                "provider_payload_bytes": EXPECTED_BYTES,
                "source": str(self.source),
                "source_manifest": str(self.source_manifest_path),
                "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
                "attempt_id": self.args.attempt_id,
                "published_at_utc": utc_now(),
                "copy_method": copy_manifest["copy_method"],
            }
            write_json(self.formal / ".complete", complete_record)
            complete_readback = json.loads(
                (self.formal / ".complete").read_text()
            )
            if complete_readback != complete_record:
                raise RuntimeError(".complete readback mismatch")
            formal_files = {
                path.relative_to(self.formal).as_posix()
                for path in self.formal.rglob("*")
                if path.is_file() and not path.is_symlink()
            }
            expected_formal = {
                item["path"] for item in self.provider_records
            } | {".complete"}
            formal_symlinks = [
                path.relative_to(self.formal).as_posix()
                for path in self.formal.rglob("*")
                if path.is_symlink()
            ]
            if formal_files != expected_formal or formal_symlinks:
                raise RuntimeError("post-publication formal tree mismatch")
            target_validation["formal_path_after_atomic_rename"] = str(
                self.formal
            )
            target_validation["staging_absent_after_atomic_rename"] = (
                not self.staging.exists()
            )
            target_validation["complete_marker"] = {
                "path": str(self.formal / ".complete"),
                "size_bytes": (self.formal / ".complete").stat().st_size,
                "sha256": sha256_file(self.formal / ".complete"),
                "readback_match": True,
            }
            target_validation["post_publication_file_count"] = len(
                formal_files
            )
            target_validation["post_publication_symlinks"] = formal_symlinks

            storage_after = {
                "schema_version": 1,
                "observed_at_utc": utc_now(),
                "hdfs": disk_record(self.formal.parent),
                "devbox_tmp": disk_record(self.scratch),
                "formal_target": {
                    "path": str(self.formal),
                    "provider_payload_file_count": EXPECTED_FILES,
                    "provider_payload_bytes": EXPECTED_BYTES,
                    "complete_size_bytes": (
                        self.formal / ".complete"
                    ).stat().st_size,
                },
                "staging_exists": self.staging.exists(),
            }
            self.log(
                "PHASE02_PUBLICATION_PASS "
                f"formal={self.formal} complete_readback=true"
            )
            self.log(
                "PHASE02_FINAL_LOG_SEAL "
                f"status=PASS worker_checks={len(self.worker_checks)}"
            )

            artifacts: dict[str, dict[str, Any]] = {}
            artifacts["copy_manifest.json"] = self.publish_small_artifact(
                "copy_manifest.json", json_bytes(copy_manifest)
            )
            artifacts["source_unchanged.json"] = self.publish_small_artifact(
                "source_unchanged.json", json_bytes(source_unchanged_record)
            )
            artifacts["target_validation.json"] = self.publish_small_artifact(
                "target_validation.json", json_bytes(target_validation)
            )
            artifacts["storage_after.json"] = self.publish_small_artifact(
                "storage_after.json", json_bytes(storage_after)
            )
            artifacts[
                "destination_checkpoint_manifest.json"
            ] = self.publish_small_artifact(
                "destination_checkpoint_manifest.json",
                json_bytes(destination_manifest),
            )
            artifacts[
                "checkpoint_provenance.json"
            ] = self.publish_small_artifact(
                "checkpoint_provenance.json", json_bytes(provenance)
            )
            artifacts[
                "source_checkpoint_manifest.json"
            ] = self.publish_small_artifact(
                "source_checkpoint_manifest.json",
                self.source_manifest_path.read_bytes(),
            )
            artifacts["worker_monitor.json"] = self.publish_small_artifact(
                "worker_monitor.json", self.worker_monitor_path.read_bytes()
            )
            artifacts["copy.log"] = self.publish_small_artifact(
                "copy.log", self.copy_log.read_bytes()
            )
            artifacts["copy_or_download.log"] = self.publish_small_artifact(
                "copy_or_download.log", self.copy_log.read_bytes()
            )
            complete_hash = sha256_file(self.formal / ".complete")
            gate = {
                "schema_version": 1,
                "authorized_phase": "Phase 02",
                "attempt_id": self.args.attempt_id,
                "audited_at_utc": utc_now(),
                "status": "PASS",
                "errors": [],
                "worker_id": self.args.worker_id,
                "worker_seen_on_every_check": all(
                    item["status"] == "PASS"
                    for item in self.worker_checks
                ),
                "keepalive_10x1s_checks": sum(
                    bool(item.get("full_keepalive_check"))
                    for item in self.worker_checks
                ),
                "keepalive_exit_gate_passed": (
                    final_worker["status"] == "PASS"
                ),
                "source_unchanged": True,
                "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
                "provider_payload_snapshot_id": EXPECTED_SNAPSHOT_ID,
                "provider_payload_file_count": EXPECTED_FILES,
                "provider_payload_bytes": EXPECTED_BYTES,
                "target_validation_passed": True,
                "target_independent_entity_copy": True,
                "formal_target": str(self.formal),
                "formal_target_exists": self.formal.is_dir(),
                "staging_absent": not self.staging.exists(),
                "complete_marker": {
                    "path": str(self.formal / ".complete"),
                    "sha256": complete_hash,
                    "readback_match": True,
                },
                "required_final_artifact_hashes": artifacts,
                "next_eligible_phase": (
                    "Phase 04 only after Phase 03 PASS and user confirmation"
                ),
            }
            write_json(self.run_dir / "phase02_gate.json", gate)
            gate_readback = json.loads(
                (self.run_dir / "phase02_gate.json").read_text()
            )
            if gate_readback != gate:
                raise RuntimeError("phase02 gate readback mismatch")
            return 0
        except Exception as error:
            self.stop_monitor.set()
            rollback_error = self.rollback_publication()
            error_record = {
                "schema_version": 1,
                "authorized_phase": "Phase 02",
                "attempt_id": self.args.attempt_id,
                "failed_at_utc": utc_now(),
                "status": "FAIL",
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
                "formal_target_exists": self.formal.exists(),
                "staging_exists": self.staging.exists(),
                "rollback_error": rollback_error,
                "worker_monitor_errors": self.monitor_errors,
            }
            try:
                self.log(
                    "PHASE02_FAIL "
                    f"error={type(error).__name__}:{error} "
                    f"rollback_error={rollback_error}"
                )
            except Exception:
                pass
            try:
                self.run_dir.mkdir(parents=True, exist_ok=True)
                write_json(self.run_dir / "phase02_gate.json", error_record)
                if self.copy_log.exists():
                    write_atomic(
                        self.run_dir / "copy.log",
                        self.copy_log.read_bytes(),
                    )
                if self.worker_monitor_path.exists():
                    write_atomic(
                        self.run_dir / "worker_monitor.json",
                        self.worker_monitor_path.read_bytes(),
                    )
            except Exception:
                traceback.print_exc()
            try:
                print(json.dumps(error_record, sort_keys=True), flush=True)
            except BrokenPipeError:
                pass
            return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--formal", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--keepalive-script", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(Phase02(parse_args()).execute())
