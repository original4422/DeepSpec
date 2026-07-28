# DeepSeek-V4-Flash-DSpark 4×H20 MVP 分阶段执行计划

- 状态：Phase 01 已授权；后续阶段采用用户确认门禁
- 更新日期：2026-07-28
- 仓库：`/mlx_devbox/users/pengzegang/playground/github/DeepSpec`
- 核心目标：在单机 4×NVIDIA H20-96G 上使用 SGLang 实际跑通
  `deepseek-ai/DeepSeek-V4-Flash-DSpark`，并完成 GSM8K test split
  前 10 条的顺序 smoke test

本文是主 Agent 调度 phase executor 时的主计划。行为约束以仓库根目录的
[`AGENTS.md`](../../AGENTS.md) 为准，领域语言以
[`CONTEXT.md`](../../CONTEXT.md) 为准；本文负责定义阶段边界、依赖关系、交付物和
交接协议。

> 主 Agent 负责分配、调整和结果验收，每个阶段由独立 subagent 实施。阶段结束后，
> 主 Agent 必须向用户提交结果汇总、符合预期判断和下一阶段就绪判断；只有用户确认
> 后才能派发下一阶段。Phase 01 依据当前对话已获授权。

## 1. MVP 完成定义

只有以下条件同时成立，最终审计才可以判定 `MVP_PASS`：

1. 当前 worker 被准确识别为单机 4×NVIDIA H20-96G，且四张卡实际参与推理；
2. 正式环境由 uv 独立管理；
3. 实际运行固定的 SGLang source commit；
4. 固定 revision 的官方 checkpoint 完整加载；
5. 日志证明 `speculative_algorithm='DSPARK'`；
6. 四个 TP rank 均成功加载 DSpark draft architecture，无静默降级；
7. OpenAI-compatible API 返回合法、非空响应；
8. GSM8K `openai/gsm8k`、`main`、`test` 前 10 条全部达到终态并保存；
9. 每条样本都保存标准答案、完整模型响应、提取答案、提取规则、匹配状态和解析状态；
10. 自动汇总成功、失败、匹配、不匹配和解析失败数量；
11. 正式运行期间没有未处理的 CUDA、NCCL 或 worker crash；
12. 正式服务退出后 CUDA context 已清空，operational keepalive 已恢复并重新通过逐卡
    利用率门禁。

GSM8K 匹配率只展示，不设成功门槛。target-only diagnostic attempt 永远不能满足
`MVP_PASS`。

## 2. 已冻结的技术决策

