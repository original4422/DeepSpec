# HEDGE on DeepSeek-V4-Flash Eagle3：8×H20 / TP=8 自主执行计划

> 本文件面向一个新开的、可独立接管任务的 Codex 会话。新会话必须先完整阅读仓库根部
> `AGENTS.md`、`CONTEXT.md` 和本文件，再开始任何写操作。本文采用 HEDGE-on-V4
> 连续授权：主 Agent 调度各阶段 subagent、验收、纠偏并在范围内自主进入下一阶段，
> 不逐阶段等待人工确认。Eagle3 是 best-effort 扩展路线，不得影响 DSpark 核心路线。

## 0. 快速阅读

| 项目 | 固定决定 |
| --- | --- |
| 路线定位 | Eagle3 best-effort；成功则给出完整 HEDGE 实验，失败则给出可复查 blocker |
| 自主窗口 | 从本会话实际执行开始计时，最长 12 小时 |
| 9 小时门槛 | 若 9 小时时仍没有一份已完成、可审计的 `B=0` 结果，停止实现和 GPU 实验，后 3 小时只整理证据与文档 |
| Worker | 独占 worker `4099544` 的全部 8×H20，`CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`，TP=8 |
| Operational ownership | Eagle3 是该 worker 唯一 steward；旧任务自然结束后使用本项目专用 8 卡 keepalive |
| SGLang | `v0.5.16`，基线 commit `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| 量化路径 | target 保留 packed FP4，`flashinfer_mxfp4`，不启用 FP4→FP8 dequant |
| Target | `deepseek-ai/DeepSeek-V4-Flash` revision `60d8d70770c6776ff598c94bb586a859a38244f1` |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1` revision `4c68aa4689d59cb1064f20abec7708174ee4613d` |
| Proposal 宽度 | 模型卡推荐的 3 个 speculative tokens；native、`B=0`、`B>0` 完全相同 |
| 数据 | 官方 `openai/gsm8k` `main/test` revision `740312add88f781978c0658806c59bc2815b9866`；固定 seed `980406`；互不重叠的 32 条校准集和 500 条正式集 |
| 请求 | 非思考 prompt、无 system prompt、`temperature=0`、`top_p=1`、`max_tokens=512`、单请求顺序执行 |
| 校准 | 正 `regret/value` 的 25% 分位数；`value_scheme=normalized_suffix`；`g=q25`、`B=g`、`m=1` |
| 正式 arm | native Eagle3 baseline 与 HEDGE `B>0` 各自新启服务、10 条 warmup、500 条只计时一次 |
| `B=0` | 32 条轻量 token-ID 等价性检查；失败不阻止后续，但所有 `B>0` 结果必须标为探索性 |
| HEDGE core | 可先完成资源、target/draft、native baseline 适配；等待 DSpark 发布纯 HEDGE core SHA 后再 cherry-pick |
| HEDGE 源核对基准 | 计划编写时 HEDGE repo HEAD `9fb903d676254ea5f5d171051fb15c54f331111c`；正式复用仍以 DSpark 发布的 pure-core marker/SHA 为准 |
| 提交 | 每半小时更新 progress 并 commit/push；关键节点必须使用 `$git-commit-message` |
| 权威结果 | `docs/experiment/hedge-deepseek-v4-flash-eagle3.md`，顶部先给快速结果 |

最终只允许出现三类结论：

1. `COMPLETE`：native、`B=0`、校准、`B>0` 和正式指标都完成；
2. `EXPLORATORY_COMPLETE`：`B=0` 已完成但不等价，仍完成校准和 `B>0`，结果顶部醒目标记
   `B0 failed — exploratory only`；
3. `BEST_EFFORT_STOPPED`：在固定时间和范围内无法完成，保存 blocker、最小复现、已完成
   artifact 和建议，不把它写成 DSpark 核心任务失败。

本实验不设置吞吐改善、接受长度改善或 GSM8K 匹配率门槛，也不做跨 DSpark、Eagle3、
DFlash 的绝对 TPS 排名。

## 1. 授权、角色与不可越界项

### 1.1 主 Agent

主 Agent 是本会话唯一跨阶段协调者，负责：

- 记录实际 `T0`、`T0+9h`、`T0+12h`；
- 为每个阶段派出边界明确的 phase executor；
- 协调并行槽、worker steward 和 DSpark HEDGE core marker；
- 只读复核 executor 的日志、artifact、diff 和 handoff；
- 验收通过后自主派发下一阶段，不等待人工阶段确认；
- 验收不通过时向原 executor 追派最小修正，或换一个 executor 重做该阶段；
- 只在关键节点统一 stage、生成 commit message、commit 和 push；
- 维护每半小时 progress 记录和最终权威实验文档。

Phase executor 只执行被分配的阶段，不进入下一阶段、不扩大范围、不自行 commit/push。
每个 executor 必须生成简洁 handoff，给出结果、证据路径、残留进程和下一阶段条件。

### 1.2 连续授权边界

12 小时内可以自主：

- 创建独立 worktree、分支和 uv 环境；
- 下载并发布本文固定 revision；
- 在 worker `4099544` 的全部 8 张物理 GPU 上运行有界 target-only diagnostic、native
  Eagle3、`B=0` 和
  `B>0` attempt；
- 阅读官方资料、issue、PR 和其他引擎源码；
- 对固定 SGLang commit 做最小 Eagle3/V4/HEDGE 适配；
- cherry-pick DSpark 会话发布的纯 HEDGE core commit；
- 在有明确上游修复证据时 cherry-pick 一个最小、固定 SHA，并记录原因；
- 对同一 blocker 做有界重试、单变量回退和策略切换。

以下事项始终禁止：

- 用 vLLM 或其他引擎产出正式 baseline、`B=0`、`B>0` 或吞吐结果；
- 训练、微调或蒸馏新的 Eagle3 drafter；
- 切换到浮动 SGLang `main`；
- 把不同 SGLang source 用于 native 与 HEDGE arm；
- 清理、暂停、终止或覆盖未知进程；
- 使用 broad `pkill`、`killall` 或模糊进程名；
- 把模型、venv、cache 或大型日志提交到 Git；
- 为追求成功擅自改成非 TP=8、offload、另一 worker 或另一 checkpoint。

