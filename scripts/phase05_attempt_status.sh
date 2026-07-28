#!/usr/bin/env bash
# Read-only status snapshot for one registered Phase 05 attempt.
set -euo pipefail

readonly ATTEMPT_ID="${1:?attempt ID is required}"
readonly SCRATCH="/tmp/deepspec-${ATTEMPT_ID}"

[[ "${ATTEMPT_ID}" =~ ^[0-9]{8}T[0-9]{6}Z-phase05- ]]

printf 'checked_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ ! -d "${SCRATCH}" ]]; then
  printf 'scratch=missing path=%s\n' "${SCRATCH}"
  exit 1
fi

for name in server sampler watchdog; do
  pid_file="${SCRATCH}/${name}.pid"
  if [[ -f "${pid_file}" ]]; then
    pid="$(<"${pid_file}")"
    if [[ "${name}" = server ]]; then
      server_group_pid="${pid}"
    fi
    printf '%s_pid=%s\n' "${name}" "${pid}"
    ps -o pid=,ppid=,pgid=,sid=,stat=,etime=,wchan= -p "${pid}" || true
    if [[ -r "/proc/${pid}/cmdline" ]]; then
      tr '\0' ' ' <"/proc/${pid}/cmdline"
      printf '\n'
    fi
  else
    printf '%s_pid=not_recorded\n' "${name}"
  fi
done

if [[ -n "${server_group_pid:-}" ]]; then
  printf '%s\n' 'server_process_group_top_cpu:'
  ps -o pid=,ppid=,stat=,pcpu=,pmem=,etime=,wchan=,comm= \
    --sort=-pcpu -g "${server_group_pid}" | head -n 30 || true
  printf '%s\n' 'server_process_group_counts:'
  ps -o comm= -g "${server_group_pid}" \
    | sort | uniq -c | sort -nr | head -n 30 || true
  printf '%s\n' 'server_and_rank_io:'
  while read -r group_pid group_comm; do
    [[ "${group_pid}" =~ ^[1-9][0-9]*$ ]] || continue
    case "${group_comm}" in
      python|sglang::*) ;;
      *) continue ;;
    esac
    if [[ -r "/proc/${group_pid}/io" ]]; then
      printf 'pid=%s comm=%s ' "${group_pid}" "${group_comm}"
      awk '
        /^(rchar|wchar|read_bytes|write_bytes):/ {
          printf "%s=%s ", $1, $2
        }
        END { print "" }
      ' "/proc/${group_pid}/io"
    fi
  done < <(ps -o pid=,comm= -g "${server_group_pid}")
fi

printf '%s\n' 'gpu_inventory:'
nvidia-smi \
  --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total \
  --format=csv,noheader,nounits
printf '%s\n' 'compute_contexts:'
nvidia-smi \
  --query-compute-apps=pid,gpu_uuid,process_name,used_memory \
  --format=csv,noheader,nounits 2>/dev/null || true

for name in lifecycle.log server.log watchdog.log; do
  path="${SCRATCH}/${name}"
  printf '%s\n' "${name}:"
  if [[ -f "${path}" ]]; then
    tr '\r' '\n' <"${path}" \
      | tail -n 160 \
      | awk '
          /NCCL INFO Channel [0-9]/ { next }
          /NCCL INFO \[Proxy/ { next }
          /NCCL INFO Connected all/ { next }
          length($0) > 1200 {
            print substr($0, 1, 1200) " ...[truncated]"
            next
          }
          { print }
        '
  else
    printf 'not_present\n'
  fi
done

printf '%s\n' 'artifacts:'
find "${SCRATCH}" -maxdepth 1 -type f \
  -printf '%f %s bytes\n' | sort
printf '%s\n' 'scratch_space:'
du -sh "${SCRATCH}"
df -h /tmp | tail -n 1
