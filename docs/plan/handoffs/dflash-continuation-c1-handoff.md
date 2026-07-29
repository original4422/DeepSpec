# DFlash continuation C1 handoff

## 结论

`C1 PASS；NATIVE CALIBRATION FROZEN`。本阶段只完成 32 条 strict native
calibration 与 q25/config freeze，没有进入 protocol B0/C2、没有启动 formal arm，
也没有 commit/push。live attempt 上限为 3；a01 首次成功后立即停止，最终计数
`1/3`，a02/a03 均未启动。

唯一成功 attempt：

- ID：`dflash-d5-native-20260729T073139Z-a01`
- HDFS：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d5-native-20260729T073139Z-a01`
- manifest：44/44 PASS，SHA-256
  `aedade1ec2bdabbc4d426f177d07d61deca8f370f3ec2eb401bba8ad39e4b3b2`
- repo acceptance：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/continuation-c1/continuation_c1_acceptance.json`

## Tooling 与冻结身份

`scripts/dflash_d5_attempt.sh` 的旧 hard-coded deadline 已改为必填的第五个 CLI
参数，严格要求可解析的 canonical `YYYY-MM-DDTHH:MM:SSZ`，并以 readonly epoch
贯穿 contract、preflight/resolved metadata、readiness、API、sampler self-call、
trap、cleanup 和 seal。C1 使用 immutable
`2026-07-29T16:31:29Z`。没有改变 SGLang/source、checkpoint、TP8、port、
block8/7、backend 或 decode 配置。

静态门禁：

- D5 tooling 5/5 PASS；
- D4-C regression 3/3 PASS；
- `bash -n`、全部 heredoc AST、API `py_compile`、contract、
  `git diff --check` PASS；
- 旧 `scripts/dflash_d4_b0_attempt.sh` 与
  `scripts/dflash_d4_b0_api.py` 相对 HEAD 无差异。

固定身份：

- worker `4099543` / `g340-cd51-4b00-4d69-9088-7ae6-6253` / 8×H20 / TP8；
- SGLang HEAD
  `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，tree
  `53fc45b1b04963736254dc7ed582047313b8075a`；
- target
  `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`；
- draft
  `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483`；
- dataset
  `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` /
  seed `980406` / fingerprint `59ec1b7f9357c7a2`。

## Live 结果与 q25

remote preflight 及唯一只读复核均真实 `rc=0`。owned keepalive 于
`2026-07-29T07:59:59Z` 暂停后八卡 CUDA context 为 `none`；唯一 server
PID/PGID/SID `129077` 于 `08:00:00Z` 启动，`08:06:50Z` ready。TP0–7 均初始化
并加载 target/draft；请求期间每张 GPU 各有 1431 个 sampler rows，峰值利用率均为
98%，日志无未处理 CUDA/NCCL/OOM/worker crash/traceback。

32 条固定 calibration 单请求顺序运行结果：

- 32/32 terminal success，request failure 0，retry 0；
- completion tokens 5016；
- match 31、mismatch 1、parse failure 0；
- 完整 response 与 output token IDs 已逐请求保存；
- wall time `669.157606774s`，从 `08:06:53.424803Z` 到
  `08:18:02.582412Z`。

first strict-rejection positive ratio：

- `trace_rows_seen=4991`、`trace_rows_dropped=0`；
- 4991 条全部 finite、positive，且 `regret/value` 可复算；
- NumPy `2.3.5`，`quantile(values,0.25,method="linear")`；
- `q25=12.5`。

唯一冻结配置：

```json
{"B":12.5,"block_size":7,"g":12.5,"m":1,"value_scheme":"normalized_suffix"}
```

config SHA-256：
`ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746`。

lifecycle 终态：

- initialized `34`；
- finished `33` + slot reuse reset `1` = initialized `34`；
- active request states `0`、state leaks `0`。

## Cleanup 与交接门禁

server/sampler 只按登记 identity/PGID 定向关停，`08:18:44Z` 八卡模型 context
均为 `none`。fresh keepalive PID/PGID/SID `166546`，identity time
`08:19:21.637673Z`；8×10×1 秒均值为 `50.0–50.1%`，全部高于 40% 门槛。
HDFS `.complete.json`、summary、API、counters 与 cleanup 均为 PASS。

主 Agent 下一步：

1. 只读复核 C1 acceptance、HDFS `.complete.json`、44/44 manifest、q25/config
   复算与 fresh keepalive；
2. 只显式暂存 C1 相关小文件并按提交纪律 commit/push；
3. 验收通过后另派独立 C2 executor 运行 32 条 protocol B0。

本 executor 到此停止，不进入 B0/C2，不 add/commit/push。