其他引擎只允许用于阅读以下信息：权重命名、模型注册、auxiliary hidden state 的语义、
张量 shape 和 proposal 流程。其服务结果不进入任何表格或结论。

## 2. 固定身份与目录

执行开始后只允许用一次 bootstrap commit 固化实际路径；不得让交互 shell 的偶然环境
成为运行依赖。

### 2.1 建议的独立身份

| 资源 | Eagle3 固定值 |
| --- | --- |
| DeepSpec branch | `exp/hedge-v4-eagle3` |
| DeepSpec worktree | `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3` |
| SGLang source worktree | `/home/tiger/src/sglang-hedge-v4-eagle3` |
| uv env | `/home/tiger/venvs/deepspec-hedge-v4-eagle3` |
| HTTP port | `31001` |
| Worker scratch | `/tmp/deepspec-hedge-v4-eagle3` |
| Worker state | `/home/tiger/.deepspec-hedge-v4-eagle3` |
| HDFS root | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3` |
| Run root | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs` |
| Coordination root | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4` |
| Progress doc | `docs/progress/hedge-deepseek-v4-flash-eagle3.md` |
| Experiment doc | `docs/experiment/hedge-deepseek-v4-flash-eagle3.md` |

若这些路径已经存在，先核对 owner marker、Git branch、PID identity 和完整命令行；只有
证明属于本 Eagle3 会话才复用。冲突时选择新的、同样独立的后缀并在 bootstrap
handoff 中记录，
不得覆盖既有目录。

### 2.2 模型和共享 marker

Target 由 Eagle3 会话负责下载、验证并原子发布：

```text
/mnt/hdfs/pengzegang/DeepSpec/models/
  deepseek-ai__DeepSeek-V4-Flash/
  snapshots/
  huggingface-60d8d70770c6776ff598c94bb586a859a38244f1
```

Draft 只供 Eagle3 使用：

```text
/mnt/hdfs/pengzegang/DeepSpec/models/
  SyzygyResearch__DeepSeek-V4-Flash-EAGLE3.1/
  snapshots/
  huggingface-4c68aa4689d59cb1064f20abec7708174ee4613d
```

共享 target 完成 marker：

```text
/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/
  target-deepseek-v4-flash-60d8d70770c6776ff598c94bb586a859a38244f1.complete.json
```

marker 至少包含：

```json
{
  "schema_version": 1,
  "status": "complete",
  "owner_session": "eagle3",
  "provider": "huggingface",
  "repo_id": "deepseek-ai/DeepSeek-V4-Flash",
  "revision": "60d8d70770c6776ff598c94bb586a859a38244f1",
  "snapshot_path": "<absolute HDFS path>",
  "manifest_path": "<absolute HDFS path>",
  "manifest_sha256": "<sha256>",
  "file_count": 0,
  "weight_shard_count": 0,
  "total_bytes": 0,
  "published_at": "<UTC timestamp>",
  "immutable": true
}
```

DFlash 只能在该 marker `status=complete` 且本地最小复核通过后只读使用 target。
Eagle3 发布后不得就地修改 target；任何修正都使用新 staging 和新 marker。

## 3. Worker `4099544` 独占与 operational steward

Eagle3 主 Agent 是 worker `4099544` 的唯一 operational steward，并独占全部
8×H20。正式命令固定：

```text
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
tensor_parallel_size=8
```

### 3.1 旧任务处理

进入 worker 前重新运行 `mlx worker list`，确认 `4099544` 仍是 8×H20。随后只读记录：

- hostname、8 张卡 UUID、型号、显存和拓扑；
- 全部 compute PID、PID/PGID/SID、完整命令行、owner 和物理 GPU；
- 现有 keepalive 的 PID/PGID、state、命令和逐卡利用率；
- worker `/tmp`、HDFS、开发机共享盘容量。

发现已有旧任务时：

- 让它自然结束，不发送 signal，不改环境，不移动文件；
- 在 `existing-processes.json` 和 progress 中记录身份与观察时间；
- 全部 8 张 GPU 未释放前只做下载、源码、环境、测试、数据和文档工作；
- 每 5–10 分钟只读检查，避免高频轮询；
- 若直到 `T0+9h` 仍无法获得全部 8 张 GPU，按 `BEST_EFFORT_STOPPED` 收尾。

### 3.2 本项目专用 8 卡 keepalive

旧任务自然结束且全部 CUDA context 为空后，启动 Eagle3 项目专用的 8 卡 sustained
keepalive：

- 脚本必须显式要求准确的 8 张卡，拒绝少卡、多卡或已有 compute context；
- 固定 `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`；
- 使用 Eagle3 独立 state dir、PID/PGID、日志和 owner marker；
- 启动后采集 10×1 秒，逐张物理 GPU mean utilization 至少 40%；
- 用 8 个 GPU UUID 证明 logical 0–7 与物理卡一一对应；
- 长下载、编译、等待 HEDGE core 和人工观察期间保持运行；
- 每个超过 20 分钟的无人值守步骤前复核 worker、keepalive 和逐卡利用率。

启动模型前紧邻地定向暂停该 8 卡 keepalive，确认 8 张卡的 keepalive CUDA context
全部退出，然后立即启动已登记模型命令。服务退出或失败后，先定向清理本 attempt，
确认 8 张卡 context 为空，再恢复同一个 keepalive 并重新通过 10×1 秒逐 8 卡门禁。
空闲 SGLang server 或单纯显存占用不构成保活。

### 3.3 进程纪律

所有长任务必须先写成仓库脚本，再从仓库根目录执行：

```text
mlx worker login 4099544 -- bash <absolute-script-path>
```

每个 launcher 保存：

- worker ID、hostname、全部 8 个物理 GPU UUID；
- `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`；
- resolved command 和显式环境变量；
- owner PID、PID/PGID/SID、start ticks；
- port、scratch、HDFS run path；
- server、TP rank 0–7、sampler、watchdog PID；
- 定向 shutdown 和 CUDA context cleanup 结果。

服务失败或结束后，只能终止本 attempt 已验证的 process group。无法证明 context 清空时
不得叠加第二套服务；先保存证据并恢复到可归因状态。

## 4. 固定实验协议

### 4.0 8 卡 packed-FP4 runtime 基线

target-only diagnostic、native、`B=0` 和 `B>0` 都从同一组保守配置开始：

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

Eagle3 draft backend 由固定 checkpoint layout 决定。若最小适配需要 method-native
scheduling 参数，必须由 checkpoint/contract 证据触发，并在 native、`B=0`、`B>0`
完全一致；除此之外不做 cache、并发、CUDA Graph 或 backend 调优。

### 4.1 数据集和 prompt

固定使用官方 `openai/gsm8k` `main/test` revision
`740312add88f781978c0658806c59bc2815b9866`，并保存实际 fingerprint。使用 seed
`980406` 对 test split 的 source indices 做确定性 shuffle：

- 前 32 个唯一 index：calibration set；
- 接着 500 个唯一 index：formal set；
- 两者不得重叠；
- 保存 source index、question、answer、dataset revision、fingerprint 和 split
  manifest SHA-256；
- 三个 arm 读取同一只读 manifest，不各自重新抽样。

每条请求只有一个 user message：

```text
<原始 GSM8K question>
Please reason step by step, and put your final answer within \boxed{}.
```

请求固定：

```json
{
  "temperature": 0,
  "top_p": 1,
  "max_tokens": 512,
  "chat_template_kwargs": {
    "enable_thinking": false
  }
}
```

不添加 system prompt，不并发请求。标准答案从 GSM8K `####` 提取；模型答案优先取最后
一个 `\boxed{}`，再按显式 fallback 规则解析。保存完整 response 和 token IDs。

