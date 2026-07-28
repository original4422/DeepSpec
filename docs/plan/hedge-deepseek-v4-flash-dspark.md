# HEDGE × DeepSeek-V4-Flash-DSpark：8×H20 自主执行计划

## 0. 顶部快速阅读

### 唯一主目标

在当前分配的单机 8×NVIDIA H20-96G worker 上，以 TP=8 的 SGLang
`DeepSeek-V4-Flash-DSpark` 路径接入 HEDGE 核心接受规则，并完成以下三类运行：

1. native DSpark baseline；
2. HEDGE `B=0` 的 32 条轻量等价性核查；
3. 自动校准后的 HEDGE `B>0` 与 native baseline 的 500 条 GSM8K 正式实验。

DSpark 是必须完成的核心路线。Eagle3、DFlash 或其他会话的状态不能替代、推迟或稀释
本计划。主 Agent 获得从实际开始时间起连续 12 小时的自主执行授权：按阶段派
subagent、验收、纠偏并自动进入下一阶段，不逐阶段等待用户确认。

### 已冻结的运行事实

| 项目 | 固定值 |
| --- | --- |
| GPU lane | worker `4106666` 的全部 8 张 H20；独占使用；TP=8 |
| 模型 | `deepseek-ai/DeepSeek-V4-Flash-DSpark` |
| 正式 checkpoint | `/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae` |
| snapshot identity | `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae` |
| SGLang | `v0.5.16` / `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| 并行与宽度 | TP=8；DSpark draft width=`5`，即 checkpoint `dspark_block_size=5` |
| 量化路径 | packed FP4；target/draft 均为 `flashinfer_mxfp4` |
| HEDGE 正式配置 | `value_scheme=normalized_suffix`；`g=q25`；`B=g`；`m=1` |
| 数据 | GSM8K `main/test`；32 条校准集与互不重叠的 500 条正式集 |
| 生成 | 非思考 prompt；`temperature=0`、`top_p=1`、`max_tokens=512` |
| 调度 | 单请求顺序执行；不做并发或吞吐调优 |
| 正式计时 | 每个正式 arm 新启服务；10 条 warmup；500 条只计时一次 |

### 完成状态

| 状态 | 定义 |
| --- | --- |
| `COMPLETE` | HEDGE core 与 DSpark 集成完成；`B=0` 等价；native 和 `B>0` 各完成一次有效 500 条正式运行；两次正式运行均证明 8 TP ranks/8 张 GPU 参与；报告齐全 |
| `COMPLETE_EXPLORATORY` | 与 `COMPLETE` 相同且保留 8 ranks/8 GPUs 证据，但 `B=0` 仍不等价；必须在结果顶部醒目标记 `B0 failed`，所有 `B>0` 结果只称探索性 |
| `INCOMPLETE` | HEDGE 未实际进入 DSpark verify 路径，或任一正式 500 条 arm 未达到终态，或关键 identity/artifact 缺失 |

TPS、平均接受长度和 GSM8K 匹配率均不设改善门槛。负增益或匹配率下降不把完整且有效
的实验改写为基础设施失败；相反，指标好看也不能弥补 HEDGE wiring、`B=0`、身份或
artifact 缺口。

### 核心阶段

```text
P00 会话与 lane 接管
  ├─P01 数据、请求与指标工具
  └─P02 纯 HEDGE core + tests + 可 cherry-pick commit
          ↓
P03 SGLang DSpark 集成与离线测试
          ↓
P04 八卡 integration smoke
          ↓
P05 32 条 native/B0 + q25 校准并冻结 B=g、g=q25、m=1
          ↓
P06 native：10 warmup + 一次 500 正式计时
          ↓
P07 HEDGE B>0：10 warmup + 一次 500 正式计时
          ↓
P08 离线审计、结果表、docs/experiment 与最终提交
```

P01 与 P02 可以并行；所有 GPU 模型运行严格串行。每阶段由独立 phase executor
实施，主 Agent 读取 handoff 和原始证据后判定 `PASS / FIX / RETRY`。`PASS` 后主
Agent 自动派发下一阶段；`FIX` 优先向原 executor 追派准确修正；`RETRY` 使用新
attempt。无需等待用户。

---

## 1. 范围、权威来源与禁止项

### 1.1 本计划的权威输入

新会话开始后必须完整读取：

```text
AGENTS.md
CONTEXT.md
docs/plan/hedge-deepseek-v4-flash-dspark.md
docs/results/deepseek-v4-flash-dspark-4xh20-mvp.md
docs/plan/handoffs/phase-06-20260728T184242Z-phase05-dspark-r1.md
```

既有 DSpark MVP 的正式证据位于：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T184242Z-phase05-dspark-r1
```

其中 `final_audit.json` 已记录 `phase06_executed=true` 和
`conclusion=MVP_PASS`。这是 worker `4105641` 上 4×H20 MVP 的历史来源证据，只允许
本计划复用已发布 checkpoint、固定 SGLang 身份和 CUDA 13 toolchain 结论；它不能
证明当前 8 卡实验成功，也不能复用为当前 TP=8/rank/GPU 参与证据。worker `4105641`
不用于本实验。不重新读取约 166 GB 做全量 hash，也不重做历史 Phase 01–06。

HEDGE 语义只从以下只读仓库提取：

```text
HEDGE_SOURCE=/mlx_devbox/users/pengzegang/playground/github/HEDGE
HEDGE_SOURCE_COMMIT=9fb903d676254ea5f5d171051fb15c54f331111c
```

只从该固定 HEAD 的 tracked `src/hedge_spec` 核心及 tracked tests 提取语义，并记录
源 commit、目标映射和逐文件 SHA-256。源 worktree 当前存在若干 untracked
docs/assets，它们不属于输入，必须忽略；不得把工作区未跟踪内容或浮动 HEAD 带入
pure core commit。只复制核心决策规则及其必要测试；不得复制 HEDGE 仓库的 Qwen
路线、ticket、实验编排、历史门禁、旧成功阈值或整个项目。

### 1.2 允许范围

- 在独立 uv 环境和固定 SGLang base 上实现 HEDGE；
- 从 HEDGE 只读源码中复制/改写最小 core 与测试；
- 为固定 SGLang commit 生成可审计的 DSpark integration patch；
- 添加请求 token ID、strict-rejection calibration trace、HEDGE counter 和离线汇总；
- 在 worker `4106666` 的全部 8 张卡上以 TP=8 运行有界的 smoke、校准与正式实验；
- 遇到错误时联网查官方 SGLang、PyTorch、CUDA、FlashInfer 文档、issue 和 PR；
- 有明确 blocker 和上游修复证据时，固定 cherry-pick 最小 commit，但所有正式 arm
  必须使用同一最终源码身份，且不得转向浮动 `main`。

