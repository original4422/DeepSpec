#!/usr/bin/env bash
# Fixed-identity, bounded D0 status/gate probe.

set -euo pipefail

CONTROL="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_keepalive.sh"

test -f "$CONTROL"
exec timeout --signal=TERM --kill-after=10s 60s \
  bash "$CONTROL" status 4099543
