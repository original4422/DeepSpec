#!/usr/bin/env bash
# Read-only progress snapshot for one active D6 native formal attempt.
set -Eeuo pipefail

readonly ATTEMPT_ID="${1:?attempt id required}"
readonly PYTHON="/home/tiger/venvs/deepspec-hedge-dflash/bin/python"
readonly SCRATCH="/tmp/deepspec-hedge-dflash/runs/${ATTEMPT_ID}"

[[ "${ATTEMPT_ID}" =~ ^dflash-d6-native-[0-9]{8}T[0-9]{6}Z-a[0-9]{2}$ ]]
[[ -d "${SCRATCH}" ]]

exec "${PYTHON}" - "${SCRATCH}" <<'PY'
import collections
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

scratch = pathlib.Path(sys.argv[1])

def inspect(path):
    rows = []
    invalid = []
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                invalid.append({"line": number, "error": str(error)})
    terminal = collections.Counter(str(row.get("terminal_state")) for row in rows)
    return {
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
        "complete_json_rows": len(rows),
        "invalid_json_lines": invalid,
        "terminal_states": dict(sorted(terminal.items())),
        "retry_count": sum(int(row.get("retry_count", 0)) for row in rows),
        "completion_tokens": sum(
            int((row.get("usage") or {}).get("completion_tokens", 0))
            for row in rows
        ),
        "match": sum(row.get("answer_status") == "match" for row in rows),
        "mismatch": sum(row.get("answer_status") == "mismatch" for row in rows),
        "parse_failure": sum(
            row.get("answer_status") == "parse_failure" for row in rows
        ),
    }

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
    "phase": (
        "formal"
        if (scratch / "formal.active").exists()
        else "warmup"
        if (scratch / "warmup.active").exists()
        else "lifecycle"
    ),
    "warmup": inspect(scratch / "warmup_outputs.jsonl"),
    "formal": inspect(
        scratch / (
            "formal_outputs.jsonl"
            if (scratch / "formal_outputs.jsonl").exists()
            else "formal_outputs.raw.jsonl"
        )
    ),
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
invalid = (
    document["warmup"]["invalid_json_lines"]
    + document["formal"]["invalid_json_lines"]
)
raise SystemExit(0 if not invalid else 1)
PY