### 1.3 明确禁止

- 禁止 vLLM 或其他引擎产生正式结果；
- 禁止训练、微调或重新蒸馏 drafter；
- 禁止将历史 MVP worker `4105641`、Eagle3 worker `4099544`、DFlash worker
  `4099543` 或任何其他 worker/GPU 用于本实验；
- 禁止跨 lane 登录、清理进程、修改环境、写 run 目录或管理 keepalive；
- 禁止将 DSpark checkpoint 改成另一种表示、FP4→FP8 dequant、offload 或扩大硬件；
- 禁止改变 DSpark width 5、TP=8 或正式数据/prompt/generation 协议；
- 禁止并发、长上下文、CUDA Graph、overlap、radix-cache 或 backend 性能调优；
- 禁止依据正式 500 条结果回调 `B`、`g`、`m`；
- 禁止重复正式计时并择优；
- 禁止设置最低 TPS gain、最低 acceptance gain 或最低准确率门槛；
- 禁止 broad `pkill`、`killall`、模糊进程名清理和删除未知 scratch；
- 禁止把模型、virtualenv、package cache 或大型 run artifact 提交到 Git。

---

## 2. 固定身份、路径和运行配置

### 2.1 路径

```text
BASE_REPO=/mlx_devbox/users/pengzegang/playground/github/DeepSpec
RECOMMENDED_WORKTREE=/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark
RECOMMENDED_BRANCH=exp/hedge-v4-dspark

BASE_VENV=/home/tiger/venvs/deepspec-dspark
HEDGE_VENV=/home/tiger/venvs/hedge-v4-dspark
SGLANG_BASE_SOURCE=/home/tiger/src/deepspec-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
HEDGE_SGLANG_SOURCE=/home/tiger/src/hedge-v4-dspark-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1

MODEL_PATH=/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae
HEDGE_RUN_ROOT=/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark
HEDGE_COORDINATION=/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4

EXPERIMENT_DOC=docs/experiment/hedge-deepseek-v4-flash-dspark.md
PROGRESS_DOC=docs/progress/hedge-deepseek-v4-flash-dspark.md
```

若新会话已经位于用户创建的 DSpark 专用 worktree/branch，则使用现场路径并准确记录，
不重复创建。若建议路径已存在，先只读核对 worktree ownership；禁止覆盖。独立
`HEDGE_VENV` 与 `HEDGE_SGLANG_SOURCE` 用于避免污染已经验证的 MVP 环境，也避免与
Eagle3/DFlash 会话共享可写状态。

### 2.2 当前 8 卡 DSpark baseline

正式三个 arm 必须在相同的最终 SGLang wheel/source/patch identity 上运行，只通过
HEDGE 开关和冻结配置切换：

```text
--model-path $MODEL_PATH
--served-model-name deepseek-v4-flash-dspark
--tp-size 8
--speculative-algorithm DSPARK
--speculative-dspark-block-size 5
--moe-runner-backend flashinfer_mxfp4
--speculative-moe-runner-backend flashinfer_mxfp4
--context-length 4096
--max-running-requests 1
--mem-fraction-static 0.80
--disable-cuda-graph
--disable-overlap-schedule
--disable-radix-cache
```

环境继续固定：

```text
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
SGLANG_RAGGED_VERIFY_MODE=static
SGLANG_DSV4_FP4_EXPERTS=1
SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH=1
SGLANG_DSV4_FP4_DEQUANT unset
TOKENIZERS_PARALLELISM=false
```

使用自洽 CUDA 13.0 compiler/runtime 和既有 driver forward-compat prefix。新 venv
中同样需要让 FlashInfer JIT 找到：

```text
cu13/lib64/libcudart.so -> ../lib/libcudart.so.13
cu13/lib64/libnvrtc.so  -> ../lib/libnvrtc.so.13
```

必须以 guarded、幂等脚本创建并运行秒级 link probe。该 probe 只证明 linker seam，
不替代八卡模型 smoke。

---

## 3. HEDGE 核心算法契约

### 3.1 只复制的最小核心

从 HEDGE 仓库读取并固定语义，在当前仓库形成引擎无关的
`deepspec/hedge_spec/` 与小型测试目录 `tests/hedge_spec/`：

- `budget.py`：可读的 pure-Python 参考规则；
- `torch_rule.py`：与参考规则一致、设备内执行的 tensor 规则；
- 最小 `config.py`：只保留 decode-affecting 字段、校验和 fingerprint；
- `__init__.py`；
- budget、config、tensor/reference equivalence 的必要测试。

`deepspec/hedge_spec/` 是本仓库的 canonical core，但运行服务使用独立的固定
SGLang source/build，不能依赖启动目录恰好位于 DeepSpec、`PYTHONPATH=.` 或其他
偶然的 cwd import。P03 必须通过可复现的 patch/build 步骤，把 canonical core
注入或打包进独立 SGLang source 的 Python package；注入前后逐文件 hash 必须相同，
wheel manifest 同时记录 canonical hash、目标路径和 wheel hash。core 变化后必须
重新注入、重建 wheel，禁止两份逻辑各自演化。

不得复制：

- HEDGE 的 `SuccessCriteria`、`metrics.py` 或旧性能/质量阈值；
- `run_artifacts.py` 的旧项目 gate；
- Qwen、DeepSpec adapter、旧 evaluator 和旧实验配置；
- HEDGE 的 keepalive、worker/runbook、ticket 或完整 SGLang patch applicator。

`HEDGE_SOURCE/patches/sglang/` 可以只读参考候选对齐、device-resident state 和 counter
设计，但不能直接假定适配当前固定 commit。P03 必须重新检查实际 DSpark verify
源码并编写本路线的确定性 patch/tests。既有 patch 只证明过局部 greedy accept；
request-slot lifecycle 与 downstream commit length 曾不完整，因此不得以“接受率日志
变化”作为 wiring 成功证据。

### 3.2 每个 token 的量

对一个长度为 `L=5` 的 DSpark draft block，位置 `i∈[0,L-1]`：

```text
top_logit_i   = target 在该位置的最大 logit
top_token_i   = 对应 argmax token
draft_logit_i = target 对 draft token 的 logit
mismatch_i    = draft_token_i != top_token_i
regret_i      = max(0, top_logit_i - draft_logit_i)
value_i       = (L - i) / L                 # normalized_suffix
ratio_i       = regret_i / value_i
```

`g` 是单个 relaxed mismatch 的 `regret/value` 上限，
`m` 是每个 block 最多 relaxed mismatch 数，`B` 是整条 request 的 regret 总预算。

### 3.3 三道 gate 与连续前缀

从位置 0 开始，返回同时满足以下条件的最长连续前缀：