| 项目 | 冻结值 |
| --- | --- |
| 硬件 | 当前 `mlx worker list` 中准确的单机 4×H20-96G worker |
| 模型 | `deepseek-ai/DeepSeek-V4-Flash-DSpark` |
| Hugging Face revision | `62af8fffb2f7030cac4de2f0169f5b8d1101b646` |
| SGLang release | `v0.5.16` |
| SGLang source commit | `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| 并行方式 | TP=4；禁用 DP、PP、EP 和分离式部署 |
| DSpark block size | checkpoint 默认值 `5` |
| ragged verify | `SGLANG_RAGGED_VERIFY_MODE=static` |
| 首选 MoE backend | `flashinfer_mxfp4`，保留 packed FP4 |
| 条件回退 backend | 仅有明确 backend/kernel 证据后使用 `marlin` |
| 首轮禁止项 | FP4→FP8 dequant、compact verify、所有 CUDA Graph、overlap schedule、radix cache |
| 请求模型 | 单请求顺序执行、低并发、短上下文 |
| 环境 | uv；正式虚拟环境 `/home/tiger/venvs/deepspec-dspark` |
| 大文件 | `/mnt/hdfs/pengzegang/DeepSpec` |
| 故障停止点 | 连续 3 个 attempt 无可验证进展后停止并交还用户决策 |
| 结束状态 | 停止 SGLang、清空 CUDA context、恢复 keepalive |

4 卡首轮不得设置 `SGLANG_DSV4_FP4_DEQUANT=1`。扩大到 8 卡、引入 offload、改变
checkpoint 表示或执行破坏性操作，不属于任何阶段的隐含授权。

## 3. 固定路径与命名

执行阶段使用以下逻辑路径；若现场发现路径不可用，必须在 handoff 中说明，不能静默
改到开发机大容量目录：

```text
REPO_ROOT=/mlx_devbox/users/pengzegang/playground/github/DeepSpec
FORMAL_VENV=/home/tiger/venvs/deepspec-dspark
HDFS_ROOT=/mnt/hdfs/pengzegang/DeepSpec
SOURCE_MODEL=/mnt/hdfs/pengzegang/HEDGE/models/deepseek-ai__DeepSeek-V4-Flash-DSpark
MODEL_PARENT=/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark
MODEL_REVISION_PATH=/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/revisions/62af8fffb2f7030cac4de2f0169f5b8d1101b646
RUN_ROOT=/mnt/hdfs/pengzegang/DeepSpec/runs
```

attempt ID 使用 UTC 时间和阶段名，示例：

```text
20260728T150000Z-phase05-dspark-flashinfer-mxfp4
```

每个 attempt 必须创建新的 `$RUN_ROOT/<attempt-id>/`，不得覆盖失败证据。仓库中的小型
handoff 写入：

```text
docs/plan/handoffs/<phase-id>-<attempt-id>.md
```

## 4. 主 Agent 与 phase executor 协议

### 4.1 职责分工

| 角色 | 职责 | 不得执行 |
| --- | --- | --- |
| 用户 | 审阅每阶段结果和主 Agent 判断，确认是否进入下一阶段；决定范围扩大和连续 3 次无进展后的方向 | 不负责替代阶段证据验收 |
| 主 Agent | 阶段拆分、subagent 调度、keepalive 协调、纠偏、只读复核、阶段验收和用户汇报 | 不直接替代 phase executor 实施阶段性工作，不凭摘要跳过证据 |
| Phase executor | 只实施一个被分配阶段，保存过程证据，完成清理并写 handoff | 不进入下一阶段，不扩大范围，不把局部成功写成阶段 PASS |

主 Agent 必须顺序调度有依赖关系的阶段。只有任务真正独立且不会共享 GPU、正式环境或
同一 artifact 路径时才可并行；正式模型 attempt 始终只有一个 owner。

### 4.2 Phase executor 入口

每个 phase executor 开始时必须依次：

1. 完整读取 `AGENTS.md`、`CONTEXT.md` 和本文；
2. 确认主 Agent 的任务中明确点名了唯一允许执行的阶段；
3. 读取上一阶段 handoff 和它引用的 HDFS artifacts；
4. 记录 Git branch、HEAD 和工作区状态，保留用户已有修改；
5. 重新运行 `mlx worker list`，根据卡数和型号选择当前 4×H20 worker；
6. 不把本文或旧 handoff 中的 worker ID、hostname、PID 当作当前事实；
7. 检查项目 keepalive 的 PID/PGID identity、CUDA context 和 10×1 秒逐卡利用率；
8. 为本阶段生成新的 attempt ID 和 artifact 目录；
9. 先声明本阶段的输入、预期退出门禁和下一检查点，再开始操作。

如果 worker 已消失，当前阶段先标为 `INTERRUPTED`，在 replacement worker 上完整重做
Phase 01 的 worker preflight；不能沿用旧 worker 的 GPU、Driver、CUDA 或 topology
结论。

### 4.3 长任务纪律

- 任何预计超过 20 分钟的复制、安装、编译或运行，都必须保存心跳并检查 worker 是否
  仍存在；
- 无模型运行时保持项目专用 keepalive，并持续满足四张卡平均利用率至少 40%；
- 模型运行前紧邻暂停 keepalive，确认全部 keepalive CUDA context 已退出，随后立即
  启动已经登记的模型命令；
- keepalive 与正式模型运行、API smoke 或 GSM8K smoke 不得并发；
- 远程长任务先落成仓库脚本，再从仓库根目录以绝对路径通过
  `mlx worker login <id> -- bash <absolute-script-path>` 调用；
- 只清理本 attempt 已验证归属的 PID/PGID，禁止 broad `pkill` 或 `killall`。

### 4.4 Phase executor 退出与主 Agent 验收

每个 phase executor 结束前必须：

1. 完成本阶段的 PASS/FAIL/INTERRUPTED 判定，不能把部分完成写成 PASS；
2. 保存完整命令、环境、日志、hash、错误和修改清单；
3. 定向停止本阶段不应跨 handoff 存活的进程；
4. 如果本阶段使用了正式 GPU 负载，证明其 CUDA context 已退出；
5. 恢复 keepalive，并重新通过 10×1 秒、逐卡平均至少 40% 的门禁；
6. 写入本阶段 handoff；
7. 向主 Agent 报告结论和证据，明确下一阶段是否具备前置条件，但不执行下一阶段。

主 Agent 必须亲自核对退出门禁和关键 artifact，才能把阶段标为 PASS。验收不通过时，
主 Agent 向原 subagent 追派明确修正，或以新 subagent/new attempt 重新分配；不得为了
赶进度降低门禁。验收完成后，主 Agent 必须向用户报告：

1. 本阶段结果汇总；
2. 是否符合预期及其证据；
3. 是否具备进入下一阶段的条件；
4. 建议进入、修正或停止。

在用户确认前，主 Agent 不得派发下一阶段。

正式 SGLang server 不允许跨 phase executor/handoff 闲置。服务启动、API smoke、
GSM8K smoke、服务停止和 keepalive 恢复被设计为 Phase 05 内的一个原子生命周期。

### 4.5 Git checkpoint

Git 提交由主 Agent 统一执行，phase executor 不 commit。以下视为关键节点：

1. `AGENTS.md`、`CONTEXT.md`、总计划和 operational keepalive 构成的治理基线；
2. 每个阶段完成、主 Agent 验收并形成 handoff；
3. 具有复现价值的 Phase R 诊断或修复；
4. Phase 06 最终审计。

每个关键节点的顺序固定为：

```text
phase executor 完成
→ 主 Agent 只读验收
→ 显式暂存该节点相关文件
→ 使用 $git-commit-message 检查 staged diff、status 和 recent log
→ 主 Agent 提交 Conventional Commit
→ 向用户汇总结果、符合预期判断和下一阶段就绪判断
→ 等待用户确认
```

如果阶段尚需修正，不为半成品创建“成功”提交；终态失败但包含可复现诊断价值时，可以
创建准确标明诊断结果的提交。任何 commit 都不得包含模型、HDFS artifacts、virtualenv、
package cache、worker scratch 或无关用户修改。

## 5. 阶段总览

| 阶段 | Phase executor 目标 | GPU 状态 | 主要退出产物 |
| --- | --- | --- | --- |
| Phase 01 | 平台 preflight 与源 checkpoint 身份确认 | keepalive；短 GPU 检查时受控暂停 | 环境记录、源 manifest、获取方式决策 |
| Phase 02 | 创建 DeepSpec-owned checkpoint copy | keepalive 持续运行 | 已发布模型目录、目标 manifest |
| Phase 03 | 建立 uv 环境并固定 SGLang source | keepalive；CUDA 验证时受控暂停 | `pyproject.toml`、`uv.lock`、依赖与源码身份 |
| Phase 04 | 构建并离线验证运行工具链 | keepalive 持续运行 | launcher、monitor、API/GSM8K runner、resolved baseline |
| Phase 05 | 首次正式 DSpark 端到端 attempt | 暂停 keepalive；结束后恢复 | server/API/GSM8K/GPU 全套证据 |
| Phase R | 条件恢复或 diagnostic attempt | 与 Phase 05 相同的原子生命周期 | 单变量对比证据或升级建议 |
| Phase 06 | 离线验收与最终报告 | keepalive 持续运行 | `MVP_PASS` 或可复查的未完成结论 |

主路径固定为：

```text
Phase 01 → Phase 02 → Phase 03 → Phase 04 → Phase 05 → Phase 06
                                                   │
                                                   └─失败→ Phase R
                                                             ├─DSpark 成功→ Phase 06
                                                             ├─有进展→ 新 Phase R
                                                             └─连续 3 次无进展→ 用户决策
