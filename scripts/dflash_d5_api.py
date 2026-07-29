#!/usr/bin/env python3
"""Phase D5 sequential calibration/B0 client and frozen-q25 evidence builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import signal
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dflash_d1c_harness import run_cohort  # noqa: E402


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class HardStop(BaseException):
    """Escape the D1C retry loop at the operational deadline."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def request_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with OPENER.open(request, timeout=timeout) as response:
        body = json.loads(response.read())
    if not isinstance(body, dict):
        raise ValueError(f"{url} did not return an object")
    return body


def hedge_snapshot(server_info: dict[str, Any]) -> dict[str, Any]:
    states = server_info.get("internal_states")
    if not isinstance(states, list) or len(states) != 1:
        raise ValueError("expected one DP internal state")
    dflash = states[0].get("dflash_info_record")
    if not isinstance(dflash, dict) or not isinstance(dflash.get("hedge"), dict):
        raise ValueError("DFlash HEDGE snapshot is missing")
    return dflash["hedge"]


def validate_lifecycle(snapshot: dict[str, Any], *, expected_mode: str) -> None:
    if snapshot.get("mode") != expected_mode:
        raise ValueError(f"unexpected HEDGE mode: {snapshot.get('mode')!r}")
    if int(snapshot.get("proposal_width", -1)) != 7:
        raise ValueError("proposal width is not seven")
    proposals = int(snapshot.get("proposals", -1))
    if proposals < 1:
        raise ValueError("no DFlash proposals were observed")
    if int(snapshot.get("draft_tokens_verifiable", -1)) != proposals * 7:
        raise ValueError("verifiable draft counter is inconsistent")
    initialized = int(snapshot.get("requests_initialized", -1))
    finished = int(snapshot.get("requests_finished", -1))
    reuse_resets = int(snapshot.get("slot_reuse_resets", -1))
    non_natural = int(snapshot.get("requests_non_natural", -1))
    if initialized < 32:
        raise ValueError("fewer than 32 request initializations were observed")
    if min(finished, reuse_resets, non_natural) < 0:
        raise ValueError("negative request lifecycle counter")
    if initialized != finished + reuse_resets:
        raise ValueError("request lifecycle accounting is inconsistent")
    if non_natural > initialized:
        raise ValueError("non-natural terminal count exceeds initialized requests")
    if int(snapshot.get("active_request_states", -1)) != 0:
        raise ValueError("active HEDGE request state remains")
    if int(snapshot.get("state_leaks", -1)) != 0:
        raise ValueError("HEDGE request state leak")
    if snapshot.get("request_state", []) != []:
        raise ValueError("request_state was not cleared")


def build_calibration(snapshot: dict[str, Any]) -> tuple[list[dict], dict, dict]:
    validate_lifecycle(snapshot, expected_mode="calibration")
    if snapshot.get("config") is not None:
        raise ValueError("native calibration unexpectedly has a decode config")
    dropped = int(snapshot.get("trace_rows_dropped", -1))
    if dropped != 0:
        raise ValueError(f"calibration trace dropped {dropped} rows")
    trace = snapshot.get("strict_rejection_trace")
    if not isinstance(trace, list):
        raise ValueError("strict_rejection_trace is not a list")
    values: list[float] = []
    clean_trace: list[dict] = []
    for index, raw in enumerate(trace):
        if not isinstance(raw, dict):
            raise ValueError(f"trace row {index} is not an object")
        regret = float(raw.get("regret", math.nan))
        value = float(raw.get("value", math.nan))
        ratio = float(raw.get("regret_per_value", math.nan))
        if not all(math.isfinite(item) and item > 0 for item in (regret, value, ratio)):
            raise ValueError(f"trace row {index} is not finite and positive")
        if not math.isclose(regret / value, ratio, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"trace row {index} ratio is not reproducible")
        clean_trace.append(dict(raw))
        values.append(ratio)
    distribution = {
        "schema_version": 1,
        "source": "first strict-rejection barrier positive regret_per_value",
        "count": len(values),
        "values_in_trace_order": values,
        "values_sorted": sorted(values),
        "numpy_version": np.__version__,
        "quantile": 0.25,
        "quantile_method": "linear",
    }
    if not values:
        calibration = {
            "schema_version": 1,
            "status": "CALIBRATION_EMPTY",
            "q25": None,
            "frozen_config": None,
            "numpy_version": np.__version__,
            "quantile": 0.25,
            "quantile_method": "linear",
        }
        return clean_trace, distribution, calibration
    q25 = float(np.quantile(np.asarray(values, dtype=np.float64), 0.25, method="linear"))
    config = {
        "B": q25,
        "g": q25,
        "m": 1,
        "value_scheme": "normalized_suffix",
        "block_size": 7,
    }
    encoded = canonical(config).encode()
    calibration = {
        "schema_version": 1,
        "status": "FROZEN",
        "q25": q25,
        "positive_ratio_count": len(values),
        "numpy_version": np.__version__,
        "quantile": 0.25,
        "quantile_method": "linear",
        "frozen_config": config,
        "config_canonical_json": encoded.decode(),
        "config_sha256": hashlib.sha256(encoded).hexdigest(),
        "parameter_rule": "g=q25, B=g, m=1, value_scheme=normalized_suffix",
    }
    return clean_trace, distribution, calibration


