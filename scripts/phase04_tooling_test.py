#!/usr/bin/env python3
"""Offline integration test for Phase 05 API/GSM8K and process lifecycle tools."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from phase05_gsm8k_smoke import extract_model_answer, normalize_number


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parent.parent
    python = Path(sys.executable)
    port = free_port()
    lifecycle_log = (args.artifact_dir / "process_lifecycle_test.log").open("w")
    tooling_log = (args.artifact_dir / "tooling_test.log").open("w")
    command = [
        str(python),
        str(repo / "scripts/phase04_mock_openai_server.py"),
        "--port",
        str(port),
        "--dataset",
        str(args.dataset),
        "--fail-first-gsm8k",
    ]
    server = subprocess.Popen(
        command,
        stdout=lifecycle_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    try:
        pgid = os.getpgid(server.pid)
        sid = os.getsid(server.pid)
        assert server.pid == pgid == sid
        tooling_log.write(
            f"fixture pid={server.pid} pgid={pgid} sid={sid} port={port}\n"
        )
        subprocess.run(
            [
                str(python),
                str(repo / "scripts/phase05_wait_ready.py"),
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--server-pid",
                str(server.pid),
                "--timeout",
                "30",
                "--output",
                str(args.artifact_dir / "mock_startup.json"),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                str(repo / "scripts/phase05_api_smoke.py"),
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--model",
                "deepseek-v4-flash-dspark",
                "--output",
                str(args.artifact_dir / "mock_api_smoke.json"),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                str(repo / "scripts/phase05_gsm8k_smoke.py"),
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--dataset",
                str(args.dataset),
                "--output",
                str(args.artifact_dir / "mock_gsm8k_outputs.jsonl"),
                "--summary",
                str(args.artifact_dir / "mock_summary.json"),
                "--timeout",
                "10",
                "--max-attempts",
                "3",
            ],
            check=True,
        )
        summary = json.loads((args.artifact_dir / "mock_summary.json").read_text())
        assert summary["success_requests"] == 10
        assert summary["failed_requests"] == 0
        assert summary["matches"] == 10
        records = [
            json.loads(line)
            for line in (
                args.artifact_dir / "mock_gsm8k_outputs.jsonl"
            ).read_text().splitlines()
        ]
        assert all(len(record["attempts"]) == 2 for record in records)
        assert normalize_number("$1,200.00") == "1200"
        assert extract_model_answer(r"x \boxed{8}, later \boxed{9}") == ("9", "boxed")
        assert extract_model_answer("work 2 #### 3") == ("3", "hashes")
        assert extract_model_answer("Final answer: $4.50") == ("4.5", "final_answer")
        assert extract_model_answer("there are 6 then 7") == ("7", "last_number")
        tooling_log.write("PASS api_smoke gsm8k_retry parser summary\n")
    finally:
        if server.poll() is None:
            cmdline = Path(f"/proc/{server.pid}/cmdline").read_bytes().replace(
                b"\0", b" "
            )
            if b"phase04_mock_openai_server.py" not in cmdline:
                raise RuntimeError("fixture PID identity changed; refusing cleanup")
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        lifecycle_log.write(f"fixture_exit_code={server.returncode}\n")
        lifecycle_log.close()
        tooling_log.close()


if __name__ == "__main__":
    main()