```

## 6. Phase 01：平台 preflight 与源 checkpoint 身份确认

### 目标

在不复制 checkpoint、不安装正式环境、不启动模型的前提下，建立后续阶段可以信任的
平台、worker、存储、网络和源 checkpoint 基线。

### 允许执行

1. 记录 Git branch、HEAD、工作区状态和操作系统信息；
2. 重新选择准确的 4×H20 worker，记录 worker ID、hostname、GPU UUID、型号、显存、
   compute capability、Driver 和 CUDA compatibility；
3. 记录 `nvidia-smi topo -m`、NCCL 信息和 GPU P2P 能力；
4. 检查开发机共享 root、HDFS 和 worker `/tmp` 容量；
5. 检查 `uv`、Python、编译工具、Rust、GitHub 和 Hugging Face 连通性；
6. 只读检查 `$SOURCE_MODEL`：
   - 文件总数和总字节数；
   - 48 个权重 shard；
   - `config.json`、tokenizer、权重 index 和 `.complete`；
   - `dspark_block_size=5`、量化配置和 DSpark draft 配置；
   - 本地 manifest、关键文件 hash 和 revision provenance；
7. 使用 Hugging Face 固定 revision 的官方文件/LFS metadata 验证源目录身份，不能凭
   目录名推断；
8. 对需要占用 GPU 的短 NCCL/P2P 检查，按通用协议暂停并恢复 keepalive。

### 获取方式决策

- 如果既有源 checkpoint 可证明与固定 revision 完全一致，Phase 02 选择
  `copy_verified_source`；
- 如果无法证明 revision 或完整性，记录具体缺口，Phase 02 选择
  `download_fixed_revision`；
- 不允许把“文件看起来齐全”当作 revision 证明。

### 必须保存

```text
environment.json
worker_inventory.json
storage_report.json
source_checkpoint_manifest.json
acquisition_decision.json
preflight.log
```

### PASS 门禁

- 当前 worker 被证明是准确的 4×H20；
- Driver/CUDA compatibility、topology、P2P/NCCL 没有未解释的硬 blocker；
- 三类存储位置容量均已记录，HDFS 能容纳独立模型副本和运行产物；
- 模型获取方式被明确判定为 `copy_verified_source` 或
  `download_fixed_revision`；
- keepalive 在阶段退出时健康。

### Handoff

写入 `docs/plan/handoffs/phase-01-<attempt-id>.md`。Phase 01 不创建正式虚拟环境，
不复制模型，也不启动 SGLang。

## 7. Phase 02：创建 DeepSpec-owned checkpoint copy

### 前置条件

- Phase 01 PASS；
- `acquisition_decision.json` 明确模型来源；
- `$MODEL_REVISION_PATH` 的父目录空间充足；
- keepalive 健康。

### 允许执行

1. 在 `$MODEL_PARENT/revisions/` 下创建同文件系统的唯一 staging 目录；
2. `copy_verified_source` 模式下只读复制 `$SOURCE_MODEL`；
3. `download_fixed_revision` 模式下只下载固定 revision，不跟随浮动 branch；
4. 禁止 symlink、hardlink、reflink 或 Hugging Face cache 引用代替实体复制；
5. 复制期间保存进度、心跳、源目录不变证据和 worker 存活状态；
6. 在 staging 中验证：
   - 文件清单、48 个 shard 和总字节数；
   - 关键配置与 tokenizer；
   - 每个大文件的固定 revision hash/LFS OID 或等价完整 manifest；
   - 无 symlink，目标 inode 不与源文件共享；
7. 完整验证后，在同一父目录内发布为 `$MODEL_REVISION_PATH`；
8. 最后写入包含 revision、manifest hash、来源和完成时间的 `.complete`。

如果正式目标目录已经存在：

- 先只读验证；
- 完全符合时可以判定本阶段幂等完成，因为它已经是 DeepSpec-owned 实体副本；
- 不符合时禁止覆盖或删除，保存差异并交还用户决策。

### 必须保存

```text
copy_or_download.log
source_checkpoint_manifest.json
destination_checkpoint_manifest.json
checkpoint_provenance.json
storage_after.json
```

### PASS 门禁

- `$MODEL_REVISION_PATH` 是完整独立实体副本；
- revision、48 个 shard、大小和 manifest 验证全部通过；
- 源 checkpoint 未被修改；
- 没有 staging 目录被误写成正式路径；
- keepalive 在整个长任务期间持续健康，阶段退出时再次通过门禁。

### Handoff

写入 `docs/plan/handoffs/phase-02-<attempt-id>.md`，给出正式模型路径和 manifest hash。
本阶段不安装环境、不启动模型。

## 8. Phase 03：uv 环境与固定 SGLang source

### 前置条件

- Phase 02 PASS；
- Phase 01 的 Driver/CUDA/toolchain 证据可用；
- keepalive 健康。

### 允许执行

1. 根据现场 Driver、CUDA compatibility 和 SGLang `v0.5.16` 约束选择 Python 与
   PyTorch CUDA 组合；
2. 只用 uv 创建或更新 `/home/tiger/venvs/deepspec-dspark`；
3. 在仓库中建立并维护 `pyproject.toml` 与 `uv.lock`；
4. 从官方 SGLang 仓库获取源码并 checkout
   `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；
