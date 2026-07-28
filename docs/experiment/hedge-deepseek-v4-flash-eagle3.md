# HEDGE on DeepSeek-V4-Flash Eagle3 实验记录

> **状态：`PHASE_00_ACCEPTED`。** 主 Agent 已按原始 artifact、两次只读 inventory、
> 仓库 diff 和静态门禁验收 Phase 00。分配的 worker
> `4099544` 是准确的 8×NVIDIA H20，采集时没有 compute PID、既有 keepalive 或
> CUDA context。按 Phase 00 授权，本阶段没有启动 keepalive、GPU workload、模型、
> 下载或正式环境安装，也没有发送 signal。后续结果仍全部 pending。
>
> **自主窗口（UTC）：** T0 `2026-07-28T20:56:27Z`；
> 实现门槛 `2026-07-29T05:56:27Z`；硬停止 `2026-07-29T08:56:27Z`。
>
> **权威 Phase 00 artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01`

## 快速结果

| 快速结果 | Native | HEDGE B+ |
| --- | ---: | ---: |
| Status | pending | pending |
| Requests terminal | — | — |
| Output TPS | — | — |
| Mean accept length | — | — |
| GSM8K matches | — | — |
| Parse failures | — | — |

| 配置 | 值 |
| --- | --- |
| Lane | worker `4099544`, 8×H20, TP=8 |
| B0 status | pending |
| `g=q25` | pending |
| `B` | pending |
| `m` | 1 |
| Proposal tokens | 3 |
| Dataset seed | 980406 |
| Formal samples | 500 |
| DeepSpec source | branch `exp/hedge-v4-eagle3`; Phase 00 base `cac6c78d88df97d395406fe831f573df3016e7f7` |
| SGLang source | planned base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`; independent source path reserved for Phase 01B, not yet created |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`; not acquired |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d`; not acquired |
| HEDGE core | pending DSpark pure-core marker |
| Formal artifacts | pending |
| Key commits | Phase 00 bootstrap 待本次主 Agent 提交后回填 SHA |

## Phase 00：bootstrap 与 operational ownership

### 独立身份

| 资源 | Phase 00 结果 |
| --- | --- |
| DeepSpec worktree | `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3` |
| DeepSpec branch | `exp/hedge-v4-eagle3` |
| SGLang source path | `/home/tiger/src/sglang-hedge-v4-eagle3`，已确认无路径冲突，留给 Phase 01B 建立 |
| uv env path | `/home/tiger/venvs/deepspec-hedge-v4-eagle3`，已确认无路径冲突，本阶段未创建 |
| HTTP port | `31001`，Phase 00 reservation 时无 listener |
| Worker state | `/home/tiger/.deepspec-hedge-v4-eagle3`，仅有 session owner marker |
| Worker scratch | `/tmp/deepspec-hedge-v4-eagle3`，仅有 session owner marker |
| HDFS root | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3` |
| Coordination | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-20260728T205627Z` |

### Worker 与进程结论

`mlx worker list` 再次显示 `4099544` 为 8×`NVIDIA-H20`。远端只读采集记录
hostname `g340-cd51-4b00-adb3-18a1-dd47-fb`，物理 GPU index `0..7` 均为
NVIDIA H20、每卡 `97871 MiB`、compute capability `9.0`。完整 UUID 和拓扑见
`worker_inventory.json` 与 `raw/gpu_topology.stdout.txt`。

采集时 `compute_pid_count=0`、`keepalive_candidate_pid_count=0`，所以没有旧任务需要
分类或等待。`existing_processes.json` 明确记录空进程集合和 `signal_sent=false`。
本阶段没有把空闲 worker 或显存占用写成 operational keepalive 成功；8 卡 keepalive
入口和 owner schema 只完成离线准备，尚未执行 10×1 秒逐卡门禁。

### 容量

只读 `df -B1` 记录：

- worker `/tmp`：总计 `3779301580800` bytes，可用 `3442749816832` bytes；
- HDFS：可用 `1124800395214848` bytes（FUSE 报告值，仅作容量观察）；
- shared filesystem：总计 `262092619776` bytes，可用 `121047613440` bytes。

### Phase 00 artifact

下列文件位于同一持久 run 目录：

- `bootstrap.json`
- `worker_inventory.json`
- `existing_processes.json`
- `worker_assignment.json`
- `deadlines.json`
- `phase-00-handoff.md`
- `namespace_bootstrap.json`
- `raw_commands.json` 与 `raw/` 全量命令输出

### Attempt 历史

| Attempt | Phase/mode | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- | --- |
| `20260728T205627Z-phase-00-bootstrap-01` | Phase 00 / CPU-only bootstrap | 新建 Eagle3 独立身份并只读 inventory | PASS，主 Agent 已验收 | 4099544 准确 8×H20 且两次 inventory 均无 compute PID/keepalive；未发 signal | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01` |

## 下一步

主 Agent 只读复核 Phase 00 artifact 和专属 worktree diff。验收通过后可并行派发
Phase 01A、01B、01C；在任何长下载或等待前，应由下一阶段按授权为当前空闲 lane 建立
并验证项目专用 8 卡 operational keepalive。本记录不声称 Phase 01 或任何模型实验已
开始。