1. `worthwhile`：exact match 免费；mismatch 必须满足 `ratio_i <= g`；
2. `affordable`：截至当前位置的 mismatch 累计 regret 不超过该 request 剩余 `B`；
3. `within_cap`：截至当前位置的 relaxed mismatch 数不超过 `m`。

首个失败位置立即截断；后面的 exact token 不能越过前面的 barrier。只有被提交前缀内
的 mismatch 才扣除 budget。

### 3.4 per-request `B`

- 每条新请求建立独立 `remaining_budget=B`；
- budget 跨该请求的所有 draft blocks 持续存在，不能每 block 重置；
- request 完成、取消、异常或 slot 回收时清理状态；
- slot 被新请求复用时必须重新初始化，不能继承上一请求余额；
- scheduler batch reorder、merge、shrink 后仍以稳定 request/slot identity 找回正确
  余额，不能按临时 row index 绑定；
- batched row 之间预算独立；本实验虽顺序请求，仍必须保留正确语义；
- `B=0` 时任何 mismatch 都不得 relaxed，包括 regret 恰为 0 的 argmax tie；
- budget 耗尽后该请求余下过程自动退化为 strict native verify。

正式 hot path 不允许逐 block `.item()`、CPU dict 回写、host sync 或 HDFS 日志。
per-request state、判断和累计 counter 留在 device；只在 calibration 或 arm 结束后
批量封存。

### 3.5 DSpark 对齐

必须从固定 SGLang source 验证以下契约，而不是凭旧 patch 猜测：

- DSpark `candidates` 的 index 0 是当前 token，不属于 5 个 draft candidates；
- HEDGE 判断的 draft IDs 应对齐 `candidates[:, 1:]`；
- target scores 应对齐判断这些 draft positions 的 logits，不能 index-for-index 错位；
- 在 TP/vocab 布局允许的 seam 上只 compact gather/reduce 每个位置的
  `top_logit/top_token_id/draft_logit`，不为 HEDGE 新建 CPU full-logit 路径；
- `verify_num_draft_tokens=6` 与 proposal width 5 的关系必须记录；
- HEDGE accepted length 仍受 `cutoff_verify_lens` 等原生 verify window 约束；
- target bonus token 必须从 HEDGE 截止位置重新取得；
- relaxed prefix 必须同步驱动真正的 `accept_index`、commit length、KV/cache commit、
  request output-token state、next-token/bonus path 和相关统计；这些状态只能消费已经
  验证/接受的前缀；
- native path 关闭 HEDGE 时必须原样调用固定 commit 的 native verifier。

### 3.6 core 测试最低集合

- pure Python 与 tensor 规则在固定 seed 随机 blocks 上一致；
- width 5 的 `normalized_suffix` 值为 `(1, .8, .6, .4, .2)`；
- `B=0` 等于 strict prefix；
- zero-regret mismatch 在 `B=0` 仍拒绝；
- budget 跨 block 持久，耗尽后回 strict；
- request/slot reset 无状态泄漏；
- contiguous-prefix reachability；
- `m=1` 的 cap 行为；
- 多 row budget 独立；
- block-size mismatch fail loudly；
- config fingerprint 随 `B/g/m/value_scheme/block_size` 改变；
- integration fixture 覆盖 candidate/logit alignment、bonus、cutoff 和 disable path。
- integration fixture 覆盖 batch reorder、abort、finish、slot reuse，以及 relaxed
  prefix 对 `accept_index`、commit length、KV/request token state、next-token path
  和统计的同一 accepted length 传播。

---

## 4. 实验协议

### 4.1 数据选择

固定使用：

```text
provider=Hugging Face
repo_id=openai/gsm8k
config=main
split=test
revision=740312add88f781978c0658806c59bc2815b9866
seed=980406
```

构造 `indices=list(range(test_size))`，使用
`random.Random(980406).shuffle(indices)` 做确定性 shuffle：

- 前 32 个索引为 calibration set；
- 随后的 500 个索引为 formal set；
- calibration 的前 10 条按既定顺序作为每个正式 arm 的 warmup；
- calibration 与 formal 必须互不重叠，三类 arm 共用同一份 immutable manifest。

保存索引、question、原始 answer、标准数值、dataset revision/fingerprint、生成脚本
commit 和 JSONL SHA-256。不得用历史 smoke 的“前 10 条”替代本协议。

### 4.2 统一 prompt 与生成参数

每条请求只有一条 user message：

```text
<原始 question>
Please reason step by step, and put your final answer within \boxed{}.
```

- 不添加 system prompt；
- 显式传 `chat_template_kwargs.enable_thinking=false`；
- `temperature=0`；
- `top_p=1`；
- `max_tokens=512`；
- 单请求顺序执行；
- baseline、`B=0`、`B>0` 的请求体、样本顺序、timeout 和重试规则完全相同。

标准答案从 GSM8K answer 末尾 `####` 提取；模型答案优先取最后一个
`\boxed{}`，无法可靠解析则 `parse_failure`。保存完整 response、模型文本、
生成 token IDs、提取规则和所有 request attempts。

### 4.3 三类运行

#### Native calibration

- 使用最终集成后的同一 SGLang source/wheel；
- `HEDGE_ENABLED=0`；
- 顺序运行 32 条 calibration；
- 保存完整输出 token IDs；
- 在不改变 native 决策的 instrumentation 下，收集每个 proposal 的 strict
  first-rejection trace。

#### HEDGE `B=0`

- 新启动服务，其他配置完全一致；
- `HEDGE_ENABLED=1`、`B=0`；
- 仍固定 width 5；`g` 可设为无限/足够大，`m` 可覆盖 width，但 `B=0` 必须保证任何
  mismatch 均不可 relaxed；
- 顺序运行相同 32 条；
- 逐样本比较完整输出 token IDs；有低成本 trace 时再比较逐 proposal accepted length。

`B=0` 不等价时保存首个最小反例、两个请求的 token IDs、proposal trace、config 和
源码身份，并优先修复。但它不是阻断完整流程的硬门禁：若在为正式运行预留时间前仍未
解决，继续 P05–P08，结果顶部标记 `B0 failed`，native/`B>0` 只作为探索性结果。

#### 正式 native 与 `B>0`

每个 arm：

1. 从完全停止的状态新启动服务；
2. ready 后运行 calibration 固定前 10 条 warmup，不计时；
3. 确认无排队/残留请求，开始一次 500 条正式计时；
4. 从第 1 条请求发出前的客户端单调时钟，到第 500 条达到终态后的单调时钟；
5. HTTP、生成、排队和 retry 时间计入；启动、加载和 warmup 不计入；
6. 完成后停止服务、清理 CUDA context、恢复 keepalive。

正式 TPS：

```text
end_to_end_output_tps =
    500 条正式请求的 completion_tokens 总数 / timed_wall_seconds
```

