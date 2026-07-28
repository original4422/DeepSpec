# AGENTS.md

本文档约束在本仓库中工作的 Agent。当前唯一核心目标是：尽快在单机
4×NVIDIA H20-96G 上用 SGLang 跑通
`deepseek-ai/DeepSeek-V4-Flash-DSpark`，并完成 GSM8K test split 前 10 条的
顺序 smoke test。除非用户明确扩展范围，不进行吞吐调优、算法对比或生产化建设。

## 1. 优先级与完成定义

按以下优先级工作：

1. 保住并正确使用 4×H20 worker；
2. 获得可复现的端到端成功结果；
3. 针对实际 blocker 做最小修复；
4. 最后才做非必要清理、抽象和性能优化。

只有同时满足以下条件，才可以声称 MVP 跑通：

- 准确识别并使用 4 张 NVIDIA H20；
- 使用 uv 管理的独立环境；
- 实际运行固定的 SGLang source commit；
- 官方 checkpoint 完整加载；
- 日志证明 `speculative_algorithm='DSPARK'`，并证明各 TP rank 加载了
  DSpark draft architecture；
- OpenAI-compatible API 返回合法、非空结果；
- GSM8K test split 固定前 10 条全部完成并保存；
- 标准答案、完整模型响应、提取答案、匹配状态和解析状态均有记录；
- 自动汇总成功、失败、匹配、不匹配和解析失败数量；
- 运行期间没有未处理的 CUDA、NCCL 或 worker 崩溃。

GSM8K 匹配率不设门槛。不得因为答案不匹配而把一次基础设施成功写成失败，也不得
因为答案匹配而忽略服务、DSpark 或四卡参与证据缺失。

## 2. 当前固定候选

除非实际错误证据要求改变，首轮使用：

- 硬件：当前 `mlx worker list` 中准确的 4×NVIDIA H20 worker；worker ID 是临时
  资源，每次操作前重新查询，不把旧 ID 当作永久配置；
- 模型：`deepseek-ai/DeepSeek-V4-Flash-DSpark`；
- checkpoint provider：Hugging Face 或 ModelScope 的官方 `deepseek-ai` snapshot
  均可；当前优先验证并复制 HDFS 上已有的 ModelScope snapshot；
- Hugging Face 跨源参考 revision：
  `62af8fffb2f7030cac4de2f0169f5b8d1101b646`，但不要求 ModelScope 的非模型
  metadata 与其逐字节相同；
- checkpoint identity：优先记录 provider revision；provider 无可验证 revision 时，
  用完整逐文件 cryptographic manifest hash 固定 snapshot ID；
- SGLang release：`v0.5.16`；
- SGLang source commit：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；
- 并行：单机 TP=4，不启用 DP、PP、EP 或分离式部署；
- DSpark block size：采用 checkpoint 的 `dspark_block_size=5`，不得为跑通而
  调参；
- ragged verify：`SGLANG_RAGGED_VERIFY_MODE=static`，不启用 compact verify；
- 单请求顺序执行，低并发、短上下文；
- 禁用 CUDA Graph、prefill CUDA Graph、draft-extend CUDA Graph 和 overlap
  schedule；
- 禁用 radix cache，不启用高级缓存和通信优化。

`v0.5.16` 是当前固定候选，因为它包含官方 DSpark 支持，且该 commit 已在同一环境的
8×H20 上验证过官方未转换 checkpoint 与 DSpark drafter 能启动。这个历史结果不能
外推为 4 卡成功；4 卡路径必须单独验证。

## 3. 4 卡 FP4 路径

官方 checkpoint 约 155.4 GiB，routed experts 是 packed FP4。8×H20 上已验证的
`SGLANG_DSV4_FP4_DEQUANT=1` 会在加载时把 FP4 experts 展开为 FP8；该路径不作为
4×H20 首选，因为它会显著增加权重显存，并很可能在 TP=4 下 OOM。

