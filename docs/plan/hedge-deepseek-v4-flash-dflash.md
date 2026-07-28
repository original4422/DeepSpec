# HEDGE × DeepSeek-V4-Flash × DFlash：8×H20 best-effort 执行计划

> 状态：`PLANNED`
>
> 本文是供新开的独立 Codex 会话直接执行的自包含计划。执行前必须完整阅读仓库根目录
> `AGENTS.md`、`CONTEXT.md` 和本文；本次实验由 `AGENTS.md` 第 0 节与本文共同约束，
> `CONTEXT.md` 只定义统一领域语言。

## 0. 快速阅读

| 项目 | 固定结论 |
| --- | --- |
| 目标 | 在同一条 DFlash lane 上完成 native baseline、HEDGE `B0` 等价性核查和 HEDGE `B+`；DFlash 是 best-effort，不影响 DSpark 主线结论 |
| 自主窗口 | 从新会话记录的 `T0` 起最多 12 小时；`T+9h` 仍无一份完整可审计的 `B0`（PASS 或 FAIL）时停止实现和新 GPU 尝试，余下最多 3 小时只整理证据；`T+12h` 硬停止 |
| worker | DFlash 独占 `4099543` 的全部 8×H20；`CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`，单机 `TP=8` |
| 禁区 | 未知进程、其他项目文件和非本 lane 进程；不得训练，不得把 vLLM 运行写成正式结果 |
| 资源所有权 | DFlash 是 worker `4099543` 唯一 operational steward，负责本项目专用 8 卡 keepalive、实验切换和自有进程清理 |
| target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`；只读等待并复用 Eagle 在 worker `4099544` 发布的 HDFS 正式目录及 `.complete`，无需 GPU/keepalive 协调 |
| primary draft | `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` |
| SGLang base | `v0.5.16` / `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| HEDGE 基准 | 当前 HEDGE repo 核对基准 `9fb903d676254ea5f5d171051fb15c54f331111c`；实际集成必须等待并复用 DSpark lane 发布的 pure-core commit SHA |
| DFlash 形状 | checkpoint `block_size=8`，每步产生 7 个 draft candidate；aux layers 为 `3,13,23,32,42`，`hc_mult=4`，目标特征宽度为 `4×4096=16384` |
| 数据 | `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866`，seed `980406` 确定性 shuffle；前 32 条校准、后 500 条正式，保存 indices 和 fingerprint |
| 解码 | 非思考、无 system prompt、temperature 0、top_p 1、max_tokens 512、单请求顺序执行 |
| 校准 | strict native 的正值 first-rejection `regret/value` 分布取 q25；`g=q25, B=g, m=1, value_scheme=normalized_suffix` |
| `B0` | `B=0, g=q25, m=1`，32/32 样本完整输出 token ID 必须与 native 一致 |
| 正式计时 | 每个 arm 新服务；10 条 calibration warmup 后仅进行一次 500 条计时；不择优重跑 |
| 进展 | 主 Agent 每 30 分钟更新 `docs/progress/hedge-deepseek-v4-flash-dflash.md`，独立 commit 并 push |
| 最终记录 | `docs/experiment/hedge-deepseek-v4-flash-dflash.md`，顶部必须让读者立即看到结果、B0 状态、blocker 和证据路径 |

完成标签只能使用以下之一：

- `DFLASH_HEDGE_COMPLETE`：`B0 PASS`，且 native 与 `B+` 两个正式 arm 均完成。
- `EXPLORATORY_COMPLETE_B0_FAILED`：`B0 FAIL`，仍按协议完成了可解释的探索性正式运行。
- `BEST_EFFORT_BLOCKED_IMPLEMENTATION`：在时限内无法完成 DFlash/SGLang/HEDGE 接入。
- `BEST_EFFORT_BLOCKED_DEPENDENCY`：target、pure-core、worker 或其他外部依赖未就绪。
- `TIMEBOX_EXPIRED`：达到硬时限，以上更具体的成功/失败标签均不适用。

不得因 DFlash lane 失败而声称 HEDGE 或 DSpark 全局失败。

## 1. 权限、角色与推进方式

### 1.1 主 Agent

主 Agent 负责：

1. 记录 `T0`、创建独立 lane、维护阶段状态和 30 分钟进展记录；
2. 每个阶段派发独立 phase subagent；可并行的准备阶段可并行派发；
3. 直接检查命令、日志、manifest、diff、测试和 GPU 证据，不能只采信 subagent 摘要；
4. 验收、纠偏、追派原 subagent 或重新分配阶段，并在授权范围内自主进入下一阶段；
5. 在关键节点使用 `$git-commit-message` 工作流提交，在 lane branch 上 push；
6. 到达时间边界时停止实现、释放自有资源并形成最终结论。