每个 arm 只有一次完整、技术有效的正式计时。服务崩溃、worker 中断或请求未达到
500 终态的 attempt 是无效技术 attempt，可以从头重跑；不得因为 TPS 不理想而重跑或
择优。

### 4.4 q25 自动校准

从 native calibration 的每个 proposal 中：

1. 找出 strict verifier 的第一个 rejection/mismatch 位置；
2. 计算该位置的 `regret/value`；
3. 只保留严格大于 0 的有限值；
4. 按升序保存完整分布及其 hash。

令 `g` 为该分布的 25% 分位数，线性插值定义为：

```text
h = (n - 1) * 0.25
g = sorted[floor(h)] * (ceil(h) - h)
  + sorted[ceil(h)]  * (h - floor(h))
```

若 `floor(h)==ceil(h)`，取该点。冻结唯一正式配置：

```text
B = g
g = q25(positive first-rejection regret/value)
m = 1
value_scheme = normalized_suffix
block_size = 5
temperature = 0
```

保存 `calibration_values.jsonl`、`calibration_summary.json`、
`hedge_config.json` 和 config fingerprint。正式 500 条结果不得反向修改该配置。
若分布为空，先把它作为 trace/wiring blocker 修复；不得静默改成经验参数。

### 4.5 指标

同时报告但不设阈值：

- 成功/失败请求、retry 和 parse failure；
- completion tokens、timed wall seconds、端到端 output TPS；
- draft-only mean accepted tokens/proposal，范围应为 0–5；
- 若引擎已有含 bonus 的 acceptance length，单独命名，禁止与 draft-only 混淆；
- HEDGE relaxed tokens、budget spent、budget-hit requests、cap-bound blocks；
- 每请求 latency、completion tokens、answer match；
- native vs `B>0` 的绝对差与百分比；
- `B=0` token-ID 等价样本数和首个 mismatch。

---

## 5. 主 Agent 调度与 12 小时自主规则

### 5.1 启动时钟

主 Agent 第一次执行本计划时立即记录：

```text
AUTONOMY_START_UTC
AUTONOMY_DEADLINE_UTC = START + 12h
worker/lane
worktree/branch
Git HEAD/remote
```

写入 `$PROGRESS_DOC` 和 HDFS session manifest。阶段间不等待用户；用户新消息若明确
改变任务，则以新指令为准。

### 5.2 并发槽

推荐最多同时占用：

1. 主 Agent：调度、只读验收、纠偏、Git 和最终结论；
2. progress recorder：每 30 分钟生成进展快照；
3. 当前 phase executor；
4. 一个独立的离线 phase/research/diagnostic executor。

P01/P02 可并行。P03 之后任何模型/GPU attempt 只能有一个 owner；禁止两个 subagent
同时暂停 keepalive或启动服务。

### 5.3 主 Agent 验收循环

每个 executor 必须写 handoff 后停止。主 Agent 对每阶段：

1. 读取 handoff 和原始 artifact，不只看 executor 摘要；
2. 做最小、直接相关的只读复算；
3. 判断：
   - `PASS`：入口/出口成立，自动派下一阶段；
   - `FIX`：向原 executor 追派准确缺口；
   - `RETRY`：新 executor/new attempt，只改变一个主要变量；
4. 更新 canonical experiment record 和 progress；
5. 在关键节点显式 stage、调用 `$git-commit-message`、commit 并 push。

phase executor 不自行 commit/push，不修改其他 lane，也不自行扩大范围。

### 5.4 时间预算与降级

- H+0–1：P00，并行启动 P01/P02；
- H+1–3：完成 core commit、协议工具和 P03；
- H+3–5：P04 GPU smoke、P05 native/B0/calibration；
- H+5–8：P06 native 500；
- H+8–11：P07 `B>0` 500；
- H+11–12：P08 审计、结果与清理。

这是调度目标，不是停止正在取得进展的 DSpark 硬门槛。若某阶段落后，先删除非必要
优化和细致门禁，不能删除 core、32 条校准、任一 500 条正式 arm 或最终证据。

同一根因连续 3 次没有新证据时，不暂停等待用户：主 Agent 必须换策略，例如缩成更小
reproducer、切换诊断层、查官方 issue/PR 或重新分配 executor。DSpark 持续推进到成功
或 12 小时窗口截止；不因为 Eagle3/DFlash 的 best-effort 规则提前停止。

到 H+11:30 不再启动非必要诊断，优先完成正在进行的正式 arm、定向清理和权威记录。
若到 deadline 仍未完整完成，停止本 lane 的登记进程、恢复 keepalive，并发布
`INCOMPLETE` 与准确 blocker；不得越过 GPU lane 或改用禁止方案“补成功”。

---

## 6. Worker、keepalive 与进程纪律

worker ID 是运行资源而非永久事实，但本次分配只授权 lane `4106666`：

1. 每次 GPU 操作前执行 `mlx worker list`，确认 `4106666` 仍是准确 8×H20；
2. 若 `4106666` 消失，不得转用历史 MVP worker `4105641`、Eagle3 worker
   `4099544`、DFlash worker `4099543` 或其他 lane；保存状态、继续离线工作并
   有界重查，最终仍不可用则记录 `INTERRUPTED/INCOMPLETE`；
3. 无模型负载时运行本项目专用 8 卡 sustained keepalive，必须明确要求且只占用
   GPU 0–7，不能复用卡数不匹配的脚本；
4. keepalive status 必须是 10×1 秒、八卡逐卡 mean 均至少 40%，缺少任一卡样本或
   只检查聚合利用率都不通过；
5. 启动服务前紧邻暂停 keepalive并证明其 CUDA context 全部退出；
6. 随后立即启动已登记的 arm，不留下长时间空窗；
7. 模型、warmup、校准和正式请求期间禁止 keepalive；
8. 服务退出后定向停止 PID/PGID，确认 CUDA contexts 为 none，再恢复 keepalive；
9. 空闲 server 不构成保活；不需要请求时停止 server 并恢复 keepalive。

所有远程长任务先写绝对路径脚本，再使用：

```text
mlx worker login 4106666 -- bash <absolute-script-path> ...
```

launcher 记录 PID、PGID、SID、hostname、GPU UUID、完整命令和 start ticks。清理前
再次核对这些 identity；只杀登记的 process group。日志中的 `SIGTERM`、`SIGQUIT`
或 `Killed` 必须结合请求时间线和 lifecycle 判断，不能仅凭关键词称为 crash。

---

## 7. 存储与 attempt artifact

### 7.1 存储

- 代码、配置、脚本和小型结果进入 Git；
- checkpoint 只读复用 `$MODEL_PATH`；
- 编译、lock、mmap、活动日志和高频小文件进入
  `/tmp/deepspec-hedge-dspark-<attempt-id>/`；
