#!/usr/bin/env python3
"""Atomically publish a passing checkpoint identity as the P00 canonical file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    run_root = Path("/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark")
    if run_root not in args.source.parents or run_root not in args.destination.parents:
        raise SystemExit("checkpoint identity paths are outside the run root")
    if args.destination.exists():
        raise SystemExit(f"refusing existing destination: {args.destination}")
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS":
        raise SystemExit("refusing to publish a non-PASS checkpoint identity")
    temporary = args.destination.with_name(
        f".{args.destination.name}.tmp-{os.getpid()}"
    )
    temporary.write_bytes(args.source.read_bytes())
    os.replace(temporary, args.destination)
    print(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