本计划已授权在 12 小时窗口内自主推进，不需要逐阶段等待用户确认。主 Agent不替代
phase executor 编写阶段实现；它可做只读复核、协调文档、progress 更新和资源协调。

### 1.2 Phase executor

每个 phase executor 只执行被分配的阶段：

- 开始前读取本计划、当前 progress、上游 handoff 和相关代码；
- 只使用分配给 DFlash lane 的路径、端口、进程和 worker `4099543` 的 8 张 GPU；
- 交付证据与 handoff 后停止，不自行进入下一阶段；
- 不自行 stage、commit 或 push；
- 不清理、不终止、不修改未知进程和其他 lane 的文件。

### 1.3 DFlash operational steward、keepalive 与旧任务

DFlash 是 worker `4099543` 的唯一 operational steward，管理全部 8×H20。

- 每次操作前重新查询 worker identity、hostname、8 张 GPU UUID 和当前进程。任何既有
  任务必须自然结束，不得 `kill`、`pkill`、`killall` 或发送信号；等待期间继续做
  draft、代码、测试和 harness 等 CPU 工作。
- worker 空闲、安装依赖、下载/校验、等待 target/pure-core 或整理代码期间，运行
  本项目专用的 8 卡 sustained keepalive。脚本必须准确要求 8 张 H20，并以 10 个一秒
  样本证明每张 GPU 平均利用率至少 40%；PID/PGID、命令、GPU UUID、日志和状态目录
  全部属于 DFlash lane。
- 启动模型前紧邻地定向停止本项目 keepalive，核对它的全部 8 卡 CUDA context 已退出，
  随即启动已登记的模型命令。启动失败、服务退出或实验结束后，只要 worker 仍需保留，
  立即恢复 8 卡 keepalive 并重新通过逐卡 40% gate。
- keepalive 是 operational load，不得与正式 smoke、校准或正式 arm 并发，也不得作为
  实验成功或性能证据。
- DFlash lane 只定向终止经过 PID、PGID、完整命令行、端口和 GPU UUID 五项核对的
  自有进程组。worker 消失时保留中断证据；未经新授权不自行换 worker或扩大硬件。
- Eagle 仅在独立 worker `4099544` 发布共享 target HDFS marker。DFlash 对该 marker
  只读等待和复用，不需要与 Eagle 做 GPU 或 keepalive 协调。

## 2. 独立资源与持久身份

首次执行时创建 `lane_identity.json` 并固定以下资源；若建议端口已被未知进程占用，
不得清理对方，选择新的 DFlash 专用端口并写回 identity：

| 资源 | 建议值 |
| --- | --- |
| branch | `exp/hedge-v4-dflash` |
| worktree | `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash` |
| uv venv | `/home/tiger/venvs/deepspec-hedge-dflash` |
| SGLang checkout | `/home/tiger/src/deepspec-sglang-hedge-dflash` |
| API port | `31457` |
| worker scratch | `/tmp/deepspec-hedge-dflash` |
| keepalive state | `/tmp/deepspec-hedge-dflash/keepalive` |
| HDFS lane root | `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash` |
| coordination root | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4` |
| progress doc | `docs/progress/hedge-deepseek-v4-flash-dflash.md` |
| experiment doc | `docs/experiment/hedge-deepseek-v4-flash-dflash.md` |

所有 active log、lock、编译 cache、频繁小文件和 mmap 数据先放 worker NVMe；只在检查点
或任务结束后封存到 HDFS。HDFS 发布使用唯一 staging、校验、正式目录和 `.complete`，
不得把半成品路径当成依赖。

建议 coordination pointer：

```text
coordination/hedge-v4/
  eagle_target_pointer.json
  dspark_pure_core_pointer.json
```

`eagle_target_pointer.json` 至少包含 provider、repo、revision、正式 HDFS 路径、
`.complete` 路径、manifest path/hash 和发布者时间戳。DFlash 只读验证，不写 target
目录，不复制第二份 target，也不将该 pointer 用作 GPU/keepalive 协调。
`dspark_pure_core_pointer.json` 至少包含 HEDGE repo、
base SHA、pure-core SHA、测试证据和允许 cherry-pick 的 commit 范围。

## 3. 固定软件、模型与回退边界

### 3.1 Source identity

pure core 先进入 DFlash 的 DeepSpec branch，再由独立 SGLang worktree 消费：

```text
DeepSpec lane branch
  -> cherry-pick DSpark 发布的 HEDGE pure-core commit
  -> canonical deepspec/hedge_spec