### 4.2 三个运行模式

| Mode | HEDGE | Budget | 用途 |
| --- | --- | ---: | --- |
| native | disabled | N/A | 原生 Eagle3 baseline |
| B0 | enabled | `B=0, m=1` | 32 条轻量等价性检查和校准 trace |
| B+ | enabled | `B=g, m=1` | 唯一正预算正式 arm |

所有 mode 必须使用：

- 同一个最终 SGLang source commit；
- 同一 uv lock 和 runtime；
- 同一 target/draft snapshot；
- 同一个 TP=8 和 worker `4099544` 的全部 8 张物理 GPU；
- 同样的 3 个 speculative tokens；
- 同一 prompt、generation 参数和数据顺序。

首次 native bring-up 可以在 HEDGE core 到达前作为 feasibility diagnostic，但不能充当
最终 baseline。正式 native 必须在 HEDGE 集成完成、最终 source freeze 后重新运行。

### 4.3 `B=0` 和正预算校准

`B=0` 在 32 条 calibration 样本上与 native 比较完整输出 token IDs：

- 32/32 相同：`B0_PASS`；
- 任一不同：`B0_FAIL`，保存第一个最小反例、两边 token IDs、文本、proposal trace 和
  首个分歧位置；
- 不要求逐 logits、逐 rank 或浮点 bitwise 相同；
- `B0_FAIL` 不阻止后续流程，但 experiment 顶部和所有结果表必须标记
  `exploratory only`。

在同一 32 条 calibration trace 中，收集严格验证首次拒绝位置的正
`regret/value`，固定：

```text
value_scheme = normalized_suffix
positive_values = all finite values > 0
g = numpy.quantile(positive_values, 0.25, method="linear")
B = g
m = 1
```

保存每个原始 value、sample/proposal identity、分位数实现、NumPy 版本、`g/B` 和
配置 hash。不得根据正式 500 条结果回调 `B` 或 `m`。

若正值集合为空、非有限或 trace 缺失，先修复 instrumentation。无法在 9 小时门槛前
得到协议合法的 `g` 时，不伪造经验 budget；按 best-effort blocker 收尾。

### 4.4 正式计时

native 和 `B+` 各自：

1. 从无残留 context 的新服务启动；
2. ready 后顺序运行 calibration set 固定前 10 条 warmup；
3. warmup 不计时；
4. 从第 1 条 formal 请求发出前取单调时钟；
5. 顺序执行 500 条，直到每条达到终态；
6. 第 500 条终态后停止计时；
7. 定向停止服务、清空 context、恢复 keepalive。

每个请求最多 3 次总 attempt；重试等待和失败耗时计入 formal 墙钟时间，并逐次保存。
端到端 TPS 定义为：

```text
formal 500 条所有成功 response 的 completion_tokens 总和
----------------------------------------------------------------
第 1 条请求发出到第 500 条达到终态的客户端单调时钟秒数
```

每个 arm 只接受一份完整正式结果。基础设施中断且没有形成 500 条终态时，该 attempt
标为 invalid，修复单一根因后从新服务完整重跑；一旦有完整结果，不重复运行择优。

正式汇总至少报告：

- 500 条成功、失败、重试和 parse failure 数；
- GSM8K match 数和比例；
- completion tokens；
- timed wall seconds 和 end-to-end output TPS；
- 平均接受长度、接受长度分布和原始 proposal 数；
- 8 卡请求窗口 utilization 和显存；
- native 与 `B+` 的绝对值和 delta；
- `B0_PASS` 或 `B0_FAIL`。

## 5. 已知实现风险：公开 checkpoint 不支持 SGLang

`SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1` 的公开模型卡明确说明当前没有 SGLang
支持。因此本路线不是“配置现有 launcher”即可完成，而是 best-effort 的最小适配。

正式调查以固定 SGLang source、checkpoint config、官方模型卡和公开一手实现为准。
其他引擎代码只用来理解以下契约：

1. draft config、architecture 注册和权重名；
2. target tokenizer/vocab 与 draft token mapping；
3. Eagle3 所需 auxiliary hidden states 的 layer、shape、dtype 和归一化语义；
4. prefill/decode 时 aux capture 的生命周期；
5. 3 个 speculative tokens 的准确 proposal 语义。

