# HEDGE × DeepSeek-V4-Flash × DFlash 实验记录

Status / outcome label: `IN_PROGRESS — D0 ACCEPTED`

Timebox: `2026-07-28T20:55:58Z` → `2026-07-29T08:55:58Z`；B0 未完成时的实现停止点为 `2026-07-29T05:55:58Z`

Worker / physical GPUs / TP: worker `4099543` / 8×NVIDIA H20 / TP=8

Target repo@revision / HDFS `.complete`: `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` / `WAIT`

Draft repo@revision / HDFS `.complete`: `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` / `NOT_STARTED`

SGLang base / final source SHA: `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` / `NOT_FROZEN`

HEDGE pure-core SHA: `WAIT`

Dataset revision / seed / fingerprint: `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` / `980406` / `NOT_PREPARED`

B0 PASS|FAIL|NOT_RUN: `NOT_RUN`

Frozen B/g/m: `NOT_CALIBRATED`

Native result: `NOT_RUN`

B+ result: `NOT_RUN`

Canonical or exploratory: `UNDETERMINED`

Primary blocker: Eagle target pointer 与 DSpark pure-core pointer 尚未发布；D0 本身无资源 blocker。

Artifact root: `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/`

Git commit: `D0 governance baseline — this commit; exact SHA will be recorded at the next progress checkpoint`

下一步：保持本 lane keepalive，并行调度 D1A/D1B/D1C。

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