独立 SGLang worktree
  SGLang fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
  -> DFlash checkpoint/capture/loader 接入 commit
  -> 注入同 hash pure core 的 DFlash HEDGE hook commit
  -> 仅有实际错误证据时的一项最小兼容修复
```

在 source freeze 后保存完整 commit 列表、`git diff --stat`、patch、submodule 状态和
源码 manifest。注入必须是可复现的 patch/build，不得依赖当前目录的偶然 import；
记录 DeepSpec pure-core SHA、注入内容 hash、SGLang base/final SHA。native、`B0`、
`B+` 只能通过 HEDGE 配置切换，不得换源码。当前 HEDGE repo HEAD
`9fb903d676254ea5f5d171051fb15c54f331111c` 仅作为核对基准；忽略其中未跟踪的
docs/assets，不能把它冒充尚未发布的 pure-core SHA。

### 3.2 8 卡 packed-FP4 runtime 基线

target 的首轮与所有正式 arm 固定使用同一组保守设置：

```text
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
--tp-size 8
--moe-runner-backend flashinfer_mxfp4
--context-length 4096
--max-running-requests 1
--disable-cuda-graph
--disable-overlap-schedule
--disable-radix-cache
SGLANG_DSV4_FP4_EXPERTS=1
SGLANG_DSV4_FP4_DEQUANT unset
```

保留 target packed FP4，不做 FP4→FP8 dequant。DFlash draft backend 由固定
checkpoint layout 决定；若接入确实要求额外 method-native scheduling 参数，必须由
实际 contract 证据触发，并在 native、`B0`、`B+` 三个 mode 完全一致。除此之外不做
CUDA Graph、cache、并发或 backend 调优。

### 3.3 Target checkpoint

target 固定为：

```text
deepseek-ai/DeepSeek-V4-Flash
revision=60d8d70770c6776ff598c94bb586a859a38244f1
```

只在 Eagle 的 `.complete` 与 pointer 同时存在且 revision、文件集合、shard/index、
config/tokenizer、size 和 manifest 一致时消费。任何 mismatch 都返回 Eagle 协调，
不得修写共享副本、从目录名猜身份或私自另下 target。

### 3.4 Draft checkpoint

首选且默认唯一 draft：

```text
RedHatAI/DeepSeek-V4-Flash-speculator.dflash
revision=e44fc94ceb1e7ed45550d15e782aeadd08050483
```

下载到 DFlash worker 的唯一 `/tmp` staging，完成 provider identity、文件集合、
safetensors header、总大小和关键 config 简单核查后，再复制到 DFlash HDFS staging；
核对文件集合/总大小后发布正式目录与 `.complete`。优先保存 provider OID，默认不在
NVMe/HDFS 各完整重读权重计算 SHA-256；只有传输损坏证据时追加重校验。不得直接在
HDFS 上做高频下载/cache。

只在证据明确证明是 checkpoint 特有问题时，允许一次备选：

```text
inference-optimization/dflash-DeepSeek-V4-Flash-speculators-50k
revision=b4863ac427d3230ac0f6f6b08afeadc4ee14046a
```

启用前，主 Agent 必须验收一份 `draft_fallback_decision.md`，证明 primary checkpoint
自身损坏、缺文件、config/weights 内部矛盾，或在其明确支持的参考实现中也无法加载。
“SGLang 尚无 adapter”“capture layout 未实现”“本地环境报错”都不是 checkpoint
特有问题。此 repo/revision 是唯一备选，不得再轮换其他 checkpoint；不得训练或微调
draft。

### 3.5 vLLM/其他引擎边界

vLLM、Speculators 或其他引擎只可用于阅读官方 loader、capture contract 和 config
解释，或做不产出正式结果的最小 checkpoint 兼容诊断。禁止以其运行结果替代 SGLang
native/`B0`/`B+`，禁止进行 vLLM benchmark。

## 4. 首要适配风险与最小 SGLang 接入

固定 SGLang base 已有通用 DFlash worker/verify 路径，但 DeepSeek-V4 target 当前只有
`set_dspark_layers_to_capture`，没有 DFlash capture hook。首要风险是 hidden-state
布局，而不是大模型能否分配显存。

checkpoint 的关键事实：

- `aux_hidden_state_layer_ids=[3,13,23,32,42]`；
- `hc_mult=4`、单 stream hidden size `4096`、target feature width `16384`；
- DFlash model `block_size=8`，其中当前位置占 1，实际 draft candidates 为 7；
- draft 有 5 层，并带自定义嵌套 `transformer_layer_config`；
- draft vocab、target vocab、mask token、sliding-window 和权重形状必须从固定
  checkpoint/config 冻结。

因此，任何大模型启动前必须完成小张量/离线 contract test：

1. 对照现有 DFlash worker、已支持模型 hook、固定 checkpoint config 和 safetensors
   header，确定 checkpoint layer ID 到 runtime hook 的 `+1`/无 `+1` 映射；
2. 构造带 stream 维的可辨识小张量，确认 4 个 mHC stream 是按何种顺序
   flatten/concat 成 `16384`，并验证每个 aux layer 的顺序；
3. 用 shape assertion 锁定 batch、sequence/candidate、aux-layer、stream 和 hidden
   维，不允许靠 reshape 后元素数量相等蒙混过关；
4. 明确禁止照搬 DSpark 的 `completed.mean(dim=1)`；平均会把预期的 `16384` 压回
   `4096`，属于最高优先级布局错误；
5. 测试 `block_size=8` 与 `candidates[:, 1:]` 的 7-token HEDGE proposal 对齐，
   防止 current token 被当作 draft 或末 token 丢失。

最小代码范围仅包括：

- 将自定义 `transformer_layer_config`、`aux_hidden_state_layer_ids`、block size、
  vocab/mask/sliding-window 字段规范化为 SGLang DFlash loader 接口；
- 注册/映射 `DFlashDraftModel`，通过 safetensors header 验证权重名与形状；
- 为 DeepSeek-V4 增加 `set_dflash_layers_to_capture`，严格实现经测试固定的 layer
  编号和 mHC concat/flatten contract；
- 将 target captured features 交给现有 DFlash worker，并在八个 TP rank 保留一次
  shape/ordering 证据；
- 在 greedy verify 点接入 HEDGE pure core：每请求状态跨 block 保持、请求终态重置，
  hot path 不引入 host synchronization，并输出 regret、value、budget、mismatch 和
  relaxed acceptance counters；
- 增加针对 B=0、budget、mismatch cap、candidate alignment 和请求状态隔离的测试。

不借机重构引擎，不增加训练、吞吐调优、CUDA Graph、高并发或其他 speculative 算法。

## 5. 数据、请求与 HEDGE 协议

### 5.1 数据身份与切分

固定数据集：

```text
repo=openai/gsm8k
config=main
split=test
revision=740312add88f781978c0658806c59bc2815b9866
shuffle_seed=980406
calibration=shuffled[0:32]
formal=shuffled[32:532]
```

使用确定性 shuffle 后保存原始 dataset index、question、answer、标准答案、32/500
membership、生成库版本和内容 fingerprint。若 DSpark lane 已发布与上述身份一致的共享
manifest，直接复用其 exact indices/fingerprint，不重新抽样。两组必须不相交。

请求固定为：

```text
<raw GSM8K question>
Please reason step by step, and put your final answer within \boxed{}.
```

无 system prompt；`chat_template_kwargs.enable_thinking=false`；temperature `0`、
top_p `1`、max_tokens `512`；单请求顺序执行。保存完整 prompt、tokenized input、
完整 response、output token IDs、usage、latency、重试、终态及答案解析。

标准答案从 GSM8K answer 最后的 `####` 数值提取；模型答案按最后一个 `\boxed{}`、
最后一个 `####`、显式 final answer、最后一个数值的固定优先级提取。规范化逗号、
货币符号、整数和有限小数；无法可靠解析为 `parse_failure`，不得猜测。

