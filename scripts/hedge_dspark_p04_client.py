#!/usr/bin/env python3
"""Run the fixed first-calibration P04 request and validate HEDGE counters."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deepspec.hedge_protocol.config import (  # noqa: E402
    DATASET_REVISION,
    DEFAULT_MODEL,
)
from deepspec.hedge_protocol.io import load_jsonl  # noqa: E402
from deepspec.hedge_protocol.runner import (  # noqa: E402
    ProtocolRunner,
)


B0_CONFIG: dict[str, int | float | str] = {
    "B": 0,
    "g": 1e30,
    "m": 5,
    "value_scheme": "normalized_suffix",
    "block_size": 5,
}
SERVER_FIELDS = {
    "tp_size": 8,
    "speculative_algorithm": "DSPARK",
    "speculative_dspark_block_size": 5,
    "moe_runner_backend": "flashinfer_mxfp4",
    "speculative_moe_runner_backend": "flashinfer_mxfp4",
    "context_length": 4096,
    "max_running_requests": 1,
    "mem_fraction_static": 0.8,
    "disable_cuda_graph": True,
    "disable_overlap_schedule": True,
    "disable_radix_cache": True,
}
JsonGet = Callable[[str, float], Mapping[str, Any]]
HealthGet = Callable[[str, float], int]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("xb") as output:
        output.write(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
        )
        output.write(b"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def validate_server_info(
    server_info: Mapping[str, Any], *, arm: str
) -> dict[str, Any]:
    """Validate the live decode config and DSpark HEDGE snapshot seam."""

    if arm not in {"native", "b0"}:
        raise ValueError("arm must be exactly native or b0")
    if not isinstance(server_info, Mapping):
        raise ValueError("/server_info response must be an object")
    mismatches = {
        key: {"expected": expected, "observed": server_info.get(key)}
        for key, expected in SERVER_FIELDS.items()
        if server_info.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"/server_info decode config mismatch: {mismatches}")
    internal_states = server_info.get("internal_states")
    if not isinstance(internal_states, list) or not internal_states:
        raise ValueError("/server_info internal_states must be non-empty")
    snapshots: list[dict[str, Any]] = []
    expected_mode = "disabled" if arm == "native" else "enabled"
    expected_enabled = 0 if arm == "native" else 1
    for index, state in enumerate(internal_states):
        if not isinstance(state, Mapping):
            raise ValueError(f"internal_states[{index}] must be an object")
        info_record = state.get("dspark_info_record")
        if not isinstance(info_record, Mapping):
            raise ValueError(
                f"internal_states[{index}].dspark_info_record is missing"
            )
        snapshot = info_record.get("hedge")
        if not isinstance(snapshot, Mapping):
            raise ValueError(
                f"internal_states[{index}] has no DSpark HEDGE snapshot"
            )
        normalized = dict(snapshot)
        if normalized.get("mode") != expected_mode:
            raise ValueError(
                f"HEDGE mode must be {expected_mode!r} for arm {arm}"
            )
        switches = normalized.get("experiment_switches")
        if switches != {
            "HEDGE_ENABLED": expected_enabled,
            "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE": 0,
        }:
            raise ValueError("HEDGE experiment switches do not match the arm")
        expected_config = None if arm == "native" else B0_CONFIG
        if normalized.get("config") != expected_config:
            raise ValueError("HEDGE config is not the exact arm config")
        if normalized.get("gamma") != 5:
            raise ValueError("HEDGE gamma is not DSpark width 5")
        if normalized.get("verify_num_draft_tokens") != 6:
            raise ValueError("HEDGE verify width is not 6")
        proposals = normalized.get("proposals")
        if (
            isinstance(proposals, bool)
            or not isinstance(proposals, int)
            or proposals < 0
        ):
            raise ValueError("HEDGE proposals must be a non-negative integer")
        snapshots.append(normalized)
    proposal_count = sum(int(item["proposals"]) for item in snapshots)
    if arm == "b0" and proposal_count <= 0:
        raise ValueError("B0 must report positive proposals")
    return {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": "PASS",
        "arm": arm,
        "source_endpoint": "/server_info",
        "server_config": {
            key: server_info[key] for key in SERVER_FIELDS
        },
        "internal_states": internal_states,
        "hedge_snapshots": snapshots,
        "proposal_count": proposal_count,
    }


class _NoProxyJsonGet:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

    def __call__(self, url: str, timeout: float) -> Mapping[str, Any]:
        request = urllib.request.Request(url, method="GET")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"GET {url} failed with HTTP {error.code}: "
                + error.read().decode(errors="replace")
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"GET {url} failed: {error!r}") from error
        if status < 200 or status >= 300:
            raise RuntimeError(f"GET {url} returned HTTP {status}")
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise RuntimeError(f"GET {url} JSON must be an object")
        return value


class _NoProxyHealthGet:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

    def __call__(self, url: str, timeout: float) -> int:
        request = urllib.request.Request(url, method="GET")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                response.read()
                return int(response.status)
        except urllib.error.HTTPError as error:
            return int(error.code)
        except urllib.error.URLError as error:
            raise RuntimeError(f"GET {url} failed: {error!r}") from error


def run_smoke(
    *,
    arm: str,
    base_url: str,
    sample: Mapping[str, Any],
    chat_transport: Callable[
        [str, dict[str, Any], float], Mapping[str, Any]
    ]
    | None = None,
    server_info_get: JsonGet | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one sequential request through the frozen P01 protocol seam."""

    if arm not in {"native", "b0"}:
        raise ValueError("arm must be exactly native or b0")
    if (
        sample.get("cohort") != "calibration"
        or sample.get("cohort_position") != 0
        or sample.get("dataset_revision") != DATASET_REVISION
    ):
        raise ValueError("P04 smoke requires calibration JSONL record zero")
    runner = ProtocolRunner(
        base_url=base_url,
        model=DEFAULT_MODEL,
        transport=chat_transport,
        sleeper=sleeper,
    )
    started_at = _utc_now()
    record = runner.run_one(
        sample, cohort="p04_smoke", cohort_position=0
    )
    successful_attempt = next(
        (
            attempt
            for attempt in reversed(record["attempts"])
            if attempt["status"] == "success"
        ),
        None,
    )
    raw_response = (
        None
        if successful_attempt is None
        else successful_attempt["raw_response"]
    )
    api = {
        "schema_version": 1,
        "authorized_phase": "P04",
        "status": (
            "PASS" if record["terminal_status"] == "succeeded" else "FAIL"
        ),
        "arm": arm,
        "base_url": base_url,
        "sample_identity": {
            key: sample[key]
            for key in (
                "cohort",
                "cohort_position",
                "dataset_index",
                "dataset_revision",
                "dataset_fingerprint",
            )
        },
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "request_started_monotonic_ns": record[
            "request_started_monotonic_ns"
        ],
        "request_finished_monotonic_ns": record["terminal_monotonic_ns"],
        "request_body": record["request_body"],
        "raw_response": raw_response,
        "output_token_ids": record["output_token_ids"],
        "completion_tokens": record["completion_tokens"],
        "request_record": record,
    }
    if api["status"] != "PASS":
        return api, {
            "schema_version": 1,
            "authorized_phase": "P04",
            "status": "NOT_REACHED",
            "arm": arm,
            "reason": "chat request did not succeed",
            "internal_states": [],
            "hedge_snapshots": [],
            "proposal_count": 0,
        }
    getter = server_info_get or _NoProxyJsonGet()
    server_info = getter(
        base_url.rstrip("/") + "/server_info",
        300.0,
    )
    counters = validate_server_info(server_info, arm=arm)
    counters["fetched_at_utc"] = _utc_now()
    counters["request_interval_monotonic_ns"] = {
        "start": api["request_started_monotonic_ns"],
        "end": api["request_finished_monotonic_ns"],
    }
    return api, counters