5. 通过 uv 将固定源码安装到正式环境，禁止把其他项目环境作为正式依赖来源；
6. 使用自洽 CUDA 13.0 JIT toolchain 与 driver forward compatibility prefix；
7. 禁止混用 CUDA 13.3 compiler 和 13.0 runtime headers；
8. 记录 PyTorch、CUDA runtime/toolkit、SGLang、sglang-kernel、FlashInfer、Triton、
   NCCL、Rust 和关键 wheel 的实际版本；
9. 从 worker 上验证：
   - 正式 Python 路径；
   - `torch.cuda.is_available()`；
   - `torch.cuda.device_count() == 4`；
   - SGLang import path、release 和 source commit；
   - DSpark 参数、`flashinfer_mxfp4` 与 `marlin` backend 在固定源码中存在；
10. CUDA import/通信验证前暂停 keepalive，验证结束后立即清理 context 并恢复。

### 必须保存

```text
pyproject.toml
uv.lock
dependency_versions.json
sglang_source_identity.json
cuda_toolchain.json
environment_validation.log
```

`pyproject.toml` 和 `uv.lock` 位于 Git 仓库；其余大日志进入本阶段 HDFS artifact
目录，小型摘要进入 handoff。

### PASS 门禁

- 正式环境由 uv 独立管理并可重建；
- `python`、`torch` 和 `sglang` 实际路径均指向登记的位置；
- SGLang commit 精确匹配固定 SHA；
- 正式环境从 worker 上准确看到 4 张 H20；
- CUDA 13.0 JIT toolchain 自洽，无通过压制兼容检查掩盖的错误；
- 尚未加载模型；
- keepalive 在阶段退出时健康。