最小 SGLang 适配优先拆成独立 seam：

1. **V4 aux capture**：当前固定 source 的 `deepseek_v4.py` 只有
   `set_dspark_layers_to_capture`，不能照搬或把它当作 Eagle3 已支持。模型卡的 Eagle3
   aux logical layers 固定为 `[1, 21, 40]`；SGLang 通常按 `layer_id + 1` 设置捕获
   hook，因此预期 hook indices 为 `[2, 22, 41]`，但必须先通过索引小测验证后才能写入
   正式实现；
2. **TP 语义**：证明每个 TP rank 的 capture shape、shard/replicate 规则与 drafter
   输入一致，不通过隐式 gather 掩盖 shape 错误；
3. **mHC reduction/layout**：DeepSeek-V4 每个被选 layer 的 4 个 mHC streams 必须在
   stream 维做 mean reduction，从每层 `4×4096` 得到 `4096`，三层形成明确的
   `3×4096` aux layout；禁止直接 flatten 4 streams、只取一个 stream 或复用 DSpark
   capture layout；
4. **Draft loader**：注册
   `DeepSeek-V4-Flash-EAGLE3.1` architecture/config，完整加载固定 draft snapshot；
5. **Runner plumbing**：通过 SGLang 现有 speculative interface 把 target token、
   aux states 和必要 metadata 交给 Eagle3 drafter；
6. **Width invariant**：将公开模型卡的 3 个 speculative tokens 映射到固定 SGLang
   参数，并在 resolved config、启动日志和 proposal trace 三处验证；
7. **HEDGE hook**：native Eagle3 成功后，才在严格验证/首次拒绝 seam 接入纯 HEDGE
   core；不把 aux capture 和风险预算逻辑揉成一个不可测试补丁。

启动大模型前必须先有一个秒级、无 GPU 的 aux contract test：为各 logical layer 和
4 个 mHC streams 注入可区分的 synthetic 值，断言 `+1` hook 精确选择 logical
`[1,21,40]`，断言四流 mean 数值正确，并断言交给 drafter 的 layout 精确为
`3×4096`。该测试不通过时禁止用 full-model attempt 猜 shape。

不能把另一引擎的大块 scheduler/engine 复制为正式路径，也不能因为 vLLM 可以运行就把
vLLM 指标写入 Eagle3 结果。

## 6. 阶段图与并行关系

```text
Phase 00  会话 bootstrap + 独占 8 卡 steward inventory
    |
    +--> Phase 01A  target/draft acquisition + target atomic publish
    +--> Phase 01B  worktree/uv/data/runner/artifact skeleton
    +--> Phase 01C  SGLang V4 aux/Eagle3 compatibility research
                     |
                     v
Phase 02  8×H20 target diagnostic + native Eagle3 最小适配/smoke
    |                    \
    |                     +-- 等待 DSpark pure HEDGE core marker
    v
Phase 03  cherry-pick pure HEDGE core + Eagle3 adapter + final source freeze
    |
    v
Phase 04  native 32 + B0 32 + q25 calibration
    |
    +--> Phase 05  native：10 warmup + 500 formal
    |
    v
Phase 06  B+：10 warmup + 500 formal
    |
    v
Phase 07  audit、权威实验记录、cleanup、最终 commit/push
```

Phase 01A、01B、01C 应在可用并行槽内同时执行。Phase 02 必须等 worker `4099544`
的全部 8 张 GPU 自然释放并完成项目专用 8 卡 keepalive 建立。等待 HEDGE core 不阻止
target/draft、native Eagle3 和离线工具链准备。Phase 05 与 Phase 06 使用同一 worker，
必须串行。

## 7. 分阶段执行、验收与回退

### Phase 00：bootstrap 与 operational ownership

**Executor 任务**

- 记录 `T0`、9/12 小时 deadline；
- 创建独立 DeepSpec/SGLang worktree、branch、state 和 HDFS run namespace；
- 查询 worker 和全 8 卡进程；
- 识别旧任务与既有 keepalive，但不终止；
- 准备本项目专用 8 卡 keepalive 脚本和 owner schema；
- 写 `docs/experiment/...` 的快速结果骨架和第一条 progress。

此阶段不下载模型、不安装正式环境、不启动 GPU 实验。若旧任务仍运行，明确进入
`WAIT_EXISTING_TASKS`，但允许 Phase 01A–01C 并行。

**退出验收**

- worktree、branch、env path、port、scratch、HDFS path 无冲突；
- worker `4099544` 确认为 8×H20，物理 UUID 映射已保存；
- 每个现有 PID 的处置是 `owned`、`known keepalive` 或 `leave untouched`；
- 没有发送 signal；
- 8 卡 keepalive 和 worker owner marker 已形成小型 JSON schema；
- `T0+9h`、`T0+12h` 可机器读取。

**Artifact**

```text
bootstrap.json
worker_inventory.json
existing_processes.json
worker_assignment.json
deadlines.json
phase-00-handoff.md
```

**主 Agent 验收/纠偏**

主 Agent 对照 `nvidia-smi`、PID/PGID/命令和路径做只读复核。GPU 归属不清时只追派
inventory 修正，不允许“先停掉再看”。验收后自主派发 Phase 01A–01C。

### Phase 01A：target/draft 下载、验证和共享 target 发布

**Executor 任务**

- 在 worker NVMe `/tmp` 的 Eagle3 项目专用目录使用固定 revision 下载；
- Hugging Face cache、lock、append 和 mmap 全部留在 NVMe；
- 验证 provider 返回的 commit 与要求 revision 完全一致；
- 验证 config、tokenizer、index、全部 index referent、shard 数、文件大小和 LFS
  identity；
- 生成逐文件 manifest；能使用 provider cryptographic OID 时同时保存；
- 将实体文件复制到唯一 HDFS staging，不发布 symlink/hardlink/cache 引用；
- staging 上再次核对文件集合、总大小和 index referent；
- 先原子发布 target snapshot，再最后发布 `.complete.json` marker；
- 通知 DFlash 只读复用；
- draft 用相同流程发布到 Eagle3 私有路径。

