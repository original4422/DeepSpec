# HEDGE × DeepSeek-V4-Flash × DFlash 实验记录

Status / outcome label: `BEST_EFFORT_BLOCKED_IMPLEMENTATION`
（具体 outcome：`BEST_EFFORT_EARLY_STOP_INCOMPLETE`；D7 evidence/cleanup audit：
`PASS`）

Timebox: `2026-07-28T20:55:58Z` → `2026-07-29T08:55:58Z`；B0 未完成时的实现停止点为 `2026-07-29T05:55:58Z`

Worker / physical GPUs / TP: worker `4099543` / 8×NVIDIA H20 / TP=8；D7 最终
owned keepalive PID/PGID/SID `123914`，八卡 fresh 10×1 秒均值全部 100%，无
owned model context

Target repo@revision / HDFS completion marker:
`deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` /
`READY — target-deepseek-v4-flash-60d8d70770c6776ff598c94bb586a859a38244f1.complete.json`,
immutable and published by Eagle at `2026-07-28T23:04:53Z`

Draft repo@revision / HDFS `.complete`: `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` / `READY — primary .complete published at 2026-07-28T23:39:20Z`

SGLang base / final source SHA: `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` / HEDGE-final `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`（parent/native D3 `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`）

HEDGE pure-core SHA: upstream `4d96f44065c07030ede67484a262006ec149626a` / DFlash canonical `86231e536573ccc43cda732b4eca920d5ce0a28a`（`READY`，exact hashes verified and injected）

Dataset revision / seed / fingerprint: `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` / `980406` / HF `59ec1b7f9357c7a2`, content `32f83c6b…b41c4`

B0 PASS|FAIL|NOT_RUN: `NOT_RUN`（D4-C 单条 short prompt 的 live `B=0` infrastructure smoke `PASS`；计划要求的 32 条 calibration `B=0` arm 未运行）

Frozen B/g/m: `NOT_CALIBRATED`（D4-C smoke 仅使用 `B=0,g=1000000,m=1`，不是自动校准结果）

Native result: `D3 SHORT SMOKE PASS`；D5 native calibration 与正式 500 条 native arm 均未运行

B+ result: `NOT_RUN`

Canonical or exploratory: `NO D5/D6 RESULT`

Primary blocker: `D5 PREFLIGHT PASS NOT SURFACED TO ORCHESTRATOR + T+9 WINDOW
INSUFFICIENT`；a01 的 `preflight.json` 于 `05:40:13Z` 写出 PASS，但 mlx PTY
wrapper 没有向主 Agent 返回可恢复的 rc/stdout；剩余窗口不足以安全完成冷启动、
32 请求、cleanup 和 seal，因此在 keepalive pause/model launch 前 early-stop。

Artifact root: `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/`