### Handoff

写入 `docs/plan/handoffs/phase-03-<attempt-id>.md`，记录唯一正式环境激活方式、源码
路径和版本矩阵。

## 9. Phase 04：运行工具链与离线 smoke 准备

### 目标

在暂停 keepalive、启动大型模型之前，把所有 launcher、进程清理、GPU 采样、API
请求、GSM8K 数据和答案比较逻辑离线验证完毕，使 Phase 05 成为一次可归因的原子运行。

### 允许执行

1. 建立项目专用远程脚本，至少覆盖：
   - 正式 preflight；
   - SGLang 启动与 PID/PGID 登记；
   - 精确停止与 CUDA context 清理；
   - 逐卡显存和利用率采样；
   - 有界 startup timeout、请求 timeout 和失联 watchdog；
   - 任意失败路径上的服务清理与 keepalive 恢复；
2. 从固定 SGLang source 的 CLI/source 验证每个启动参数的真实名称和语义；
3. 生成首轮 `resolved_config.json`，固定：
   - TP=4 和 DSpark；
   - checkpoint `dspark_block_size=5`；
   - `SGLANG_RAGGED_VERIFY_MODE=static`；
   - `flashinfer_mxfp4`；
   - packed FP4，不设置 FP4 dequant；
   - 禁用 CUDA Graph、prefill CUDA Graph、draft-extend CUDA Graph、overlap、
     compact verify 和 radix cache；
   - 单并发、短 context、保守 `mem-fraction-static`；
