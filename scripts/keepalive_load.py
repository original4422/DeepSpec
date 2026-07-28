#!/usr/bin/env python3
"""Sustain and verify per-GPU utilization for the DSpark worker.

The ``check`` command uses only the Python standard library. Torch is imported
only by ``load``, so a health check never creates a CUDA context.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
import signal
import statistics
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


DEFAULT_EXPECTED_GPUS = 4
DEFAULT_MINIMUM_UTILIZATION = 40.0
PLATFORM_RECLAMATION_THRESHOLD = 30.0


def validate_policy(
    *,
    expected_gpus: int,
    minimum_utilization: float,
    platform_reclamation_threshold: float,
) -> dict[str, int | float]:
    """Validate an exact GPU count and a retention threshold with headroom."""

    if isinstance(expected_gpus, bool) or expected_gpus <= 0:
        raise ValueError("expected_gpus must be a positive integer")
    if not 0.0 <= platform_reclamation_threshold < 100.0:
        raise ValueError(
            "platform_reclamation_threshold must be in [0, 100)"
        )
    if not (
        platform_reclamation_threshold < minimum_utilization <= 100.0
    ):
        raise ValueError(
            "minimum_utilization must be above the platform threshold "
            "and at most 100"
        )
    return {
        "expected_gpus": expected_gpus,
        "minimum_utilization": float(minimum_utilization),
        "platform_reclamation_threshold": float(
            platform_reclamation_threshold
        ),
    }


def parse_nvidia_smi_sample(
    payload: str,
    *,
    expected_gpus: int,
) -> dict[int, float]:
    """Parse one exact GPU index/utilization inventory."""

    observed: dict[int, float] = {}
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2:
            raise ValueError(f"unexpected nvidia-smi row: {raw_line!r}")
        try:
            index = int(fields[0])
            utilization = float(fields[1])
        except ValueError as error:
            raise ValueError(
                f"non-numeric nvidia-smi row: {raw_line!r}"
            ) from error
        if index in observed or not 0.0 <= utilization <= 100.0:
            raise ValueError(f"invalid nvidia-smi row: {raw_line!r}")
        observed[index] = utilization

    expected = set(range(expected_gpus))
    if set(observed) != expected:
        raise ValueError(
            "GPU inventory differs from the exact expected index set"
        )
    return observed


def evaluate_samples(
    samples: Sequence[Mapping[int, float]],
    *,
    expected_gpus: int,
    minimum_utilization: float,
    platform_reclamation_threshold: float,
) -> dict[str, Any]:
    """Evaluate the mean utilization of each GPU independently."""

    policy = validate_policy(
        expected_gpus=expected_gpus,
        minimum_utilization=minimum_utilization,
        platform_reclamation_threshold=platform_reclamation_threshold,
    )
    if not samples:
        raise ValueError("at least one utilization sample is required")

    expected = set(range(expected_gpus))
    for sample in samples:
        if set(sample) != expected:
            raise ValueError(
                "GPU inventory changed during utilization sampling"
            )

    per_gpu: dict[str, dict[str, int | float]] = {}
    underutilized: list[int] = []
    for index in range(expected_gpus):
        values = [float(sample[index]) for sample in samples]
        mean = statistics.fmean(values)
        if mean < minimum_utilization:
            underutilized.append(index)
        per_gpu[str(index)] = {
            "sample_count": len(values),
            "mean_utilization": round(mean, 2),
            "minimum_observed": min(values),
            "maximum_observed": max(values),
        }

    return {
        "schema_version": 1,
        "healthy": not underutilized,
        **policy,
        "sample_count": len(samples),
        "per_gpu": per_gpu,
        "underutilized_gpus": underutilized,
    }


def collect_samples(
    *,
    expected_gpus: int,
    count: int,
    interval_seconds: float,
) -> list[dict[int, float]]:
    """Collect exact per-GPU utilization samples from nvidia-smi."""

    if count <= 0 or interval_seconds < 0.0:
        raise ValueError("sample count and interval are invalid")

    samples: list[dict[int, float]] = []
    for sample_index in range(count):
        completed = subprocess.run(
            (
                "nvidia-smi",
                "--query-gpu=index,utilization.gpu",
                "--format=csv,noheader,nounits",
            ),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "nvidia-smi utilization query failed: "
                f"{completed.stderr.strip()}"
            )
        samples.append(
            parse_nvidia_smi_sample(
                completed.stdout,
                expected_gpus=expected_gpus,
            )
        )
        if sample_index + 1 < count:
            time.sleep(interval_seconds)
    return samples


def _load_one_gpu(
    index: int,
    matrix_size: int,
    ready_queue: multiprocessing.Queue,
) -> None:
    """Run a continuous bounded-memory BF16 matrix multiply on one GPU."""

    import torch

    torch.cuda.set_device(index)
    device = torch.device("cuda", index)
    with torch.inference_mode():
        left = torch.randn(
            (matrix_size, matrix_size),
            device=device,
            dtype=torch.bfloat16,
        )
        right = torch.randn(
            (matrix_size, matrix_size),
            device=device,
            dtype=torch.bfloat16,
        )
        output = torch.empty_like(left)
        for _ in range(4):
            torch.mm(left, right, out=output)
        torch.cuda.synchronize(device)
        ready_queue.put(
            {
                "gpu_index": index,
                "pid": os.getpid(),
                "ready": True,
            }
        )
        while True:
            for _ in range(32):
                torch.mm(left, right, out=output)
            torch.cuda.synchronize(device)


def run_load(*, expected_gpus: int, matrix_size: int) -> int:
    """Supervise one load process per visible GPU until terminated."""

    validate_policy(
        expected_gpus=expected_gpus,
        minimum_utilization=DEFAULT_MINIMUM_UTILIZATION,
        platform_reclamation_threshold=PLATFORM_RECLAMATION_THRESHOLD,
    )
    if matrix_size < 1024:
        raise ValueError("matrix_size must be at least 1024")

    import torch

    observed_gpus = torch.cuda.device_count()
    if not torch.cuda.is_available() or observed_gpus != expected_gpus:
        raise RuntimeError(
            "CUDA inventory mismatch: "
            f"available={torch.cuda.is_available()} "
            f"observed={observed_gpus} expected={expected_gpus}"
        )

    context = multiprocessing.get_context("spawn")
    ready_queue = context.Queue()
    workers = [
        context.Process(
            target=_load_one_gpu,
            args=(index, matrix_size, ready_queue),
            name=f"deepspec-keepalive-gpu-{index}",
        )
        for index in range(expected_gpus)
    ]
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    for worker in workers:
        worker.start()

    try:
        ready: dict[int, dict[str, Any]] = {}
        deadline = time.monotonic() + 300.0
        while len(ready) < expected_gpus and not stopping:
            if time.monotonic() >= deadline:
                raise RuntimeError("GPU load workers did not become ready")
            for worker in workers:
                if worker.exitcode is not None:
                    raise RuntimeError(
                        f"{worker.name} exited before readiness: "
                        f"{worker.exitcode}"
                    )
            try:
                record = ready_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            index = int(record["gpu_index"])
            if index in ready or record.get("ready") is not True:
                raise RuntimeError("invalid or duplicate GPU readiness")
            ready[index] = dict(record)

        if stopping:
            return 0
        print(
            json.dumps(
                {
                    "event": "all_gpus_ready",
                    "expected_gpus": expected_gpus,
                    "matrix_size": matrix_size,
                    "workers": [ready[index] for index in sorted(ready)],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        while not stopping:
            for worker in workers:
                if worker.exitcode is not None:
                    raise RuntimeError(
                        f"{worker.name} exited unexpectedly: "
                        f"{worker.exitcode}"
                    )
            time.sleep(1.0)
        return 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
        for worker in workers:
            worker.join(timeout=15.0)
        for worker in workers:
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=5.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    load = subparsers.add_parser("load")
    load.add_argument(
        "--expected-gpus",
        type=int,
        default=DEFAULT_EXPECTED_GPUS,
    )
    load.add_argument("--matrix-size", type=int, default=8192)

    check = subparsers.add_parser("check")
    check.add_argument(
        "--expected-gpus",
        type=int,
        default=DEFAULT_EXPECTED_GPUS,
    )
    check.add_argument(
        "--minimum-utilization",
        type=float,
        default=DEFAULT_MINIMUM_UTILIZATION,
    )
    check.add_argument(
        "--platform-reclamation-threshold",
        type=float,
        default=PLATFORM_RECLAMATION_THRESHOLD,
    )
    check.add_argument("--samples", type=int, default=10)
    check.add_argument("--sample-interval", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "load":
        return run_load(
            expected_gpus=args.expected_gpus,
            matrix_size=args.matrix_size,
        )

    samples = collect_samples(
        expected_gpus=args.expected_gpus,
        count=args.samples,
        interval_seconds=args.sample_interval,
    )
    report = evaluate_samples(
        samples,
        expected_gpus=args.expected_gpus,
        minimum_utilization=args.minimum_utilization,
        platform_reclamation_threshold=(
            args.platform_reclamation_threshold
        ),
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"keepalive error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