Target 下载和发布是 Eagle3 会话的明确责任，不能等待 DFlash 代办。若下载中断，继续
同一 pinned revision 的 NVMe scratch，不创建多个模糊 snapshot。优先记录 provider
LFS/OID，默认不在 NVMe 与 HDFS 各完整重读约 160 GiB 权重计算 SHA-256；只有出现
传输损坏或身份矛盾证据时才追加重校验。

**退出验收**

- target repo/revision 精确为
  `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`；
- draft repo/revision 精确为
  `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d`；
- HDFS 目标是独立实体目录；
- manifest、size、index referents 和关键 config 检查通过；
- target complete marker 最后写入且字段完整；
- DFlash 可以在不写目标目录的前提下读取 marker。

**Artifact**

```text
target_provider_identity.json
target_manifest.jsonl
target_manifest.sha256
target_publish.json
draft_provider_identity.json
draft_manifest.jsonl
draft_manifest.sha256
draft_publish.json
phase-01a-handoff.md
```

**回退**

下载失败优先更换传输方式、代理或断点续传实现，不改变 repo/revision。HDFS FUSE
不支持的操作退回 NVMe 完成。只有出现源文件身份矛盾时才停止发布并保存证据，不能
用目录名猜测完整性。

### Phase 01B：独立 uv/SGLang 环境、数据和运行工具

**Executor 任务**

- 从固定 `fdebc938...` 建立 Eagle3 独立 SGLang source worktree；
- 使用 uv 创建独立环境和 lock，不复用 DSpark/DFlash venv；
- 记录 Python、Torch、CUDA、NCCL、FlashInfer、Triton、sglang-kernel 版本；
- 在本 Eagle3 环境复用已经验证的 CUDA 13.0 自洽 toolchain 和可复现
  `lib64/libcudart.so`、`lib64/libnvrtc.so` link-layout 修复；
- 生成固定 32+500 split manifest；
- 实现顺序 API runner、完整 response/token-ID 保存、答案提取、重试、单调计时、
  GPU sampler 和 process cleanup；
- 为 native/B0/B+ 生成同一 schema 的 resolved config；
- 用 fixture 离线验证 B0 diff、q25 校准、summary 和 experiment table 生成。

**退出验收**

- uv lock 可重建，SGLang import path 指向独立 source；
- source parent 为 `fdebc938...`；
- 32 与 500 不重叠且 manifest hash 固定；
- prompt 和 generation 参数 fixture 精确；
- q25 fixture 证明 `B=g=q25`、`m=1`；
- runner 在 mock API 上完成 10 warmup + 500 顺序终态；
- cleanup fixture 只触及登记 PID/PGID；
- 没有 GPU 操作。

**Artifact**

```text
environment_lock.json
sglang_source_identity.json
gsm8k_split_manifest.json
runner_fixture_summary.json
process_fixture_summary.json
phase-01b-handoff.md
```

### Phase 01C：兼容性研究和最小适配设计

**Executor 任务**

- 完整读取固定 revision 的 model card/config；
- 阅读固定 SGLang commit 的 Eagle/Eagle3、DeepSeek-V4 target、model runner 和
  speculative verify seam；
- 从公开一手实现提取 aux state 契约，但不运行正式其他引擎实验；
- 输出张量 shape、layer IDs、dtype、TP ownership、prefill/decode 生命周期；
- 针对 logical `[1,21,40]` → hook `[2,22,41]`、mHC 4-stream mean 和最终
  `3×4096` layout 编写 synthetic contract test；
- 列出最小文件改动和离线测试 seam；
- 为 native bring-up 排出 3–5 个可证伪风险假设。

**退出验收**

- 明确公开 checkpoint “无 SGLang 支持”的实际缺口；
- aux capture 不是基于猜测，能引用 config/源码字段；
- synthetic contract test 已证明 `layer_id+1`、四流 mean 和 `3×4096` layout；
- target、draft、runner 和 verify 四层责任分开；
- 给出最小 native smoke 信号；
- 没有复制整个其他引擎 scheduler。

**Artifact**

```text
eagle3_compatibility_research.md
aux_state_contract.json
integration_seams.md
phase-01c-handoff.md
```

### Phase 02：8 卡 target diagnostic 与 native Eagle3 bring-up

**前置条件**

- worker `4099544` 上的旧任务全部自然退出；
- 本项目专用 8 卡 keepalive 已建立并通过逐卡门禁；
- target/draft 已发布；
- uv 和 launcher 离线 gate 已通过。

**Executor 任务**

1. 紧邻启动定向暂停 Eagle3 8 卡 keepalive，并确认 8 张卡 context 为空；
2. 用 target-only TP=8 diagnostic 验证干净 V4 target、packed FP4 backend、API 和
   8 卡；它不计入正式 baseline；
3. 清理并恢复 8 卡 keepalive；
4. 确认当前 `deepseek_v4.py` 不存在 Eagle3 capture 支持，不复用
   `set_dspark_layers_to_capture` 语义；
5. 先运行 logical `[1,21,40]` → hook `[2,22,41]`、mHC 4-stream mean、
   `3×4096` aux layout 的离线 synthetic contract test；
6. 只有该测试通过后，实现最小 V4 aux capture、draft loader 和 Eagle3 runner
   plumbing；
7. 再运行 native Eagle3 TP=8 smoke；
8. 验证实际 proposal width 为 3；
9. 保存至少 3 条顺序 API response 和 proposal/acceptance trace；
10. 定向停止、清空全部 8 张卡的 context、恢复 8 卡 keepalive。

**退出验收**

- target-only diagnostic 能返回非空响应；
- native Eagle3 日志证明 TP rank 0–7、target、draft architecture 和
  3-token proposal；
- aux state shape/dtype/device/TP 规则有运行时断言；
- 3 条请求全部达到终态；
- 至少一条 trace 证明 drafter proposal 和 target verify 都执行；
- 8 张卡均有对应 rank、模型显存和请求期利用率；
- 无残留 context，项目专用 8 卡 keepalive 恢复健康。