4 卡首轮必须保留 packed FP4 权重，并显式选择 Hopper 可用的 MoE backend：

1. 首选 `--moe-runner-backend flashinfer_mxfp4`；
2. 若有明确的 backend/kernel 错误，再单变量回退到
   `--moe-runner-backend marlin`；
3. 只有两条 packed-FP4 Hopper 路径都有明确失败证据后，才重新讨论量化表示、
   offload、并行方式或硬件范围。

不得把未指定 backend 的默认路径称为 FP4 支持；该路径在既有 H20 证据中会把 packed
宽度当作 FP8 逻辑宽度并失败。每次启动都要从日志确认实际选中的 MoE backend 和
expert layout。

## 4. Worker 保活纪律

平台会回收 GPU 利用率连续 3 小时低于 30% 的 worker。显存占用、进程存活或偶发
短 burst 都不构成保活证据。

- 在 worker 空闲、安装依赖、写代码、下载/校验模型或等待人工决策期间，运行本项目
  专用的 4 卡 sustained keepalive。
- keepalive 必须准确识别 4 张卡，并以 10 个一秒样本验证每张 GPU 的平均利用率
  至少为 40%。
- HEDGE 仓库现有 `scripts/keepalive.sh` 固定要求 8 卡，禁止原样用于 4 卡 worker。
  本项目必须有独立、明确要求 4 卡的脚本和状态目录。
- 启动任何模型实验前，紧邻地暂停 keepalive，并确认其全部 CUDA context 已退出；
  随后立即启动已登记的模型命令，不能留下长时间无负载窗口。
- 服务退出、启动失败或实验结束后，若 worker 仍需保留，立即恢复 keepalive并重新
  通过逐卡 40% gate。
- 不把一个空闲的 SGLang server 当作保活手段。若服务需要长时间保持但没有真实请求，
  要么执行明确隔离的持续请求负载并监控逐卡利用率，要么停止服务并恢复 keepalive。
- 在任何超过 20 分钟的无人值守步骤前，检查 `mlx worker list`、keepalive 状态和
  逐卡利用率；长任务同时保存心跳和 worker 消失检测。
- keepalive 是 operational load，不是实验结果。它不得与正式 smoke test 并发，以免
  污染显存、错误归因或结果。

worker 消失时，把当前 attempt 标为中断并保留已有日志；重新查询资源并在 replacement
worker 上完整重做 preflight。不得把半成品写成成功。

## 5. 远程执行与进程清理

- 从本仓库根目录调用 `mlx worker login <id> -- bash <absolute-script-path>`。
- 非交互和长任务必须先写成仓库脚本，再用绝对路径远程执行；避免复杂的
  `bash -c`、多层引号和 pipe。
- 启动脚本记录自己的 PID/PGID、worker ID、hostname、GPU UUID、命令和日志路径。
- 清理前先用 `nvidia-smi`、PID、PGID 和完整命令行确认归属，只定向终止本项目的
  process group。
- 禁止未经核对运行 broad `pkill`、`killall` 或按模糊进程名清理。
- 每个失败路径都做有界等待与清理；无法证明 CUDA context 已退出时 fail closed，
  保留诊断信息，不叠加启动第二套服务。

## 6. 存储布局

按以下位置放置文件：

| 位置 | 用途 |
| --- | --- |
| 本 Git 仓库 | 代码、配置、脚本、文档和小型可复现结果 |
| `/home/tiger/venvs/deepspec-dspark` | uv 创建的独立 Python 环境 |
| `/mnt/hdfs/pengzegang/DeepSpec` | 模型、需要跨 worker/阶段保留的大文件和持久 run artifacts |
| worker NVMe `/tmp` | 需要 POSIX 语义的下载、编译、cache、活动日志和单次运行 scratch |

硬约束：