def validate_native_run(native_run: Path) -> dict[str, Any]:
    complete = json.loads((native_run / ".complete.json").read_text())
    summary = json.loads((native_run / "summary.json").read_text())
    calibration = json.loads((native_run / "calibration.json").read_text())
    if complete.get("status") != "PASS" or summary.get("status") != "PASS":
        raise ValueError("native calibration attempt is not sealed PASS")
    if calibration.get("status") != "FROZEN":
        raise ValueError("native calibration did not freeze q25")
    config = calibration.get("frozen_config")
    if canonical(config) != calibration.get("config_canonical_json"):
        raise ValueError("frozen config canonical JSON mismatch")
    digest = hashlib.sha256(canonical(config).encode()).hexdigest()
    if digest != calibration.get("config_sha256"):
        raise ValueError("frozen config hash mismatch")
    return config


def b0_config(native_run: Path) -> dict[str, Any]:
    """Derive the protocol B=0 config without mutating the frozen B+ config."""

    config = dict(validate_native_run(native_run))
    config["B"] = 0
    return config


def emit_config(args: argparse.Namespace) -> int:
    print(canonical(b0_config(args.native_run)))
    return 0


def _arm_paths(scratch: Path, arm: str) -> tuple[Path, Path]:
    output = scratch / (
        "native_calibration_outputs.jsonl" if arm == "native" else "b0_outputs.jsonl"
    )
    return output, scratch / "cohort_summary.json"


def _install_deadline(hard_stop_utc: str) -> None:
    deadline = datetime.fromisoformat(hard_stop_utc.replace("Z", "+00:00"))
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise HardStop("D5 hard stop already reached")

    def stop(_signum: int, _frame: Any) -> None:
        raise HardStop("D5 absolute hard stop reached")

    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, remaining)