**回退顺序**

1. target-only 失败：先修 V4 target/runtime/backend；
2. draft load 失败：只修 config、architecture 注册或权重映射；
3. aux shape 失败：保存第一个 tensor contract 反例，缩小到单 batch/单 step；
4. prefill 成功、decode 失败：分开捕获两个生命周期，不同时改 scheduler；
5. 明确存在上游固定修复：cherry-pick 最小 SHA，记录来源；
6. 其他引擎仅用于核对 contract，不切换正式引擎。

同一根因连续 3 个 attempt 没有新证据时，必须换策略，例如从完整服务切换到离线 aux
replay、从 draft 路径切换到 target-only seam、或从运行时猜测切换到源码断言；不能只换
参数重复启动。

### Phase 03：纯 HEDGE core cherry-pick、注入与 Eagle3 adapter

**Executor 任务**

- 轮询 DSpark 发布的 HEDGE core marker；marker 必须包含 repo、commit SHA、parent、
  tests 和 scope；
- 把计划编写时的 HEDGE repo HEAD
  `9fb903d676254ea5f5d171051fb15c54f331111c` 记录为 source identity 核对基准；
  HEDGE repo 中既有 untracked docs/assets 不属于 pure core，不作为 dirty failure，
  也不得随 cherry-pick 或 commit 带入；
- 等待期间继续完成 Phase 02，不复制或重写一份平行 HEDGE core；
- 在 Eagle3 DeepSpec branch fetch 并 cherry-pick 纯 core commit，得到 canonical
  `deepspec/hedge_spec/`；
- 通过可复现 patch/build 将同 hash core 注入独立 Eagle3 SGLang worktree，不依赖
  当前工作目录的偶然 Python import；
- 分别记录 DeepSpec pure-core SHA、注入内容 hash、SGLang base/final SHA；
- 解决冲突时保持 core 算法语义，把 Eagle3-specific glue 放在独立 adapter commit；
- 在 native strict verification 首次拒绝 seam 接入 regret/value 与 risk budget；
- 实现 `disabled`、`B=0`、`B=g` 三种显式模式；
- 离线测试 budget accounting、`m=1`、normalized suffix 和无副作用 disabled path；
- freeze 最终 SGLang source SHA 和 uv lock。

**退出验收**

- core commit 与 DSpark 发布 SHA 一致；
- SGLang 内实际消费的 core hash 与 canonical `deepspec/hedge_spec/` 一致；
- Eagle3 adapter 与 pure core 可在 Git 历史中分开；
- native disabled path 不经过 HEDGE decision；
- `B=0` 和 `B>0` 使用同一 verifier/proposal trace schema；
- native/B0/B+ resolved config 只有 HEDGE mode/budget 的预期差异；
- 最终 source identity 已写入 marker，后续正式 arm 不再改代码。

**回退**

core marker 未到时不阻塞 native 适配，但不得自行发明第二套 core。cherry-pick 冲突优先
在 Eagle3 adapter 解决；若发现 pure core 缺陷，制作最小失败测试并通过 coordination
marker 通知 DSpark owner。只有修复以新的、已 push 纯 core SHA 发布后才继续。

### Phase 04：native 32、`B=0` 32 和 q25 校准

**Executor 任务**

- 在最终 source 上启动 native 服务，顺序运行 32 条 calibration，保存完整 token IDs
  和 native proposal trace；
- 清理后启动 `B=0,m=1` 服务，运行相同 32 条；
- 执行轻量 token-ID diff，保存 `B0_PASS` 或首个最小反例；
- 从严格 verification trace 收集正 normalized-suffix values；
- 按固定 NumPy 公式计算 `g=q25`、`B=g`、`m=1`；
- 用少量 calibration 请求 smoke `B+` 配置，不在正式 500 上调参；
- 更新 experiment 顶部状态。

**退出验收**

- native 和 B0 各有 32 条终态；
- 每条有完整 response、token IDs、答案和 proposal identity；
- B0 判定可由脚本重算；
- `B0_FAIL` 时 experiment 顶部已标探索性；
- positive value 集合、q25 方法、`g/B/m` 和 hash 完整；
- 正式配置冻结。

`B0_FAIL` 不回退为“必须修好才能继续”。在保存最小反例并做一次有界根因检查后，继续
Phase 05/06；只有 B0 根本未完成或 calibration 无法形成合法 `B` 时才触发时间门槛。

### Phase 05：最终 native baseline

**Executor 任务**

- 确认 source/env/model/config freeze；
- 定向暂停本项目专用 8 卡 keepalive；
- 新启动 native Eagle3 服务；
- 10 条固定 warmup；
- 顺序运行一次 500 条正式集并计时；
- 保存逐请求 latency、attempt、response、token IDs、答案、completion tokens 和
  acceptance trace；
- 汇总 TPS、平均接受长度和 GSM8K；
- 定向停止服务、清空 context、恢复 keepalive。

**退出验收**

- 500/500 均达到终态；
- timed interval、completion token 合计和 TPS 可重算；
- 3-token proposal 不变；
- 请求窗口 8 rank / 8 卡参与证据完整；
- 没有未处理 crash；
- formal result 只运行并接受一次。

基础设施中断的 incomplete attempt 不算正式结果，但必须保留并说明单一修复变量。不得
从多份完整结果中择优。

### Phase 06：HEDGE `B+` 正式 arm

与 Phase 05 完全相同，只把 mode 改为：

```text
HEDGE enabled
B = frozen g
m = 1
value_scheme = normalized_suffix
```

**退出验收**

- 500/500 终态；
- `B/g/m` 与 calibration artifact 完全一致；
- source/env/model/proposal width 与 native 相同；
- TPS、接受长度、匹配、失败和重试可重算；
- 若 `B0_FAIL`，summary 和 experiment 顶部明确写 `exploratory only`；
- shutdown、context cleanup 和 keepalive 恢复完成。

### Phase 07：最终审计和交接

**Executor 任务**

