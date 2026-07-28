#!/usr/bin/env bash
# Fixed-scope Phase D1A launcher. The caller must run `mlx worker list` first.

set -euo pipefail

readonly WORKTREE="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly ACQUIRE="${WORKTREE}/scripts/dflash_d1a_acquire_publish.py"
readonly ATTEMPT_ID="${1:-}"
readonly TIMEBOX="${WORKTREE}/docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/timebox.json"

if [[ ! "$ATTEMPT_ID" =~ ^dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "usage: $0 dflash-d1a-primary-YYYYmmddTHHMMSSZ" >&2
  exit 2
fi

test -f "$ACQUIRE"
test -f "$TIMEBOX"
test "$(hostname)" = "g340-cd51-4b00-4d69-9088-7ae6-6253"

# The internal loop rechecks the DFlash hard stop and keepalive while curl/copy
# are active. This outer watchdog bounds the remote operation even if a lower
# layer becomes unresponsive. A vanished worker also terminates the enclosing
# `mlx worker login` connection used by the caller.
exec timeout --signal=TERM --kill-after=30s 10800s \
  python3 "$ACQUIRE" --attempt-id "$ATTEMPT_ID"
