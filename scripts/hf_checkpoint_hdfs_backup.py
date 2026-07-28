#!/usr/bin/env python3
"""Copy the validated Hugging Face NVMe snapshot to an HDFS backup path."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any


BUFFER_BYTES = 16 * 1024 * 1024
COPY_WORKERS = 4
PROGRESS_SECONDS = 30
KEEPALIVE_SECONDS = 600
EXPECTED_FILES = 74
EXPECTED_BYTES = 166_898_666_055
EXPECTED_SHARDS = [
    f"model-{number:05d}-of-00048.safetensors" for number in range(1, 49)
]
CORE_FILES = [
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("xb") as handle:
        handle.write(payload)
    os.replace(temporary, path)


def write_json(path: Path, payload: Any) -> None:
    write_atomic(path, json_bytes(payload))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stat_record(path: Path, relative: str) -> dict[str, Any]:
    observed = path.lstat()
    return {
        "path": relative,
        "size_bytes": observed.st_size,
        "mode": stat.S_IMODE(observed.st_mode),
        "mtime_ns": observed.st_mtime_ns,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "link_count": observed.st_nlink,
        "is_regular": stat.S_ISREG(observed.st_mode),
        "is_symlink": stat.S_ISLNK(observed.st_mode),
    }


class Backup:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.source = args.source
        self.staging = args.staging
        self.formal = args.formal
        self.run_dir = args.run_dir
        self.scratch = args.scratch
        self.log_path = self.scratch / "copy.log"
        self.expected: dict[str, int] = {}
        self.copy_results: list[dict[str, Any]] = []
        self.bytes_copied = 0
        self.files_copied = 0
        self.copy_started = 0.0
        self.state_lock = threading.Lock()
        self.stop_monitor = threading.Event()
        self.monitor_errors: list[str] = []
        self.keepalive_checks: list[dict[str, Any]] = []
        self.published = False

    def log(self, message: str) -> None:
        line = f"{utc_now()} {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        try:
            print(line, flush=True)
        except BrokenPipeError:
            pass

    def load_authority(self) -> None:
        metadata = read_json(self.args.metadata)
        source_validation = read_json(self.args.source_validation)
        if not (
            metadata.get("provider") == "huggingface"
            and metadata.get("repo_id") == self.args.repo_id
            and metadata.get("requested_revision") == self.args.revision
            and metadata.get("resolved_revision") == self.args.revision
            and metadata.get("file_count") == EXPECTED_FILES
            and metadata.get("shard_count") == 48
            and metadata.get("expected_total_bytes") == EXPECTED_BYTES
        ):
            raise RuntimeError("Hugging Face metadata identity mismatch")
        if not (
            source_validation.get("status") == "PASS"
            and source_validation.get("resolved_revision") == self.args.revision
            and source_validation.get("actual_file_count") == EXPECTED_FILES
            and source_validation.get("actual_shard_count") == 48
            and source_validation.get("actual_total_bytes") == EXPECTED_BYTES
            and source_validation.get("content_hashes_computed") is False
        ):
            raise RuntimeError("source minimal validation is not PASS")
        self.expected = {
            item["path"]: int(item["size"]) for item in metadata["files"]
        }
        if (
            len(self.expected) != EXPECTED_FILES
            or sum(self.expected.values()) != EXPECTED_BYTES
        ):
            raise RuntimeError("metadata path/size aggregate mismatch")

    def scan(
        self, root: Path, *, ignore_hf_cache: bool = False
    ) -> dict[str, Any]:
        paths: set[str] = set()
        symlinks: list[str] = []
        for candidate in root.rglob("*"):
            relative = candidate.relative_to(root)
            if (
                ignore_hf_cache
                and relative.parts
                and relative.parts[0] == ".cache"
            ):
                continue
            relative_text = relative.as_posix()
            if candidate.is_symlink():
                symlinks.append(relative_text)
            elif candidate.is_file():
                paths.add(relative_text)
        records = []
        size_mismatches = []
        for relative in sorted(set(self.expected) & paths):
            record = stat_record(root / relative, relative)
            records.append(record)
            if (
                not record["is_regular"]
                or record["is_symlink"]
                or record["size_bytes"] != self.expected[relative]
            ):
                size_mismatches.append(
                    {
                        "path": relative,
                        "expected_size_bytes": self.expected[relative],
                        "actual_size_bytes": record["size_bytes"],
                    }
                )
        shards = sorted(
            path
            for path in paths
            if re.fullmatch(r"model-\d{5}-of-00048\.safetensors", path)
        )
        result = {
            "root": str(root),
            "actual_paths": sorted(paths),
            "missing_paths": sorted(set(self.expected) - paths),
            "extra_paths": sorted(paths - set(self.expected)),
            "symlinks": sorted(symlinks),
            "size_mismatches": size_mismatches,
            "actual_file_count": len(paths),
            "actual_total_bytes": sum(item["size_bytes"] for item in records),
            "actual_shards": shards,
            "missing_core_files": sorted(set(CORE_FILES) - paths),
            "records": records,
        }
        result["status"] = (
            "PASS"
            if (
                not result["missing_paths"]
                and not result["extra_paths"]
                and not result["symlinks"]
                and not result["size_mismatches"]
                and result["actual_file_count"] == EXPECTED_FILES
                and result["actual_total_bytes"] == EXPECTED_BYTES
                and result["actual_shards"] == EXPECTED_SHARDS
                and not result["missing_core_files"]
            )
            else "FAIL"
        )
        return result

    def check_keepalive(self) -> dict[str, Any]:
        completed = subprocess.run(
            [
                "bash",
                str(self.args.keepalive_script),
                "status",
                self.args.worker_id,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        report = None
        for line in completed.stdout.splitlines():
            if line.startswith("{") and '"healthy"' in line:
                report = json.loads(line)
        passed = (
            completed.returncode == 0
            and isinstance(report, dict)
            and report.get("healthy") is True
            and report.get("expected_gpus") == 4
            and not report.get("underutilized_gpus")
        )
        result = {
            "checked_at_utc": utc_now(),
            "status": "PASS" if passed else "FAIL",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "report": report,
        }
        self.keepalive_checks.append(result)
        if not passed:
            self.monitor_errors.append("keepalive gate failed")
        return result

    def progress_payload(self, status: str) -> dict[str, Any]:
        with self.state_lock:
            elapsed = max(time.monotonic() - self.copy_started, 0.001)
            rate = self.bytes_copied / elapsed
            remaining = max(EXPECTED_BYTES - self.bytes_copied, 0)
            return {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "updated_at_utc": utc_now(),
                "status": status,
                "bytes_copied": self.bytes_copied,
                "expected_bytes": EXPECTED_BYTES,
                "files_completed": self.files_copied,
                "expected_files": EXPECTED_FILES,
                "throughput_bytes_per_second": rate,
                "eta_seconds": remaining / rate if rate else None,
                "published": self.published,
            }

    def write_progress(self, status: str) -> dict[str, Any]:
        payload = self.progress_payload(status)
        write_json(self.scratch / "progress.json", payload)
        write_json(self.run_dir / "progress.json", payload)
        return payload

    def monitor_loop(self) -> None:
        next_keepalive = time.monotonic() + KEEPALIVE_SECONDS
        while not self.stop_monitor.wait(PROGRESS_SECONDS):
            progress = self.write_progress("copying")
            self.log(
                "COPY_PROGRESS "
                f"bytes={progress['bytes_copied']}/{EXPECTED_BYTES} "
                f"files={progress['files_completed']}/{EXPECTED_FILES} "
                f"rate_Bps={progress['throughput_bytes_per_second']:.0f} "
                f"eta_s={progress['eta_seconds']:.0f}"
            )
            if time.monotonic() >= next_keepalive:
                check = self.check_keepalive()
                self.log(f"KEEPALIVE_CHECK status={check['status']}")
                next_keepalive = time.monotonic() + KEEPALIVE_SECONDS

    def copy_one(self, relative: str) -> dict[str, Any]:
        source = self.source / relative
        destination = self.staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.part-{self.args.attempt_id}"
        )
        if destination.exists() or temporary.exists():
            raise FileExistsError(f"destination already exists: {relative}")
        started = time.monotonic()
        written = 0
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640
        )
        try:
            with source.open("rb", buffering=BUFFER_BYTES) as reader:
                with os.fdopen(
                    descriptor, "wb", buffering=BUFFER_BYTES
                ) as writer:
                    descriptor = -1
                    while chunk := reader.read(BUFFER_BYTES):
                        writer.write(chunk)
                        written += len(chunk)
                        with self.state_lock:
                            self.bytes_copied += len(chunk)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if written != self.expected[relative]:
            raise RuntimeError(f"copy byte count mismatch: {relative}")
        if temporary.stat().st_size != self.expected[relative]:
            raise RuntimeError(f"temporary size mismatch: {relative}")
        os.replace(temporary, destination)
        result = {
            "path": relative,
            "size_bytes": written,
            "elapsed_seconds": time.monotonic() - started,
            "method": "python-buffered-userspace-read-write",
        }
        with self.state_lock:
            self.files_copied += 1
            self.copy_results.append(result)
        self.log(
            f"COPY_FILE_DONE path={relative} bytes={written} "
            f"elapsed_s={result['elapsed_seconds']:.3f}"
        )
        return result

    def copy_payload(self) -> None:
        order = sorted(
            self.expected, key=lambda path: self.expected[path], reverse=True
        )
        self.copy_started = time.monotonic()
        self.write_progress("copying")
        monitor = threading.Thread(
            target=self.monitor_loop, name="hf-hdfs-monitor", daemon=True
        )
        monitor.start()
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=COPY_WORKERS
        ) as executor:
            futures = [executor.submit(self.copy_one, path) for path in order]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        if self.monitor_errors:
            raise RuntimeError("; ".join(self.monitor_errors))

    def publish(self, target_validation: dict[str, Any]) -> None:
        if self.staging.parent != self.formal.parent:
            raise RuntimeError("staging and formal must have the same parent")
        os.rename(self.staging, self.formal)
        self.published = True
        complete = {
            "schema_version": 1,
            "status": "complete",
            "provider": "huggingface",
            "repository": self.args.repo_id,
            "provider_revision": self.args.revision,
            "provider_payload_file_count": EXPECTED_FILES,
            "provider_payload_bytes": EXPECTED_BYTES,
            "source_nvme_snapshot": str(self.source),
            "source_nvme_retained": True,
            "attempt_id": self.args.attempt_id,
            "published_at_utc": utc_now(),
            "validation_level": "operational_minimal_user_authorized",
            "content_hashes_computed": False,
            "copy_method": "4-worker userspace buffered byte copy",
        }
        write_json(self.formal / ".complete", complete)
        if read_json(self.formal / ".complete") != complete:
            raise RuntimeError(".complete readback mismatch")
        formal_validation = self.scan(self.formal)
        formal_paths = set(formal_validation["actual_paths"])
        if ".complete" not in formal_paths:
            raise RuntimeError("formal .complete is missing")
        formal_paths.remove(".complete")
        if (
            formal_paths != set(self.expected)
            or formal_validation["symlinks"]
            or target_validation["status"] != "PASS"
        ):
            raise RuntimeError("formal post-publication tree mismatch")

    def rollback(self) -> str | None:
        if not self.published:
            return None
        try:
            marker = self.formal / ".complete"
            if marker.exists():
                marker.unlink()
            if self.staging.exists():
                return "staging and formal both exist; rollback refused"
            os.rename(self.formal, self.staging)
            self.published = False
            return None
        except Exception as error:
            return f"{type(error).__name__}: {error}"

    def run(self) -> int:
        started_at = utc_now()
        source_before: dict[str, Any] | None = None
        target_validation: dict[str, Any] | None = None
        try:
            self.scratch.mkdir(parents=True, exist_ok=True)
            self.log_path.touch(exist_ok=False)
            if self.run_dir.exists():
                raise FileExistsError(f"run dir exists: {self.run_dir}")
            self.run_dir.mkdir(parents=True, exist_ok=False)
            if self.staging.exists() or self.formal.exists():
                raise FileExistsError("staging or formal target already exists")
            self.staging.parent.mkdir(parents=True, exist_ok=True)
            self.load_authority()
            source_before = self.scan(self.source, ignore_hf_cache=True)
            if source_before["status"] != "PASS":
                raise RuntimeError("fresh source path/size validation failed")
            keepalive = self.check_keepalive()
            if keepalive["status"] != "PASS":
                raise RuntimeError("initial keepalive gate failed")
            free_bytes = shutil.disk_usage(self.staging.parent).free
            if free_bytes < EXPECTED_BYTES:
                raise RuntimeError("insufficient HDFS free space")
            self.staging.mkdir(parents=False, exist_ok=False)
            identity = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "started_at_utc": started_at,
                "pid": os.getpid(),
                "pgid": os.getpgid(0),
                "sid": os.getsid(0),
                "hostname": os.uname().nodename,
                "worker_id": self.args.worker_id,
                "source": str(self.source),
                "staging": str(self.staging),
                "formal": str(self.formal),
                "revision": self.args.revision,
            }
            write_json(self.scratch / "process_identity.json", identity)
            write_json(self.run_dir / "process_identity.json", identity)
            self.log(
                f"HF_HDFS_COPY_START attempt={self.args.attempt_id} "
                f"source={self.source} staging={self.staging}"
            )
            self.copy_payload()
            self.stop_monitor.set()
            source_after = self.scan(self.source, ignore_hf_cache=True)
            if source_after != source_before:
                raise RuntimeError("source stat/path snapshot changed")
            target_validation = self.scan(self.staging)
            if target_validation["status"] != "PASS":
                raise RuntimeError("staging minimal validation failed")
            final_keepalive = self.check_keepalive()
            if final_keepalive["status"] != "PASS":
                raise RuntimeError("final keepalive gate failed")
            self.publish(target_validation)
            completed_at = utc_now()
            copy_manifest = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "provider": "huggingface",
                "repository": self.args.repo_id,
                "provider_revision": self.args.revision,
                "source": str(self.source),
                "formal": str(self.formal),
                "file_count": EXPECTED_FILES,
                "total_bytes": EXPECTED_BYTES,
                "copy_workers": COPY_WORKERS,
                "buffer_bytes": BUFFER_BYTES,
                "links_reflinks_or_cache_references_used": False,
                "content_hashes_computed": False,
                "files": sorted(
                    self.copy_results, key=lambda item: item["path"]
                ),
                "status": "PASS",
            }
            gate = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "status": "PASS",
                "started_at_utc": started_at,
                "completed_at_utc": completed_at,
                "worker_id": self.args.worker_id,
                "provider": "huggingface",
                "repository": self.args.repo_id,
                "provider_revision": self.args.revision,
                "formal_target": str(self.formal),
                "formal_target_exists": self.formal.is_dir(),
                "staging_absent": not self.staging.exists(),
                "complete_marker_readback": True,
                "provider_file_count": EXPECTED_FILES,
                "provider_payload_bytes": EXPECTED_BYTES,
                "weight_shard_count": 48,
                "core_files_present": True,
                "no_symlinks": True,
                "path_set_and_sizes_match": True,
                "source_nvme_retained": self.source.is_dir(),
                "content_hashes_computed": False,
                "validation_level": "operational_minimal_user_authorized",
                "keepalive_checks_passed": all(
                    item["status"] == "PASS"
                    for item in self.keepalive_checks
                ),
            }
            write_json(self.run_dir / "source_validation.json", source_before)
            write_json(self.run_dir / "target_validation.json", target_validation)
            write_json(self.run_dir / "copy_manifest.json", copy_manifest)
            write_json(
                self.run_dir / "keepalive_checks.json", self.keepalive_checks
            )
            write_atomic(self.run_dir / "copy.log", self.log_path.read_bytes())
            self.write_progress("complete")
            write_json(self.run_dir / "hf_hdfs_gate.json", gate)
            self.log(
                f"HF_HDFS_PUBLICATION_PASS formal={self.formal} "
                f"files={EXPECTED_FILES} bytes={EXPECTED_BYTES}"
            )
            write_atomic(self.run_dir / "copy.log", self.log_path.read_bytes())
            return 0
        except Exception as error:
            self.stop_monitor.set()
            rollback_error = self.rollback()
            failure = {
                "schema_version": 1,
                "attempt_id": self.args.attempt_id,
                "status": "FAIL",
                "failed_at_utc": utc_now(),
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
                "formal_target_exists": self.formal.exists(),
                "staging_exists": self.staging.exists(),
                "source_nvme_retained": self.source.exists(),
                "rollback_error": rollback_error,
            }
            try:
                self.run_dir.mkdir(parents=True, exist_ok=True)
                write_json(self.run_dir / "hf_hdfs_gate.json", failure)
                if self.log_path.exists():
                    write_atomic(
                        self.run_dir / "copy.log", self.log_path.read_bytes()
                    )
            except Exception:
                traceback.print_exc()
            return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--source-validation", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--keepalive-script", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(Backup(parse_args()).run())