Formal artifact: `NONE`；D4-C short-smoke HDFS run
`/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d4-b0-20260729T045317Z-a01`；
D7 final audit
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/final_audit.json`

Git commit: D7 final audit `711747ad2e80d69de38fa93c10a42e78569413c0`；
D7 main acceptance `324684bc55d6255b4d87dbea845d9e50f8f21a57`；06:12 progress
checkpoint `fc71d0c`；D5 tooling/blocker `af6e4a6`；D4
source/evidence `a80031a`；D4-C live evidence `a18655a`；DeepSpec canonical core
`86231e536573ccc43cda732b4eca920d5ce0a28a`；SGLang HEDGE-final
`9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`

下一步：本 timebox 不进入 D6；保持 worker `4099543` owned keepalive。任何未来
续跑都需要新的授权窗口，并从 native calibration 开始；不得声称本次存在
q25/protocol B0/B+ 或 formal 结果。

## 快速结果

### 协议状态

| 项目 | 状态 | 证据/解释 |
| --- | --- | --- |
| D4-C one-prompt live `B=0` | `INFRASTRUCTURE PASS` | output token IDs `[22,1]` 与 D3 一致；39/39 HDFS manifest PASS；不是 GSM8K calibration |
| native calibration 32 | `NOT_RUN` | D5 仅完成 preflight metadata，`requests.jsonl` 为 0 bytes / 0 rows |
| positive ratio / q25 | `NOT_RUN` / `NOT_CALIBRATED` | 无 native trace，不能生成 q25 |
| protocol B0 32 | `NOT_RUN` | 没有 32 条完整 output token-ID comparison；不是 FAIL |
| native formal 500 | `NOT_RUN` | D6 未启动 |
| HEDGE B+ formal 500 | `NOT_RUN` | D6 未启动 |
| formal result class | `NONE` | 没有 canonical 或 exploratory formal result |

### 正式结果表

| Arm | HEDGE | B | g | m | Source SHA | Samples | Success/Fail | Mean accepted drafts (0–7) | Completion tokens | Timed sec | E2E TPS | Match/Mismatch/Parse fail | Retries | Result class |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| native | off | — | — | — | `9a01e2d` | 0/500 | `NOT_RUN` | — | — | — | — | — | — | `NONE` |
| B+ | on | — | — | — | `9a01e2d` | 0/500 | `NOT_RUN` | — | — | — | — | — | — | `NONE` |

### `B0` 表

| Native samples | B0 samples | Full token-ID identical | First divergent sample | First divergent token | Evidence |
| ---: | ---: | --- | --- | --- | --- |
| 0/32 | 0/32 | `NOT_RUN` | — | — | D5 final scratch：preflight-only，0 requests |

### 最终 attempt 摘要

| Time | Phase | Attempt | Single changed variable | Outcome/root-cause fingerprint | New evidence | Next strategy |
| --- | --- | --- | --- | --- | --- | --- |
| 03:33Z | D3 | `dflash-d3-native-20260729T033321Z-a05` | TP loader source fix only | short native smoke PASS | TP0–7 target/draft、API 200、7 proposals | D4 HEDGE integration |
| 04:53Z | D4-C | `dflash-d4-b0-20260729T045317Z-a01` | HEDGE enabled with `B=0` | one-prompt infrastructure PASS | token IDs exact、zero relaxation/leak、39/39 manifest | D5 protocol calibration |
| 05:37Z | D5 | `dflash-d5-native-20260729T053735Z-a01` | native calibration preflight | preflight PASS 未及时 surfaced；模型未启动 | 14 个 preflight-only 文件、0 requests、zero GPU side effect | T+9 early-stop，转 D7 |
| — | D6 | `NONE` | — | `NOT_RUN` | 无 formal artifact | 不在本 timebox 启动 |

## D0 会话与资源基线

DFlash lane 从 `cac6c78d88df97d395406fe831f573df3016e7f7` 建立独立
`exp/hedge-v4-dflash` branch 与 worktree。主 DSpark worktree 的既有未提交修改未被
触碰或混入。

两次启动前只读 inventory 均未发现 legacy CUDA compute process，因此无需等待或发送
任何 signal。8 卡 operational keepalive 在独立 `/tmp` state 与 uv-created runtime
中启动，PID/PGID 为 `34059`，10×1 秒逐卡均值均为 100%。该负载不属于模型实验结果。

Eagle target 与 DSpark pure-core canonical coordination pointer 当前均不存在，只读
状态为 `WAIT`；D0 未写 coordination root。

主 Agent 已直接复核 D0 的 6 份 JSON、80 行逐卡采样、脚本语法、跨 artifact identity、
远端实时 keepalive 状态和原 DSpark worktree 状态；D0 退出门禁验收通过。

## D1A primary draft 获取与发布

固定 primary
`RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483`
已从 Hugging Face 下载到 worker NVMe，完成 provider identity/OID、6 文件
`3,607,606,957` bytes、config、62-tensor safetensors header/shape 与 payload
offset 核查后，独立复制到 HDFS staging 并原子发布。正式 `.complete` SHA-256 为
`f26d58995a8f9ff3e387fb6e940e13521bc4ad82455bd51f548faa610e94338b`，lane pointer
SHA-256 为 `d2b439945df143bff0873705b7f1aac37bf35e47b098eaaf3e1a6a408c2e1add`。

首次 weight pass 接近 `3.40 GB` 时，同一
`curl --retry --retry-all-errors --continue-at -` 进程从 invocation offset 重新开始。
PID/inode、`/proc` I/O 与 byte trajectory 将根因固定为
`curl-internal-retry-restarts-from-invocation-offset-zero`。未发送 signal、未切换
checkpoint；同一进程的第二 pass 自然完成，fallback 始终关闭。

主 Agent 独立复核 pointer/marker/formal file set、header、config、NVMe↔HDFS
独立实体、small-file hash、原子 staging 消失与 21 份 repo/HDFS evidence 镜像；
signed-URL 重扫无命中，7 个 Python AST、8 个 shell、19 个 JSON 和 2 个 JSONL
语法/解析门禁均 PASS。keepalive PID/PGID/SID `34059` 全程未停，最终八卡
10×1 秒均值均为 100%。权威 handoff 为
`docs/plan/handoffs/dflash-phase-d1a-handoff.md`，主验收记录为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1a/dflash_d1a_main_acceptance.json`。

