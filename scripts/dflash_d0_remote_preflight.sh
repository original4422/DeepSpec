#!/usr/bin/env bash
# Read-only, bounded Phase D0 inventory for the assigned DFlash worker.

set -euo pipefail

REPO="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
PREFLIGHT="$REPO/scripts/dflash_d0_remote_preflight.py"

test -f "$PREFLIGHT"
exec timeout --signal=TERM --kill-after=5s 55s python3 "$PREFLIGHT"
