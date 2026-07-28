# HEDGE on DeepSeek-V4-Flash Eagle3 实验记录

> **状态：`PHASE_01_COMPLETE`。** Phase 00 与 Phase 01A/B/C 均已由主 Agent
> 验收，具备进入 Phase 02 的条件；尚无模型或正式结果。固定 target 与 draft 均已
> 发布为独立 HDFS 实体；共享 target complete marker 可供 DFlash 只读复核。
> worker `4099544` 上的项目专用
> 8 卡 operational keepalive 已于 `2026-07-28T22:39:34Z` 建立：8 张
> NVIDIA H20 各有 10 个一秒样本且 mean utilization 均为 `100%`，owner
> `PID/PGID/SID=277607/277607/277607`，精确 UUID、进程归属和 CUDA 13
> forward-compat 链接顺序均已由主 Agent 复核；Phase 01B 最终状态复核仍为八卡
> mean utilization `100%`。target/draft acquisition 已自然结束，发布后的 NVMe
> snapshot、owner、manifest 和日志证据仍保留。
> DSpark pure HEDGE core marker 已只读验收为 READY，但本路线尚未 cherry-pick。
> 固定 SGLang 的顺序 blocker 已缩小为 DeepSeek-V4 guard 首先拒绝 `EAGLE3`，
> 放开后缺少独立 `set_eagle3_layers_to_capture` 与 V4 mHC aux capture。
> Phase 01B 的独立 uv/SGLang、固定 GSM8K split、顺序 runner、B0/q25/report
> fixtures 与定向 process cleanup 均 PASS。当前尚未启动模型服务或正式实验；
> 后续结果仍全部 pending。
>
> **自主窗口（UTC）：** T0 `2026-07-28T20:56:27Z`；
> 实现门槛 `2026-07-29T05:56:27Z`；硬停止 `2026-07-29T08:56:27Z`。
>
> **权威 Phase 00 artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01`
>
> **权威 Phase 01A artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T211500Z-phase-01a-acquisition-01`
>
> **权威 Phase 01B artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T232000Z-phase-01b-final-17`

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
| SGLang source | `/home/tiger/src/sglang-hedge-v4-eagle3`; clean base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`; source/import/lock gates PASS |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`; 73 regular files，`159630041626` bytes，manifest `af6f274af9b0b257a6b910ae9b8ac4d0e1dd0a0bbcd96898fc6772c7e158facd`，published |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d`; 7 regular files，`1858538499` bytes，manifest `dfa6b2de48c46f4fda0cf7070466d35e6bd3df44b84ba0363616cc0f1f6020a0`，published |
| HEDGE core | READY marker audited：pure-core commit `4d96f44065c07030ede67484a262006ec149626a`，33 tests PASS；not cherry-picked |
| Formal artifacts | pending |
| Phase 01B runtime | Python 3.11；Torch `2.11.0+cu130`；CUDA `13.0`；NCCL `2.28.9`；FlashInfer `0.6.14`；Triton `3.6.0`；sglang-kernel `0.4.5+cu130`；201 packages，`uv pip check` PASS |
| Dataset split | GSM8K revision `740312add88f781978c0658806c59bc2815b9866`，fingerprint `59ec1b7f9357c7a2`；seed `980406`；32 calibration + 500 formal，overlap 0 |
| Runner fixture | 10 warmup + 500 formal，500 terminal/500 success/5 retries，最大 in-flight 1；q25 fixture `g=B=1.75`，B0 PASS/FAIL 两路径 PASS |
| Phase 01C contract | logical `[1,21,40]` → hook `[2,22,41]` → 4-stream mean → `[N,3,4096]` → runner `[N,12288]`; 3 CPU tests PASS |
| Phase 01C research | `docs/research/hedge_eagle3_phase01c/eagle3_compatibility_research.md` |
| Key commits | Phase 00 bootstrap `9369479acb6cbd88ae98a6e04446c6d50134feae`；Phase 01C contract `a8d913e8f200f02519a446ea77fcb235f2c76681`；Phase 01A publication `bb6ae8a92eac8c7d5a130b247835a01c70fe891b`（均已 push）；Phase 01B runtime commit 待本次提交后回填 |

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
| `phase-01c-contract` | Phase 01C / CPU-only research + fixture | 固定 checkpoint、SGLang 与一手实现上建立 aux interface | PASS，主 Agent 复跑 3 tests | blocker 顺序缩小为 guard → V4 capture；TP ownership 明确保留到 Phase 02 live assertion | `docs/research/hedge_eagle3_phase01c/` |
| `20260728T223200Z-phase-01b-keepalive-05` | Phase 01B / operational keepalive | 首次用 lane-local torch/CUDA 闭包启动 8 卡 keepalive | FAIL，前后均为 0 context | `LD_LIBRARY_PATH` 误用 `/usr/local/cuda/compat`，CUDA 13 runtime 只看到宿主 driver 12.6；未叠加进程 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T223200Z-phase-01b-keepalive-05` |
| `20260728T223600Z-phase-01b-keepalive-06` | Phase 01B / operational keepalive | 唯一变化为已验证私有 CUDA 13 compat prefix | PASS，active | 8×10 样本逐卡 mean=100%；精确 owner/descendants、UUID、环境与设备用户证据通过 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T223600Z-phase-01b-keepalive-06` |
| `20260728T211500Z-phase-01a-acquisition-01` | Phase 01A / pinned acquisition | 双 keepalive gate 后启动唯一 target/draft 下载 | PASS，主 Agent 已验收 | 两个 provider commit/OID、manifest、size、index/config/tokenizer 和 HDFS entity 均通过；target marker 最后发布；0 symlink/hardlink | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T211500Z-phase-01a-acquisition-01` |
| `20260728T224200Z-phase-01b-full-env-07` → `...224500Z...-08` → `...224800Z...-09` | Phase 01B / isolated runtime | 每次只补齐当前缺失的 Rust，再补 pinned protoc | PASS | blocker 依次从缺 Rust 迁移至缺 protoc，最后 frozen sync、editable source import 与 `uv pip check` PASS | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T224800Z-phase-01b-full-env-protoc-09` |
| `20260728T230000Z-phase-01b-dataset-11` → `...230100Z...-12` | Phase 01B / pinned dataset | 仅修正本地 revision 常量的尾字符 | PASS | provider 对错误 revision fail-closed；固定 revision、fingerprint、确定性 split 与 request contract 经独立重算一致 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T230100Z-phase-01b-dataset-revision-12` |
| `20260728T230600Z-phase-01b-fixtures-13` → `...231000Z...-14` → `...231700Z...-15` | Phase 01B / runner/process fixtures | 先增加差异诊断，再仅对 lane-local loopback bypass inherited proxy | PASS | 定位 `HTTP_PROXY` 劫持 loopback；10+500、retry、B0、q25、答案解析和精确 PGID cleanup 全部通过 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T231700Z-phase-01b-fixtures-proxy-bypass-15` |
| `20260728T232000Z-phase-01b-final-17` | Phase 01B / authoritative seal | required artifacts 采用 temp→fsync→hash→atomic replace→post-validate | PASS，主 Agent 已验收 | 初次封存暴露 runner summary 零长度竞态；修复后 6 个 artifact 的 size/hash 与 manifest 全部独立复算一致，无 empty SHA | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T232000Z-phase-01b-final-17` |

## 下一步

保持已验收的 8 卡 operational keepalive。Phase 02 按 test-first 与 01C 已证据化的
guard → capture → loader → runner 顺序进入 native bring-up：每个正式模型 attempt
紧邻地定向暂停 keepalive、确认 8 个 CUDA context 均退出；先做 target-only TP=8
诊断，再做 native Eagle3 smoke，并在每个 attempt 后恢复 keepalive。OpenAI chat
完整 output token IDs 是 fail-closed runtime gate，禁止静默重 tokenize。本记录不声称
任何模型实验已开始。
