#!/usr/bin/env bash
# Fixed-scope recovery launcher for one failed D1A acquisition attempt.

set -euo pipefail

readonly WORKTREE="/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash"
readonly RECOVERY="${WORKTREE}/scripts/dflash_d1a_resume_publish.py"
readonly ATTEMPT_ID="${1:-}"

if [[ ! "$ATTEMPT_ID" =~ ^dflash-d1a-primary-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "usage: $0 dflash-d1a-primary-YYYYmmddTHHMMSSZ" >&2
  exit 2
fi
test "$(hostname)" = "g340-cd51-4b00-4d69-9088-7ae6-6253"
exec timeout --signal=TERM --kill-after=30s 10800s \
  python3 "$RECOVERY" --attempt-id "$ATTEMPT_ID"
