#!/usr/bin/env python3
"""Validate and materialize the frozen Phase 05 launch baseline."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

REQUIRED_ARGS = {
    "--tp-size": "4",
    "--speculative-algorithm": "DSPARK",
    "--speculative-dspark-block-size": "5",
    "--moe-runner-backend": "flashinfer_mxfp4",
    "--speculative-moe-runner-backend": "flashinfer_mxfp4",
    "--context-length": "4096",
    "--max-running-requests": "1",
    "--mem-fraction-static": "0.80",
}
REQUIRED_FLAGS = {
    "--disable-cuda-graph",
    "--disable-overlap-schedule",
    "--disable-radix-cache",
}


def load_and_validate(path: Path) -> dict:
    config = json.loads(path.read_text())
    command = config["command"]
    if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
        raise ValueError("command must be a list of strings")
    for flag, value in REQUIRED_ARGS.items():
        index = command.index(flag)
        if command[index + 1] != value:
            raise ValueError(f"{flag} must resolve to {value}")
    missing = REQUIRED_FLAGS.difference(command)
    if missing:
        raise ValueError(f"missing flags: {sorted(missing)}")
    if "--speculative-draft-model-path" in command:
        raise ValueError("bundled DSpark draft path must be auto-resolved")
    environment = config["environment"]
    if environment["SGLANG_RAGGED_VERIFY_MODE"] != "static":
        raise ValueError("ragged verify must be static")
    if environment["SGLANG_DSV4_FP4_EXPERTS"] != "1":
        raise ValueError("packed FP4 experts must be enabled")
    if "SGLANG_DSV4_FP4_DEQUANT" in environment:
        raise ValueError("FP4 dequant must not be exported")
    if "SGLANG_DSV4_FP4_DEQUANT" not in config["unset_environment"]:
        raise ValueError("FP4 dequant must be explicitly unset")
    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-config", type=Path)
    parser.add_argument("--output-command", type=Path)
    parser.add_argument("--print-command-null", action="store_true")
    args = parser.parse_args()
    config = load_and_validate(args.config)
    if args.output_config:
        args.output_config.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n"
        )
    if args.output_command:
        env = " ".join(
            f"{key}={shlex.quote(value)}"
            for key, value in sorted(config["environment"].items())
        )
        unset = " ".join(f"unset {key};" for key in config["unset_environment"])
        command = shlex.join(config["command"])
        args.output_command.write_text(f"{unset} env {env} {command}\n")
    if args.print_command_null:
        import sys

        for item in config["command"]:
            sys.stdout.buffer.write(item.encode() + b"\0")


if __name__ == "__main__":
    main()
