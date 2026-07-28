# Phase 01 Handoff

- Status: PASS
- Attempt ID: `20260728T151614Z-phase01-preflight`
- Started at: `2026-07-28T15:16:14Z`
- Finished at: `2026-07-28T16:12:08Z`（主 Agent 验收后完成 evidence
  reseal）
- Git branch / HEAD: `exp/v4-flash-dspark` /
  `b98846f8e78b4d9e0739df84b15d74b85b7007e1`
- Worktree: dirty；本 executor 未提交、未回滚用户或其他 agent 的修改
- Worker ID / hostname: `4105641` /
  `g340-cd51-4b00-e6cb-5724-8a1b-59f0`
- GPU UUIDs:
  - `GPU-dccbc830-5459-6b2b-84d5-a1eb5eb05252`
  - `GPU-9995c88c-bcf4-0482-60a5-fc04880a0df8`
  - `GPU-8e412234-a4de-5e4c-1414-6d3acd681896`
  - `GPU-26c888a5-df24-039f-c0c5-621163ce32cf`
- Authorized phase: Phase 01 — 平台 preflight 与源 checkpoint 身份确认
- Artifact root:
  `/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T151614Z-phase01-preflight`

## Outcome

Phase 01 退出门禁通过，且主 Agent 验收发现的 gate sealing-order 缺陷已经修复并
重新封存。当前 worker 被证明为准确的单机
4×NVIDIA H20-96G；四卡 CUDA peer access 与 4-rank NCCL all-reduce 均通过；存储、
网络、工具链和源 checkpoint 证据已保存。现有 ModelScope source 可固定为完整
cryptographic manifest snapshot，因此获取决策为 `copy_verified_source`。

本阶段没有复制 checkpoint、创建正式 uv 环境、安装 SGLang 或启动模型。

## Changes

### HDFS artifacts

以下 required artifacts 已生成：

- `environment.json`
- `worker_inventory.json`
- `storage_report.json`
- `source_checkpoint_manifest.json`
- `acquisition_decision.json`
- `preflight.log`

辅助证据还包括：

- `phase01_gate.json`
- `checkpoint_manifest_validation.json`
- `modelscope_repository_metadata.json`
- `modelscope_file_metadata.json`
- `hf_revision_metadata.json`
- `gpu_probe.json` 与 `gpu_probe_rank_{0..3}.json`
- `nccl_probe.log`
- `process_inventory_after_incident.json`
- `cuda_toolchain_discovery.json`
- `worker_connectivity.json`
- `keepalive_exit.txt`
- `worker_list_exit.txt`

### Repository files

本 executor 新增了 Phase 01 的只读采集、校验和退出门禁脚本，以及本 handoff。未修改
`AGENTS.md`、`CONTEXT.md`、总计划或既有 keepalive 脚本；这些文件的并发修改属于主
Agent。未创建 git commit。

## Evidence

### Worker 与 GPU

- `worker_inventory.json`：
  - `gpu_count=4`；
  - 四卡均为 `NVIDIA H20`，每卡 `97871 MiB`；
  - compute capability 均为 `9.0`；
  - Driver `535.261.03`，系统 CUDA compatibility / toolkit `12.6`；
  - `nvidia-smi topo -m` 显示四卡两两 `NV18`；
  - `nvidia-smi topo -p2p r/w` 的所有非对角项均为 `OK`。
- `gpu_probe.json`：
  - `status=pass`；
  - 4 个 rank 的 NCCL all-reduce 均得到期望值 `10.0`；
  - CUDA P2P 4×4 matrix 全部为 `true`；
  - 探针使用 PyTorch `2.9.1+cu128`、NCCL `2.27.5`。
- `worker_connectivity.json`：worker 到 GitHub、Hugging Face 和 ModelScope 均返回
  HTTP 200。

### CUDA / build toolchain

- worker 系统 `nvcc` 为 `12.6.85`。
- 已发现共享的私有 CUDA 13.3 compat 与 `ptxas 13.3.73`，但
  `formal_toolchain_selected=false`。
- 这些 CUDA 13.3 组件不应与 Phase 03 的 CUDA 13.0 runtime headers 混用。Phase 03
  必须建立并验证一套自洽的 CUDA 13.0 JIT toolchain 和 driver forward-compat
  prefix。
