#!/usr/bin/env bash
# Migrate the registered P00 keepalive from the historical read-only runtime.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly HDFS_RUN_ROOT="/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark"
readonly KEEPALIVE="$REPO_ROOT/scripts/hedge_dspark_keepalive.sh"
readonly WORKER_ID="${1:?worker ID is required}"
readonly ARTIFACT_DIR="${2:?artifact directory is required}"
readonly OLD_PYTHON="/home/tiger/venvs/deepspec-dspark/bin/python"
readonly NEW_PYTHON="/home/tiger/venvs/hedge-v4-dspark/bin/python"

[[ "$WORKER_ID" = "4106666" ]]
case "$ARTIFACT_DIR" in
  "$HDFS_RUN_ROOT"/*) ;;
  *)
    echo "artifact directory is outside $HDFS_RUN_ROOT" >&2
    exit 2
    ;;
esac
[[ -x "$OLD_PYTHON" && -x "$NEW_PYTHON" ]]
mkdir -p -- "$ARTIFACT_DIR/keepalive-migration"
readonly MIGRATION_DIR="$ARTIFACT_DIR/keepalive-migration"
[[ ! -e "$MIGRATION_DIR/keepalive_migration.json" ]]

restore_old_on_error() {
  local rc=$?
  if [[ "$rc" -ne 0 ]]; then
    {
      printf 'fallback_started_at_utc=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      export DEEPSPEC_HEDGE_DSPARK_KEEPALIVE_PYTHON="$OLD_PYTHON"
      bash "$KEEPALIVE" start "$WORKER_ID"
    } >"$MIGRATION_DIR/fallback_old_runtime.txt" 2>&1 || true
  fi
  exit "$rc"
}
trap restore_old_on_error EXIT

export DEEPSPEC_HEDGE_DSPARK_KEEPALIVE_PYTHON="$OLD_PYTHON"
bash "$KEEPALIVE" status "$WORKER_ID" \
  >"$MIGRATION_DIR/old_status.txt" 2>&1
bash "$KEEPALIVE" pause "$WORKER_ID" \
  >"$MIGRATION_DIR/old_pause.txt" 2>&1
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,process_name,used_memory \
  --format=csv,noheader,nounits \
  >"$MIGRATION_DIR/contexts_after_old_pause.txt"
if grep -q '[^[:space:]]' "$MIGRATION_DIR/contexts_after_old_pause.txt"; then
  echo "CUDA contexts remain after old keepalive pause" >&2
  exit 1
fi

export DEEPSPEC_HEDGE_DSPARK_KEEPALIVE_PYTHON="$NEW_PYTHON"
bash "$KEEPALIVE" resume "$WORKER_ID" \
  >"$MIGRATION_DIR/new_resume.txt" 2>&1
bash "$KEEPALIVE" status "$WORKER_ID" \
  >"$MIGRATION_DIR/new_status.txt" 2>&1

python3 - "$MIGRATION_DIR" "$OLD_PYTHON" "$NEW_PYTHON" <<'PY'
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
old_python = sys.argv[2]
new_python = sys.argv[3]

def parse_status(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    status_line = lines[0]
    match = re.search(r"pid=(\d+) pgid=(\d+) sid=(\d+)", status_line)
    if not match:
        raise RuntimeError(f"missing identity in {path}")
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
        raise RuntimeError(f"missing health JSON in {path}")
    return {
        "status_line": status_line,
        "pid": int(match.group(1)),
        "pgid": int(match.group(2)),
        "sid": int(match.group(3)),
        "health": health,
    }

old = parse_status(root / "old_status.txt")
new = parse_status(root / "new_status.txt")
errors = []
for label, record in (("old", old), ("new", new)):
    if not record["status_line"].startswith("HEALTHY "):
        errors.append(f"{label} status is not HEALTHY")
    health = record["health"]
    if health.get("expected_gpus") != 8 or health.get("sample_count") != 10:
        errors.append(f"{label} does not have an exact 8-GPU 10-sample gate")
    if health.get("underutilized_gpus"):
        errors.append(f"{label} contains underutilized GPUs")
    for index in range(8):
        item = health.get("per_gpu", {}).get(str(index), {})
        if item.get("sample_count") != 10:
            errors.append(f"{label} GPU {index} sample count is not 10")
        if float(item.get("mean_utilization", -1)) < 40.0:
            errors.append(f"{label} GPU {index} mean is below 40")
if old["pid"] == new["pid"]:
    errors.append("keepalive supervisor PID did not change")
if (root / "contexts_after_old_pause.txt").read_text().strip():
    errors.append("contexts remained after old pause")

payload = {
    "schema_version": 1,
    "authorized_phase": "P00",
    "observed_at_utc": dt.datetime.now(dt.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "worker_id": "4106666",
    "status": "PASS" if not errors else "FAIL",
    "old_runtime_python": old_python,
    "new_runtime_python": new_python,
    "old": old,
    "new": new,
    "contexts_after_old_pause": "none",
    "new_resolved_environment": {
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "cuda_compat": (
            "/home/tiger/toolchains/deepspec-cuda-compat-13.0-580.173.02/"
            "usr/local/cuda-13.0/compat"
        ),
        "cuda_runtime_lib": (
            "/home/tiger/venvs/hedge-v4-dspark/lib/python3.11/"
            "site-packages/nvidia/cu13/lib"
        ),
    },
    "errors": errors,
}
output = root / "keepalive_migration.json"
temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
if errors:
    raise SystemExit("; ".join(errors))
print(json.dumps({
    "status": payload["status"],
    "old_pid": old["pid"],
    "new_pid": new["pid"],
    "new_pgid": new["pgid"],
    "new_sid": new["sid"],
}))
PY

trap - EXIT