### 5.2 校准与参数冻结

在 32 条 calibration 上运行 strict native DFlash，并对每次 standard verification
的首个拒绝位置记录：

```text
regret = max(0, target_top_logit - target_logit_at_draft_token)
value  = normalized_suffix_value
ratio  = regret / value
```

只保留正值 first-rejection ratio，使用明确记录的线性 q25 算法计算 `q25`。随后一次性
冻结：

```text
g=q25
B=g
m=1
value_scheme=normalized_suffix
proposal_width=7
```

不得在 500 条 formal 数据上调参。若没有任何正值 ratio，记录
`CALIBRATION_EMPTY`，不得臆造 q25 或把 `B+` 写成 canonical；仍可完成 native arm 和
故障整理。

### 5.3 `B0` 等价性核查

在相同最终 source、模型、prompt 和 generation config 下，以
`B=0, g=q25, m=1` 跑同一 32 条 calibration。逐样本比较完整 output token ID：

- 32/32 全同才是 `B0 PASS`；
- 任一差异即 `B0 FAIL`，保存首个最小反例：sample/index、prompt hash、首次 divergence
  token position、两侧 token IDs/text、strict verify trace、HEDGE state/counters；
- `B0 FAIL` 不阻止在剩余时间内继续跑 `B+`，但最终文档顶部必须写
  `B0 FAILED — exploratory only`，所有后续数字只能称探索性结果；