- 需要跨阶段保留的 artifact 封存到
  `$HEDGE_RUN_ROOT/<attempt-id>/`；
- HDFS 不长时间 append；活动日志先写 NVMe，checkpoint/结束时短操作转移；
- 每个 attempt 使用唯一目录，失败证据不覆盖。

### 7.2 GPU attempt 文件

只保留复现或判定当前阶段直接需要的文件，不为“证据更完整”增加实机探针。P04
integration smoke 的最小集合是：

```text
resolved_config.json
engine_identity.json
checkpoint_identity.json
server.log
gpu_samples.csv
api_smoke.json
hedge_counters.json
shutdown.json
cuda_contexts_after.txt
keepalive_before.json
keepalive_after.json
```

其中 `server.log` 必须保留 TP rank 0–7 初始化/加载记录，`gpu_samples.csv` 必须按
GPU UUID 分列覆盖全部 8 张卡；P06/P07 用两者证明正式请求期间 8 ranks/8 GPUs
参与，不增加与此无关的细粒度探针。

P05 calibration 除上述运行身份/日志外需要：

```text
dataset_manifest.json
native_calibration_outputs.jsonl
b0_calibration_outputs.jsonl
b0_equivalence.json
strict_rejection_trace.jsonl
calibration_values.jsonl
calibration_summary.json
hedge_config.json
```

P06/P07 正式 arm 除运行身份/日志外需要：

```text
warmup_outputs.jsonl
formal_outputs.jsonl
formal_timing.json
acceptance_summary.json
answer_summary.json
```

`engine_identity.json` 必须同时记录：

- upstream SGLang base SHA；
- DeepSpec 的 pure HEDGE core commit；
- DSpark integration commit/patch SHA；
- 实际 build source tree/commit；
- wheel SHA-256、安装路径和 import path；
- decode-affecting config fingerprint。

如果任何 decode-affecting source/config 在 P06 native 之后变化，旧 native 正式 run
立即作废，必须在同一最终身份上重新运行 P06 和 P07。仅报告脚本或 Markdown 修正不
触发重跑。

---

## 8. Git、共享 core 和进展记录

### 8.1 提交所有权

主 Agent 统一 commit/push。每次只显式暂存当前节点文件，保留用户和其他 agent 的
修改；提交前必须读取并按 `$git-commit-message` 执行 staged diff、status、recent
log 流程。禁止 `git add .`、force push 或把 HDFS/NVMe 产物纳入 Git。

关键节点至少包括：

1. 本计划/治理基线；
2. pure HEDGE core + tests；
3. DSpark integration + instrumentation/tests；
4. 固定数据与实验 runner；
5. q25 calibration config freeze；
6. native/B+ 正式结果摘要；
7. 最终 `docs/experiment` 与审计。

### 8.2 纯 HEDGE core commit

P02 验收后，主 Agent 只暂存引擎无关 core 和 tests，形成一个不包含 DSpark/SGLang
integration、数据、run 结果或进展文档的纯 commit。测试通过并 push 后，原子发布：

```text
/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/hedge-core.json
```

marker 至少记录：

```text
status=READY
producer_lane=dspark
repository/branch/remote
commit_sha
parent_sha
HEDGE source commit
file list and hashes
test command and result
published_at_utc
```

Eagle3/DFlash 只通过已 push SHA cherry-pick，并只读该 marker。DSpark 会话不得进入
他们的 worktree 代为应用。已存在冲突 marker 时不能覆盖，先保存对比并选择新的
versioned marker 或记录 blocker。

### 8.3 每半小时进展

从 `AUTONOMY_START_UTC` 起每 30 分钟更新：

```text
docs/progress/hedge-deepseek-v4-flash-dspark.md
```

顶部保持最新快照，正文追加时间线。每次至少写：

- elapsed/deadline；
- 当前 phase、executor 和结论；
- worker/keepalive/server/PID 状态；
- 最新 attempt 与 HDFS artifact；
- core/integration/config/result commit；
- blocker、已尝试方向和下一 30 分钟动作。

每次更新都必须 commit 并 push。progress recorder 可以准备内容，但与 Git index
交互、commit/push 由主 Agent协调；只暂存该 progress 文件，不能卷入其他未提交修改。
若半小时点恰逢关键提交，可在同一提交包含该时间点进展，但不能漏记。任务提前完成时
立即写最终进展并 commit/push，不等待下一个半小时点。

---

## 9. 分阶段执行

## P00：会话、worktree、lane 与环境接管

### Executor 任务

派一个 `p00_bootstrap` subagent，只执行本阶段：

1. 记录自主窗口 start/deadline；
2. 检查 Git branch、HEAD、remote、worktree 和 dirty 状态；
3. 建立或验证 DSpark 专用 branch/worktree，不覆盖既有路径；
4. `mlx worker list` 重新确认 `4106666` 是 8×H20 且本实验独占全部卡；
5. 核对本项目专用 8 卡 keepalive identity、10×1 秒八卡逐卡 gate 及无未知
   SGLang context；
6. 只读核对既有 checkpoint `.complete`、路径、少量关键 config 和历史 identity；
7. 建立独立 `$HEDGE_VENV` 和 `$HEDGE_SGLANG_SOURCE`，base 精确固定
   `fdebc...`；
8. 用 uv 从现有 lock/cache 建环境，记录实际版本；
9. 建立 CUDA 13 `lib64` link layout 并运行秒级 probe；
10. 创建 HDFS session manifest、progress doc 和 canonical experiment doc skeleton。

不重新全量 hash checkpoint，不启动模型。

### 入口

- 本计划已在可访问 branch；
- 用户给出的 12 小时连续授权有效；
- 无其他会话占用 lane `4106666` 的任一 GPU。

### 出口 artifact

```text
session.json
worker_inventory.json
keepalive_initial.json
checkpoint_identity.json
environment_identity.json
sglang_base_identity.json
cuda_link_probe.json
```

### 主 Agent 验收

- worker/lane 精确，8 张 GPU 的 UUID、型号和拓扑已记录；
- checkpoint path/identity 与历史 MVP 一致；
- 独立 uv 与 SGLang source 不污染 MVP 环境；
- base commit、CUDA probe 和 keepalive 均通过；
- progress 计时已开始。

### 回退

- worker 不存在：禁止跨 lane，继续 P01/P02 离线工作并有界轮询；
- venv 同步错误：先查 lock/index/cache 和实际错误，不换 SGLang；
- CUDA link 错误：复用已验证的 RED→GREEN link seam，不启动模型掩盖问题。

---

## P01：冻结数据、请求、计时和汇总工具

### Executor 任务

派 `p01_protocol_tooling`，可与 P02 并行：

