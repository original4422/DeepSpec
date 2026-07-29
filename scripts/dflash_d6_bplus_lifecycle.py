#!/usr/bin/env python3
"""B+ configuration adapter over the sealed D6 native lifecycle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dflash_d6_lifecycle as native  # noqa: E402


REPO = Path(
    "/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
)
BPLUS_API = REPO / "scripts/dflash_d6_bplus_api.py"
C1_ACCEPTANCE = (
    REPO
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/"
    "continuation-c1/continuation_c1_acceptance.json"
)
C2_ACCEPTANCE = (
    REPO
    / "docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/"
    "continuation-c2/continuation_c2_acceptance.json"
)
EXPECTED_CONFIG = {
    "B": 12.5,
    "block_size": 7,
    "g": 12.5,
    "m": 1,
    "value_scheme": "normalized_suffix",
}
EXPECTED_CANONICAL = (
    '{"B":12.5,"block_size":7,"g":12.5,"m":1,'
    '"value_scheme":"normalized_suffix"}'
)
EXPECTED_SHA256 = (
    "ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746"
)
MAXIMUM_LIVE_ATTEMPTS = 3

_NATIVE_SERVER_ENVIRONMENT = native.server_environment
_NATIVE_CONTRACT = native.contract
_NATIVE_WRITE_JSON = native.write_json


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def load_protocol_identity(
    c1_path: Path = C1_ACCEPTANCE,
    c2_path: Path = C2_ACCEPTANCE,
) -> dict[str, Any]:
    """Load the sole frozen B+ config and require the sealed B0 PASS gate."""

    c1 = json.loads(c1_path.read_text())
    c2 = json.loads(c2_path.read_text())
    calibration = c1.get("calibration")
    comparison = c2.get("b0_comparison")
    configuration = c2.get("configuration")
    if (
        c1.get("phase") != "CONTINUATION_C1"
        or c1.get("status") != "PASS"
        or not isinstance(calibration, Mapping)
        or calibration.get("status") != "FROZEN"
        or calibration.get("q25") != 12.5
    ):
        raise ValueError("C1 frozen calibration acceptance is not PASS")
    config = calibration.get("frozen_config")
    if config != EXPECTED_CONFIG:
        raise ValueError("C1 frozen B+ config differs from the protocol")
    rendered = canonical(config)
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    if (
        rendered != EXPECTED_CANONICAL
        or digest != EXPECTED_SHA256
        or calibration.get("config_sha256") != EXPECTED_SHA256
    ):
        raise ValueError("C1 frozen B+ config canonical identity changed")
    if (
        c2.get("phase") != "CONTINUATION_C2"
        or c2.get("status") != "PASS"
        or not isinstance(comparison, Mapping)
        or comparison.get("status") != "PASS"
        or comparison.get("mismatches") != 0
        or comparison.get("full_output_token_ids_identical") != 32
        or not isinstance(configuration, Mapping)
        or configuration.get("frozen_bplus_config_sha256") != EXPECTED_SHA256
    ):
        raise ValueError("C2 sealed result is not protocol B0 PASS")
    return {
        "schema_version": 1,
        "config": dict(config),
        "canonical_json": rendered,
        "sha256": digest,
        "c1_status": c1["status"],
        "c2_status": c2["status"],
        "b0_status": comparison["status"],
        "c1_acceptance": str(c1_path),
        "c2_acceptance": str(c2_path),
    }


def paths(attempt_id: str) -> tuple[Path, Path]:
    if not re.fullmatch(
        r"dflash-d6-bplus-\d{8}T\d{6}Z-a\d{2}", attempt_id
    ):
        raise ValueError("invalid D6 B+ attempt ID")
    return native.RUN_ROOT / attempt_id, native.HDFS_RUN_ROOT / attempt_id


def server_environment() -> dict[str, str]:
    identity = load_protocol_identity()
    environment = _NATIVE_SERVER_ENVIRONMENT()
    environment["HEDGE_ENABLED"] = "1"
    environment["SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE"] = "0"
    environment["SGLANG_DFLASH_HEDGE_CONFIG_JSON"] = identity["canonical_json"]
    environment.pop("SGLANG_DFLASH_HEDGE_CONFIG_PATH", None)
    return environment


def contract(hard_stop_utc: str) -> dict[str, Any]:
    identity = load_protocol_identity()
    document = copy.deepcopy(_NATIVE_CONTRACT(hard_stop_utc))
    environment = server_environment()
    document.update(
        arm="B+",
        hedge_enabled=True,
        calibration_trace=False,
        hedge_config=identity["config"],
        hedge_config_canonical_json=identity["canonical_json"],
        hedge_config_sha256=identity["sha256"],
        b0_status=identity["b0_status"],
        c1_acceptance=identity["c1_acceptance"],
        c2_acceptance=identity["c2_acceptance"],
        prep_live_attempts_used=0,
        maximum_live_attempts=MAXIMUM_LIVE_ATTEMPTS,
    )
    document["environment"] = {
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
            "SGLANG_DFLASH_HEDGE_CONFIG_JSON",
        )
    }
    document["unset_environment"] = [
        "SGLANG_DSV4_FP4_DEQUANT",
        "SGLANG_DFLASH_HEDGE_CONFIG_PATH",
    ]
    return document


def adapt_document(path: Path, value: Any) -> Any:
    """Relabel native lifecycle-owned metadata before hashing and sealing."""

    if not isinstance(value, Mapping):
        return value
    document = copy.deepcopy(dict(value))
    if document.get("phase") != "D6":
        return document
    identity = load_protocol_identity()
    if document.get("arm") == "native":
        document["arm"] = "B+"
    if path.name in {
        "source_identity.json",
        "hedge_counters.json",
        "summary.json",
        "api_smoke.json",
    }:
        document["hedge_enabled"] = True
        document["calibration_trace"] = False
        if "config" in document:
            document["config"] = identity["config"]
        document["hedge_config"] = identity["config"]
        document["hedge_config_sha256"] = identity["sha256"]
        document["b0_status"] = identity["b0_status"]
    if path.name == "summary.json":
        counters_path = path.parent / "hedge_counters.json"
        if counters_path.is_file():
            counters = json.loads(counters_path.read_text())
            risk_audit = counters.get("risk_lifecycle_audit")
            if isinstance(risk_audit, Mapping):
                document["risk_lifecycle_audit"] = copy.deepcopy(
                    dict(risk_audit)
                )
            formal_delta = counters.get("formal_hedge_counter_delta")
            if isinstance(formal_delta, Mapping):
                document["formal_hedge_counter_delta"] = copy.deepcopy(
                    dict(formal_delta)
                )
    return document


def adapted_write_json(path: Path, value: Any) -> None:
    _NATIVE_WRITE_JSON(path, adapt_document(path, value))


def configure_native_adapter() -> None:
    """Configure the imported lifecycle only inside this B+ process."""

    native.API = BPLUS_API
    native.paths = paths
    native.server_environment = server_environment
    native.contract = contract
    native.write_json = adapted_write_json


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("action", choices=("contract", "preflight", "live"))
    root.add_argument("attempt_id")
    root.add_argument("hard_stop_utc")
    return root


def main() -> int:
    args = parser().parse_args()
    paths(args.attempt_id)
    if args.action == "contract":
        print(json.dumps(contract(args.hard_stop_utc), indent=2, sort_keys=True))
        return 0
    configure_native_adapter()
    if args.action == "preflight":
        print(
            json.dumps(
                native.preflight(args.attempt_id, args.hard_stop_utc),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    return native.live(args.attempt_id, args.hard_stop_utc)


if __name__ == "__main__":
    raise SystemExit(main())
