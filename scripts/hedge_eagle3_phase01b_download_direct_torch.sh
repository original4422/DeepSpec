#!/usr/bin/env bash
# Download and hash the exact torch wheel already pinned in uv.lock.

set -euo pipefail

EXPECTED_WORKER="4099544"
WORKER_ID="${1:?usage: hedge_eagle3_phase01b_download_direct_torch.sh WORKER_ID ATTEMPT_DIR}"
ATTEMPT_DIR="${2:?usage: hedge_eagle3_phase01b_download_direct_torch.sh WORKER_ID ATTEMPT_DIR}"
IDENTITY="$ATTEMPT_DIR/direct_artifact_identity.json"
SCRATCH_DIR="/tmp/deepspec-hedge-v4-eagle3/direct-torch-04"
WHEEL_NAME="torch-2.11.0+cu130-cp311-cp311-manylinux_2_28_x86_64.whl"
PARTIAL="$SCRATCH_DIR/$WHEEL_NAME.partial"
WHEEL="$SCRATCH_DIR/$WHEEL_NAME"
URL="https://download-r2.pytorch.org/whl/cu130/torch-2.11.0%2Bcu130-cp311-cp311-manylinux_2_28_x86_64.whl"
EXPECTED_SHA256="225b22e0a4e36ea573d3a68796e6816a160616f67e8b8c55683a88bf7777f4cd"

if [ "$WORKER_ID" != "$EXPECTED_WORKER" ]; then
  echo "refusing unassigned worker: $WORKER_ID" >&2
  exit 2
fi
case "$ATTEMPT_DIR" in
  /mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/*)
    ;;
  *)
    echo "refusing attempt outside Eagle3 run root" >&2
    exit 2
    ;;
esac
test -f "$IDENTITY"
if [ -e "$ATTEMPT_DIR/direct_download.json" ]; then
  echo "refusing to overwrite download evidence" >&2
  exit 2
fi
if [ -e "$SCRATCH_DIR" ]; then
  echo "refusing to reuse direct-wheel scratch: $SCRATCH_DIR" >&2
  exit 2
fi

python3 - "$IDENTITY" "$URL" "$EXPECTED_SHA256" <<'PY'
import json
from pathlib import Path
import sys

identity = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if identity.get("status") != "DIRECT_ARTIFACT_IDENTITY_PASS":
    raise SystemExit("direct artifact identity gate did not pass")
if identity.get("wheel_url") != sys.argv[2]:
    raise SystemExit("wheel URL differs from identity evidence")
if identity.get("wheel_hash") != f"sha256:{sys.argv[3]}":
    raise SystemExit("wheel hash differs from identity evidence")
if identity.get("compute_context_count") != 0:
    raise SystemExit("identity did not prove zero CUDA contexts")
PY

umask 027
mkdir -p "$SCRATCH_DIR"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

curl \
  --fail \
  --location \
  --max-time 60 \
  --silent \
  --show-error \
  --dump-header "$SCRATCH_DIR/head.headers" \
  --output /dev/null \
  --head \
  "$URL"

curl \
  --fail \
  --location \
  --retry 3 \
  --retry-all-errors \
  --connect-timeout 30 \
  --continue-at - \
  --output "$PARTIAL" \
  --stderr "$SCRATCH_DIR/curl.stderr.txt" \
  --write-out \
  'http_code=%{http_code} remote_ip=%{remote_ip} bytes=%{size_download} seconds=%{time_total}\n' \
  "$URL" \
  >"$SCRATCH_DIR/curl.result.txt"

actual_sha256="$(sha256sum "$PARTIAL" | awk '{print $1}')"
if [ "$actual_sha256" != "$EXPECTED_SHA256" ]; then
  echo "direct torch wheel SHA-256 mismatch" >&2
  exit 2
fi
mv "$PARTIAL" "$WHEEL"
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cp "$SCRATCH_DIR/head.headers" "$ATTEMPT_DIR/direct_download_head.headers"
cp "$SCRATCH_DIR/curl.stderr.txt" "$ATTEMPT_DIR/direct_download_curl.stderr.txt"
cp "$SCRATCH_DIR/curl.result.txt" "$ATTEMPT_DIR/direct_download_curl.result.txt"

python3 - \
  "$ATTEMPT_DIR/direct_download.json" \
  "$WHEEL" \
  "$URL" \
  "$EXPECTED_SHA256" \
  "$started_at" \
  "$finished_at" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
wheel = Path(sys.argv[2])
payload = {
    "schema_version": 1,
    "status": "DIRECT_DOWNLOAD_PASS",
    "worker_id": "4099544",
    "wheel_path": str(wheel),
    "wheel_url": sys.argv[3],
    "wheel_sha256": sys.argv[4],
    "wheel_bytes": wheel.stat().st_size,
    "started_at": sys.argv[5],
    "finished_at": sys.argv[6],
    "environment_modified": False,
    "cuda_operation_performed": False,
}
output.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

printf 'DIRECT_DOWNLOAD_PASS wheel=%s evidence=%s\n' \
  "$WHEEL" "$ATTEMPT_DIR/direct_download.json"