1. 实现固定 seed 的 32+500 数据 manifest；
2. 实现统一非思考 prompt/request；
3. 实现顺序 runner、最多 3 次总尝试、timeout 和完整 response 保存；
4. 获取或添加不改变 decode 的生成 token ID 输出；
5. 实现标准/模型答案提取；
6. 用单调时钟实现 warmup 外的一次 500 计时；
7. 实现 acceptance/HEDGE counter schema 和离线汇总；
8. 用 mock/fixture 测试 32/500 分割、无重叠、prompt、计时边界、retry、token/答案
   解析和 summary 重算。

### 入口

- P00 已记录 repo identity；GPU 不需要可用。

### 出口

```text
dataset_manifest.json
gsm8k_calibration_32.jsonl
gsm8k_formal_500.jsonl
protocol_config.json
tooling_test.log
```

以及可复用的 runner/summary 代码。

### 主 Agent 验收

- revision、seed、索引和两个 JSONL hash 固定；
- 32/500 无重叠；
- prompt 和所有生成参数逐字段匹配；
- warmup 不进入正式 wall time/token count；
- mock 中 500 条均达到终态且 summary 可重算。

### 回退

仅修复具体工具错误；不得切换数据集、使用旧前 10 条 smoke 文件或复制 DeepSpec
并行 evaluator。

---

## P02：复制纯 HEDGE core 与必要 tests

### Executor 任务

派 `p02_hedge_core`，可与 P01 并行：

1. 记录 HEDGE source HEAD 与被采用文件 hash；
2. 拒绝 source HEAD 偏离
   `9fb903d676254ea5f5d171051fb15c54f331111c`，只读取该 commit 的 tracked
   `src/hedge_spec` 核心/tests，忽略 untracked docs/assets；
3. 提取第 3 节最小 core，不携带旧成功阈值/项目编排；
4. 固定 `B/regret/normalized_suffix/g/m` 命名和 config fingerprint；
5. 在 `deepspec/hedge_spec/` 实现 core，并在 `tests/hedge_spec/` 补齐第 3.6 节测试；
6. 在 CPU 和正式 torch 环境运行 pure/tensor tests；
7. 写 handoff，列出 source 到目标文件映射和任何有意改写。

### 入口

- HEDGE source 只读可访问；
- P00 repo/worktree identity 已登记。

### 出口

- 引擎无关 core；
- 必要 tests；
- `hedge_core_identity.json`；
- 测试日志。

### 主 Agent 验收与提交

主 Agent 独立运行测试，确认 staged diff 不含 SGLang/DSpark integration，然后使用
`$git-commit-message` 创建并 push pure core commit，最后发布 HDFS READY marker。
P02 只有 commit 已 push 且 marker 与 SHA 相符时才 `PASS`。

### 回退

参考/tensor 不一致时只修 core；不得用 SGLang integration 的偶然输出覆盖规则测试。

---

## P03：接入固定 SGLang DSpark verify

### Executor 任务

派 `p03_dspark_integration`：

1. 从 `fdebc...` source 定位实际 DSpark greedy verify、request lifecycle、pool slot、
   bonus、cutoff 和 metric seam；
2. 设计确定性 patch/apply/build 流程，禁止直接留下未登记的 site-packages edit；
3. 将 `deepspec/hedge_spec/` 的同 hash core 注入或打包进独立 SGLang source，
   记录 canonical/target 逐文件 hash；禁止依赖 DeepSpec cwd、`PYTHONPATH=.` 或
   从本仓库偶然 import；
4. 在 HEDGE disabled 时保留 native verifier；
5. 在 enabled 时执行 device-resident core；
6. 在原生 TP/vocab verify seam 上实现 compact
   `top_logit/top_token_id/draft_logit` gather/reduce，保持 device resident；
7. 正确初始化/更新/清除 per-request budget，并处理 batch reorder、abort、finish 和
   slot reuse；
8. 把 HEDGE relaxed accepted length 传播到真正的 `accept_index`、commit length、
   KV/cache、request output-token state、next-token/bonus path 和统计，而不只覆盖
   日志/counter；
9. 添加 calibration-only first-rejection trace；
10. 添加 formal-run device counters 和结束时 dump；
11. 添加生成 token IDs 的稳定 artifact seam；
12. 实现 alignment、bonus、cutoff、batch reorder、abort/finish、slot reuse、B0 tie、
    downstream state propagation 和 counter-called-but-ignored 等 integration tests；
13. 从最终 patched source 构建一次 wheel，记录 wheel hash并用 uv 安装到
    `$HEDGE_VENV`。

### 入口

- P02 pure core commit 已 push；
- P00 fixed source/venv identity 可用；
- P01 的 artifact schema 至少已冻结。

### 出口

```text
integration.patch
patch_record.json
engine_identity.json
wheel_manifest.json
core_injection_manifest.json
integration_test.log
```

### 主 Agent 验收

- base commit 精确；
- disabled path 调用 native；
- enabled path 的 fixture/state assertions 证明 relaxed prefix 真正影响
  accept-index、commit/KV/request-token/next-token seam，counter 只作辅助证据；
- compact score gather 与 full-reference fixture 等价；
- per-request state 在 reorder/abort/finish/reuse 后不泄漏；
- 独立 SGLang source 中的注入 core 与 `deepspec/hedge_spec/` hash 一致，且从非
  DeepSpec cwd 启动时 import 正常；
- 所有正式 arm 能使用同一 wheel hash；
- 没有 CPU hot-path sync 或逐 block 文件写入。

验收后使用 `$git-commit-message` 提交并 push integration/tooling。此后
decode-affecting code 进入 freeze 候选。

### 回退

- 先用最小 tensor fixture 缩小对齐问题；
- 再用单 request server smoke；
- 具体上游 bug才允许固定 cherry-pick；应用后重建 wheel并让所有 arm 共用；
- 禁止切到 vLLM、浮动 main 或另一 checkpoint。

---

## P04：八卡 integration smoke

### Executor 任务

派 `p04_gpu_smoke`，独占 lane：

1. 新建 attempt，保存 resolved config；
2. 验证 keepalive，暂停并确认 contexts none；
3. 先以 HEDGE disabled 启动 TP8 DSpark；
4. 确认 TP rank 0–7、8 张 GPU、target/draft 48/48、DSpark width 5、packed FP4、
   `flashinfer_mxfp4` 和 API；
5. 完成一个固定 native 请求并保存 API 响应；
6. 定向停止并恢复 keepalive；
7. 再次暂停 keepalive，新 attempt 以 `B=0` 启动，完成同一请求，保存合法 API
   响应和证明 HEDGE verify 被调用的 counter；
8. 定向停止，确认项目 CUDA context 已退出并恢复 keepalive。

