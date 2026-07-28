# HEDGE × DeepSeek-V4-Flash × DFlash 实验记录

Status / outcome label: `IN_PROGRESS — D0/D1B/D1C ACCEPTED; D1A RUNNING`

Timebox: `2026-07-28T20:55:58Z` → `2026-07-29T08:55:58Z`；B0 未完成时的实现停止点为 `2026-07-29T05:55:58Z`

Worker / physical GPUs / TP: worker `4099543` / 8×NVIDIA H20 / TP=8

Target repo@revision / HDFS `.complete`: `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` / `WAIT`

Draft repo@revision / HDFS `.complete`: `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` / `NOT_STARTED`

SGLang base / final source SHA: `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` / `D1B clean base; D2 integration pending`

HEDGE pure-core SHA: `WAIT`

Dataset revision / seed / fingerprint: `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` / `980406` / HF `59ec1b7f9357c7a2`, content `32f83c6b…b41c4`

B0 PASS|FAIL|NOT_RUN: `NOT_RUN`

Frozen B/g/m: `NOT_CALIBRATED`

Native result: `NOT_RUN`

B+ result: `NOT_RUN`

Canonical or exploratory: `UNDETERMINED`

Primary blocker: Eagle target pointer 与 DSpark pure-core pointer 尚未发布；D1A primary draft 正常传输中，无 retry/error。

Artifact root: `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/`

Git commit: latest pushed progress `60d7e46`; D1B source/env/contract key node is this commit

下一步：保持本 lane keepalive，完成 D1A/D1B 验收后调度独立 D2 executor。

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
