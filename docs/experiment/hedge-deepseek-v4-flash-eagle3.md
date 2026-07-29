# HEDGE on DeepSeek-V4-Flash Eagle3 实验记录

> **状态：`PHASE_02_COMPLETE`。** target-only TP=8
> diagnostic 与 native Eagle3 TP=8 smoke 均已跑通；这只是 bring-up，不是正式
> native baseline，32 条 calibration、`B=0`、`g/B` 与正式 500 条仍全部 pending。
> native 服务实际加载固定 target 和
> `LlamaForCausalLMEagle3` draft，TP0–7 均记录 draft `flashinfer` backend 与
> DeepSeek-V4 Eagle3 aux trace；3/3 顺序 API 请求 HTTP 200 并保存完整 token IDs
> 和 proposal/acceptance trace。短回答 smoke 的 accepted draft tokens 为 `0/9`，
> 本计划不设 acceptance 门槛，不能据此外推 calibration 或正式结果。
> attempt 结束后已定向 SIGTERM 登记的 server group，无 KILL fallback；8 卡
> context 清空，operational keepalive 恢复为 owner `315671`，8 张 H20 的
> 10×1 秒 utilization 均为 `100%`。DSpark pure HEDGE core marker 已 READY，
> 但本路线尚未 cherry-pick，也未进入 Phase 03。
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
>
> **权威 Phase 02 target artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235505Z-phase-02-target-diagnostic-02`
>
> **权威 Phase 02 native/TDD artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T002900Z-phase-02-tdd-native-adapter-01`
>
> **权威 Phase 02 native live artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T012234Z-phase-02-native-smoke-02`

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
| SGLang source | `/home/tiger/src/sglang-hedge-v4-eagle3`; HEAD/base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`; reviewed native runtime patch SHA-256 `64ce797b2a4ac5f668557fb481f9577c4a72baf601c5350eee03dd4ad7e60fe2`; final commit pending Phase 03 |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`; 73 regular files，`159630041626` bytes，manifest `af6f274af9b0b257a6b910ae9b8ac4d0e1dd0a0bbcd96898fc6772c7e158facd`，published |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d`; 7 regular files，`1858538499` bytes，manifest `dfa6b2de48c46f4fda0cf7070466d35e6bd3df44b84ba0363616cc0f1f6020a0`，published |
| HEDGE core | READY marker audited：pure-core commit `4d96f44065c07030ede67484a262006ec149626a`，33 tests PASS；not cherry-picked |
| Formal artifacts | pending |
| Phase 01B runtime | Python 3.11；Torch `2.11.0+cu130`；CUDA `13.0`；NCCL `2.28.9`；FlashInfer `0.6.14`；Triton `3.6.0`；sglang-kernel `0.4.5+cu130`；201 packages，`uv pip check` PASS |
| Dataset split | GSM8K revision `740312add88f781978c0658806c59bc2815b9866`，fingerprint `59ec1b7f9357c7a2`；seed `980406`；32 calibration + 500 formal，overlap 0 |
| Runner fixture | 10 warmup + 500 formal，500 terminal/500 success/5 retries，最大 in-flight 1；q25 fixture `g=B=1.75`，B0 PASS/FAIL 两路径 PASS |
| Phase 01C contract | logical `[1,21,40]` → hook `[2,22,41]` → 4-stream mean → `[N,3,4096]` → runner `[N,12288]`; 3 CPU tests PASS |
| Phase 01C research | `docs/research/hedge_eagle3_phase01c/eagle3_compatibility_research.md` |
| Phase 02 target | TP0–7、46/46 shards、packed FP4 `flashinfer_mxfp4`、八卡 context/API PASS；非正式 diagnostic |
| Phase 02 native | 3/3 terminal、6 completion tokens、proposal `3` / internal verify `4`、accepted `0/9`；八 rank Eagle3 aux trace PASS；非正式 smoke |
| Key commits | Phase 00 bootstrap `9369479acb6cbd88ae98a6e04446c6d50134feae`；Phase 01C contract `a8d913e8f200f02519a446ea77fcb235f2c76681`；Phase 01A publication `bb6ae8a92eac8c7d5a130b247835a01c70fe891b`；Phase 01B runtime `dccbb219faf25fa803cc27e26f59cc1b9786b9f4`（均已 push） |

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

## Phase 02：target diagnostic 与 native Eagle3 smoke

### 最小实现与可复现封存

Phase 02 按 TDD 完成 DeepSeek-V4 Eagle3 native adapter。目标模型的 logical layers
`[1,21,40]` 映射到 after-layer hooks `[2,22,41]`；每个原始 mHC tensor
`[N,4,4096]` 以 BF16 沿 stream 维求均值，按 logical layer 排序为
`[N,3,4096]`，再交付 runner 所需的 `[N,12288]`。实现明确隔离 DSpark capture，
并为每个 TP rank 只发一次 shape/dtype/device/checksum trace。

SGLang tracked runtime patch 为 `19290` bytes，SHA-256
`64ce797b2a4ac5f668557fb481f9577c4a72baf601c5350eee03dd4ad7e60fe2`；
source-side test 为 `9671` bytes，SHA-256
`2f32eecbe96c104352b9e9793da519abd339408044bc15b9a3c4994f3af5232b`。
两者已固化到 `patches/hedge_eagle3_phase02/`，并在固定 base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 的临时 clean worktree 上通过
`git apply --check` 和 11/11 tests；重放日志为
`canonical_clean_replay.log`，SHA-256
`99e52acf0c9e7c439ced3d525197e1deb948d2979a6d51c0635d63ac547a6024`。