def _start_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    fields = stat[stat.rfind(")") + 2 :].split()
    return fields[19] if len(fields) > 19 else None


def wait_ready(
    *,
    base_url: str,
    server_pid: int,
    server_start_ticks: str,
    timeout_seconds: float,
    poll_seconds: float = 5.0,
    health_get: HealthGet | None = None,
    process_alive: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Wait up to one hour while continuously checking server PID reuse."""

    if not 0 < timeout_seconds <= 3600:
        raise ValueError("startup timeout must be in (0, 3600]")
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    getter = health_get or _NoProxyHealthGet()
    identity_is_alive = process_alive or (
        lambda: _start_ticks(server_pid) == server_start_ticks
    )
    while time.monotonic() - started < timeout_seconds:
        if not identity_is_alive():
            return {
                "schema_version": 1,
                "status": "server_exited_or_identity_changed",
                "server_pid": server_pid,
                "checks": checks[-20:],
            }
        try:
            status = getter(base_url.rstrip("/") + "/health", 5.0)
            checks.append({"at_utc": _utc_now(), "http_status": status})
            if status == 200:
                return {
                    "schema_version": 1,
                    "status": "ready",
                    "server_pid": server_pid,
                    "elapsed_seconds": time.monotonic() - started,
                    "checks": checks[-20:],
                }
        except Exception as error:
            checks.append({"at_utc": _utc_now(), "error": repr(error)})
        time.sleep(poll_seconds)
    return {
        "schema_version": 1,
        "status": "timeout",
        "server_pid": server_pid,
        "elapsed_seconds": time.monotonic() - started,
        "checks": checks[-20:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    ready = subparsers.add_parser("wait-ready")
    ready.add_argument("--base-url", required=True)
    ready.add_argument("--server-pid", type=int, required=True)
    ready.add_argument("--server-start-ticks", required=True)
    ready.add_argument("--timeout", type=float, default=3600)
    ready.add_argument("--output", type=Path, required=True)

    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--arm", choices=("native", "b0"), required=True)
    smoke.add_argument("--base-url", required=True)
    smoke.add_argument("--dataset", type=Path, required=True)
    smoke.add_argument("--api-output", type=Path, required=True)
    smoke.add_argument("--counters-output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "wait-ready":
        result = wait_ready(
            base_url=args.base_url,
            server_pid=args.server_pid,
            server_start_ticks=args.server_start_ticks,
            timeout_seconds=args.timeout,
        )
        _atomic_json(args.output, result)
        return 0 if result["status"] == "ready" else 1
    if args.command == "smoke":
        samples = load_jsonl(args.dataset)
        if len(samples) != 32:
            parser.error("P04 dataset must be the fixed 32-row calibration JSONL")
        try:
            api, counters = run_smoke(
                arm=args.arm,
                base_url=args.base_url,
                sample=samples[0],
            )
        except BaseException as error:
            api = {
                "schema_version": 1,
                "authorized_phase": "P04",
                "status": "FAIL",
                "arm": args.arm,
                "error_type": type(error).__name__,
                "error": repr(error),
            }
            counters = {
                "schema_version": 1,
                "authorized_phase": "P04",
                "status": "NOT_REACHED",
                "arm": args.arm,
                "reason": "client exception before counter validation",
                "internal_states": [],
                "hedge_snapshots": [],
                "proposal_count": 0,
            }
        _atomic_json(args.api_output, api)
        _atomic_json(args.counters_output, counters)
        return (
            0
            if api.get("status") == "PASS"
            and counters.get("status") == "PASS"
            else 1
        )
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
