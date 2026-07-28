#!/usr/bin/env python3
"""Resume a failed D1A partial with one curl process per bounded attempt.

This recovery changes exactly one acquisition variable: retries move outside
curl, so every new curl invocation recomputes the current `--continue-at -`
offset. It reuses the same primary revision, attempt directory, NVMe staging,
provider manifest, HDFS destinations, and keepalive.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import traceback
import urllib.parse
from typing import Any

import dflash_d1a_acquire_publish as base


MAX_EXTERNAL_ATTEMPTS = 5


def active_original_processes(attempt_id: str) -> list[dict[str, Any]]:
    records = []
    own_pid = os.getpid()
    for candidate in pathlib.Path("/proc").iterdir():
        if not candidate.name.isdigit() or int(candidate.name) == own_pid:
            continue
        pid = int(candidate.name)
        try:
            raw = (candidate / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        command = [
            item.decode(errors="replace")
            for item in raw.split(b"\0")
            if item
        ]
        if (
            attempt_id in command
            and any("dflash_d1a_acquire_publish.py" in item for item in command)
        ) or (
            command
            and pathlib.Path(command[0]).name == "curl"
            and any(base.REVISION in item for item in command)
            and any("model.safetensors" in item for item in command)
        ):
            records.append({"pid": pid, "argv": command})
    return records


class Resume:
    def __init__(self, attempt_id: str) -> None:
        self.acquisition = base.Acquisition(attempt_id)
        self.events = (
            self.acquisition.attempt_root / "recovery_events.jsonl"
        )

    def event(self, value: dict[str, Any]) -> None:
        value = {"timestamp_utc": base.utc_now(), **value}
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def preflight(self) -> None:
        acq = self.acquisition
        if not acq.attempt_root.is_dir() or not acq.nvme_staging.is_dir():
            raise RuntimeError("original D1A attempt/staging is missing")
        active = active_original_processes(acq.attempt_id)
        if active:
            raise RuntimeError(
                f"original acquisition/curl remains active: {active}"
            )
        if socket.gethostname() != base.EXPECTED_HOSTNAME:
            raise RuntimeError(f"unexpected hostname: {socket.gethostname()}")
        acq.timebox = json.loads(base.TIMEBOX_PATH.read_text())
        acq.require_timebox()
        acq.verify_keepalive()
        provider = json.loads(
            (acq.attempt_root / "provider_metadata.json").read_text()
        )
        if (
            provider.get("repo_id") != base.REPO_ID
            or provider.get("requested_revision") != base.REVISION
            or provider.get("resolved_revision") != base.REVISION
            or {item["path"] for item in provider.get("files", [])}
            != base.EXPECTED_PROVIDER_FILES
        ):
            raise RuntimeError("original pinned provider metadata mismatch")
        acq.provider = provider
        if base.HDFS_FORMAL.exists() or base.HDFS_POINTER.exists():
            raise RuntimeError(
                "formal/pointer already exists; recovery publication refused"
            )
        if acq.hdfs_staging.exists():
            raise RuntimeError(
                "HDFS staging already exists; recovery scope is ambiguous"
            )
        gpu_query = subprocess.run(
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
        gpu_rows = [
            [part.strip() for part in line.split(",", 2)]
            for line in gpu_query.stdout.splitlines()
        ]
        if (
            len(gpu_rows) != 8
            or [int(item[0]) for item in gpu_rows] != list(range(8))
            or any(item[2] != "NVIDIA H20" for item in gpu_rows)
        ):
            raise RuntimeError("recovery worker is not the assigned 8xH20")
        record = {
            "schema_version": 1,
            "attempt_id": acq.attempt_id,
            "single_variable_change": (
                "replace curl-internal retry with external bounded curl "
                "re-invocation so --continue-at - recomputes current size"
            ),
            "repo_id": base.REPO_ID,
            "revision": base.REVISION,
            "nvme_staging": str(acq.nvme_staging),
            "keepalive_pid": acq.keepalive_pid,
            "worker_id": base.WORKER_ID,
            "hostname": socket.gethostname(),
            "gpu_count": 8,
            "fallback_checkpoint_enabled": False,
            "model_process_started": False,
            "checked_at_utc": base.utc_now(),
        }
        base.write_json(
            acq.attempt_root / "recovery_preflight.json", record
        )
        acq.log(
            "D1A recovery preflight PASS; same primary/attempt/partial, "
            "external resume retry only"
        )

    def curl_once(
        self, url: str, partial: pathlib.Path, expected: int, ordinal: int
    ) -> tuple[int, int, str, str, float]:
        acq = self.acquisition
        before = partial.stat().st_size if partial.exists() else 0
        command = [
            "curl",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "30",
            "--speed-limit",
            "1024",
            "--speed-time",
            "300",
            "--max-time",
            "3600",
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
            base.USER_AGENT,
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
                if now - last_heartbeat >= base.HEARTBEAT_INTERVAL_SECONDS:
                    acq.require_timebox()
                    acq.verify_keepalive()
                    acq.heartbeat()
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
        after = partial.stat().st_size if partial.exists() else 0
        self.event(
            {
                "event": "external_resume_curl_complete",
                "ordinal": ordinal,
                "path": str(partial),
                "before_size_bytes": before,
                "after_size_bytes": after,
                "expected_size_bytes": expected,
                "returncode": process.returncode,
                "duration_seconds": duration,
                "curl_stdout": stdout.strip(),
                "curl_stderr": stderr.strip(),
                "internal_retry_enabled": False,
            }
        )
        if after < before:
            raise RuntimeError(
                f"external resume was not monotonic: {after} < {before}"
            )
        return process.returncode, after, stdout.strip(), stderr.strip(), duration

    def resume_file(self, entry: dict[str, Any]) -> None:
        acq = self.acquisition
        relative = entry["path"]
        destination = acq.nvme_staging / relative
        if destination.is_file():
            if destination.stat().st_size != entry["size_bytes"]:
                raise RuntimeError(
                    f"completed file has wrong size: {destination}"
                )
            acq.log(f"recovery reuse completed path={relative}")
            return
        partial = destination.with_name(destination.name + ".partial")
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = "/".join(
            urllib.parse.quote(part, safe="")
            for part in pathlib.PurePosixPath(relative).parts
        )
        url = (
            f"https://huggingface.co/{base.REPO_ID}/resolve/"
            f"{base.REVISION}/{encoded}?download=true"
        )
        acq.current_path = partial
        for ordinal in range(1, MAX_EXTERNAL_ATTEMPTS + 1):
            acq.require_timebox()
            acq.verify_keepalive()
            before = partial.stat().st_size if partial.exists() else 0
            acq.log(
                f"external resume start ordinal={ordinal} path={relative} "
                f"offset={before} expected={entry['size_bytes']}"
            )
            returncode, after, _, stderr, duration = self.curl_once(
                url,
                partial,
                int(entry["size_bytes"]),
                ordinal,
            )
            acq.log(
                f"external resume end ordinal={ordinal} rc={returncode} "
                f"path={relative} size={after} duration={duration:.3f}s"
            )
            if returncode == 0 and after == entry["size_bytes"]:
                os.rename(partial, destination)
                acq.log(
                    f"external resume PASS path={relative} bytes={after}"
                )
                return
            if returncode == 0:
                raise RuntimeError(
                    f"curl success with wrong size for {relative}: "
                    f"{after} != {entry['size_bytes']}"
                )
            if ordinal == MAX_EXTERNAL_ATTEMPTS:
                raise RuntimeError(
                    f"external resume exhausted for {relative}: {stderr}"
                )
            time.sleep(min(30, ordinal * 5))
        raise AssertionError("unreachable")

    def run(self) -> None:
        acq = self.acquisition
        self.preflight()
        acq.current_stage = "external_resume_download"
        acq.heartbeat()
        for entry in acq.provider["files"]:
            self.resume_file(entry)
        acq.current_path = None
        acq.validate_nvme()
        acq.copy_to_hdfs()
        hdfs_manifest = acq.validate_hdfs()
        acq.publish(hdfs_manifest)
        acq.success_summary()
        acq.export_evidence()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args()
    recovery: Resume | None = None
    try:
        recovery = Resume(args.attempt_id)
        recovery.run()
        return 0
    except BaseException as error:
        if recovery is not None:
            recovery.acquisition.failure_summary(error)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