`accept_index`、commit length、KV/cache、request token、next-token/bonus 和
reorder/abort/finish 的深层正确性只在 P03 小型 integration fixture 中断言；P04
不为逐项观测这些内部状态增加实机 instrumentation 或门禁。32 条完整 token ID 的
`B=0` 等价核查属于 P05。

### 入口

- P03 offline tests PASS；
- P01 runner 可用；
- lane/keepalive 健康。

### 出口

native 与 `B=0` 两个 smoke attempt，包含第 7.2 节 P04 最小文件。

### 主 Agent 验收

- TP rank 0–7 均初始化且 8 张 GPU 参与，DSpark/packed-FP4 backend 身份正确；
- native 与 `B=0` API 都返回合法、非空结果；
- `B=0` 的 HEDGE counter 证明 verify 路径实际被调用；
- 服务定向停止、项目 CUDA context 退出、keepalive 恢复。

以上是 P04 全部门禁；不要求在真实 GPU 上逐项观测内部提交状态，也不以单请求推断
性能或提前完成 `B=0` 等价结论。

### 回退

每次只改一个方向并保留 attempt。相同错误三次无新证据则换诊断层；不改 backend、
width、模型或 lane。P04 未通过前不做 32/500。

---

## P05：32 条 B0 核查、q25 校准与配置冻结

### Executor 任务

派 `p05_calibration`：

1. 用最终 wheel 新启 native service；
2. 顺序运行 32 条，保存 token IDs 和 strict first-rejection trace；
3. 清理/keepalive；
4. 新启 `B=0` service，顺序运行同一 32 条；
5. 比较 32 组完整 token IDs，生成 `b0_equivalence.json`；
6. 若失败，保存首个最小反例并执行有界的单变量修复；
7. 无论 B0 最终 PASS/FAIL，都从 native trace 按第 4.4 节计算 q25；
8. 冻结 `B=g`、`g=q25`、`m=1`、normalized_suffix、width 5；
9. 输出 config fingerprint；清理并恢复 keepalive。

### 入口

- P04 PASS；
- immutable 32 条 calibration manifest；
- decode-affecting integration 尚未正式冻结。

### 出口

第 7.2 节 calibration artifact，以及：

```text
b0_status=PASS|FAILED
positive_value_count
q25_method
g
B
m=1
config_fingerprint
```

### 主 Agent 验收与提交

- 原始 trace 可复算 q25；
- B/g/m 逐字段符合协议；
- B0 比较确实使用完整 token IDs；
- B0 失败时 experiment doc 顶部已加入 `B0 failed` 和探索性标签。

主 Agent 使用 `$git-commit-message` 提交/push dataset manifest、校准配置和小型
calibration summary。该 commit 后 decode config/source 正式冻结。

### 回退

- trace 为空优先判断 instrumentation 未调用、对齐错误或真正无 positive values；
- B0 失败不能无限占用正式 arm 时间；
- 仍未修好时继续 P06/P07，但结论只能 `COMPLETE_EXPLORATORY`；
- 禁止手工挑 g、把 q25 改成其他 percentile 或看正式结果后调参。

---

## P06：native 正式 500

### Executor 任务

派 `p06_native_formal`，独占 lane：

1. 登记 formal native attempt；
2. `HEDGE_ENABLED=0`，其他最终源码、wheel、模型和请求配置固定；
3. 完成启动与身份核对；
4. 保存 TP rank 0–7 初始化/加载日志和请求期间八卡逐卡显存/利用率采样；
5. 顺序运行 calibration 前 10 条 warmup；
6. 清空 runner 的计时累计，顺序运行 500 条一次；
7. 保存逐请求 latency/token/answer/acceptance、完整 timing 与 summary；
8. 定向停止、contexts none、恢复 keepalive。

### 入口

- P05 配置/源码 freeze；
- B0 可以 PASS 或 FAILED；
- worker 健康。

### 出口

一次有效 native 500 run；技术失败 attempt 单独保存。

### 主 Agent 验收

- 10 warmup 不计时；
- 500 条全部终态；
- completion-token sum 与逐请求重算一致；
- monotonic time 边界正确；
- HEDGE disabled；
- source/wheel/config identity 与待运行 B+ 可匹配；
- server log 和正式请求期采样证明 TP rank 0–7 均存活、8 张 GPU 均参与；
- 清理/keepalive PASS。

### 回退

技术失败可以从头重跑；不得续跑后拼接 wall time，也不得因 TPS 低重跑。任何
decode-affecting修复都会使已完成 native 作废，并要求 P06/P07 同一身份重跑。

---

## P07：HEDGE `B>0` 正式 500

### Executor 任务

派 `p07_hedge_formal`，独占 lane：

1. 登记 formal HEDGE attempt；
2. 使用与 P06 相同的 source/wheel/模型/请求；
3. `HEDGE_ENABLED=1`，加载 P05 唯一 config；
4. 启动时验证 width 5 和 config fingerprint；
5. 保存 TP rank 0–7 初始化/加载日志和请求期间八卡逐卡显存/利用率采样；
6. 顺序运行相同 10 条 warmup；
7. 顺序运行同顺序 500 条一次；
8. 保存逐请求指标、HEDGE counters、timing 和 summary；
9. 定向停止、contexts none、恢复 keepalive。

### 入口

- P06 有效；
- P05 config frozen；
- P06 后没有 decode-affecting变化。

### 出口

一次有效 `B>0` 500 run。

### 主 Agent 验收

- 500 条全部终态；
- HEDGE runtime 被调用；
- 每请求 B 初始化/清理，counter 无 slot leak；
- `B=g`、`g=q25`、`m=1`、normalized_suffix、width 5；
- timing 和 summary 可重算；
- 与 P06 identity 完全相同，除 HEDGE 开关/config；
- server log 和正式请求期采样证明 TP rank 0–7 均存活、8 张 GPU 均参与；
- 清理/keepalive PASS。

### 回退

技术失败按 P06 规则；若只有 HEDGE wiring failure，修复后必须重建 identity，并让
native/B+ 在同一新身份重跑。不得改 g/B/m 追求更好结果。

---

## P08：最终离线审计与权威实验记录

### Executor 任务

派 `p08_final_audit`，不启动模型：

1. 读取 P00–P07 handoff 和原始 artifact；
2. 重算数据 manifest、B0、q25、两个 500 summary 和 delta；
3. 核对 source/wheel/checkpoint/config identity；
4. 核对 P06/P07 均有 8 TP ranks/8 张 GPU 参与证据；
5. 核对正常 shutdown、contexts none 和最终 keepalive；
6. 生成最终 JSON/Markdown 和 artifact hash；
7. 完成 `$EXPERIMENT_DOC`；
8. 完成最终 progress 和记载所有失败 attempt。

### 入口

- P06/P07 有效正式 run；
- P05 B0 状态已冻结；
- 所有服务已停止，keepalive 健康。

### 出口