- `B0` 失败不得通过改 seed、删样本、改 max_tokens 或多次重跑择优来掩盖。

### 5.4 正式 arm

正式顺序固定为 native baseline，然后 `B+`。每个 arm：

1. 使用同一 frozen source、target、draft、`CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`、
   TP8 和服务参数启动全新服务；
2. 以 calibration 集固定 10 条请求 warmup，不计时；
3. 只执行一次 500 条 formal 顺序计时；
4. wall time 从第 1 条正式请求发出到第 500 条达到终态，包含 API 调度、失败和有界重试，
   不含启动和 warmup；
5. E2E TPS = 500 条全部 completion tokens / wall time；
6. 平均接受 draft 长度只统计 0–7 个 draft candidate，不含 bonus/current token。

保存每请求 latency、completion tokens、accepted draft count、HEDGE counters、完整
answer/status，以及汇总的 success/failure、match/mismatch/parse failure、retry、
completion tokens、wall time、TPS。没有最低提速或准确率门槛，也不跨 DFlash/DSpark
lane 排名。

## 6. 阶段计划、验收与回退

每个阶段使用新的 executor 和 handoff：
`docs/plan/handoffs/dflash-phase-<id>-handoff.md`。失败 attempt 不覆盖；一次只改变一个
主要变量。

### Phase D0：会话与资源基线

Executor：

- 读取治理文档，记录 `T0`、deadline、git/worktree/branch、路径、端口和 worker identity；
- 只读检查 `mlx worker list`、worker hostname、全部 8 张物理 GPU 的 UUID/型号/拓扑
  和当前进程，列出等待自然结束的既有任务且不向其发送信号；
- 准备本项目专用 8 卡 keepalive；既有任务自然结束后启动，并用 10 个一秒样本验证
  每张 GPU 平均利用率至少 40%；
- 检查 HDFS、共享 root、worker `/tmp` 容量；检查 target/pure-core pointer 状态；
- 建立 progress、session manifest 和 30 分钟计时机制。

Artifacts：`lane_identity.json`、`timebox.json`、`preflight.json`、
`legacy_process_inventory.json`、`keepalive_identity.json`、`keepalive_gpu_samples.csv`、
D0 handoff。

验收：身份和路径无冲突、时间门禁可自动执行、旧任务被明确识别为只等待不清理；
空闲后的 8 卡 keepalive 逐卡通过 40% gate。旧任务尚未结束时继续 CPU-only 准备，
不能把等待写成 keepalive 或 GPU preflight 通过。

### Phase D1A：primary draft 获取与发布

可与 D1B/D1C 并行。Executor 只在 `/tmp/deepspec-hedge-dflash` 下载固定 revision，
验证 provider identity/config/safetensors，再通过唯一 HDFS staging 发布 `.complete`。

Artifacts：provider metadata、download log、file/hash manifest、config summary、
NVMe/HDFS 二次校验、draft pointer、D1A handoff。

验收：revision 精确、独立实体完整、关键字段与权重 shape 自洽。失败时先区分网络、
容量、FUSE 和 checkpoint 特有问题；没有 checkpoint 特有证据时不得启用备选。

### Phase D1B：source、环境与 contract 审计

Executor 使用 uv 建独立环境，固定 SGLang base，记录 Python/PyTorch/CUDA/NCCL/
FlashInfer/Triton/sglang-kernel；阅读现有 DFlash worker 和参考实现，完成不加载大模型的
config parser、safetensors header、layer-index、mHC concat/flatten、block8/7 小测设计。

Artifacts：`environment-lock.json`、source identity、dependency versions、
`dflash_contract.md`、小测输出、D1B handoff。

验收：`16384` layout、aux 顺序和 layer index 规则都有可运行测试支撑；任何使用
`mean(dim=1)` 的方案拒收。

### Phase D1C：数据与 harness

Executor 获取固定 GSM8K revision，生成 seed `980406` 的 32+500 manifest，编写顺序
请求、完整记录、答案解析、计时和汇总 harness；使用 mock API 测试失败重试和终态。

Artifacts：dataset identity、indices/fingerprint、prompt manifest、harness tests、
artifact schema、D1C handoff。

验收：32/500 无重叠、prompt/generation 参数精确、500 wall-time 边界和 token 计数
有测试，不能依赖仓库旧 prompt-only jsonl 作为标准答案来源。

