#!/usr/bin/env bash
# Reserve only the small Eagle3 Phase 00 state/scratch/coordination namespaces.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${1:?usage: hedge_eagle3_phase00_namespace.sh RUN_DIR}"
WORKER_ID="${2:-4099544}"

if [ "$WORKER_ID" != "4099544" ]; then
  echo "refusing unassigned worker: $WORKER_ID" >&2
  exit 2
fi

exec python3 "$REPO_ROOT/scripts/hedge_eagle3_phase00_namespace.py" \
  --worker-id "$WORKER_ID" \
  --run-dir "$RUN_DIR" \
  --started-at "2026-07-28T20:56:27Z"