Eagle 共享 target 也已由主 Agent 只读验收：固定 revision、provider commit/OID、
manifest SHA、73 files / `159,630,041,626` bytes、官方 46-shard index referents、
config/tokenizer、零 symlink/hardlink 及 immutable atomic publication 全部一致。

## D1C 数据与请求 harness

固定 GSM8K test split 经 seed `980406` 一次 shuffle，形成 32 条 calibration 与其后
不重叠的 500 条 formal；前 10 条 calibration 固定为每个正式 arm 的 warmup。DFlash
保存的 shared manifest 与 DSpark `77053dd3ea84bb1c8dde7971f5f12759c1375e1f`
byte-identical，SHA-256 为 `34db2fc76099b2725f51dfd6ceeb1410802ad54c9008b2ab3cc1b8927f02be90`。

顺序 harness 固定单条 user message、非思考、temperature 0、top_p 1、max_tokens 512，
保存 prompt/output token IDs、完整响应、usage、latency、retry、终态与答案解析。
正式请求不启用 `logprobs`；canonical output token IDs 严格来自
`choices[0].meta_info.output_token_ids`，避免给正式 TPS 引入计划外开销。主 Agent
复跑 13 个 mock tests，并复算 9 个 artifact hash、32/500 indices 与无重叠，均 PASS。

## D1B 固定 source、正式环境与 DFlash contract

独立 SGLang checkout 固定在 `v0.5.16` /
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 且 clean；formal uv env 为
`/home/tiger/venvs/deepspec-hedge-dflash`。实测 Python `3.11.2`、PyTorch
`2.11.0+cu130`、CUDA/nvcc `13.0`、NCCL `2.28.9`、FlashInfer `0.6.14`、
Triton `3.6.0`、sglang-kernel `0.4.5+cu130`，`uv pip check` 验证 201 个包兼容。

固定 primary config/header 与 5 个 CPU-only contract tests 证明：

- aux 层顺序为 `[3,13,23,32,42]`，DeepSeek-V4 after-layer seam 使用原 ID、不加一；
- 每层 mHC 必须由 `[N,4,4096]` 经 `flatten(1)` 得到 `[N,16384]`，五层 concat
  为 `[N,81920]`，与 `fc.weight=[4096,81920]` 一致；
- `completed.mean(dim=1)` 只会形成 `[N,20480]`，被 contract test 明确拒绝；
- block size 8 中第 0 列是 current token，HEDGE proposal 固定为
  `candidates[:,1:]` 的 7 个 draft token。

因此 D2 的最小 production 范围已锁定为 config normalization、DeepSeek after-layer
DFlash capture hook 与 81920-wide projection/loader；D1B 没有修改 SGLang。

## D2 native DFlash 接入

固定 SGLang base 上的 native 接入已由独立 executor 完成，并由主 Agent 直接复验后
固化为本 lane 的 SGLang commit
`7245c3d607a1eadc26582bb78ebd603a70c22fa7`，其唯一 parent 是固定 base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`。该 commit 没有 push 到共享
SGLang origin；完整可复现 patch 和文件 hash 保存在 D2 artifact。

接入范围包括 nested Speculators config normalization、DeepSeek-V4 after-layer mHC
flatten capture、`fc.weight=[4096,81920]` 与 checkpoint 自带
embedding/LM head/`t2d`/`d2t` loader、block 8 中七个 draft-vocab token 到 target
token space 的映射，以及请求显式开启 `return_meta_info` 时的
`choices[0].meta_info.output_token_ids`。

executor 与主 Agent 分别复跑相同 CPU/meta 门禁，均得到 `186 PASS / 1 CUDA-only
SKIP`；artifact manifest、逐文件 hash、JSON、patch reverse-apply 和零 HEDGE source
scan 均 PASS。主 Agent staged 审核曾发现新增 config 文件 EOF 多一行空白；原 executor
只删除该空白、重生成证据并重跑全套测试后，`git diff --cached --check` 通过。D2
没有启动 GPU、大模型或 HEDGE，也没有暂停 keepalive。权威 handoff 为
`docs/plan/handoffs/dflash-phase-d2-handoff.md`，主验收记录为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d2/dflash_d2_main_acceptance.json`。

## D3 native DFlash 启动与短 smoke

