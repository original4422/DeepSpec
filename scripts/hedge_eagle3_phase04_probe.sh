#!/usr/bin/env bash
# Read-only status probe for one registered Phase 04 attempt.

set -euo pipefail

readonly ATTEMPT_ID="${1:?usage: hedge_eagle3_phase04_probe.sh ATTEMPT_ID}"
readonly OUTPUT_LABEL="${2:-}"
readonly SCRATCH="/tmp/deepspec-hedge-v4-eagle3/${ATTEMPT_ID}"

case "${ATTEMPT_ID}" in
  20??????T??????Z-phase-04-*)
    ;;
  *)
    echo "invalid Phase 04 attempt ID: ${ATTEMPT_ID}" >&2
    exit 2
    ;;
esac

test -d "${SCRATCH}"
if [ -n "${OUTPUT_LABEL}" ]; then
  case "${OUTPUT_LABEL}" in
    [a-z0-9][a-z0-9_-]*)
      ;;
    *)
      echo "invalid Phase 04 probe output label: ${OUTPUT_LABEL}" >&2
      exit 2
      ;;
  esac
  exec > >(tee "${SCRATCH}/${OUTPUT_LABEL}.txt") 2>&1
fi
printf 'hostname=%s attempt_id=%s scratch=%s\n' \
  "$(hostname)" "${ATTEMPT_ID}" "${SCRATCH}"
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
        if int(member_fields[2]) != identity["pgid"]:
            continue
        try:
            command = (proc / "cmdline").read_bytes().replace(
                b"\0", b" "
            ).decode("utf-8", errors="replace")[:200]
            wchan = (proc / "wchan").read_text(encoding="utf-8").strip()
            member_io = {}
            for line in (proc / "io").read_text(
                encoding="utf-8"
            ).splitlines():
                name, value = line.split(":", maxsplit=1)
                member_io[name] = int(value.strip())
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        members.append(
            {
                "pid": int(proc.name),
                "state": member_fields[0],
                "wchan": wchan,
                "utime_ticks": int(member_fields[11]),
                "stime_ticks": int(member_fields[12]),
                "rchar": member_io.get("rchar"),
                "read_bytes": member_io.get("read_bytes"),
                "syscr": member_io.get("syscr"),
                "command": command,
            }
        )
    print(f"server_group_members={sorted(members, key=lambda x: x['pid'])}")
else:
    print("server_state=exited")
PY
else
  printf '%s\n' "server_identity=pending"
fi
if [ -f "${SCRATCH}/server.log" ]; then
  printf 'server_log=%s bytes=%s\n' \
    "${SCRATCH}/server.log" "$(stat -c '%s' "${SCRATCH}/server.log")"
  tail -n 25 "${SCRATCH}/server.log"
else
  printf '%s\n' "server_log=pending"
fi
for output in \
  native_calibration_outputs.jsonl \
  b0_calibration_outputs.jsonl \
  bplus_smoke_outputs.jsonl; do
  if [ -f "${SCRATCH}/${output}" ]; then
    printf 'output=%s lines=%s bytes=%s\n' \
      "${output}" \
      "$(wc -l <"${SCRATCH}/${output}")" \
      "$(stat -c '%s' "${SCRATCH}/${output}")"
  fi
done
printf '%s\n' "compute_contexts:"
nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,used_gpu_memory \
  --format=csv,noheader,nounits
printf '%s\n' "physical_gpus:"
nvidia-smi \
  --query-gpu=index,uuid,utilization.gpu,memory.used \
  --format=csv,noheader,nounits

exit 0
