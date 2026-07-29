# HEDGE × DeepSeek-V4-Flash × DFlash 实验记录

Status / outcome label: `IN_PROGRESS — D0–D3 ACCEPTED; D4 AUTHORIZED`

Timebox: `2026-07-28T20:55:58Z` → `2026-07-29T08:55:58Z`；B0 未完成时的实现停止点为 `2026-07-29T05:55:58Z`

Worker / physical GPUs / TP: worker `4099543` / 8×NVIDIA H20 / TP=8

Target repo@revision / HDFS `.complete`: `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` / `READY — immutable completion pointer published by Eagle at 2026-07-28T23:04:53Z`

Draft repo@revision / HDFS `.complete`: `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` / `READY — primary .complete published at 2026-07-28T23:39:20Z`

SGLang base / final source SHA: `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` / native D3 `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`; HEDGE-final pending D4

HEDGE pure-core SHA: `4d96f44065c07030ede67484a262006ec149626a` (`READY`, verified; not yet cherry-picked)

Dataset revision / seed / fingerprint: `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` / `980406` / HF `59ec1b7f9357c7a2`, content `32f83c6b…b41c4`

B0 PASS|FAIL|NOT_RUN: `NOT_RUN`

Frozen B/g/m: `NOT_CALIBRATED`

Native result: `D3 SHORT SMOKE PASS`；正式 500 条 native arm 尚未运行

B+ result: `NOT_RUN`

Canonical or exploratory: `UNDETERMINED`

Primary blocker: `NONE FOR D4 ENTRY`；native TP8、target/draft、pure core、dataset 与 worker/keepalive 前置均已 READY。

Artifact root: `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/`

Git commit: latest pushed progress `c65a60a`; DeepSpec D3 recovery `6c929a8`; SGLang native D3 `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`

下一步：调度独立 D4 executor；验证 DSpark pure-core pointer，cherry-pick canonical core，并以可复现注入把同一 core 接入独立 SGLang source。

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