- 检查所有 artifact schema、hash 和绝对路径；
- 生成 native 与 `B+` 对照表和 delta；
- 区分正常 shutdown 与 worker crash；
- 更新 `docs/experiment/hedge-deepseek-v4-flash-eagle3.md`；
- 更新 progress 最终状态；
- 检查 worker `4099544` 全部 8 张卡的 context、Eagle3 owned PID 和 keepalive；
- 给出复现命令、限制和下一建议。

**退出验收**

- 权威实验记录可独立阅读；
- 顶部快速结果与 artifact 数据一致；
- target shared marker 可供 DFlash 只读复用；
- 没有模型、venv、cache 或大日志进入 Git；
- 无 Eagle3 残留服务；
- 结论属于 `COMPLETE`、`EXPLORATORY_COMPLETE` 或
  `BEST_EFFORT_STOPPED` 之一。

## 8. 时间管理与停止规则

### 8.1 12 小时状态机

主 Agent 在 `T0` 发布：

```json
{
  "started_at": "<UTC>",
  "implementation_cutoff": "<T0+9h>",
  "hard_stop": "<T0+12h>",
  "worker": "4099544",
  "gpu_count": 8,
  "tp_size": 8
}
```

时间策略：

- `T0–T0+3h`：优先并行完成 acquisition、环境、数据和兼容性研究；
- `T0+3h–T0+6h`：集中完成 native Eagle3 bring-up；
- `T0+6h–T0+9h`：cherry-pick core、完成 B0 和 calibration；
- 已在 9 小时前完成一份可审计 B0（无论 PASS 或 FAIL）：可继续正式 native/B+，但
  `T0+12h` 必须停止；
- 9 小时时仍无已完成 B0：不再改源码、不再启动 GPU 实验，后 3 小时只整理 blocker、
  target publish、artifact、文档和 commit；
- 12 小时时：定向停止本项目 owned process，清空全部 8 张卡 context，恢复 8 卡
  keepalive，
  写最终状态并退出。

这里“无 B0”指没有完整、可重算的 32 条 B0 结果。`B0_FAIL` 是已经完成 B0，因此仍按
用户要求继续，但结果只能称为探索性。

### 8.2 三次无新证据

对每个 root-cause signature 维护：

```text
signature
attempt_count
new_evidence
falsified_hypotheses
next_strategy
```

只有 blocker 迁移、范围缩小、假设被证伪或新最小复现出现，才算新证据。相同根因连续
3 次没有新证据时：

1. 停止重复相同 full-model attempt；
2. 切换到另一个 in-scope 策略或更紧反馈环；
3. 若没有新的 in-scope 策略，提前 best-effort 收尾；
4. 不因此切 vLLM、训练、另一 worker 或浮动 SGLang main。

## 9. Artifact 规范

每个 attempt 使用唯一目录：

```text
/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/
  <UTC>-<phase>-<mode>-<attempt>/
```

活动日志、JIT cache 和频繁小文件先写 worker NVMe：

```text
/tmp/deepspec-hedge-v4-eagle3/<attempt-id>/
```

attempt 结束时封存到 HDFS，至少包含：

```text
resolved_config.json
environment.json
source_identity.json
checkpoint_identity.json
process_identity.json
startup.json
server.log
gpu_samples.csv
warmup_outputs.jsonl
request_outputs.jsonl
acceptance_trace.jsonl
summary.json
shutdown.json
cuda_contexts_after.txt
keepalive_before.txt
keepalive_after.txt
artifact_manifest.json
```

Phase 04 额外包含：

```text
native_calibration_outputs.jsonl
b0_calibration_outputs.jsonl
b0_comparison.json
b0_first_counterexample.json
positive_values.jsonl
calibration.json
```

正式 `summary.json` 至少包含：

```json
{
  "mode": "native|B+",
  "source_sha": "<sha>",
  "target_revision": "60d8d70770c6776ff598c94bb586a859a38244f1",
  "draft_revision": "4c68aa4689d59cb1064f20abec7708174ee4613d",
  "worker_id": "4099544",
  "gpu_count": 8,
  "tp_size": 8,
  "proposal_tokens": 3,
  "hedge_B": null,
  "hedge_m": null,
  "total": 500,
  "success": 0,
  "failed": 0,
  "retries": 0,
  "parse_failures": 0,
  "matches": 0,
  "completion_tokens": 0,
  "timed_seconds": 0,
  "output_tps": 0,
  "mean_accept_length": 0,
  "b0_status": "PASS|FAIL"
}
```

## 10. 权威实验文档

`docs/experiment/hedge-deepseek-v4-flash-eagle3.md` 顶部必须在不滚动大量历史的情况下
回答：

- 当前状态和结论；
- 是否 `B0 failed — exploratory only`；
- worker、source SHA、target/draft revision；
- calibrated `g/B/m`；
- native 与 `B+` 的 TPS、平均接受长度、GSM8K match；
- 正式 HDFS artifact；
- 最后 blocker 或限制；
- 关键 Git commits。

建议顶部模板：

| 快速结果 | Native | HEDGE B+ |
| --- | ---: | ---: |
| Status | pending | pending |
| Requests terminal | — | — |
| Output TPS | — | — |
| Mean accept length | — | — |
| GSM8K matches | — | — |
| Parse failures | — | — |

固定配置区：

| 配置 | 值 |
| --- | --- |
| B0 status | pending |
| `g=q25` | pending |
| `B` | pending |
| `m` | 1 |
| Proposal tokens | 3 |
| Dataset seed | 980406 |
| Formal samples | 500 |

正文必须保留 attempt 历史：

| Attempt | Phase/mode | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- | --- |
| pending | pending | pending | pending | pending | pending |

失败不能只写最后一次错误；至少给首个错误、最小复现、三次策略判断和为什么停止。

## 11. Progress、Git 与 commit/push

### 11.1 每半小时

从 `T0` 起每 30 分钟更新：

```text
docs/progress/hedge-deepseek-v4-flash-eagle3.md
```

记录：

