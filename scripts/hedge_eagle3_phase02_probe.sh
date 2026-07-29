#!/usr/bin/env bash
# Read-only status probe for one registered Phase 02 attempt.

set -euo pipefail

readonly ATTEMPT_ID="${1:?usage: hedge_eagle3_phase02_probe.sh ATTEMPT_ID}"
readonly SCRATCH="/tmp/deepspec-hedge-v4-eagle3/${ATTEMPT_ID}"

case "${ATTEMPT_ID}" in
  20??????T??????Z-phase-02-*)
    ;;
  *)
    echo "invalid Phase 02 attempt ID: ${ATTEMPT_ID}" >&2
    exit 2
    ;;
esac

test -d "${SCRATCH}"
printf 'hostname=%s attempt_id=%s\n' "$(hostname)" "${ATTEMPT_ID}"
if [ -f "${SCRATCH}/server_identity.json" ]; then
  /home/tiger/venvs/deepspec-hedge-v4-eagle3/bin/python - \
    "${SCRATCH}/server_identity.json" <<'PY'
import json
from pathlib import Path
import sys

identity = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    "server_pid={pid} pgid={pgid} sid={sid} start_ticks={start_ticks}".format(
        **identity
    )
)
stat_path = Path(f"/proc/{identity['pid']}/stat")
if stat_path.is_file():
    payload = stat_path.read_text(encoding="utf-8")
    fields = payload[payload.rfind(")") + 2 :].split()
    print(f"server_state={fields[0]} current_start_ticks={fields[19]}")
    print(
        "server_wchan="
        + Path(f"/proc/{identity['pid']}/wchan").read_text(
            encoding="utf-8"
        ).strip()
    )
    io_fields = {}
    for line in Path(f"/proc/{identity['pid']}/io").read_text(
        encoding="utf-8"
    ).splitlines():
        name, value = line.split(":", maxsplit=1)
        io_fields[name] = int(value.strip())
    print(
        "server_io="
        + " ".join(
            f"{name}={io_fields[name]}"
            for name in ("rchar", "read_bytes", "syscr")
        )
    )
    members = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            member_payload = (proc / "stat").read_text(encoding="utf-8")
            member_fields = member_payload[
                member_payload.rfind(")") + 2 :
            ].split()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if int(member_fields[2]) == identity["pgid"]:
            member_io = {}
            try:
                member_command = (proc / "cmdline").read_bytes().replace(
                    b"\0", b" "
                ).decode("utf-8", errors="replace")[:240]
                for line in (proc / "io").read_text(
                    encoding="utf-8"
                ).splitlines():
                    name, value = line.split(":", maxsplit=1)
                    member_io[name] = int(value.strip())
                member_wchan = (proc / "wchan").read_text(
                    encoding="utf-8"
                ).strip()
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                member_command = "unavailable"
                member_io = {}
                member_wchan = "unavailable"
            members.append(
                {
                    "pid": int(proc.name),
                    "command": member_command,
                    "state": member_fields[0],
                    "wchan": member_wchan,
                    "utime_ticks": int(member_fields[11]),
                    "stime_ticks": int(member_fields[12]),
                    "rchar": member_io.get("rchar"),
                    "read_bytes": member_io.get("read_bytes"),
                    "syscr": member_io.get("syscr"),
                }
            )
    print(f"server_group_members={sorted(members, key=lambda item: item['pid'])}")
else:
    print("server_state=exited")
PY
else
  printf '%s\n' "server_identity=pending"
fi
if [ -f "${SCRATCH}/server.log" ]; then
  printf 'server_log=%s bytes=%s\n' \
    "${SCRATCH}/server.log" "$(stat -c '%s' "${SCRATCH}/server.log")"
  tail -n 20 "${SCRATCH}/server.log"
else
  printf '%s\n' "server_log=pending"
fi
printf '%s\n' "compute_contexts:"
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,used_gpu_memory \
  --format=csv,noheader,nounits
printf '%s\n' "physical_gpus:"
nvidia-smi \
  --query-gpu=index,uuid,utilization.gpu,memory.used \
  --format=csv,noheader,nounits