### Phase D2：最小 native DFlash 接入

Executor 在固定 SGLang base 上实现第 4 节最小范围，并运行 CPU/小 CUDA contract
tests；等待 DSpark pure-core 时只做 native 接入，不复制临时 HEDGE 实现。

Artifacts：小粒度 patch、测试日志、weight mapping report、shape trace、source diff、
D2 handoff。

验收：config/loader/capture/candidate alignment 测试通过，修改范围可审计；八卡大模型
未启动前，必须先证明 layer `+1` 规则和 mHC `4×4096 -> 16384` 顺序。失败时派发单问题
修复 phase，不并改多个方向。

### Phase D3：native DFlash 启动与短 smoke

前置：旧任务已自然退出、本项目 8 卡 keepalive 已通过 gate、target/draft `.complete`、
source/env 就绪。Executor 紧邻启动前定向暂停自有 keepalive，确认全部 CUDA context
退出，然后以 `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7` 启动 TP8 native DFlash：

- 八个 rank 均加载 target 与 draft；
- 日志证明 DFlash、block 8/7 candidates、aux 3/13/23/32/42、实际 MoE backend；
- 八卡显存与请求期间利用率样本逐 rank 映射到物理 GPU index/UUID；
- OpenAI-compatible API 返回合法非空结果；
- 只做有界短 smoke，不做 benchmark。

Artifacts：标准 attempt 目录、server log、GPU samples、API smoke、rank/shape evidence、
keepalive pause/resume evidence、cleanup evidence、D3 handoff。

验收：无 CUDA/NCCL/worker crash，八 rank 和 feature layout 可证；服务退出后自有
8 卡 keepalive 已恢复并再次通过 gate。失败时保存根因 fingerprint；不把 target-only
结果写成成功，只在隔离故障确有必要时做一个独立诊断。

### Phase D4：复用 pure core、接入 HEDGE、冻结 source

Executor 等待 DSpark pointer，验证 pure-core SHA 相对核对基准和测试证据，cherry-pick
到 DFlash DeepSpec branch；再用可复现 patch/build 把同 hash core 注入独立 SGLang
worktree。仅在 DFlash greedy verify seam 增加适配层和 counters，不改 pure-core
语义、不依赖 cwd import。运行 pure-core tests、DFlash unit tests、并发请求状态隔离
测试和短 B=0 smoke。

Artifacts：core pointer 验证、commit graph、tests、hook trace、final source manifest、
D4 handoff。

验收：per-request budget/mismatch 状态跨 block 保持且请求终态重置；canonical 与
SGLang 注入 core hash 一致；无 host-sync hot path；native/B0/B+ 可通过配置切换；
source freeze 后生成唯一 SHA。pure-core 未发布时等待并继续完善其他准备，不能复制
DSpark 未发布的临时代码。

### Phase D5：32 条校准与 `B0`

Executor 在 frozen source 上完成 strict native calibration trace、正值 ratio q25、
参数冻结和 32 条 `B0`。禁止调参或择优重跑。

Artifacts：native outputs、first-rejection trace、ratio distribution、quantile method、
`calibration.json`、B0 outputs/comparison、最小反例（若有）、D5 handoff。

验收：`g=q25, B=g, m=1` 可由原始 trace 复算；B0 状态明确。B0 FAIL 时主 Agent 标记
后续 exploratory，但只要时限允许仍可进入 D6。

### Phase D6：native 与 `B+` 正式运行

Executor 按固定顺序分别以全新服务跑 native、`B+`；每 arm 10 warmup + 一次 500。
每次启动前定向停止自有 keepalive 并确认八卡 context 退出；服务退出后定向清理自有
PGID，立即恢复本项目 8 卡 keepalive 并重新通过 gate。若 source 或固定输入发生改变，
已完成 arm 作废；时间允许才按原顺序重做，不能混用。

Artifacts：每 arm 完整 attempt、500 request JSONL、warmup record、timing、GPU samples、
HEDGE counters、summary、cleanup evidence、D6 handoff。

验收：所有 500 条到达终态、wall time/TPS 可复算、两 arm identity 除 HEDGE 配置外
相同。单 arm 未完成则保留部分结果，不能外推完整指标。

### Phase D7：最终审计与收尾

Executor 复核 source/checkpoint/dataset/worker/arm identity，检查 artifact manifest，
生成结果表和复现命令草案，确认无自有 CUDA context。主 Agent据此编写 canonical
experiment 顶部快速结果，提交最终审计。

Artifacts：`final_audit.json`、artifact manifest、reproduction command、D7 handoff、
experiment doc。