- checkpoint、转换权重和大型 cache 不得写入开发机共享 root 或 Git 仓库；
- 并非所有中间数据都必须直接写入 HDFS。凡是依赖 file lock、`ftruncate`、长时间
  append、频繁小文件、mmap 或其他 HDFS FUSE 不完整支持的 POSIX 操作，必须先在
  worker NVMe `/tmp` 的项目专用目录完成；
- 只有需要跨 worker、跨阶段或供最终验收留存的数据才转移到 HDFS。转移前先在 NVMe
  完成校验，转移时使用唯一 staging，转移后再次验证 size/hash/manifest；二次校验
  通过后才可删除 NVMe 唯一副本或发布 HDFS 正式路径；
- worker `/tmp` 不得保存唯一持久副本；用户已授权 Hugging Face acquisition 先在
  worker NVMe `/tmp` 完成固定 snapshot 下载和校验，再复制到 HDFS staging。NVMe
  内容始终视为可丢弃 acquisition scratch，不得直接发布为正式模型路径；
- HDFS 不用于高频小文件或要求完整 POSIX 语义的活动 scratch；活动日志可先写 NVMe，
  在检查点或任务结束时以短生命周期文件操作封存到 HDFS；
- 下载必须使用 pinned snapshot、临时目录和完成标记；校验完整后才发布为正式模型路径；
- 对已经存在的 HDFS checkpoint，必须证明它来自允许的官方 provider，并用 provider
  revision 或完整逐文件 cryptographic manifest 固定 snapshot identity，再从源目录
  只读地复制到 DeepSpec 命名空间中的临时目录；完整校验通过后才发布；
- DeepSpec 模型路径必须是约 155.4 GiB 的独立实体副本，禁止用 symlink、hardlink 或
  provider cache 引用代替复制；源目录保持不变；
- 若既有 checkpoint 无法证明官方来源、snapshot identity 或完整性，不凭目录名复制，
  改为下载 pinned snapshot 并按同样的临时目录、校验和发布流程处理；
- 运行前检查开发机、HDFS 和 worker `/tmp` 容量。

## 7. uv 与依赖纪律

- 只使用 uv 创建和修改项目环境；不复用其他项目的 vLLM/SGLang/CUDA 环境作为正式
  运行环境。
- 用 `pyproject.toml` 和 `uv.lock` 固定可解析依赖；安装命令使用 `uv sync` 或
  `uv pip` 并显式指定目标 Python。
- 记录 Python、PyTorch、CUDA runtime/toolkit、SGLang、sglang-kernel、FlashInfer、
  Triton、NCCL 和关键 wheel 的实际版本。
- 固定并验证 SGLang source commit；仅记录 `sglang==x.y.z` 不足以证明源码身份。
- 不依赖交互 shell 偶然存在的 `PATH`、`LD_LIBRARY_PATH`、`CUDA_HOME` 或 cache
  状态。远程 launcher 显式设置并记录它们。
- 当前已知可行的 H20 路径使用自洽 CUDA 13.0 JIT toolchain 和 driver forward
  compatibility prefix。不得混用 CUDA 13.3 compiler 与 13.0 runtime headers，也不得
  用压制兼容检查或降低优化级别来掩盖 JIT 编译器错误。
- 修改依赖或 engine commit 时，新建 attempt 并说明由哪条实际错误触发；一次只改变
  一个主要方向。

## 8. Preflight 与证据

核查默认只服务于尽快跑通主链路：

- 只执行足以进入下一阶段的最小核查，不为提前排除潜在风险或“证据更完整”重复做
  耗时验证；允许问题在真正加载模型或启动服务时暴露，再按具体错误回退；
- 已由可信 source manifest 验明并通过实体复制 size/path 检查的 checkpoint，不为每个
  新副本重复读取约 166 GB 做全量 SHA-256；实际模型加载是后续可用性门禁；
