#!/usr/bin/env python3
"""Read only the already-downloaded safetensors header of a D1A partial."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import struct


REVISION = "e44fc94ceb1e7ed45550d15e782aeadd08050483"
ROOT = pathlib.Path("/tmp/deepspec-hedge-dflash/d1a")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_id")
    args = parser.parse_args()
    if not re.fullmatch(
        r"dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z", args.attempt_id
    ):
        raise SystemExit("invalid attempt id")
    partial = (
        ROOT
        / f".staging-primary-{REVISION}-{args.attempt_id}"
        / "model.safetensors.partial"
    )
    with partial.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise RuntimeError("safetensors prefix is not available")
        header_length = struct.unpack("<Q", raw_length)[0]
        raw_header = handle.read(header_length)
    if len(raw_header) != header_length:
        raise RuntimeError("safetensors header is not fully available")
    header = json.loads(raw_header)
    tensors = {
        name: value
        for name, value in header.items()
        if name != "__metadata__"
    }
    layer_indices = sorted(
        {
            int(match.group(1))
            for name in tensors
            if (
                match := re.search(r"(?:^|\.)layers\.(\d+)\.", name)
            )
        }
    )
    output = {
        "path": str(partial),
        "partial_size_bytes": partial.stat().st_size,
        "header_length_bytes": header_length,
        "tensor_count": len(tensors),
        "layer_indices": layer_indices,
        "target_width_16384": [
            {"name": name, "shape": value["shape"]}
            for name, value in sorted(tensors.items())
            if 16384 in value["shape"]
        ],
        "draft_vocab_32000": [
            {"name": name, "shape": value["shape"]}
            for name, value in sorted(tensors.items())
            if 32000 in value["shape"]
        ],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
