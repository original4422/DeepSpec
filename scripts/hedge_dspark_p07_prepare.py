#!/usr/bin/env python3
"""Resolve the frozen P07 HEDGE-on formal contract."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deepspec.hedge_spec.config import HedgeConfig  # noqa: E402
from deepspec.hedge_protocol.io import sha256_file  # noqa: E402
from hedge_dspark_p04_prepare import (  # noqa: E402
    EXPECTED_WORKER,
    RUN_ROOT,
    _atomic_json,
    _check_fixed_port,
    _emit_nul,
    _fingerprint,
    _gpu_inventory_query,
    _wait_no_cuda_contexts,
    build_checkpoint_identity,
    build_engine_identity,
    parse_gpu_inventory,
    parse_keepalive_status,
)
from hedge_dspark_p06_prepare import (  # noqa: E402
    DATASET_MANIFEST,
    FROZEN_CONFIG,
    FROZEN_CONFIG_FINGERPRINT,
    FROZEN_CONFIG_SHA256,
    resolve_attempt as resolve_native_attempt,
    validate_formal_datasets,
)


P06_ATTEMPT_ID = "20260729T062241Z-p06-native-formal-r1"
P06_ARCHIVE = RUN_ROOT / P06_ATTEMPT_ID
ATTEMPT_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z-p07-hedge-formal"
    r"(?:-[a-z0-9][a-z0-9-]{0,63})?$"
)
SCRATCH_ENVIRONMENT_KEYS = {
    "FLASHINFER_WORKSPACE_BASE",
    "SGLANG_CACHE_DIR",
    "TORCH_EXTENSIONS_DIR",
    "TRITON_CACHE_DIR",
}
HEDGE_ENVIRONMENT_KEYS = {
    "HEDGE_ENABLED",
    "SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE",
    "SGLANG_DSPARK_HEDGE_CONFIG_PATH",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path} must contain an object")
    return value


def _native_attempt_id(attempt_id: str) -> str:
    return attempt_id.replace(
        "-p07-hedge-formal", "-p06-native-formal", 1
    )


def _resolved_parity(
    hedge: Mapping[str, Any], native: Mapping[str, Any]
) -> dict[str, Any]:
    archive_manifest = _load_object(P06_ARCHIVE / "archive_manifest.json")
    artifact_validation = _load_object(
        P06_ARCHIVE / "artifact_validation.json"
    )
    hedge_environment = hedge["server"]["environment"]
    native_environment = native["server"]["environment"]
    static_keys = (
        set(native_environment)
        - SCRATCH_ENVIRONMENT_KEYS
        - HEDGE_ENVIRONMENT_KEYS
    )
    hedge_decode = dict(hedge["decode_affecting"])
    native_decode = dict(native["decode_affecting"])
    for key in (
        "hedge_enabled",
        "hedge_calibration_trace",
        "hedge_trace_capacity",
        "hedge_config",
    ):
        hedge_decode.pop(key, None)
        native_decode.pop(key, None)
    checks = {
        "p06_archive_complete": all(
            (P06_ARCHIVE / name).is_file()
            for name in (
                "resolved_config.json",
                "engine_identity.json",
                "checkpoint_identity.json",
                "archive_manifest.json",
            )
        ),
        "p06_archive_pass": (
            archive_manifest.get("status") == "PASS"
            and archive_manifest.get("authorized_phase") == "P06"
            and archive_manifest.get("arm") == "native"
            and archive_manifest.get("destination") == str(P06_ARCHIVE)
            and artifact_validation.get("status") == "PASS"
            and artifact_validation.get("authorized_phase") == "P06"
            and artifact_validation.get("arm") == "native"
        ),
        "server_command": (
            hedge["server"]["command"] == native["server"]["command"]
        ),
        "server_unset_environment": (
            hedge["server"]["unset_environment"]
            == native["server"]["unset_environment"]
        ),
        "api": hedge["api"] == native["api"],
        "worker": hedge["worker_id"] == native["worker_id"],
        "dataset": hedge["dataset"] == native["dataset"],
        "formal_protocol": (
            hedge["formal_protocol"] == native["formal_protocol"]
        ),
        "p05_freeze": hedge["p05_freeze"] == native["p05_freeze"],
        "static_environment": all(
            hedge_environment.get(key) == native_environment.get(key)
            for key in static_keys
        ),
        "scratch_environment_only": all(
            str(hedge["scratch"]) in str(hedge_environment[key])
            for key in SCRATCH_ENVIRONMENT_KEYS
        ),
        "decode_non_hedge_fields": hedge_decode == native_decode,
    }
    _require(all(checks.values()), f"P06 resolved identity parity failed: {checks}")
    return {
        "status": "PASS",
        "reference_attempt_id": P06_ATTEMPT_ID,
        "reference_archive": str(P06_ARCHIVE),
        "reference_artifacts": {
            name: sha256_file(P06_ARCHIVE / name)
            for name in (
                "resolved_config.json",
                "engine_identity.json",
                "checkpoint_identity.json",
                "artifact_validation.json",
                "archive_manifest.json",
            )
        },
        "allowed_differences": [
            "authorized_phase",
            "arm",
            "attempt_id",
            "scratch",
            "hdfs_run",
            "scratch-scoped cache paths",
            "HEDGE enable/config fields",
            "decode_config_fingerprint",
        ],
        "checks": checks,
    }


def resolve_attempt(*, attempt_id: str, scratch: Path) -> dict[str, Any]:
    """Derive P07 from the accepted P06 contract and change only HEDGE state."""

    _require(
        ATTEMPT_PATTERN.fullmatch(attempt_id) is not None,
        "attempt-id does not match the P07 HEDGE formal pattern",
    )
    scratch = scratch.resolve()
    _require(scratch.is_dir(), f"scratch directory does not exist: {scratch}")
    _require(
        sha256_file(FROZEN_CONFIG) == FROZEN_CONFIG_SHA256,
        "P05 frozen config bytes changed",
    )
    config = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    canonical = HedgeConfig.from_mapping(config)
    _require(
        canonical.to_mapping() == config
        and canonical.fingerprint() == FROZEN_CONFIG_FINGERPRINT,
        "P05 frozen config semantic identity changed",
    )
    native = resolve_native_attempt(
        attempt_id=_native_attempt_id(attempt_id),
        scratch=scratch,
    )
    archived_native = _load_object(P06_ARCHIVE / "resolved_config.json")
    config_path = scratch / "hedge_config.json"
    resolved = dict(native)
    resolved.update(
        authorized_phase="P07",
        arm="hedge",
        attempt_id=attempt_id,
        hdfs_run=str(RUN_ROOT / attempt_id),
    )
    server = dict(native["server"])
    environment = dict(server["environment"])
    environment.update(
        HEDGE_ENABLED="1",
        SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE="0",
        SGLANG_DSPARK_HEDGE_CONFIG_PATH=str(config_path),
    )
    environment.pop("SGLANG_DSPARK_HEDGE_TRACE_CAPACITY", None)
    server["environment"] = environment
    resolved["server"] = server
    resolved["hedge"] = {
        "mode": "enabled",
        "enabled": True,
        "calibration_trace": False,
        "config": config,
        "config_path": str(config_path),
        "config_sha256": FROZEN_CONFIG_SHA256,
        "config_fingerprint": FROZEN_CONFIG_FINGERPRINT,
    }
    decode = dict(native["decode_affecting"])
    decode.update(
        hedge_enabled=True,
        hedge_calibration_trace=False,
        hedge_trace_capacity=None,
        hedge_config={
            "mapping": config,
            "path": str(config_path),
            "sha256": FROZEN_CONFIG_SHA256,
            "fingerprint": FROZEN_CONFIG_FINGERPRINT,
        },
    )
    resolved["decode_affecting"] = decode
    resolved["decode_config_fingerprint"] = _fingerprint(decode)
    resolved["p06_identity_parity"] = _resolved_parity(
        resolved, archived_native
    )
    return resolved


def _without_phase(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("authorized_phase", None)
    return result


def validate_runtime_identity_parity(
    *,
    engine: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare only stable source/wheel/model identity to accepted P06."""

    p06_engine = _load_object(P06_ARCHIVE / "engine_identity.json")
    p06_checkpoint = _load_object(P06_ARCHIVE / "checkpoint_identity.json")
    wheel = dict(engine.get("wheel", {}))
    p06_wheel = dict(p06_engine.get("wheel", {}))
    # The disposable build file may appear/disappear after the wheel was
    # atomically published. Its pinned bytes and installed content are stable.
    wheel.pop("build_path_exists", None)
    p06_wheel.pop("build_path_exists", None)
    checks = {
        "source": engine.get("source") == p06_engine.get("source"),
        "wheel": wheel == p06_wheel,
        "dspark_integration": (
            engine.get("dspark_integration")
            == p06_engine.get("dspark_integration")
        ),
        "hedge_core": (
            engine.get("hedge_core") == p06_engine.get("hedge_core")
        ),
        "checkpoint_identity": (
            _without_phase(checkpoint)
            == _without_phase(p06_checkpoint)
        ),
    }
    _require(
        all(checks.values()),
        f"P06 source/wheel/model identity parity failed: {checks}",
    )
    return {"status": "PASS", "checks": checks}