D3 用单变量链条保留了四个可审计节点。a02 暴露并修复 DeepSeek-V4 DFLASH allowlist；
a03 在八 rank target/backend 初始化后暴露 FlashInfer `fused_moe_90` 缺少
`-lcudart/-lnvrtc` 的 CUDA 13 link layout。lane-scoped CUDA view 与独立
`FLASHINFER_WORKSPACE_BASE` 随后完成 183/183 构建，并证明共享
`~/.cache/flashinfer` 未被写入。

a04 越过 JIT 后，在八个 rank 的 draft load 同时复现 global checkpoint
`down_proj=(4096,2048)` 被 local TP shard `(4096,256)` 前置等形检查拒绝。真实
`RowParallelLinear.weight_loader` 的 TP=8 RED/GREEN fixture 固定根因；source
`1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5` 只让 custom TP loader 先执行分片，
并保留 replicated 参数和 buffer 的严格形状检查。主 Agent 独立复跑 primary
10/10 与 overlap 6 PASS/1 CUDA-only skip。

唯一 source-only a05 完成八 rank target 与 draft load、DFLASH block 8、5 层 fused KV、
HTTP 200 chat API 和 7 个 draft proposal。ready 后八卡显存为 `92949–93189 MiB`；
API 返回后的即时逐卡利用率为 `[62,67,38,30,42,53,7,62]%`。0.395 秒请求短于
一秒 sampler 周期，因此没有 `phase=request` 行；该限制已在 handoff 置明，没有补跑。

a05 HDFS manifest
`cf92016603857ba58ee7f067c74ab0eb6e42d01777d93c40bc89cc86c9a0b558`
由 executor 与主 Agent分别验证 38/38。cleanup 后 contexts clear，keepalive
fresh readback PID `110847`、八卡 10×1 秒均值均为 100%。D3 权威 handoff 为
`docs/plan/handoffs/dflash-phase-d3-handoff.md`，主验收记录为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d3/dflash_d3_main_acceptance.json`。

## D4 HEDGE source freeze 与 D4-C short live `B=0`

上游 pure core
`4d96f44065c07030ede67484a262006ec149626a` 已 exact cherry-pick 为 DFlash
canonical commit `86231e536573ccc43cda732b4eca920d5ce0a28a`。10 个 tracked
core/test 文件逐一 hash 一致，canonical 33/33 tests PASS；同一 canonical core 的
5 个 package 文件通过可复现脚本注入独立 SGLang checkout，injected content hash
为 `2c868811…c732c348`。

DFlash integration 把 HEDGE 接在 target logits adjustments 后的 greedy verify
seam；native config-off 仍走原 Triton/eager verifier。DFlash model block 保持 `8`，
proposal width 固定 `7`。per-request budget 和累计 relaxed mismatch 常驻 device，
rid/slot reorder、prefill bind、natural finish、abort 和真实 slot reuse 均有 fixture；
calibration 首个正 strict-rejection barrier、acceptance/lifecycle counters 也只在显式
snapshot 时批量转 CPU。active mode 对 non-greedy fail closed。

主 Agent 已把最终 SGLang source 固化为
`9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，tree
`53fc45b1b04963736254dc7ed582047313b8075a`。reproducible unified-zero
integration patch SHA-256 为 `1788696e…226024`；从 parent
`1ac1f382…2c5` 注入 core 并以 `git apply --unidiff-zero` 应用 patch 得到的
tree 与 final tree 完全一致。patch artifact 自身的隔离
`git diff --cached --check` PASS。post-commit CPU validation 为 canonical
33/33、integration 9/9、DFlash primary 10/10、overlap 6 PASS/1 CUDA-only skip、
D4-C tooling 3/3、source-capture tooling 1/1，且 source/injection/syntax 门禁
全部 PASS。

unified-zero serialization 是一次 artifact-only correction：首版 contextful patch
中的 5 个单空格 context marker 在 patch 文件自身 staged 时触发 trailing-whitespace
gate；它们不是 source 新增空格。correction 不改 SGLang commit/tree 或
integration/core content hash，也不通过字符串替换吞掉其他尾随空格。

D4-C 独立 short live `B=0` launcher 与 API auditor 锁定 worker `4099543`、
port `31457`、TP=8、block 8/proposal 7、final source、原 checkpoint/CUDA/JIT
contract，以及
`B=0,g=1000000,m=1,value_scheme=normalized_suffix,block_size=7`。请求复用 sealed
D3 a05 的 short prompt，完整 output token IDs 必须等于 `[22,1]`；终态
`/get_server_info` 还必须证明 strict/HEDGE accepted 相等、零 relaxation/regret、
request lifecycle 清空。D4 sampler 已改为本 launcher 自调用并由静态测试禁止引用
D3 attempt sampler。