- devbox 与 worker 都有 `uv 0.11.32`、Python 3.11、GCC/G++ 和 CMake；当前未发现
  `ninja`、`rustc` 或 `cargo`。这是 Phase 03 的显式安装前置项，不是 Phase 02
  checkpoint 复制 blocker。

### 存储

`storage_report.json` 记录：

- devbox shared root 可用约 `148.7 GB`，不用于 checkpoint；
- HDFS 可用 `1124800395214848` bytes；
- worker `/tmp` 可用 `3077796872192` bytes；
- 为一份独立 checkpoint 加 50 GiB artifact reserve 计算的需求为
  `220585758052` bytes，capacity gate 通过。

### ModelScope source identity

源目录：

```text
/mnt/hdfs/pengzegang/HEDGE/models/deepseek-ai__DeepSeek-V4-Flash-DSpark
```

完整读取前后文件 snapshot 一致。独立 validator 的结论：

- ModelScope official provider files：`75/75` 的 size 和 SHA-256 全匹配；
- provider payload bytes：`166898666759`；
- 本地 regular files：76 个，额外文件仅为本地 `.complete`；
- 48 个实际 weight shards 与 index 引用的 48 个 shards 均精确完整；
- `expert_dtype=fp4`；
- `dspark_block_size=5`；
- `dspark_target_layer_ids=[40, 41, 42]`；
- `num_nextn_predict_layers=1`；
- tokenizer、config、configuration、generation config 和 weight index 均存在；
- provider payload snapshot ID：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`；
- including-local-marker tree snapshot ID：
  `72e6ae851c07e719cc297cfb3b91096824bc0346ce0a66d5862ca779c83ff2fd`；
- 最终 `source_checkpoint_manifest.json` SHA-256：
  `186d562ff6b1ebda2051cd12725acf5d230ed55a078106de95137630434806e9`。

ModelScope API 只提供 symbolic `master` 和逐文件 revisions，没有可证明的单一 immutable
resolved commit。因此以上完整 payload manifest SHA-256 是本次 canonical snapshot
identity。

### Hugging Face cross-provider reference

相对于
`62af8fffb2f7030cac4de2f0169f5b8d1101b646`：

- 48/48 weight shards 的 LFS SHA-256 全匹配；
- Hugging Face 中存在的 5 个核心 config/tokenizer/index blob 全匹配；
- 核心文件无 mismatch；
- ancillary mismatch 仅为 `.gitattributes` 与 `LICENSE`；
- ModelScope snapshot 另有 `configuration.json`。

这些非模型 metadata 差异按已更新约束不阻止 ModelScope snapshot 使用，但均完整记录。

### Acquisition decision

`acquisition_decision.json`：

- decision：`copy_verified_source`；
- provider：`modelscope`；
- gaps：空；
- Phase 02 推荐目标：
  `/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`；
- `publication_authorized=false`、`copy_started=false`。

## Process and GPU state at exit

- SGLang PID/PGID：无；本阶段未启动 SGLang。
- Phase 01 probe：`process_inventory_after_incident.json` 证明无 active probe
  process。
- Operational keepalive：
  - worker-local supervisor PID：`2492`；
  - process identity 由 worker `4105641` 上远程执行的项目
    `scripts/keepalive.sh status` 验证；
  - 最终 10×1 秒采样中 GPU 0–3 的 mean/min/max 均为 `100%`；
  - 每卡 `sample_count=10`，总报告 `sample_count=10`、
    `underutilized_gpus=[]`；
  - 每卡显存约 `811 MiB`；
  - `phase01_gate.json` 最终状态为 `PASS`，errors 为空；
  - `keepalive_remote_status_10x1s_passed=true`。

## Failure or open questions

### GPU probe lifecycle incident

首轮 `mlx worker login` 客户端在远端 wrapper 完成前返回。executor 随后手动恢复
keepalive；远端原 wrapper 后续把新 keepalive 的 host PID 误判为 probe residual。
四个 rank JSON 与 NCCL log 证明 NCCL/P2P 探针本身已成功，故事件分类为：

```text
client_observation_and_concurrent_recovery_defect
```

它不是 NCCL failure，也不计为 DSpark attempt。wrapper 已加入 registered
PID/PGID/SID、有界 timeout、heartbeat 和 ERR/HUP/INT/TERM/EXIT 恢复路径，但根据主
Agent 决策没有为验证 wrapper 再执行第二次 GPU lifecycle；现有 rank 证据已经完整。

### HDFS append incident

完整 hash 期间 HDFS FUSE 对长持有的 `tee -a preflight.log` 返回一次
`Operation not supported`，使外层 pipeline 返回 1；hash Python 继续完成并原子写出
manifest。独立 validator 从逐文件 records 重算 file count、bytes、payload/tree
snapshot ID，结论为 PASS。`preflight.log` 已通过短生命周期原子替换补入事件和最终
摘要。后续 heartbeat 不应长持有 HDFS append fd。

已知 residual risk：历史执行脚本 `scripts/phase01_checkpoint_verify.sh` 仍保留长时间
`tee -a` HDFS 日志的实现，若原样重跑可能再次得到 wrapper 假失败。按用户的优先级
决定，本轮不再为已经完成的 Phase 01 重构该 wrapper；Phase 02 不调用它。后续若需要
重新执行完整 checkpoint hash，应先把活动日志放到 worker NVMe `/tmp`，结束后再以
短生命周期操作转移并二次校验 HDFS 留存副本。

### Gate sealing-order incident

主 Agent 在首次阶段验收时发现，旧 gate 中 `preflight.log` 的记录是追加退出摘要前的
`11406` bytes / `7f0bf160...`，而 gate 写出后 audit 又向同一日志追加
`PHASE01_EXIT_GATE`，使当前文件变为 `11984` bytes / `75e50868...`。这属于证据封存
顺序缺陷，不是 GPU、checkpoint 或模型故障。

修复后：

1. `phase01_exit_gate.sh` 在 worker 上完成 10×1 秒 status，并通过临时文件和原子
   rename 发布 `keepalive_exit.txt`；
2. `phase01_gate_audit.py` 完成 worker、keepalive 和全部 Phase 01 判断；
3. audit 先以短生命周期临时文件和原子 replace 封存唯一的最终
   `PHASE01_EXIT_GATE` summary；
4. 封存后才计算 6 个 required artifacts 的最终 size/SHA-256；
5. 最后原子写 `phase01_gate.json`，字段明确命名为
   `required_final_artifact_hashes`；gate 写出后不再修改任何 covered artifact。

本次只重跑远端 keepalive status 和小型 gate audit，没有重跑 GPU probe，也没有重新
读取或 hash 155 GiB checkpoint。独立只读验收结果：

- 6/6 `required_final_artifact_hashes` 均与当前文件完全匹配；
- 所有 covered JSON 与 gate 均可解析；
- gate `status=PASS`、`errors=[]`；
- 最终 `preflight.log`：`12106` bytes，
  SHA-256 `acde1f789be3170016a59aff76ff1d89f4fb9d0829ff0283ed2682eaddc0de36`；
- `source_checkpoint_manifest.json` 仍为 `125329` bytes，
  SHA-256 `186d562ff6b1ebda2051cd12725acf5d230ed55a078106de95137630434806e9`；
- 最终 `phase01_gate.json`：`2559` bytes，
  SHA-256 `eac1e4ad596915a36d074aa46ba278dddb56dde1c50428cb43cdea90895935e8`。

连续无进展 attempt 计数：不适用；本阶段没有 DSpark model attempt。

## Suggested staging

主 Agent 若在阶段验收节点提交，建议只暂存本 executor 产生的以下文件：

```text
scripts/phase01_checkpoint_manifest.py
scripts/phase01_checkpoint_verify.sh
scripts/phase01_cuda_toolchain_discovery.py
scripts/phase01_cuda_toolchain_discovery.sh
scripts/phase01_exit_gate.sh
scripts/phase01_finalize.py
scripts/phase01_gate_audit.py
scripts/phase01_process_inventory.sh
scripts/phase01_remote_preflight.sh
scripts/phase01_validate_manifest.py
scripts/phase01_worker_connectivity.sh
scripts/phase01_worker_probe.py
docs/plan/handoffs/phase-01-20260728T151614Z-phase01-preflight.md
```

不要把 HDFS artifacts、checkpoint、virtualenv、package cache 或其他 agent 的并行 HF
staging 脚本混入本 executor 的 Phase 01 提交。

## Next eligible phase

Phase 01 已具备进入 Phase 02 的技术前置条件。只有用户确认后，主 Agent 才能调度
Phase 02 executor；本 handoff 不构成 Phase 02 授权，也未执行任何复制或发布。