4. 获取 `openai/gsm8k`、`main`、`test` 的固定前 10 条，保存 dataset revision 或
   可验证 fingerprint；
5. 不使用仓库现有只有 prompt 的 `eval_datasets/gsm8k.jsonl` 代替标准数据；
6. 实现并测试：
   - 标准答案末尾 `####` 数值提取；
   - 模型答案按最后一个 `\boxed{}`、最后一个 `####`、显式 final answer、最后一个
     数值的优先级提取；
   - 逗号、货币符号、整数和有限小数规范化；
   - 无法可靠解析时返回 `parse_failure`；
   - 完整 OpenAI-compatible response 序列化；
   - 顺序请求和有界重试；
7. 每条 GSM8K 请求最多 3 次总尝试（首次请求加最多 2 次 retry），每次错误都保存；
8. 用 fixture/mock API 做离线测试，不启动真实 SGLang model；
9. 对所有 shell/Python 脚本做语法、静态和小型单元测试；
10. 生成 Phase 05 的完整 resolved command，但不执行。

### 必须保存

```text
resolved_config.json
resolved_command.txt
dataset_manifest.json
gsm8k_first10.jsonl
tooling_test.log
process_lifecycle_test.log
```

仓库中应出现可复用的 launcher、monitor、API smoke 和 GSM8K smoke 脚本；大型
dataset/cache 与测试日志仍放 HDFS。

### PASS 门禁

- 固定 commit 中的所有启动参数都经过 source/CLI 验证；
- 启动命令不依赖交互 shell 的偶然环境；
- 进程 owner、PID/PGID、watchdog、清理和 keepalive 切换路径均有离线证据；
- GSM8K 10 条、标准答案和 fingerprint 已固定；
- 答案解析与汇总测试通过；
- Phase 05 无需临场编写关键脚本或临时决定参数；
- keepalive 在阶段退出时健康。

### Handoff

写入 `docs/plan/handoffs/phase-04-<attempt-id>.md`。本阶段不得以“顺便验证”为理由
启动模型。

## 10. Phase 05：首次正式 DSpark 端到端 attempt

### 原子性约束

本阶段必须由同一个 phase executor 在一个原子生命周期内完成：

```text
登记 attempt
→ 暂停 keepalive
→ 证明 keepalive CUDA context 已清空
→ 启动 SGLang
→ API smoke
→ GSM8K 前 10 条
→ 保存证据
→ 定向停止 SGLang
→ 证明 CUDA context 已清空
→ 恢复并验证 keepalive
```

不得在“server 已启动但没有持续真实请求”的状态下结束 phase executor。

### 前置条件

- Phase 01 至 Phase 04 全部 PASS；
- 模型正式路径、uv 环境、固定源码和运行脚本均与 handoff 一致；
- 当前重新查询到准确的 4×H20 worker；
- keepalive 已通过 10×1 秒逐卡门禁；
- `$RUN_ROOT/<attempt-id>/` 是新的空 attempt 目录。

### 执行步骤

1. 保存 `resolved_config.json`、环境变量和完整命令；
2. 记录 worker ID、hostname、GPU UUID 和 keepalive 当前 PID/PGID；
3. 紧邻启动前暂停 keepalive，确认其全部 CUDA context 已退出；
4. 立即启动已经登记的 SGLang process group，并启动独立 GPU sampler；
5. 有界等待四个 TP rank 初始化和权重加载；
6. 从日志确认：
   - `speculative_algorithm='DSPARK'`；
   - 四个 TP rank；
   - 每个 rank 的 DSpark draft architecture；
   - 实际 MoE backend 为 `flashinfer_mxfp4`；
   - packed FP4 expert layout 没有被错误解释；
7. 从四张卡保存符合预期的显存占用；
8. API ready 后执行：
   - models endpoint；
   - 一个简单、固定参数的 chat completion；