native attempt 01 暴露 draft backend 继承错误：target 合法使用 `dsv4`，但
`LlamaForCausalLMEagle3` draft 的 `head_dim=128` 被送入只接受 DeepSeek-V4
`head_dim=512` 的 DSV4 backend assertion。单变量修复是只为 draft 显式设置
`flashinfer`，target 保持 `dsv4`。Phase 01B 的三臂配置源同时固定这一字段，保证后续
native、`B=0` 和 `B>0` 使用相同 decode-affecting server config。最终离线回归：
SGLang 11/11、Phase 01C 3/3、Phase 01B 6/6、Phase 02 safety 14/14 与 mock
10 warmup + 500 formal 全部 PASS；日志为 `offline_final_v3.log`，SHA-256
`b36b335cee4a615f3309a232b9740cb8c28b4afe925d675d0be33317701d9bdc`。

### Live 证据

target-only attempt 02 是隔离 diagnostic，不是 baseline：TP0–7 全部初始化，
46/46 target shards 加载完成，packed FP4 使用 `flashinfer_mxfp4`；八张物理 H20
均有 context/模型显存和请求期活动，OpenAI-compatible API 返回 HTTP 200 非空结果，
且无未处理 CUDA/NCCL/worker crash。

native attempt 02 使用相同 target、固定
`SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1` draft、TP=8、proposal tokens `3`
与 internal verify width `4`。TP0–7 均加载 `LlamaForCausalLMEagle3`，各 rank
明确记录 target `dsv4`、draft `flashinfer`，以及一次 Eagle3 aux trace：
raw shapes 均为 `[[4,4,4096]]*3`，structured `[4,3,4096]`，runner
`[4,12288]`，dtype BF16，device 分别为 local `cuda:0..7`。

服务 ready 后 3/3 顺序请求均 HTTP 200，保存完整响应和 output token IDs；共
6 completion tokens。三次 request 都有 `verify_count=1`、proposed draft
tokens `3`、accepted draft tokens `0`、histogram `[1,0,0,0]`，因此合计
accepted `0/9`。这是短回答基础设施 smoke，不是质量/性能评测；计划没有 acceptance
门槛，`0/9` 不影响 Phase 02 native bring-up PASS，也不能据此外推 calibration 或
formal arm。

native 请求窗口合计仅约 1 秒，1 秒粒度 sampler 在该切片捕获到 7/8 GPU 非零
utilization，GPU4 恰好漏采；因此不声称“精确请求窗口 sampled utilization 8/8”。
八卡参与结论由 TP0–7 各自的 forward aux trace、八张卡的 CUDA context/模型显存，
以及全服务期每卡 maximum utilization `100%` 共同支持。

server 登记身份为 `PID/PGID/SID=303437/303437/303437`。结束时仅向该 process
group 发送 SIGTERM，无 KILL fallback；随后验证八卡 CUDA context 为空。keepalive
恢复为 owner `315671`，准确 8 个 owned workers/context，8×10 个 1 秒样本逐卡
utilization 均为 `100%`。

### Attempt 历史

| Attempt | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- |
| `20260728T235315Z-phase-02-target-diagnostic-01` | 首次 target-only 编排 | FAIL CLOSED | `/proc/stat` 本地 Python one-liner 转义语法错误；服务未 ready，无模型结论；定向 SIGTERM、0 context、keepalive 恢复 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235315Z-phase-02-target-diagnostic-01` |
| `20260728T235505Z-phase-02-target-diagnostic-02` | 仅修正 sampler 编排语法 | PASS diagnostic | TP0–7、46/46 shards、packed FP4 backend、八卡参与和 HTTP 200 均证实；不作为 baseline | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235505Z-phase-02-target-diagnostic-02` |
| `20260729T002900Z-phase-02-tdd-native-adapter-01` | test-first 实现 aux adapter 与 native harness | PASS offline | patch/test 固化；draft backend inheritance 由专用 RED→GREEN 缩小并修复；clean-base replay 11/11 PASS | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T002900Z-phase-02-tdd-native-adapter-01` |
| `20260729T010230Z-phase-02-native-smoke-01` | 首次 target+draft native 启动 | FAIL CLOSED | draft 误继承 target `dsv4`，`head_dim=128` 触发 DSV4 `head_dim=512` assertion；精确清理、0 context、keepalive 恢复 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T010230Z-phase-02-native-smoke-01` |
| `20260729T012234Z-phase-02-native-smoke-02` | 唯一变化为 draft backend `flashinfer` | PASS native smoke | 8 ranks target+draft/aux trace、3/3 HTTP 200、token IDs 与 acceptance trace 完整；accepted `0/9` 非质量门槛；无未处理 crash | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T012234Z-phase-02-native-smoke-02` |

## 下一步

Phase 02 executor 已满足退出门禁，并经主 Agent 独立重放与 artifact 复核验收通过。
下一步进入 Phase 03：先保持 owner `315671` 的 8 卡 operational keepalive，核对 DSpark pure-core
commit/marker 与本仓库 canonical patch manifest，再 cherry-pick pure core 并以可复现
patch/build 注入独立 SGLang source。不得把本次 3-request smoke 写成 native baseline，
不得在 Phase 03 前运行 32 条 calibration、`B=0` 或正式 500 条。