- checkpoint 默认检查文件集合、总大小、48 个 shard、index、config、tokenizer 和
  关键 DSpark/FP4 字段；只有具体 corruption/identity 证据出现时才升级为全量 hash；
- 环境默认检查固定 source commit、uv lock、依赖一致性、SGLang import、四卡可见和
  一次短 CUDA 操作；不做与启动无关的长时间细粒度审计；
- 并行阶段不得因另一已登记任务的短暂 keepalive pause 产生假失败；需要暂停 GPU 时先
  协调所有 watcher，或改用不暂停 keepalive 的最小检查；
- 每项额外门禁都必须是进入下一阶段的直接必要条件；否则不加入主线。

首次 GPU 启动前至少记录：

- Git branch、HEAD、工作区状态；
- worker ID、hostname、4 张 GPU 的 UUID/型号/显存/compute capability；
- Driver、CUDA compatibility、NCCL 和 GPU topology；
- PyTorch CUDA 可用性与准确的 4 卡数量；
- HDFS、共享 root 和 worker `/tmp` 容量；
- 模型 provider、repo、provider revision 或 manifest snapshot ID、总文件数、48 个
  权重 shard、文件大小与关键 manifest hash；
- SGLang import path、版本和 source commit；
- resolved 启动命令与显式环境变量。

证明“4 张卡均参与”至少需要：

- 四个 TP rank 均成功初始化和加载；
- 四张卡均出现符合预期的模型显存占用；
- 请求期间保存逐卡利用率采样；
- 无 rank 提前退出或被静默降级。

每个 attempt 使用新目录，不覆盖失败证据。正式 smoke attempt 至少包含：

```text
resolved_config.json
environment.json
server.log
gpu_samples.csv
api_smoke.json
gsm8k_outputs.jsonl
summary.json
```

日志必须区分普通 shutdown 信号和真实 worker crash，不能仅凭包含 `SIGTERM` 或
`SIGQUIT` 字样就下结论。

## 9. GSM8K smoke test

- 数据源固定为 Hugging Face `openai/gsm8k`、`main` config、`test` split 的前 10 条，
  保存 dataset revision 或可验证的数据指纹。
- 仓库现有 `eval_datasets/gsm8k.jsonl` 只有 prompt，没有标准答案，不能单独用于本次
  自动比较。
- 请求必须顺序执行，固定 generation 参数并保存完整响应。
- 标准答案优先从 GSM8K answer 字段末尾的 `####` 数值提取。
- 模型答案按明确优先级提取：最后一个 `\boxed{}`、最后一个 `####`、显式
  `final answer` 字段、最后一个数值；记录使用了哪条规则。
- 规范化逗号、货币符号、整数和有限小数后再比较；无法可靠解析时标记
  `parse_failure`，不得猜测。
- 单条 API 失败按有界重试规则执行，并记录每次错误；所有 10 条都达到终态后才汇总。
- 匹配数量只展示，不作为 MVP gate。

## 10. 故障处理与联网检索

遇到错误先保存完整日志和最小 reproducer，再查官方 SGLang、PyTorch、CUDA、
FlashInfer、Hugging Face 文档、release notes、issue 和 PR。技术问题优先使用一手资料。

默认回退顺序：

1. 环境、Driver/CUDA/toolchain、PyTorch 和固定 SGLang identity；
2. 模型 provider/snapshot identity、manifest、DSpark config 与 FP4 layout；
3. packed-FP4 Hopper backend：`flashinfer_mxfp4` 后 `marlin`；
4. 更短 context、更低 `mem-fraction-static` 和准确的单并发；
5. 确认所有 CUDA Graph、overlap、compact verify 和高级 cache 已关闭；
6. NCCL、P2P、残留 context 和 worker 生命周期；
7. 只有具体错误证据支持时才更换 SGLang commit 或扩大方案范围。

每次只改变一个主要变量，并用新 attempt 保留前后对比。不得通过同时改动大量参数来
得到一个无法归因的“偶然成功”。

