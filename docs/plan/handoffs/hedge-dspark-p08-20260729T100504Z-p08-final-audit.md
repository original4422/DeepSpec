# HEDGE DSpark P08 handoff

- Status: `PASS`; route `COMPLETE`; `MAIN_AGENT_ACCEPTED`
- Attempt ID: `20260729T100504Z-p08-final-audit`
- Started / finished: `2026-07-29T10:05:04Z` /
  `2026-07-29T10:27:19Z`
- Autonomy elapsed / deadline: user removed the original deadline at
  `2026-07-29T07:47:18Z`; current deadline `NONE`
- Git branch / input HEAD / worktree: `exp/hedge-v4-dspark` /
  `966823eb2c8f9fe26aa8039f30e4c210beea47a6` /
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
- Worker / GPU lane: assigned lane `4106666` / 8×NVIDIA H20；P08 did not
  log in or query the worker
- TP ranks / GPU participation: P08 没有模型运行；只读重放证明 P06/P07
  TP/target/draft ranks 0–7 与八张物理 GPU 参与证据均 `PASS`
- Authorized phase: bounded offline `P08` only
- Main-Agent acceptance: `PASS` at `2026-07-29T10:45:54.693Z`

## Outcome

P08 出口门禁全部通过，建议路线发布为 `COMPLETE`：

- 固定 dataset verifier 18/18 `PASS`；
- P05 reducer 从 immutable native r4/B0 r1 原始输入重放，四个冻结文件逐字节
  相同；B0 32/32 完整 token IDs 相同，线性 q25 再得 `2.0625`；
- P06/P07 client、timing、answer、acceptance、source/wheel/checkpoint/config
  identity、TP8/八卡、server、sampler、lifecycle、shutdown、contexts 与
  keepalive validator 全部 `PASS`；
- 两个正式 archive manifest 各 39/39 文件 size/SHA 独立重算匹配；
- 最终结果表只报告单次路线内观察值，没有自创阈值、跨方法绝对排名或
  formal-to-calibration 参数回调。

## Changes

P08 只新增/更新小型仓库 artifact 与文档：

```text
artifacts/hedge-dspark/p08-final/final_audit.json
artifacts/hedge-dspark/p08-final/final_results.json
artifacts/hedge-dspark/p08-final/artifact_manifest.json
artifacts/hedge-dspark/p08-final/reproduction.md
docs/results/hedge-deepseek-v4-flash-dspark.md
docs/results/hedge-deepseek-v4-flash-dspark-reproduction.md
docs/experiment/hedge-deepseek-v4-flash-dspark.md
docs/progress/hedge-deepseek-v4-flash-dspark.md
docs/plan/handoffs/hedge-dspark-p08-20260729T100504Z-p08-final-audit.md
```

另补齐三份历史阶段程序性缺口：

```text
docs/plan/handoffs/hedge-dspark-p04-20260729T010603Z-p04-b0-r1.md
docs/plan/handoffs/hedge-dspark-p05-20260729T051340Z-p05-b0-calibration-r1.md
docs/plan/handoffs/hedge-dspark-p06-20260729T062241Z-p06-native-formal-r1.md
```

它们均明确标记 `Retrospective evidence reconstruction: true` 与
`Contemporaneous standalone executor handoff: not written`，不冒充当时
executor 记录。P08 executor 没有 commit/push。

## Evidence and artifact paths

最终小型 artifact：

```text
artifacts/hedge-dspark/p08-final/final_results.json
artifacts/hedge-dspark/p08-final/final_audit.json
artifacts/hedge-dspark/p08-final/artifact_manifest.json
artifacts/hedge-dspark/p08-final/reproduction.md
```

关键 immutable 输入：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T044309Z-p05-native-calibration-r4
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T051340Z-p05-b0-calibration-r1
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T062241Z-p06-native-formal-r1
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T084544Z-p07-hedge-formal-r1
```

独立 reducer 临时输出：

```text
/tmp/deepspec-hedge-dspark-p08-recompute-20260729T1005Z
```

该目录不是 canonical artifact；HDFS raw 输入未改变。

## Source/config identity

- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- integration / patch / patched tree：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36` /
  `a4077b9f822c9c830511adf85a3480ed1f6f994ff416da20ce2391b769910c52` /
  `69e80df97b815587a5b7b57665c99cd436b2ceb617dc71f31c7e44807ab82422`
- pure core / fixed HEDGE source：
  `4d96f44065c07030ede67484a262006ec149626a` /
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- formal wheel / installed RECORD：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9` /
  `675b26b198e9ebc6b14d4961b3d9f70be4fc3a54e50319403704c29c5afa283f`
- checkpoint provider snapshot / HF reference：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae` /
  `62af8fffb2f7030cac4de2f0169f5b8d1101b646`
- formal config：`g=B=2.0625,m=1,normalized_suffix,block_size=5`；
  fingerprint
  `6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921`

## Process, CUDA context and keepalive state

P08 未登录 worker、未启动进程、未发 signal、未暂停/恢复 keepalive。最终状态
采用两份明确分层的证据：

1. P07 immutable archive：登记 server/sampler 已退出，contexts none；
   keepalive `121312/121312/121312`，8×10 每卡 mean/min/max 100%。
2. 主 Agent `2026-07-29T18:44:58.993+08:00` live read-only attestation：
   worker `4106666` 在线，同一 keepalive 健康，八卡 8×10 全 100%，每张卡
   只有该 keepalive context、815 MiB。

## First root cause / progress since prior attempt

P08 没有实验 blocker。审计发现的唯一程序性缺口是 P04/P05/P06 没有各自的
standalone handoff；它不影响 immutable phase evidence 或既有主验收。缺口已用
明确标记的 retrospective reconstruction 修复，并纳入最终 manifest。

历史失败 attempt 继续保留且不被覆盖：P00 environment/checker/bootstrap
失败、P03 superseded build、P04 wheel/cadence validator 恢复，以及 P05
`FAIL_TRACE_SCOPE`、`FAIL_PRE_COHORT_QUIESCENCE`、
`FAIL_PREFILL_TERMINAL_LIFECYCLE`。P06/P07 live 均一次通过。

## Main-Agent acceptance

主 Agent 已独立验收 `PASS` 并发布总体路线 `COMPLETE`：

1. dataset verifier 18/18、P05 reducer 四文件 byte replay 均通过；
2. P00/P02/P03 session、pure-core marker、core injection、patch、wheel、
   installed RECORD 与固定 SGLang base 身份链通过；
3. P04 recovered native/B0 replay 与 91/91 token IDs 等价通过；
4. P06/P07 read-only replay、两个 39/39 archive、1000 条 formal raw
   result 重算与所有路线内 delta 通过；
5. 153/153 回归、39 direct + 6 nested / 214-file manifest、JSON、
   Markdown links 与 `git diff --check` 均通过；
6. `2026-07-29T18:44:58.993+08:00` 最终 live status 继续证明 worker
   `4106666` 与 keepalive `121312` 健康。

## Next eligible phase

没有下一实验 phase；不得重启模型。只剩主 Agent最终 commit/push 仓库节点。
