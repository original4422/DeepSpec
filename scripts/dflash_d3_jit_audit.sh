#!/usr/bin/env bash
# Read-only independent audit of one completed DFlash D3 JIT prebuild.
set -Eeuo pipefail

[[ "$#" -eq 2 ]]
readonly SCRATCH="$1"
readonly ATTEMPT_ID="$2"
readonly WORKER_ID="4099543"
readonly EXPECTED_HOST="g340-cd51-4b00-4d69-9088-7ae6-6253"
readonly SCRATCH_ROOT="/tmp/deepspec-hedge-dflash/jit-prebuild"
readonly EXPECTED_SCRATCH="${SCRATCH_ROOT}/${ATTEMPT_ID}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"

[[ "${ATTEMPT_ID}" =~ ^dflash-d3-jit-prebuild-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ "${SCRATCH}" = "${EXPECTED_SCRATCH}" ]]
[[ "${SCRATCH}" = /* && -d "${SCRATCH}" && ! -L "${SCRATCH}" ]]
[[ "$(readlink -f -- "${SCRATCH}")" = "${SCRATCH}" ]]
[[ "$(hostname)" = "${EXPECTED_HOST}" ]]
[[ -x "${PYTHON}" ]]

export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1

"${PYTHON}" - "${SCRATCH}" "${ATTEMPT_ID}" "${WORKER_ID}" \
  "${EXPECTED_HOST}" <<'PY'
from __future__ import annotations

import csv
import hashlib
import json
import os
import pathlib
import socket
import stat
import subprocess
import sys
from collections import Counter
from typing import Any


scratch = pathlib.Path(sys.argv[1])
attempt_id = sys.argv[2]
worker_id = sys.argv[3]
expected_host = sys.argv[4]
workspace_base = pathlib.Path(
    "/tmp/deepspec-hedge-dflash/cache/flashinfer-workspace"
)
cuda_view = pathlib.Path("/tmp/deepspec-hedge-dflash/toolchains/cuda-13.0")
cu13_payload = pathlib.Path(
    "/home/tiger/venvs/deepspec-hedge-dflash/"
    "lib/python3.11/site-packages/nvidia/cu13"
)
compat_dir = pathlib.Path(
    "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
    "usr/local/cuda-13.0/compat"
)
expected_links = {
    cuda_view / "bin": cu13_payload / "bin",
    cuda_view / "include": cu13_payload / "include",
    cuda_view / "nvvm": cu13_payload / "nvvm",
    cuda_view / "lib64/libcudart.so": cu13_payload / "lib/libcudart.so.13",
    cuda_view / "lib64/libnvrtc.so": cu13_payload / "lib/libnvrtc.so.13",
    cuda_view / "lib64/stubs/libcuda.so": (
        compat_dir / "libcuda.so.580.173.02"
    ),
}
forbidden = {
    "eagle": b"eagle",
    "shared_home_cache": b"/home/tiger/.cache/flashinfer",
    "cuda_12_6_dash": b"cuda-12.6",
    "cuda_12_6_compact": b"cuda12.6",
    "cuda_12_6_space": b"cuda 12.6",
    "cu126": b"cu126",
}


def read_json(name: str) -> dict[str, Any]:
    path = scratch / name
    assert path.is_file() and not path.is_symlink(), path
    value = json.loads(path.read_text())
    assert isinstance(value, dict), name
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: pathlib.Path) -> dict[str, Any]:
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and not path.is_symlink(), path
    return {
        "path": str(path),
        "size_bytes": info.st_size,
        "sha256": sha256_file(path),
    }


def normalized_csv(path: pathlib.Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with path.open(newline="") as handle:
        for row in csv.reader(handle):
            if not row or not "".join(row).strip():
                continue
            assert len(row) == 3, row
            rows.append(tuple(item.strip() for item in row))
    return sorted(rows)


def scan_forbidden(path: pathlib.Path) -> list[str]:
    hits: set[str] = set()
    overlap = max(len(marker) for marker in forbidden.values()) - 1
    tail = b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            payload = (tail + block).lower()
            hits.update(
                name for name, marker in forbidden.items() if marker in payload
            )
            tail = payload[-overlap:]
    return sorted(hits)


assert socket.gethostname() == expected_host
gpu_query = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=index,uuid,name",
        "--format=csv,noheader,nounits",
    ],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
current_gpus = []
for row in csv.reader(gpu_query.stdout.splitlines()):
    assert len(row) == 3, row
    index, uuid, name = (item.strip() for item in row)
    current_gpus.append({"index": int(index), "uuid": uuid, "name": name})
assert [gpu["index"] for gpu in current_gpus] == list(range(8))
assert all(gpu["name"] == "NVIDIA H20" for gpu in current_gpus)

summary = read_json("summary.json")
jit = read_json("jit_prebuild.json")
validation = read_json("artifact_validation.json")
assert summary == {
    **summary,
    "attempt_id": attempt_id,
    "status": "PASS",
    "main_complete": True,
    "main_returncode": 0,
    "postflight_returncode": 0,
    "final_returncode": 0,
    "keepalive_paused": False,
    "shared_cache_modified": False,
}
assert jit["status"] == "PASS"
assert jit["operation"] == "flashinfer_fused_moe_sm90_prebuild"
assert jit["flashinfer_version"] == "0.6.14"
assert jit["module_name"] == "fused_moe_90"
assert validation["status"] == "PASS"

expected_environment = {
    "CUDA_HOME": str(cuda_view),
    "CUDA_VISIBLE_DEVICES": "",
    "FLASHINFER_CUDA_ARCH_LIST": "9.0",
    "FLASHINFER_WORKSPACE_BASE": str(workspace_base),
    "MAX_JOBS": "16",
    "PYTHONNOUSERSITE": "1",
}
assert jit["preimport"]["environment"] == expected_environment
assert "release 13.0" in jit["preimport"]["nvcc_version"]
assert pathlib.Path(jit["preimport"]["path_nvcc"]) == cuda_view / "bin/nvcc"

resolved_workspace_base = workspace_base.resolve(strict=True)
assert workspace_base.is_dir() and not workspace_base.is_symlink()
assert pathlib.Path(jit["workspace_base"]) == workspace_base
workspace = pathlib.Path(jit["workspace"]).resolve(strict=True)
build_dir = pathlib.Path(jit["build_dir"]).resolve(strict=True)
build_ninja = pathlib.Path(jit["ninja_file"])
shared_object = pathlib.Path(jit["shared_object"]["path"])
assert workspace.is_relative_to(resolved_workspace_base)
assert build_dir.is_relative_to(workspace)
assert build_ninja.parent.resolve(strict=True) == build_dir
assert shared_object.parent.resolve(strict=True) == build_dir
assert build_ninja.is_file() and not build_ninja.is_symlink()
assert shared_object.is_file() and not shared_object.is_symlink()
assert validation["workspace_base"] == str(workspace_base)
assert pathlib.Path(validation["build_dir"]).resolve(strict=True) == build_dir
assert pathlib.Path(validation["build_ninja"]) == build_ninja
assert pathlib.Path(validation["shared_object"]) == shared_object

build_ninja_identity = file_identity(build_ninja)
shared_object_identity = file_identity(shared_object)
assert shared_object_identity["size_bytes"] == jit["shared_object"]["size_bytes"]
assert shared_object_identity["sha256"] == jit["shared_object"]["sha256"]
marker_scan = {
    str(build_ninja): scan_forbidden(build_ninja),
    str(shared_object): scan_forbidden(shared_object),
}
assert all(not hits for hits in marker_scan.values())
assert all(not hits for hits in validation["matches"].values())
assert set(validation["forbidden_markers"]) == set(forbidden)

ldd_path = scratch / "ldd.txt"
readelf_path = scratch / "readelf_dynamic.txt"
ldd_text = ldd_path.read_text()
readelf_text = readelf_path.read_text()
assert "not found" not in ldd_text.lower()
assert "not found" not in readelf_text.lower()
assert str(cu13_payload / "lib/libcudart.so.13") in ldd_text
assert str(compat_dir / "libcuda.so.1") in ldd_text
assert "Shared library: [libcudart.so.13]" in readelf_text
assert "Shared library: [libcuda.so.1]" in readelf_text

shared_before_path = scratch / "shared_cache_before.json"
shared_after_path = scratch / "shared_cache_after.json"
shared_before = read_json(shared_before_path.name)
shared_after = read_json(shared_after_path.name)
assert shared_before_path.read_bytes() == shared_after_path.read_bytes()
assert shared_before == shared_after
assert shared_before["root"] == "/home/tiger/.cache/flashinfer"
assert shared_before["fingerprint_kind"] == "lstat-tree-metadata-v1"

identity_before = read_json("keepalive_identity_before.json")
identity_after = read_json("keepalive_identity_after.json")
stable_identity_keys = (
    "schema_version",
    "lane",
    "worker_id",
    "hostname",
    "pid",
    "pgid",
    "sid",
    "argv",
    "expected_gpu_count",
    "cuda_visible_devices",
    "physical_gpus",
    "started_at_utc",
)
for key in stable_identity_keys:
    assert identity_before[key] == identity_after[key], key
assert identity_before["worker_id"] == identity_after["worker_id"] == worker_id
assert identity_before["hostname"] == identity_after["hostname"] == expected_host
assert (
    identity_before["pid"]
    == identity_before["pgid"]
    == identity_before["sid"]
)
assert identity_before["expected_gpu_count"] == 8
assert identity_before["physical_gpus"] == current_gpus

gate_before_path = scratch / "keepalive_gate_before.json"
gate_after_path = scratch / "keepalive_gate_after.json"
gate_before = read_json(gate_before_path.name)
gate_after = read_json(gate_after_path.name)
assert gate_before_path.read_bytes() == gate_after_path.read_bytes()
assert gate_before == gate_after
assert gate_before["healthy"] is True
assert gate_before["expected_gpus"] == 8
assert gate_before["sample_count_per_gpu"] == 10
assert all(
    value >= gate_before["minimum_mean_utilization_percent"]
    for value in gate_before["per_gpu_mean_utilization_percent"].values()
)
status_before = scratch / "keepalive_status_before.txt"
status_after = scratch / "keepalive_status_after.txt"
assert status_before.read_bytes() == status_after.read_bytes()
assert (
    f"HEALTHY worker={worker_id} host={expected_host} "
    f"pid={identity_before['pid']}"
) in status_before.read_text()

compute_before_path = scratch / "compute_apps_before.csv"
compute_after_path = scratch / "compute_apps_after.csv"
assert compute_before_path.read_bytes() == compute_after_path.read_bytes()
compute_before = normalized_csv(compute_before_path)
compute_after = normalized_csv(compute_after_path)
assert compute_before == compute_after
assert len(compute_before) == 8
uuid_counts = Counter(row[0] for row in compute_before)
assert set(uuid_counts) == {gpu["uuid"] for gpu in current_gpus}
assert all(count == 1 for count in uuid_counts.values())
assert all(row[1].isdigit() and int(row[1]) > 0 for row in compute_before)
assert len({row[1] for row in compute_before}) == 8
compute_json_before = read_json("compute_apps_before.json")
compute_json_after = read_json("compute_apps_after.json")
assert compute_json_before == compute_json_after
assert compute_json_before["row_count"] == 8
assert compute_json_before["pid_namespace"] == {
    "nvidia_smi_rows": "host",
    "keepalive_supervisor_proc": "container-local",
    "direct_pid_equality_expected": False,
}

view_links = {}
for link, target in expected_links.items():
    assert link.is_symlink(), link
    assert os.readlink(link) == str(target), (link, target)
    assert link.resolve(strict=True) == target.resolve(strict=True)
    view_links[str(link)] = str(target)
assert jit["preimport"]["links"] == view_links
view_ensure = read_json("cuda_view_ensure.json")
view_verify = read_json("cuda_view_verify.json")
assert view_ensure["status"] == view_verify["status"] == "PASS"
assert view_ensure["action"] == "ensure"
assert view_verify["action"] == "verify"
assert view_ensure["cuda_view"] == view_verify["cuda_view"] == str(cuda_view)

artifact_inventory = {}
for path in sorted(scratch.iterdir()):
    assert path.is_file() and not path.is_symlink(), path
    artifact_inventory[path.name] = file_identity(path)

result = {
    "schema_version": 1,
    "status": "PASS",
    "read_only_audit": True,
    "worker_id": worker_id,
    "hostname": expected_host,
    "attempt_id": attempt_id,
    "scratch": str(scratch),
    "summary": summary,
    "jit_prebuild": jit,
    "artifact_validation": validation,
    "build_artifacts": {
        "build_ninja": build_ninja_identity,
        "shared_object": shared_object_identity,
        "forbidden_marker_matches": marker_scan,
    },
    "dynamic_dependencies": {
        "ldd": file_identity(ldd_path),
        "readelf": file_identity(readelf_path),
        "not_found": False,
    },
    "shared_cache": {
        "equal": True,
        "fingerprint": shared_before,
        "before": file_identity(shared_before_path),
        "after": file_identity(shared_after_path),
    },
    "keepalive": {
        "stable_identity_equal": True,
        "pid": identity_before["pid"],
        "gate_equal": True,
        "gate": gate_before,
        "identity_before": file_identity(
            scratch / "keepalive_identity_before.json"
        ),
        "identity_after": file_identity(
            scratch / "keepalive_identity_after.json"
        ),
    },
    "compute_apps": {
        "equal": True,
        "row_count": len(compute_before),
        "host_pids": sorted(int(row[1]) for row in compute_before),
        "gpu_uuids": sorted(uuid_counts),
        "before": file_identity(compute_before_path),
        "after": file_identity(compute_after_path),
    },
    "cuda_view_links": view_links,
    "artifact_inventory": artifact_inventory,
}
print(json.dumps(result, indent=2, sort_keys=True))
PY