只有正式 DSpark attempt 已经留下完整失败证据时，才允许运行 target-only
diagnostic attempt，以区分基础 checkpoint/FP4 backend 与 DSpark drafter 故障。
该诊断必须使用独立 attempt、不得做 benchmark 或 A/B，也不得被写成 MVP 成功。
连续 3 个 attempt 均无可验证进展时，停止继续消耗 GPU，恢复 keepalive，并汇报完整
证据、可选后续路径及推荐方案，由用户决定是否扩大范围。“有进展”必须由 blocker
明确迁移或故障范围被证据缩小来证明，不能仅凭修改了参数或产生了不同日志而重置计数。

## 11. 范围冻结

本次不做：

- 作为性能或质量基线的 target-only 运行，以及任何 A/B benchmark；已有 DSpark
  失败证据后的隔离诊断例外见第 10 节；
- 吞吐、TTFT、acceptance length/rate 测量；
- compact verify、CUDA Graph、overlap schedule；
- 高并发、长上下文、block size 调优；
- TP/DP/PP/EP 组合探索；
- vLLM 对比；
- 正式 GSM8K 准确率评测；
- 生产化部署。

若首轮在 4×H20 上因不可压缩的显存下限失败，先提交可复查的峰值显存与失败证据，
再与用户讨论是否允许 offload、另一种 checkpoint 表示或扩大硬件范围；Agent 不自行
改变任务定义。

## 12. 沟通与提交

- 面向用户的进展和仓库文档默认使用中文，代码标识、路径、命令和产品名保留英文。
- 先报告结论和 blocker，再给证据与下一步。
- 长任务期间持续报告阶段、日志位置、worker/keepalive 状态和预计下一检查点。
- 不提交模型、virtualenv、package cache、worker scratch 或大型运行产物。
- 需求对齐阶段只允许用户单独授权的 operational keepalive；不得复制 checkpoint、
  安装正式环境或启动模型，也不得产生 MVP 成功结论。
- 根线程的主 Agent 负责阶段拆分、subagent 调度、纠偏、证据审查、阶段验收和面向
  用户的进展汇报。
- 实施按 `docs/plan/` 中的多阶段计划执行。每个阶段由主 Agent 派出的独立 subagent
  实施；phase executor 只能执行被分配的阶段，完成退出门禁和 handoff 后停止，不得
  自行进入下一阶段。
- 主 Agent 不替代 phase executor 实施阶段性工作；它可以维护 operational keepalive、
  修改协调文档、做只读复核，并在验收不通过时向原 subagent 追派修正或重新分配阶段。
- 用户已单独授权在 Phase 01 期间由另一 subagent 并行下载固定 Hugging Face revision：
  先下载到 worker NVMe 的唯一 `/tmp` scratch，完整校验后复制到唯一 HDFS staging。
  该下载只产生候选实体文件，不构成 Phase 02 PASS，不得发布或替换正式模型路径，也
  不得干扰 ModelScope source 的只读 manifest 校验。
- 每个阶段结束后，主 Agent 必须向用户提交结果汇总、是否符合预期的判断，以及是否
  具备进入下一阶段的条件。只有用户明确确认后，主 Agent 才能调度下一阶段。
- 扩大硬件范围、引入 offload、改变 checkpoint 表示或执行破坏性操作仍须另行确认。
- Git 提交由主 Agent 在关键节点统一执行，phase executor 不自行 commit。关键节点
  至少包括：治理与计划基线、每个阶段完成并经主 Agent 验收、具有复现价值的恢复
  结论，以及最终审计。
- 提交前只显式暂存当前节点相关的小型仓库文件，运行 `$git-commit-message` 规定的
  staged diff/status/recent log 流程，使用生成的 Conventional Commit message。不得
  提交模型、HDFS artifacts、virtualenv、package cache、worker scratch 或无关用户
  修改。
