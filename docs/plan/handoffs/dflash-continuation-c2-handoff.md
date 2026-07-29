# DFlash continuation C2 handoff

## 结论

`C2 PASS；PROTOCOL B0 PASS`。本阶段只完成 32 条 protocol `B=0` arm 以及与
C1 sealed native calibration 的完整 output token-ID comparison，没有进入 C3、
native formal 或任何 500 条运行，也没有 commit/push。live attempt 上限为 3；
a01 首次成功后立即停止，最终计数 `1/3`，a02/a03 均未启动。

唯一成功 attempt：

- ID：`dflash-d5-b0-20260729T083442Z-a01`
- HDFS：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d5-b0-20260729T083442Z-a01`
- manifest：47/47 PASS，SHA-256
  `321ab6047fe22795e1c4c1a697e1742ba556618fe7900de1ef4a7a6f820426d5`
- repo acceptance：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/continuation-c2/continuation_c2_acceptance.json`

## Tooling 修正与协议配置

RED 测试首先证明现有 D5 `b0` 路径错误地复用 C1 frozen positive-budget config：
contract 实际为 `B=12.5`，且 API 没有 `b0_config`。最小 GREEN 修正只改
`scripts/dflash_d5_api.py` 与相应 D5 tooling tests：

- 保留 frozen `g=12.5,m=1,value_scheme=normalized_suffix,block_size=7`；
- 仅把 protocol B0 的 `B` 派生为 `0`，不修改 C1 frozen B+ config；
- 32 行比较前锁定 `request_index/cohort_position/dataset_index/prompt`；
- 比较完整 output token IDs；若失败会保存两侧完整 IDs/text、prompt hash、
  首 divergence 与 HEDGE snapshot。

B0 canonical config：

```json
{"B":0,"block_size":7,"g":12.5,"m":1,"value_scheme":"normalized_suffix"}
```

SHA-256：
`09fd47e2aca30c8ec558662f0f3e4ddbaea1894664219343248ca1fedc52b3ef`。
C1 frozen B+ config SHA
`ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746`
保持不变。

静态门禁为 D5 + D4-C 共 11/11 PASS；`bash -n`、API `py_compile`、
embedded Python AST、contract 与 `git diff --check` PASS。另增加只读
`scripts/dflash_d5_progress.sh`，用于长请求期间安全统计完整 JSON 行、终态、
retry/error 与 fatal pattern，不修改 attempt 状态。

## Live 结果

preflight 真实 `rc=0`，keepalive pause 后八卡 context 于
`2026-07-29T08:44:52Z` 为 `none`；唯一 server PID/PGID/SID
`169134` 于 `08:44:52.896199Z` 启动，`08:51:43.591808Z` ready。
TP0–7 均初始化并加载 target/draft；每张 GPU 在请求阶段各有 1429 个 sampler
rows、峰值利用率均为 99%，ready 显存为 `92843–93083 MiB`。日志没有未处理
CUDA、NCCL、OOM、worker crash 或 traceback。

32 条固定 calibration 从 `08:51:46.222892Z` 到 `09:02:58.928041Z`
单请求顺序完成：

- 32/32 terminal success、request failure 0、retry 0；
- completion tokens 5016；
- match 31、mismatch 1、parse failure 0；
- 完整 response 与 output token IDs 已逐请求保存；
- wall time `672.705146071s`。这是 protocol B0 诊断，不是正式 benchmark。

逐样本 identity/order 为 32/32 相同，完整 output token IDs 为 32/32 相同，
所以 `B0 PASS`；首差异样本/位置均为 `null`，
`b0_minimal_counterexample.status=NOT_APPLICABLE`。

终态 HEDGE snapshot：

- config 为 `B=0,g=12.5,m=1,normalized_suffix,block_size=7`；
- proposals `4991`，verifiable draft tokens `34937`；
- strict/HEDGE accepted draft tokens 均为 `0`；
- relaxed mismatch `0`、charged regret `0`、budget exhaustion `0`；
- initialized `34`、finished `33`、slot reuse reset `1`；
- active request states `0`、state leaks `0`、request state `[]`。

## Cleanup 与交接门禁

server/sampler 只按登记 identity/PGID 定向关停；`09:03:32Z` 八卡模型 context
均为 `none`。fresh keepalive PID/PGID/SID `206956`，identity time
`09:04:08.414159Z`；resume 10×1 秒 gate 逐卡均值最低 `40.0%`，随后
`09:05Z` fresh observation 八卡均为 `100%`。端口 `31457` 空闲，八卡仅保留
每卡约 804 MiB 的 owned operational keepalive context。

主 Agent 下一步：

1. 只读复核 C2 acceptance、HDFS `.complete.json`、47/47 manifest、B0
   comparison/counters/lifecycle 与 fresh keepalive；
2. 只显式暂存 C2 相关小文件并按提交纪律 commit/push；
3. 验收通过后另派独立 C3 executor 运行 native formal 的固定 10 warmup + 500。

本 executor 到此停止，不进入 C3，不 add/commit/push。