9. API smoke 成功后，顺序执行 GSM8K 前 10 条；
10. 请求期间持续保存逐卡利用率采样，证明四卡实际参与；
11. 所有样本达到终态后生成自动汇总；
12. 正常停止本 attempt 的 SGLang process group；
13. 区分预期 shutdown signal 与真实 worker crash；
14. 确认没有残留 CUDA context；
15. 恢复 keepalive，并重新通过 10×1 秒逐卡门禁。

### 正式 attempt 最小产物

```text
attempt.json
resolved_config.json
environment.json
process_identity.json
server.log
gpu_samples.csv
api_smoke.json
dataset_manifest.json
gsm8k_outputs.jsonl
summary.json
shutdown.json
keepalive_after.json
```

### PASS 门禁

- 满足本文第 1 节所有条件；
- GSM8K 10 条全部保存且汇总逻辑完成；
- 匹配数可以为任意值；
- 服务已停止，四张卡上没有残留模型 context；
- keepalive 已恢复健康。

### FAIL 处理

- 保留完整 attempt，不覆盖；
- 写清最小 reproducer、第一处根因错误和失败层级；
- 定向清理并恢复 keepalive；
- 写入 `docs/plan/handoffs/phase-05-<attempt-id>.md`；
- 不在同一 phase executor 中连续尝试多个 backend 或大批参数；
- 主 Agent 验收并向用户报告后，只有用户确认才可派发一个 Phase R。

## 11. Phase R：条件恢复或 diagnostic attempt

Phase R 不是固定主路径；只有 Phase 05 或前一个 Phase R 留下完整失败证据，且用户
确认后才能派发。每个 Phase R 使用一个新 phase executor、一个新 attempt 和一个
主要变量。

### Phase executor 入口

1. 读取失败 attempt 的完整日志和 handoff；
2. 先确认错误可重现且不是普通 shutdown；
3. 查阅官方 SGLang、PyTorch、CUDA、FlashInfer、Hugging Face 文档、release notes、
   issue 或 PR；
4. 写出本阶段唯一假设、唯一主要变量和预期区分结果；
5. 读取并更新连续无进展计数。

### 默认排查顺序

1. 正式环境、Driver/CUDA/toolchain、PyTorch 和 SGLang identity；
2. 模型 revision、manifest、DSpark config 与 packed FP4 layout；
3. 有明确 `flashinfer_mxfp4` backend/kernel 证据后，单变量切换到 `marlin`；
4. 分别尝试更短 context 或更低 `mem-fraction-static`，一次只能改变一个；
5. 再次确认所有 CUDA Graph、overlap、compact verify 和高级 cache 已关闭；
6. NCCL、P2P、残留 context 和 worker 生命周期；
7. 只有具体上游证据支持时才更换 SGLang commit。

### target-only diagnostic

已有 DSpark 正式失败证据后，可以在独立 Phase R 中做 target-only diagnostic，以区分
基础 checkpoint/FP4 backend 与 DSpark drafter 故障。它：

- 不做 benchmark、A/B 或质量基线；
- 不满足 `MVP_PASS`；
- 必须保存为独立 diagnostic attempt；
- 成功后只允许形成下一次 DSpark attempt 的单变量假设。

### attempt 生命周期

任何需要启动模型的 Phase R 都复用 Phase 05 的原子生命周期和清理门禁。如果修复后
DSpark 服务成功启动，必须由同一个 phase executor 继续完成 API smoke 和 GSM8K 10
条，然后停止服务、恢复 keepalive。主 Agent 验收并向用户报告后，等待用户确认是否
进入 Phase 06。

### 三次无进展停止点

“有进展”只包括：

- blocker 明确迁移到新的层级；或
- 新证据实质缩小了故障范围。

只修改了参数、日志文本不同或失败时间改变，不构成进展。连续 3 个 Phase 05/Phase R
attempt 均无可验证进展后：

1. 禁止启动第四个无进展 attempt；
2. 恢复并验证 keepalive；
3. 汇总三次 attempt 的同异、峰值显存和第一处根因；
4. 给出后续选项、成本、风险和推荐方案；
5. 等待用户决定是否允许 offload、另一种 checkpoint 表示、扩大硬件范围或其他
   范围变更。

worker 被平台回收导致的 `INTERRUPTED` 不写成技术失败，但 replacement worker 必须
完整重做 Phase 01 的 worker preflight。

