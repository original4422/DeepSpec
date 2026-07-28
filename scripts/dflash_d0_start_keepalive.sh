#!/usr/bin/env bash
# Fixed-identity D0 launcher for the DFlash operational keepalive.

set -euo pipefail

CONTROL="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_keepalive.sh"

test -f "$CONTROL"
exec timeout --signal=TERM --kill-after=10s 360s \
  bash "$CONTROL" start 4099543