验收：结果标签符合第 0 节，B0 FAIL 明显置顶，缺失证据明确写 blocker；没有把 vLLM、
target-only 或其他 lane 写成正式 DFlash 结果。

## 7. 尝试纪律与自动换策略

每个 attempt 使用 UTC 唯一 ID，记录唯一主要变量、预期、实际、根因 fingerprint 和
下一步。以下任一项改变都必须新建 attempt：source SHA、checkpoint、backend、环境、
capture layout、HEDGE hook、服务关键参数。

同一根因连续 3 次且没有新证据时，主 Agent不得继续同类重试，必须自动切换到一种
不同证据路径：

1. 离线 config/safetensors/shape probe；
2. 对照固定参考实现的 loader/capture contract；
3. 一个独立 target-only 或 draft-loader-only 诊断；
4. 一个由日志直接支持的 pinned upstream 最小修复；
5. 仅满足 checkpoint 特有门槛时启用固定备选 draft。

“有进展”必须是 blocker 迁移、故障范围缩小或出现能排除假设的新证据，不能只是换参数
或产生不同日志。禁止 broad kill、未知进程清理和多变量碰运气。

## 8. 12 小时时间边界

`timebox.json` 固定 `T0`、`T+9h`、`T+12h`，以 wall clock 为准；等待 target、
pure-core、worker 或旧任务自然结束也计入时间。

- `T0–T+9h`：可执行准备、实现、诊断、B0 和正式运行。
- `T+9h` 时若尚无一份完整可审计的 `B0`（PASS 或 FAIL）：立即停止新增代码实现、
  checkpoint 切换和新 GPU
  attempt；定向停止自有服务并恢复本项目 8 卡 keepalive，余下只封存日志、复核和
  写文档。
- 若 `B0` 已 FAIL，可在 `T+9h` 前、且有把握在时限内结束时继续 `B+`，结果必须
  exploratory；到 `T+9h` 不再启动新的长运行。
- `T+12h`：硬停止所有自有活动，确认自有 CUDA context 退出，push 当前文档并给出
  最准确的 best-effort 标签；不得为了“差一点”延长窗口。

## 9. Artifact contract

active attempt 先写：

```text
/tmp/deepspec-hedge-dflash/runs/<attempt-id>/
```

封存后发布到：

```text
/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/<attempt-id>/
```

每个 GPU attempt 至少包含：

```text
resolved_config.json
environment.json
source_identity.json
checkpoint_identity.json
dataset_identity.json
command.txt
process_identity.json
server.log
gpu_samples.csv
api_smoke.json
requests.jsonl
hedge_counters.json
summary.json
cleanup.json
artifact_manifest.sha256
```

`process_identity.json` 记录 worker、hostname、PID/PGID、完整命令、端口、物理 GPU
index/UUID、`CUDA_VISIBLE_DEVICES` 和启动时间。`gpu_samples.csv` 必须保留物理
GPU 0–7 的逐卡显存/利用率，并显式记录本地 TP rank 0–7 到物理 GPU index/UUID 的
映射。每个 attempt 还要关联模型启动前的 keepalive pause/context-exit 证据，以及模型
退出后的 keepalive resume/逐卡 40% gate 证据。

校准额外保存：

```text
calibration_indices.json
native_calibration_outputs.jsonl
first_rejection_trace.jsonl
ratio_distribution.json
calibration.json
b0_outputs.jsonl
b0_comparison.json
b0_minimal_counterexample.json
```

正式 arm 额外保存 warmup、500 条完整输出、单请求计时/token/acceptance、arm timing
边界和聚合 summary。HDFS 正式目录只有 manifest 二次验证后才写 `.complete`。

## 10. 30 分钟 progress、Git 与 push

主 Agent 从 `T0` 起每 30 分钟更新：

```text
docs/progress/hedge-deepseek-v4-flash-dflash.md
```

顶部固定展示：当前标签、已用/剩余时间、当前 phase、worker/8×H20 状态、本项目
keepalive 状态、Eagle target marker、draft/core 依赖、最近证据、当前 blocker和下一
检查点。历史表每次追加时间、phase、动作、结论、artifact 和 next step；即使状态未变，
也记录“等待何物”和仍在进行的安全工作。

每次 30 分钟更新：

1. 先确认 shared index 没有他人 staged changes；有则协调等待，不混入；
2. 只显式 stage progress 文件；
3. 按 `$git-commit-message` 要求检查 staged diff/status/recent log，生成
   Conventional Commit message；
4. commit 后 push `exp/hedge-v4-dflash`；
5. push 失败时记录原因和待补推 commit SHA，下个周期先补推。