def prepare_attempt(
    *, attempt_id: str, scratch: Path, inventory_payload: str
) -> dict[str, Any]:
    resolved = resolve_attempt(attempt_id=attempt_id, scratch=scratch)
    config_path = Path(resolved["hedge"]["config_path"])
    with config_path.open("xb") as output:
        output.write(FROZEN_CONFIG.read_bytes())
    _require(
        sha256_file(config_path) == FROZEN_CONFIG_SHA256,
        "materialized runtime config hash mismatch",
    )
    resolved["gpu_inventory"] = parse_gpu_inventory(inventory_payload)
    engine = build_engine_identity(
        decode_config_fingerprint=resolved["decode_config_fingerprint"]
    )
    checkpoint = build_checkpoint_identity()
    engine["authorized_phase"] = "P07"
    checkpoint["authorized_phase"] = "P07"
    resolved["p06_runtime_identity_parity"] = (
        validate_runtime_identity_parity(
            engine=engine,
            checkpoint=checkpoint,
        )
    )
    _atomic_json(scratch / "resolved_config.json", resolved)
    _atomic_json(scratch / "engine_identity.json", engine)
    _atomic_json(scratch / "checkpoint_identity.json", checkpoint)
    with DATASET_MANIFEST.open("rb") as source, (
        scratch / "dataset_manifest.json"
    ).open("xb") as destination:
        shutil.copyfileobj(source, destination, 1024 * 1024)
    return {
        "schema_version": 1,
        "authorized_phase": "P07",
        "status": "PASS",
        "arm": "hedge",
        "attempt_id": attempt_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--attempt-id", required=True)
    resolve.add_argument("--scratch", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--worker-id", required=True)
    prepare.add_argument("--attempt-id", required=True)
    prepare.add_argument("--scratch", type=Path, required=True)
    for name in ("emit-command", "emit-environment"):
        command = commands.add_parser(name)
        command.add_argument("--resolved", type=Path, required=True)
    keepalive = commands.add_parser("parse-keepalive")
    keepalive.add_argument("--worker-id", required=True)
    keepalive.add_argument("--input", type=Path, required=True)
    keepalive.add_argument("--output", type=Path, required=True)
    contexts = commands.add_parser("wait-no-contexts")
    contexts.add_argument("--worker-id", required=True)
    contexts.add_argument("--output", type=Path, required=True)
    contexts.add_argument("--timeout", type=int, default=120)
    port = commands.add_parser("check-port")
    port.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    worker = getattr(args, "worker_id", EXPECTED_WORKER)
    if worker != EXPECTED_WORKER:
        parser.error(f"only worker {EXPECTED_WORKER} is authorized")
    if args.command == "resolve":
        result = resolve_attempt(attempt_id=args.attempt_id, scratch=args.scratch)
        _atomic_json(args.scratch / "resolved_config.json", result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "prepare":
        inventory = _gpu_inventory_query()
        result = prepare_attempt(
            attempt_id=args.attempt_id,
            scratch=args.scratch,
            inventory_payload=inventory,
        )
        _atomic_json(
            args.scratch / "gpu_inventory.json",
            {
                "schema_version": 1,
                "authorized_phase": "P07",
                "status": "PASS",
                "worker_id": EXPECTED_WORKER,
                "gpus": parse_gpu_inventory(inventory),
            },
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    resolved = (
        _load_object(args.resolved)
        if hasattr(args, "resolved")
        else None
    )
    if args.command == "emit-command":
        _emit_nul([str(item) for item in resolved["server"]["command"]])
        return 0
    if args.command == "emit-environment":
        _emit_nul(
            [
                f"{key}={value}"
                for key, value in sorted(
                    resolved["server"]["environment"].items()
                )
            ]
        )
        return 0
    if args.command == "parse-keepalive":
        record = parse_keepalive_status(args.input.read_text(encoding="utf-8"))
        record["authorized_phase"] = "P07"
        _atomic_json(args.output, record)
        return 0
    if args.command == "wait-no-contexts":
        _wait_no_cuda_contexts(output=args.output, timeout=args.timeout)
        return 0
    if args.command == "check-port":
        _check_fixed_port()
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