唯一 live attempt `dflash-d4-b0-20260729T045317Z-a01` 已在同一 ID 内完成。首次
orchestration wrapper 的返回码不可恢复，但其真实 preflight body 于
`2026-07-29T04:56:25Z` 为 PASS；恢复审计证明此前没有 keepalive pause、server、
sampler 或 HDFS side effect，因此在主 Agent 明确授权后继续同一 attempt，而没有
制造第二个模型 attempt。服务于 `05:03:52Z` 启动、`05:10:43Z` ready：
TP rank 0–7 均初始化并加载 target 与 draft，八卡 ready 显存为
`92843–93083 MiB`，日志确认 DFlash block 8/proposal 7 和 HEDGE enabled。

short API 在 `0.377162s` 内 HTTP 200，返回 content `4`、completion tokens `2`、
output token IDs `[22,1]`，与 sealed D3 a05 精确一致。8 个 proposals 对应 56 个
可验证 draft tokens；strict/HEDGE accepted 均为 `0`，relaxed mismatch 与 charged
regret 均为 `0`，accept-length histogram 为 `[8,0,0,0,0,0,0,0]`。终态
active request states 与 state leaks 均为 `0`，真实 slot reuse 计数为 `1` 且旧状态
已清除。

请求短于 sampler 的前一秒 lifecycle polling interval，因此
`gpu_samples.csv` 没有 `phase=request` 行；这不是采样缺失的隐瞒。HTTP response 后
紧邻快照的八卡利用率为 `[65,58,49,4,49,31,65,67]%`，并结合 TP0–7 load、八卡约
93 GiB 显存证明参与。日志无 Traceback、CUDA/NCCL error、OOM、scheduler exception
或被杀；cleanup 中的 SIGTERM、detokenizer `-15` 与 SIGQUIT 按已登记顺序发生，属于
定向正常关停，不是未处理 worker crash。

cleanup 于 `05:11:58Z` PASS，CUDA contexts clear；恢复 gate 八卡 10×1 秒均值为
`60.0–61.3%`，随后 fresh observation 的 keepalive PID `123914` 八卡均值均为
100%。HDFS `.complete.json` 为 PASS，39/39 manifest hash 一致，manifest SHA-256
为 `eae4f4b21dd89c55a39133ecd5acd29f3ad356e5587304887bbd9732cdee43d6`。
权威 repo audit 为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4c_success_audit.json`，
handoff 为 `docs/plan/handoffs/dflash-phase-d4b-handoff.md`。

该结果只证明单条 short prompt 的 live `B=0` 基础设施与 strict-equivalence 链路，
不是计划定义的 32 条 calibration arm。因此顶部继续标记
`B0 PASS|FAIL|NOT_RUN = NOT_RUN`；D5 才负责形成 protocol-level B0 结论与自动校准。

## D5 preflight 与 T+9 best-effort early stop

D5 executor 完成了独立 launcher/API/tooling：native calibration contract 固定
`HEDGE_ENABLED=0`、trace 开启且不加载 config；D1C harness 固定 32 条顺序请求与
完整 output token IDs。trace 分析只接受 dropped=0 的 finite positive
first-rejection `regret/value`，并固定 NumPy 2.3.5 的
`quantile(values,0.25,method="linear")`，由 q25 一次性生成
`B=g=q25,m=1,value_scheme=normalized_suffix,block_size=7` 与 config SHA-256。
空分布明确是 `CALIBRATION_EMPTY`/非 PASS。B0 tooling 会读取 sealed native config
并比较 32 条完整 token IDs，但本会话没有启动 B0。

CPU gate 为 D5 4/4、D4-C regression 3/3，合计 7/7 PASS；shell syntax、API
`py_compile`、全部 embedded Python AST 与 `git diff --check` PASS。已冻结的 D4
launcher 在 D5 开发后仍与 HEAD 完全相同。

唯一 D5 preflight ID 为
`dflash-d5-native-20260729T053735Z-a01`。执行时 mlx PTY 没有向 orchestrator 返回
隔离 `import sglang` 之后的完整 stdout/rc；主线程基于当时可见的陈旧 inventory
记录了两个 CUDA-view 文件。D7 最终逐文件审计纠正了这项 inventory：
`preflight.json` 实际于 `05:40:13.212797Z` 写出 `PASS`，最终 scratch 有 14 个
preflight-only 小文件，mtime 均不晚于 `05:40:13.581845Z`。

这项纠正不改变 GPU/实验结论：`requests.jsonl` 是 0 bytes / 0 rows，
`hedge_counters.status=NOT_RUN`，没有 keepalive pause、server/sampler/startup/smoke
artifact、API 或 HDFS publication。正确 blocker 是
`PREFLIGHT_PASS_NOT_SURFACED_TO_ORCHESTRATOR`，不是 calibration 成功，也不是模型
attempt 成功或失败。

此时距 DFlash 在无完整 B0 时的 T+9 实现停止点已不足以完成实测约 6 分 51 秒冷启动、
32 请求、定向 cleanup 与 seal。主 Agent 接受安全判断并在模型启动前 early-stop；
没有启动第二个 model attempt，后续只读 PTY diagnostic 自然退出、未发送 signal。
`2026-07-29T05:42:45Z` operational audit 证明 keepalive
PID/PGID/SID `123914` 仍在运行，8 卡 10×1 秒均值全部 100%，无 pause marker、模型
server 或模型 CUDA context。

因此 D5 的准确结论是：native calibration `NOT_RUN`、ratio/q25/config
`NOT_CALIBRATED`、protocol B0 `NOT_RUN`。不进入 D6，不产生 canonical/exploratory
B+ 指标。权威 blocker artifact 与 handoff 分别为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d5/dflash_d5_preflight_blocker.json`
和 `docs/plan/handoffs/dflash-phase-d5-handoff.md`。前者的
`preflight.result=BLOCKED_BEFORE_PASS` 与两文件 inventory 已被 D7 标为
`SUPERSEDED_IN_PART_BY_D7_AUDIT`；其 zero-GPU、NOT_RUN 与 early-stop 结论仍有效。