```text
final_audit.json
final_results.json
reproduction.md
artifact_manifest.json
docs/experiment/hedge-deepseek-v4-flash-dspark.md
docs/progress/hedge-deepseek-v4-flash-dspark.md
```

### 主 Agent 验收

- 根据第 0 节发布 `COMPLETE` 或 `COMPLETE_EXPLORATORY`；
- B0 failure 不被隐藏；
- 所有指标是观察值，无自创阈值；
- 正式结果表可从原始 JSONL 重算；
- native 与 HEDGE 正式 arm 的 8 ranks/8 GPUs 证据均完整；
- 最终 worker/process/keepalive 状态明确；
- 复现步骤使用固定身份。

验收后，主 Agent用 `$git-commit-message` 提交并 push 结果、实验记录、handoff 和最终
进展。阶段结束后不重启服务。

---

## 10. Handoff 与失败恢复协议

每个 phase handoff 写入：

```text
docs/plan/handoffs/hedge-dspark-<phase>-<attempt-id>.md
```

最小结构：

```markdown
# HEDGE DSpark <phase> handoff

- Status:
- Attempt ID:
- Started / finished:
- Autonomy elapsed / deadline:
- Git branch / HEAD / worktree:
- Worker / GPU lane:
- TP ranks / GPU participation:
- Authorized phase:

## Outcome
## Changes
## Evidence and artifact paths
## Source/config identity
## Process, CUDA context and keepalive state
## First root cause / progress since prior attempt
## Main-Agent acceptance recommendation
## Next eligible phase
```

失败时：

1. 保存第一处根因和完整日志；
2. 定向停止本 attempt；
3. contexts none 后恢复 keepalive；
4. 新 attempt 不覆盖旧目录；
5. 一次只改变一个主要变量；
6. 三次同根因无新证据后必须换诊断策略；
7. 不等待用户，除非下一步需要本计划之外的新 authority；
8. B0 failure 按探索性规则继续；
9. worker/lane 丢失时禁止跨 lane。

“有进展”只包括 blocker 迁移或故障范围被证据缩小；改参数、换日志文本或延长 timeout
本身不算。

---

## 11. `docs/experiment` 权威记录模板

文件：

```text
docs/experiment/hedge-deepseek-v4-flash-dspark.md
```

顶部必须始终保持可快速阅读：

```markdown
# HEDGE × DeepSeek-V4-Flash-DSpark

## 快速结果

- 状态：IN_PROGRESS | COMPLETE | COMPLETE_EXPLORATORY | INCOMPLETE
- B0：PASS | FAILED | NOT_RUN
- 结论/首要 blocker：
- 正式 native run：
- 正式 HEDGE run：
- worker / TP / GPU 参与：`4106666` / 8 / 8 ranks & 8 GPUs
- g / B / m：
- native TPS / HEDGE TPS / delta：
- native accepted length / HEDGE accepted length / delta：
- native GSM match / HEDGE GSM match：
- artifact root：
- core / integration / config / result commits：
```

正文必须详细记录：

1. 固定模型、checkpoint、SGLang、wheel 和 GPU identity；
2. worker `4106666`、TP rank 0–7 初始化以及两个正式 arm 的八卡参与证据；
3. HEDGE 算法与 config fingerprint；
4. dataset/prompt/generation/timing 协议；
5. 每个 attempt、唯一变化、结果和日志路径；
6. B0 首个反例或等价证据；
7. q25 原始分布、方法和冻结结果；
8. native/B+ 完整表和逐指标 delta；
9. 正常 shutdown 与失败归因；
10. 限制、探索性标签和复现命令。

`docs/progress` 不能替代该文件。

---

## 12. 最终结果表模板

### 12.1 B0 核查

| 项目 | Native | HEDGE B0 | 结论 |
| --- | ---: | ---: | --- |
| 样本数 | 32 | 32 | |
| 请求成功 | | | |
| 完整 token IDs 相等 | — | | `PASS/FAILED` |
| accepted trace 相等（若有） | — | | |
| relaxed tokens | 0 | | 必须为 0 |
| 首个 mismatch sample/token | — | | |

### 12.2 q25 校准

| positive values | q25 method | `g` | `B` | `m` | scheme | width | fingerprint |
| ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| | linear | | | 1 | normalized_suffix | 5 | |

### 12.3 正式 arm

| Arm | Worker / TP | 8 ranks / 8 GPUs | HEDGE | B / g / m | Warmup / formal | 成功 / 失败 | Completion tokens | Timed seconds | Output TPS | Mean accepted draft | GSM match / parse fail | Retries | Run |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| Native | 4106666 / 8 | | off | — | 10 / 500 | | | | | | | | |
| HEDGE B+ | 4106666 / 8 | | on | | 10 / 500 | | | | | | | | |

### 12.4 观察差异（无门槛）

| 指标 | Native | HEDGE B+ | Absolute delta | Relative delta |
| --- | ---: | ---: | ---: | ---: |
| Output TPS | | | | |
| Mean accepted draft/proposal | | | | |
| Completion tokens | | | | |
| GSM8K match count | | | | |
| Parse failures | | | | |

### 12.5 HEDGE counters

| relaxed tokens | budget spent | requests hitting budget | cap-bound blocks | runtime calls | state leaks |
| ---: | ---: | ---: | ---: | ---: | ---: |
| | | | | | 0 |

表下必须声明：

- 指标不构成 performance/accuracy PASS gate；
- `B0 failed` 时所有 `B>0` 表格均为探索性；
- 不做跨 DSpark/Eagle3/DFlash TPS 排名。

---

## 13. 新 Codex 会话启动清单

新会话可以直接按以下顺序开始，无需再次讨论方案：

1. 完整读取第 1.1 节文件；
2. 记录 `AUTONOMY_START_UTC` 和 `+12h` deadline；
3. 检查工作区、branch、remote 和已有用户修改；
4. 重新查询 `mlx worker list`，只接管 `4106666` 的全部 8 张卡并固定 TP=8；
5. 检查本项目专用 8 卡 keepalive、八卡逐卡 gate 和无未知 SGLang context；
6. 创建/验证专用 worktree、uv env、SGLang source 和 HDFS session root；
7. 派出 persistent progress recorder；
8. 派 P00 executor；
9. P00 基础 repo identity 完成后并行派 P01/P02；
10. 对每个 handoff执行主 Agent 验收/纠偏/自动推进；
11. 每 30 分钟更新、commit、push progress；
12. 每个关键节点使用 `$git-commit-message`；
13. 完成 P08 后停止所有模型进程、保持或恢复 lane keepalive，并发布最终状态。

主 Agent 的目标不是证明 HEDGE 一定更快，而是用固定、可复现、可审计的 DSpark
路径把 HEDGE core 真正接入并完成 native/B0/B+ 全流程。
