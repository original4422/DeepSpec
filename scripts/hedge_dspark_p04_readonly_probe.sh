#!/usr/bin/env bash
# Read-only P04 engine identity and keepalive gate; never pauses or starts a model.

set -euo pipefail

readonly REPO_ROOT="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark"
readonly PYTHON="/home/tiger/venvs/hedge-v4-dspark/bin/python"
readonly PREPARE="$REPO_ROOT/scripts/hedge_dspark_p04_prepare.py"
readonly KEEPALIVE="$REPO_ROOT/scripts/hedge_dspark_keepalive.sh"
readonly EXPECTED_WORKER="4106666"

if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 <worker-id> <unique-probe-id>" >&2
  exit 2
fi

readonly WORKER_ID="$1"
readonly PROBE_ID="$2"
if [[ "$WORKER_ID" != "$EXPECTED_WORKER" ]]; then
  echo "refusing worker $WORKER_ID; only $EXPECTED_WORKER is authorized" >&2
  exit 2
fi
if [[ ! "$PROBE_ID" =~ ^[0-9]{8}T[0-9]{6}Z-p04-engine-probe-[a-z0-9-]+$ ]]; then
  echo "invalid P04 read-only probe ID: $PROBE_ID" >&2
  exit 2
fi

readonly SCRATCH="/tmp/deepspec-hedge-dspark-$PROBE_ID"
if [[ -e "$SCRATCH" ]]; then
  echo "refusing to overwrite probe scratch: $SCRATCH" >&2
  exit 1
fi
mkdir -- "$SCRATCH"

"$PYTHON" "$PREPARE" probe-engine \
  --worker-id "$WORKER_ID" \
  --decode-config-fingerprint "readonly-persistent-wheel-probe" \
  --output "$SCRATCH/engine_identity.json"

bash "$KEEPALIVE" status "$WORKER_ID" \
  >"$SCRATCH/keepalive_status.txt"
"$PYTHON" "$PREPARE" parse-keepalive \
  --worker-id "$WORKER_ID" \
  --input "$SCRATCH/keepalive_status.txt" \
  --output "$SCRATCH/keepalive_status.json"

sha256sum \
  "$SCRATCH/engine_identity.json" \
  "$SCRATCH/keepalive_status.json"