def compare_b0_outputs(
    native_rows: list[dict[str, Any]],
    b0_rows: list[dict[str, Any]],
    hedge_snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare full token IDs after proving both cohorts have identical identity."""

    if len(native_rows) != 32 or len(b0_rows) != 32:
        raise ValueError(
            "B0 comparison requires exactly 32 native and 32 B0 rows: "
            f"native={len(native_rows)} b0={len(b0_rows)}"
        )
    comparisons = []
    for index, (native, b0) in enumerate(zip(native_rows, b0_rows)):
        for field in ("request_index", "cohort_position", "dataset_index", "prompt"):
            if native.get(field) != b0.get(field):
                raise ValueError(
                    f"B0 sample identity/order mismatch at row {index}: {field}"
                )
        left = [int(token) for token in native["output_token_ids"]]
        right = [int(token) for token in b0["output_token_ids"]]
        divergence = next(
            (i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]),
            min(len(left), len(right)) if len(left) != len(right) else None,
        )
        comparisons.append(
            {
                "request_index": index,
                "cohort_position": native["cohort_position"],
                "dataset_index": native["dataset_index"],
                "prompt_sha256": hashlib.sha256(
                    native["prompt"].encode("utf-8")
                ).hexdigest(),
                "identical": left == right,
                "first_divergence_token_position": divergence,
                "native_output_token_ids": left,
                "b0_output_token_ids": right,
            }
        )
    mismatches = [row for row in comparisons if not row["identical"]]
    comparison = {
        "schema_version": 1,
        "status": "PASS" if not mismatches else "FAIL",
        "compared": len(comparisons),
        "identical": len(comparisons) - len(mismatches),
        "mismatches": len(mismatches),
        "samples": comparisons,
    }
    if not mismatches:
        counterexample = {"schema_version": 1, "status": "NOT_APPLICABLE"}
    else:
        first = mismatches[0]
        row_index = int(first["request_index"])
        native = native_rows[row_index]
        b0 = b0_rows[row_index]
        counterexample = {
            "schema_version": 1,
            "status": "B0_TOKEN_ID_MISMATCH",
            **first,
            "prompt": native["prompt"],
            "question": native.get("question"),
            "native_model_text": native.get("model_text"),
            "b0_model_text": b0.get("model_text"),
            "native_terminal_state": native.get("terminal_state"),
            "b0_terminal_state": b0.get("terminal_state"),
            "hedge_snapshot": hedge_snapshot,
        }
    return comparison, counterexample


def run_arm(args: argparse.Namespace) -> int:
    scratch: Path = args.scratch
    result = {
        "schema_version": 1,
        "phase": "D5",
        "arm": args.arm,
        "status": "FAIL",
        "arm_pass": False,
        "started_at_utc": utc_now(),
        "hard_stop_utc": args.hard_stop_utc,
    }
    _install_deadline(args.hard_stop_utc)
    output_path, cohort_summary_path = _arm_paths(scratch, args.arm)
    marker = scratch / "request.active"
    try:
        if args.arm == "b0":
            expected_config = b0_config(args.native_run)
            for name in (
                "native_calibration_outputs.jsonl",
                "first_rejection_trace.jsonl",
                "ratio_distribution.json",
                "calibration.json",
            ):
                shutil.copy2(args.native_run / name, scratch / name)
        else:
            expected_config = None
        samples = [
            json.loads(line)
            for line in args.dataset.read_text().splitlines()
            if line.strip()
        ]
        if len(samples) != 32:
            raise ValueError("D5 calibration dataset must contain 32 rows")
        marker.write_text(utc_now() + "\n")
        try:
            cohort = run_cohort(
                samples,
                cohort_kind="calibration",
                base_url=args.base_url,
                model=args.model,
                output_path=output_path,
                summary_path=cohort_summary_path,
                max_attempts=3,
                request_timeout_seconds=args.timeout,
                retry_backoff_seconds=1,
            )
        finally:
            marker.unlink(missing_ok=True)
        shutil.copy2(output_path, scratch / "requests.jsonl")
        if not cohort["all_terminal"] or cohort["terminal_counts"]["request_failure"]:
            raise ValueError("not all 32 requests reached a successful terminal state")
        info = request_json(args.base_url.rstrip("/") + "/get_server_info", 30)
        snapshot = hedge_snapshot(info)
        if args.arm == "native":
            trace, distribution, calibration = build_calibration(snapshot)
            with (scratch / "first_rejection_trace.jsonl").open("w") as stream:
                for row in trace:
                    stream.write(canonical(row) + "\n")
            write_json(scratch / "ratio_distribution.json", distribution)
            write_json(scratch / "calibration.json", calibration)
            arm_pass = calibration["status"] == "FROZEN"
            b0_status = None
        else:
            validate_lifecycle(snapshot, expected_mode="enabled")
            if snapshot.get("config") != expected_config:
                raise ValueError("B0 runtime config differs from frozen q25 config")
            strict = int(snapshot.get("strict_accepted_draft_tokens", -1))
            accepted = int(snapshot.get("hedge_accepted_draft_tokens", -2))
            if strict != accepted:
                raise ValueError("B0 strict/HEDGE acceptance counters differ")
            if int(snapshot.get("relaxed_mismatches", -1)) != 0:
                raise ValueError("B0 relaxed a mismatch")
            if float(snapshot.get("regret_charged", math.nan)) != 0.0:
                raise ValueError("B0 charged regret")
            native_rows = [
                json.loads(line)
                for line in (args.native_run / "native_calibration_outputs.jsonl")
                .read_text()
                .splitlines()
            ]
            b0_rows = [json.loads(line) for line in output_path.read_text().splitlines()]
            comparison, counterexample = compare_b0_outputs(
                native_rows,
                b0_rows,
                snapshot,
            )
            write_json(scratch / "b0_comparison.json", comparison)
            write_json(scratch / "b0_minimal_counterexample.json", counterexample)
            arm_pass = comparison["status"] == "PASS"
            b0_status = "PASS" if arm_pass else "FAIL"
        write_json(
            scratch / "hedge_counters.json",
            {
                "schema_version": 1,
                "phase": "D5",
                "arm": args.arm,
                "status": "PASS",
                "hedge": snapshot,
            },
        )
        result.update(
            status="PASS" if arm_pass else "FAIL",
            arm_pass=arm_pass,
            request_count=32,
            cohort_summary=cohort,
            b0_status=b0_status,
            server_info_after=info,
        )
    except BaseException as error:
        result.update(
            status="FAIL",
            arm_pass=False,
            error_type=type(error).__name__,
            error=str(error),
        )
        write_json(
            scratch / "hedge_counters.json",
            {"schema_version": 1, "status": "FAIL", "error": repr(error)},
        )
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        marker.unlink(missing_ok=True)
        result["finished_at_utc"] = utc_now()
        write_json(scratch / "api_smoke.json", result)
    return 0 if result["arm_pass"] else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config")
    config.add_argument("--native-run", type=Path, required=True)
    config.set_defaults(handler=emit_config)
    run = commands.add_parser("run")
    run.add_argument("--arm", choices=("native", "b0"), required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--scratch", type=Path, required=True)
    run.add_argument("--native-run", type=Path, required=True)
    run.add_argument("--hard-stop-utc", required=True)
    run.add_argument("--timeout", type=float, default=300)
    run.set_defaults(handler=run_arm)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