## 12. Phase 06：离线验收与最终报告

### 前置条件

- 某个正式 DSpark attempt 已完整执行并完成 post-smoke handoff；
- 正式服务已经停止；
- keepalive 健康；
- 所有必需 artifact 可读。

### 允许执行

1. 交叉核对正式 attempt 的配置、环境、源码、模型、日志和 API/GSM8K 产物；
2. 验证四个 TP rank、四卡显存与请求期间逐卡利用率证据；
3. 验证 checkpoint revision、SGLang source commit 和 uv 环境 identity；
4. 重新计算 GSM8K summary，确认原始 JSONL 与汇总一致；
5. 区分正常 shutdown 与真实 crash；
6. 检查没有未登记的模型进程或 CUDA context；
7. 复查 keepalive 的 10×1 秒逐卡门禁；
8. 生成中文最终报告和可复现命令；
9. 将匹配率作为观察值展示，不把它加入 gate。

### 最终结论

- 所有完成条件成立：`MVP_PASS`；
- 任一基础设施或证据条件缺失：不得声称跑通，列为
  `MVP_INCOMPLETE` 并指出准确缺口；
- target-only 成功但 DSpark 未成功：`MVP_INCOMPLETE`；
- 连续 3 次无进展：`DECISION_REQUIRED`，附后续建议。

### 必须保存

```text
final_audit.json
final_report.md
reproduction.md
keepalive_final.json
```

小型最终报告建议写入：

```text
docs/results/deepseek-v4-flash-dspark-4xh20-mvp.md
```

完整运行证据继续保留在 HDFS。除非用户明确要求，本阶段不创建 Git commit。

### Handoff

写入 `docs/plan/handoffs/phase-06-<attempt-id>.md`。完成后不重新启动 SGLang；
worker 由 keepalive 保持。

## 13. Handoff 模板

每个阶段使用以下最小模板，保证新 phase executor 不依赖主线程聊天上下文：

```markdown
# <Phase ID> Handoff

- Status: PASS | FAIL | INTERRUPTED | DECISION_REQUIRED
- Attempt ID:
- Started at:
- Finished at:
- Git HEAD / worktree:
- Worker ID / hostname:
- GPU UUIDs:
- Authorized phase:

## Outcome

一句话结论。

## Changes

仓库文件、环境、HDFS 路径和外部状态的准确变化。

## Evidence

artifact 绝对路径、关键 hash、日志定位和验证命令。

## Process and GPU state at exit

SGLang PID/PGID、CUDA context、keepalive PID/PGID 和 10×1 秒门禁结果。

## Failure or open questions

第一处根因、最小 reproducer、连续无进展计数。

## Next eligible phase

只说明具备条件的下一阶段；不得写成已获用户确认。
```

## 14. Subagent 任务模板

主 Agent 派发 phase executor 时使用以下格式：

```text
你是 Phase <NN> 的唯一 phase executor。请先完整读取 AGENTS.md、CONTEXT.md 和
docs/plan/deepseek-v4-flash-dspark-4xh20-mvp.md，
然后只执行 Phase <NN>。读取上一阶段 handoff，完成本阶段退出门禁并写 handoff 后
向主 Agent 报告；不要进入下一阶段。主 Agent 将独立验收，并在用户确认后再派发后续。
```

Phase R 还应补充要验证的单一假设或失败 attempt ID。

## 15. 计划编写时的当前状态快照

以下内容仅是 2026-07-28 的快照，任何 phase executor 都必须重新查询：

- 当前列表中 4×H20 worker ID 为 `4105641`，但 ID 是临时资源；
- 项目专用 keepalive 已运行，并曾以 10×1 秒采样验证四张卡均高于 40%；
- keepalive 脚本位于 `scripts/keepalive.sh` 和 `scripts/keepalive_load.py`；
- 尚未复制 checkpoint；
- 尚未创建正式 uv 环境；
- 尚未安装固定 SGLang source；
- 尚未启动任何模型或产生 MVP 证据；
- 当前仓库存在未提交文件，phase executor 必须先检查并保留用户工作区。
