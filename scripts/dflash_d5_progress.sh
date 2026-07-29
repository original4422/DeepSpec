#!/usr/bin/env bash
# Read-only progress snapshot for one active D5 attempt.
set -Eeuo pipefail

readonly ATTEMPT_ID="${1:?attempt id required}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/runs/${ATTEMPT_ID}"

[[ "${ATTEMPT_ID}" =~ ^dflash-d5-(native|b0)-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ -d "${SCRATCH}" ]]

exec "${PYTHON}" - "${SCRATCH}" <<'PY'
import collections
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

scratch = pathlib.Path(sys.argv[1])
output = scratch / (
    "b0_outputs.jsonl"
    if scratch.name.startswith("dflash-d5-b0-")
    else "native_calibration_outputs.jsonl"
)
rows = []
invalid_lines = []
if output.exists():
    for line_number, line in enumerate(output.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            invalid_lines.append({"line": line_number, "error": str(error)})
terminal = collections.Counter(str(row.get("terminal_state")) for row in rows)
retry_count = sum(int(row.get("retry_count", 0)) for row in rows)
request_errors = sum(
    1
    for row in rows
    for attempt in row.get("attempts", [])
    if attempt.get("error") is not None
)
server_log = (
    (scratch / "server.log").read_text(errors="replace")
    if (scratch / "server.log").exists()
    else ""
)
fatal_patterns = {
    "traceback": r"Traceback \(most recent call last\):",
    "cuda_error": r"(?:CUDA error|CUDA out of memory)",
    "nccl_error": r"(?:NCCL WARN|NCCL ERROR|ncclUnhandledCudaError)",
    "worker_crash": r"(?:Scheduler hit an exception|Worker crashed)",
}
document = {
    "schema_version": 1,
    "attempt_id": scratch.name,
    "captured_at_utc": datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "output_path": str(output),
    "output_bytes": output.stat().st_size if output.exists() else 0,
    "complete_json_rows": len(rows),
    "invalid_json_lines": invalid_lines,
    "terminal_states": dict(sorted(terminal.items())),
    "retry_count": retry_count,
    "request_attempt_errors": request_errors,
    "request_active": (scratch / "request.active").exists(),
    "startup": (
        json.loads((scratch / "startup.json").read_text())
        if (scratch / "startup.json").exists()
        else None
    ),
    "server_fatal_pattern_counts": {
        name: len(re.findall(pattern, server_log, flags=re.IGNORECASE))
        for name, pattern in fatal_patterns.items()
    },
}
print(json.dumps(document, indent=2, sort_keys=True))
raise SystemExit(0 if not invalid_lines else 1)
PY