## D7 最终审计与收尾

D7 在不启动模型、不发送 signal 的前提下完成 source/checkpoint/dataset/Git/HDFS
与 worker 终态审计。DeepSpec D7 起点 HEAD 与 origin 均为 `af6e4a6`，
ahead/behind `0/0`；SGLang final
`9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`、tree
`53fc45b1b04963736254dc7ed582047313b8075a`、parent `1ac1f382…2c5` 与 fixed
base ancestry 全部一致，checkout clean。

target marker、73-file manifest、46 shards 与 `159,630,041,626` bytes 一致；
primary draft pointer/`.complete`、6 files 与 `3,607,606,957` bytes 一致。D4-C
实际 completion marker 名为 `.complete.json`，marker 外另有 39 条 manifest
records；D7 重算 39/39 PASS，manifest SHA-256
`eae4f4b21dd89c55a39133ecd5acd29f3ad356e5587304887bbd9732cdee43d6`。
HDFS run inventory 只有 D3 a02–a05 和 D4-C a01，没有 D5、D6 或 formal run。

最终 CPU 复验为 canonical core 33/33、integration 9/9、D4-C tooling 3/3、
D4 source capture 1/1、D5 tooling 4/4、DFlash primary 10/10、overlap
6 PASS/1 CUDA-only skip；合计 67 cases、66 PASS、1 skip、0 FAIL。core injection
逐文件 hash 和 `--check` PASS。inject CLI 的 aggregate
`7a82564b…e22f208c` 与 capture 的 `2c868811…ac732c348` 使用不同序列化算法，
不能直接比较；逐文件 byte identity 才是门禁，两者不存在 identity 冲突。

worker `4099543` 的 final remote audit 证明 owned keepalive PID/PGID/SID
`123914`、argv、hostname、CVD 和八个 GPU UUID 均匹配；fresh 8×10×1 秒均值全部
100%，无 pause marker，端口 `31457` 空闲，无 owned model process。八卡只存在每
UUID 一个约 804 MiB 的 operational keepalive context；D7 没有模型 launch 或 signal。

D7 evidence 为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/final_audit.json`，
manifest 为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/artifact_manifest.sha256`，
三条记录全部 PASS，manifest 自身 SHA-256
`2ca891756d410971cee655b314987cfd9a6368012a14c545437ec8d606e5aef3`；
复现命令为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/reproduction_commands.txt`。

最终限制保持明确：D4-C 只证明 one-prompt infrastructure path；没有 native
calibration trace、ratio/q25、protocol B0、native formal 或 B+ formal。故 D7
`audit_status=PASS` 只表示证据一致与 operational cleanup 健康，不能提升实验结果；
最终 `formal_result=NONE`。
