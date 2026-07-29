# DFlash Phase D5 early-stop handoff

## 结论

`D5 EARLY STOPPED BEFORE MODEL LAUNCH`。计划要求的 32 条 native calibration、
正值 first-rejection ratio、线性 q25、参数冻结和 32 条 `B0` 均未运行，故
`native calibration=NOT_RUN`、`B0=NOT_RUN`、`B/g=NOT_CALIBRATED`。不得把 D4-C
单条 short smoke 外推为 protocol-level B0，也不得把本阶段写成成功。

主 blocker 是 T+9 实现边界前的 preflight import stall：a01 已通过 worker/CUDA
view、固定输入和 SGLang source identity 核查，但 mlx PTY 没有从隔离的
`import sglang` 返回完整 stdout/rc。此时距 `2026-07-29T05:55:58Z` 已不足以完成
约 6 分 51 秒冷启动、32 条请求、定向清理和 HDFS seal。主 Agent 因此接受安全早停，
禁止继续 native/B0 模型 attempt。

## 已完成的 CPU tooling

- `scripts/dflash_d5_attempt.sh`
  - 独立 D5 attempt contract，不修改已冻结的 D4 launcher；
  - native 固定 `HEDGE_ENABLED=0`、
    `SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE=1` 且无 HEDGE config；
  - B0 只允许读取 sealed native calibration 的 q25 config；
  - 复用 D4 的 worker/source/checkpoint、owned PGID、sampler、cleanup、keepalive
    resume/gate 与 HDFS manifest lifecycle；
  - `2026-07-29T05:55:48Z` 绝对 server stop safety margin 在 pause 前、
    readiness 每轮和 API 前后检查，失败走完整参数的 cleanup trap。
- `scripts/dflash_d5_api.py`
  - 复用 D1C harness 的 32 条固定顺序、完整 response/output token IDs 与请求参数；
  - calibration 要求 trace dropped=0、正 ratio 全部 finite/positive，使用
    NumPy `quantile(values, 0.25, method="linear")`；
  - 保存 trace、ratio distribution、NumPy version、q25、canonical config JSON
    和 SHA-256；
  - `CALIBRATION_EMPTY` 明确不构成 PASS，也不能为 B0 发布配置；
  - lifecycle 允许 SGLang 内部 warmup/slot reuse，门禁为
    `initialized>=32`、`initialized=finished+slot_reuse_resets`、零 active/leak；
  - B0（本阶段未运行）逐样本比较 32 条完整 token IDs 并保存首个 divergence。
- `tests/hedge_dflash_integration/test_dflash_d5_tooling.py`
  - native contract、绝对 deadline/self-call arity、全部 heredoc AST、
    linear q25/config 和真实 slot-reuse lifecycle fixture。

最终 CPU gate：D5 4/4 与 D4-C regression 3/3，共 7/7 PASS；`bash -n`、
API `py_compile`、`git diff --check` PASS；冻结的
`scripts/dflash_d4_b0_attempt.sh` 与 HEAD 完全一致。

## a01 preflight 与零 GPU 副作用

- attempt ID：
  `dflash-d5-native-20260729T053735Z-a01`
- scratch：
  `/tmp/deepspec-hedge-dflash/runs/dflash-d5-native-20260729T053735Z-a01`
- scratch 仅有：
  `cuda_view_ensure.json`、`cuda_view_verify.json`
- 未到达：
  keepalive pause、CUDA-context-clear gate、server/sampler/API、HDFS publication
- SGLang identity：
  `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，parent
  `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`，worktree clean
- fresh final keepalive：
  PID/PGID/SID `123914`，worker `4099543`，8×H20 的 10×1 秒均值均为 100%，
  无 pause marker、无模型 server/context

mlx PTY 未保留 a01 wrapper 的原始 rc。后续只读 diagnose wrapper 没有创建 GPU
attempt、没有 pause/launch，按治理要求让其自然退出，未发送 signal。权威小型记录为
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d5/dflash_d5_preflight_blocker.json`。

## 交还主 Agent

主 Agent 应只读复核上述 tooling、a01 scratch/final keepalive 和
preflight blocker artifact；随后按早停策略提交/push 当前可复现状态并进入最终 D7
整理。不得派发 D6，也不得声称 canonical 或 exploratory `B+` 结果存在。