- 当前时间、elapsed、9/12 小时剩余；
- worker、旧任务和项目专用 8 卡 keepalive 状态；
- 当前 phase、executor 和 attempt；
- target/draft/HEDGE core marker；
- 最新里程碑或 blocker；
- artifact/log 路径；
- 下一 30 分钟动作。

主 Agent 显式只 stage 本次 progress 文件，检查 index 无其他内容，commit 并 push。
不能因为长下载、JIT 或等待旧任务而跳过半小时记录。

### 11.2 关键节点

至少在以下节点使用 `$git-commit-message` 规定的 staged diff/status/recent log 流程：

1. Eagle3 bootstrap、计划和独立运行骨架；
2. target 原子发布工具和共享 marker；
3. native Eagle3 最小适配；
4. DSpark pure HEDGE core cherry-pick；
5. Eagle3 HEDGE adapter 和 B0；
6. calibration 配置冻结；
7. native formal 完成；
8. `B+` formal 完成；
9. 最终 experiment record 和审计。

每个关键 commit 后 push 当前 Eagle3 branch，并把 SHA 写入 experiment。若 SGLang
adaptation 位于独立 SGLang repo，也必须记录 repo、remote、parent、commit 和 push
状态；DeepSpec 文档中不能只写一个无法定位的短 SHA。

Phase executor 不 commit。主 Agent 只 stage 当前节点相关的小文件，不带入其他 worktree
或用户修改。

## 12. 故障回退矩阵

| 故障 | 首选隔离 | 允许的下一策略 | 禁止 |
| --- | --- | --- | --- |
| 旧任务占用 GPU | 只读 PID/UUID inventory | 等自然结束，同时推进 CPU/下载阶段 | kill 旧任务 |
| 8 卡 keepalive 无法建立 | 验证 8 卡 inventory、owner/PID 和残留 context | 修复本项目专用脚本并重跑逐 8 卡门禁 | 模糊 pkill、少卡保活 |
| target 下载中断 | pinned NVMe scratch 和 provider identity | 断点续传、换传输方式 | 换 revision/latest |
| HDFS 发布失败 | NVMe 已验证实体和唯一 staging | 修复制/rename/marker 流程 | 直接发布半成品 |
| target-only 启动失败 | 固定 V4 target 最小 service | runtime/backend/link-layout 单变量修复 | 直接归因 Eagle3 |
| draft load 失败 | config/architecture/weight mapping | 最小 loader adapter | 换不可信 draft |
| aux state 错误 | 单 batch、单 step shape replay | 分开 prefill/decode seam | 复制完整其他引擎 |
| native Eagle3 verify 错误 | 3-token proposal trace | 缩小到首个 proposal/拒绝 | 改 proposal 宽度 |
| HEDGE core 未到 | 等 marker，继续 native 准备 | 9 小时规则收尾 | 自建不同 core |
| core cherry-pick 冲突 | pure core tests + Eagle3 adapter | 分离 adapter commit | 修改 core 语义且不回报 |
| B0 不等价 | 首个 token-ID 反例 | 有界诊断后继续探索性 B+ | 隐藏失败 |
| calibration 无正值 | 验证 trace/instrumentation | 修复采集；无合法 q25 则停止 | 手填经验 B |
| formal 服务中断 | incomplete attempt 全量证据 | 单变量修复后完整重跑 | 从半程续算/多次择优 |

## 13. 主 Agent 阶段验收表

| 阶段 | 主 Agent 最小验收 | 验收后动作 |
| --- | --- | --- |
| 00 | 独立身份、8 卡 inventory、无 signal、deadline | 并行派发 01A/01B/01C |
| 01A | 两个 pinned snapshot；target complete marker | 通知 DFlash；允许模型加载 |
| 01B | uv/source/data/runner fixture PASS | 允许 GPU lifecycle |
| 01C | aux contract 和最小 seam 有证据 | 派发 native 适配 |
| 02 | target diagnostic + native Eagle3 3-token smoke | 等/cherry-pick core |
| 03 | pure core SHA、Eagle3 adapter、final source freeze | 派发 B0/calibration |
| 04 | 32 native + 32 B0；合法 q25；探索性标记正确 | 派发 formal native |
| 05 | native 500 完整、可重算、cleanup | 派发 B+ |
| 06 | B+ 500 完整、可重算、cleanup | 派发最终审计 |
| 07 | experiment、artifact、Git、worker 状态一致 | 结束会话 |

“验收通过”只要求能进入下一阶段，不增加与主链路无关的耗时门禁。主 Agent 若发现
handoff 与原始 artifact 不一致，先追派最小修正；不得凭 executor 摘要跳过证据。

## 14. 最终完成定义

### 14.1 `COMPLETE`

- target 与 draft 固定 revision 已发布；
- DFlash 可只读复用 target complete marker；
- 固定 SGLang source 上 native Eagle3 TP8/3-token 正常；
- HEDGE pure core 和 Eagle3 adapter identity 完整；
- 32 条 B0 token-ID 等价；
- q25 calibration 合法，`B=g`、`m=1`；
- native 与 B+ 各完成 10 warmup + 一次 500 formal；
- TPS、平均接受长度、GSM8K、失败/重试和 8 rank / 8 卡证据完整；
- cleanup、keepalive、experiment 和 Git 均完成。

### 14.2 `EXPLORATORY_COMPLETE`

除 B0 token-ID 等价外，其余完整完成；所有权威位置均醒目标记：

```text
B0 failed — exploratory only
```

不得声称 HEDGE Eagle3 接入通过等价性验证。

### 14.3 `BEST_EFFORT_STOPPED`

满足以下交接质量即可：

- 遵守 9/12 小时时限；
- 没有越过固定 worker/TP/引擎/训练边界；
- target 发布责任已尽力完成并明确当前 marker 状态；
- blocker 有完整日志、最小复现和已尝试策略；
- 同根因三次无证据时已经换策略或停止；
- owned process 已清理，项目专用 8 卡 keepalive 已恢复；
- experiment 顶部直接写 blocker、已完成内容和下一建议；
- progress、关键 commit 和 push 状态完整。

Eagle3 best-effort 失败不影响 DSpark 核心路线结论。
