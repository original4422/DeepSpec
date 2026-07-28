#!/usr/bin/env bash
# Post-publication D1A evidence audit; never starts a model or changes keepalive.

set -euo pipefail

readonly WORKTREE="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly ATTEMPT_ID="${1:-}"

if [[ ! "$ATTEMPT_ID" =~ ^dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "usage: $0 dflash-d1a-primary-YYYYmmddTHHMMSSZ" >&2
  exit 2
fi
test "$(hostname)" = "g340-cd51-4b00-4d69-9088-7ae6-6253"
exec timeout --signal=TERM --kill-after=10s 120s \
  python3 "${WORKTREE}/scripts/dflash_d1a_finalize_evidence.py" \
    "$ATTEMPT_ID"
