#!/usr/bin/env bash
# Start and capture the P00 8-GPU keepalive gate on worker 4106666.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly WORKER_ID="${1:?worker ID is required}"
readonly ARTIFACT_DIR="${2:?artifact directory is required}"
readonly PYTHON_PATH="${3:-/home/tiger/venvs/hedge-v4-dspark/bin/python}"

if [[ "$WORKER_ID" != "4106666" ]]; then
  echo "refusing worker $WORKER_ID; only 4106666 is authorized" >&2
  exit 2
fi
case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
test -x "$PYTHON_PATH"
mkdir -p -- "$ARTIFACT_DIR"

export DEEPSPEC_HEDGE_DSPARK_KEEPALIVE_PYTHON="$PYTHON_PATH"
bash "$REPO_ROOT/scripts/hedge_dspark_keepalive.sh" start "$WORKER_ID" \
  >"$ARTIFACT_DIR/keepalive_start.txt" 2>&1
bash "$REPO_ROOT/scripts/hedge_dspark_keepalive.sh" status "$WORKER_ID" \
  >"$ARTIFACT_DIR/keepalive_initial.txt" 2>&1

python3 - "$ARTIFACT_DIR/keepalive_initial.txt" \
  "$ARTIFACT_DIR/keepalive_initial.json" "$PYTHON_PATH" \
  "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/usr/local/cuda-13.0/compat" \
  "${PYTHON_PATH%/bin/python}/lib/python3.11/site-packages/nvidia/cu13/lib" <<'PY'
import json
import pathlib
import re
import sys

text_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
python_path = sys.argv[3]
cuda_compat = sys.argv[4]
cuda_runtime_lib = sys.argv[5]
lines = text_path.read_text(encoding="utf-8").splitlines()
status = lines[0]
match = re.search(r"pid=(\d+) pgid=(\d+) sid=(\d+)", status)
if not match:
    raise SystemExit("missing PID/PGID/SID identity")
health = None
for line in lines[1:]:
    try:
        candidate = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(candidate, dict) and "per_gpu" in candidate:
        health = candidate
        break
if health is None:
    raise SystemExit("missing health JSON")
errors = []
if not status.startswith("HEALTHY "):
    errors.append("status is not HEALTHY")
if health.get("expected_gpus") != 8:
    errors.append("expected_gpus is not 8")
if health.get("sample_count") != 10:
    errors.append("sample_count is not 10")
if health.get("underutilized_gpus"):
    errors.append("one or more GPUs are underutilized")
for index in range(8):
    item = health.get("per_gpu", {}).get(str(index), {})
    if item.get("sample_count") != 10:
        errors.append(f"GPU {index} sample count is not 10")
    if float(item.get("mean_utilization", -1)) < 40.0:
        errors.append(f"GPU {index} mean utilization is below 40")
payload = {
    "schema_version": 1,
    "status": "PASS" if not errors else "FAIL",
    "worker_id": "4106666",
    "runtime_python": python_path,
    "resolved_environment": {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "cuda_compat": cuda_compat,
        "cuda_runtime_lib": cuda_runtime_lib,
        "LD_LIBRARY_PATH_prefix": f"{cuda_compat}:{cuda_runtime_lib}",
    },
    "supervisor_pid": int(match.group(1)),
    "supervisor_pgid": int(match.group(2)),
    "supervisor_sid": int(match.group(3)),
    "health": health,
    "errors": errors,
}
temporary = output_path.with_name(f".{output_path.name}.tmp")
temporary.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
temporary.replace(output_path)
if errors:
    raise SystemExit("; ".join(errors))
print(json.dumps(payload, sort_keys=True))
PY