关键节点单独提交：治理基线、draft 发布证据、native 接入、pure-core/HEDGE hook 与
source freeze、校准/B0、正式 arms、最终审计。每次只 stage 当前节点的小型仓库文件。
禁止提交 checkpoint、venv、cache、worker scratch、HDFS artifact 或无关用户改动。
Phase executor 不 commit；主 Agent验收后统一 commit/push。

## 11. Canonical experiment 顶部与结果表

`docs/experiment/hedge-deepseek-v4-flash-dflash.md` 顶部必须先填：

```text
Status / outcome label:
Timebox:
Worker / physical GPUs / TP:
Target repo@revision / HDFS .complete:
Draft repo@revision / HDFS .complete:
SGLang base / final source SHA:
HEDGE pure-core SHA:
Dataset revision / seed / fingerprint:
B0 PASS|FAIL|NOT_RUN:
Frozen B/g/m:
Native result:
B+ result:
Canonical or exploratory:
Primary blocker:
Artifact root:
Git commit:
```

正式结果表：

| Arm | HEDGE | B | g | m | Source SHA | Samples | Success/Fail | Mean accepted drafts (0–7) | Completion tokens | Timed sec | E2E TPS | Match/Mismatch/Parse fail | Retries | Result class |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| native | off | — | — | — | TBD | 500 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | canonical/exploratory |
| B+ | on | q25 | q25 | 1 | TBD | 500 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | canonical/exploratory |

`B0` 表：

| Native samples | B0 samples | Full token-ID identical | First divergent sample | First divergent token | Evidence |
| ---: | ---: | --- | --- | --- | --- |
| 32 | 32 | TBD | TBD | TBD | TBD |

Attempt 历史：

| Time | Phase | Attempt | Single changed variable | Outcome/root-cause fingerprint | New evidence | Next strategy |
| --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

所有指标必须链接到可复算 artifact。match rate 仅展示，不是 gate；不得只展示最好一次。

## 12. 最终审计清单

- [ ] 确认 DFlash 独占 worker `4099543` 的全部 8×H20，`CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`，TP=8。
- [ ] 既有任务自然结束且未被发送信号；本项目 8 卡 keepalive 的 PID/PGID、暂停/恢复、
      CUDA context 退出和逐卡 10×1s/40% gate 均有证据。
- [ ] target 精确 revision、Eagle worker `4099544` 发布的 HDFS `.complete` 和 DFlash
      只读消费均可验证，且未发生 GPU/keepalive 协调或共享目录写入。
- [ ] primary draft 精确 revision并经 NVMe/HDFS 二次校验；如使用备选，有 checkpoint
      特有证据、固定 repo 和完整 revision。
- [ ] SGLang base、pure-core SHA、最终 source SHA 和各 arm source identity 一致。
- [ ] aux layer 编号、`+1` 规则、mHC concat/flatten `16384` 形状和 block8/7 对齐有小测。
- [ ] 数据 revision、seed、32/500 indices/fingerprint 和请求参数完全固定。
- [ ] q25、`B=g/g=q25/m=1` 可由原始 trace 复算。
- [ ] `B0` 比较的是完整 output token IDs；失败时最小反例和 exploratory 标识置顶。
- [ ] native 与 `B+` 各自 fresh server、10 warmup、一次 500 计时且 retry 在 wall time 内。
- [ ] 八个 TP rank、八卡显存/利用率及 rank-to-GPU UUID 映射、API、无未处理
      CUDA/NCCL/worker crash 有证据。
- [ ] 每 30 分钟 progress 已 commit/push；关键节点提交未混入模型或他人改动。
- [ ] 达到 9h/12h 时间边界时已按规则停止，所有自有 CUDA context 已定向清理。
- [ ] canonical experiment 顶部、结果表、artifact manifest 和完成标签一致。

## 13. 一手参考

- Red Hat primary draft：
  <https://huggingface.co/RedHatAI/DeepSeek-V4-Flash-speculator.dflash>
- 固定 primary config：
  <https://huggingface.co/RedHatAI/DeepSeek-V4-Flash-speculator.dflash/blob/e44fc94ceb1e7ed45550d15e782aeadd08050483/config.json>
- 固定备选 namespace：
  <https://huggingface.co/inference-optimization/dflash-DeepSeek-V4-Flash-speculators-50k>
- DFlash paper：<https://arxiv.org/abs/2602.06036>
- Speculators DFlash reference：
  <https://docs.vllm.ai/projects/speculators/en/latest/reference/speculators/models/dflash/>
- SGLang releases：<https://github.com/sgl-project/sglang/releases>
