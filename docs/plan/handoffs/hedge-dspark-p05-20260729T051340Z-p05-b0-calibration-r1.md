# HEDGE DSpark P05 handoff（追溯重建）

- Status: `PASS`
- Retrospective evidence reconstruction: `true`
- Contemporaneous standalone executor handoff: `not written`
- Reconstruction basis: immutable P05 artifacts、当时的
  `docs/experiment` / `docs/progress` 结论与已 push Git 节点；本文不是冒充当时
  executor 写下的 contemporaneous handoff
- Canonical attempts:
  `20260729T044309Z-p05-native-calibration-r4` /
  `20260729T051340Z-p05-b0-calibration-r1`
- Started / finished: P05 首个 live attempt 于
  `2026-07-29T02:01:44Z` 开始；阶段于 `2026-07-29T05:45:29Z`
  完成主 Agent验收
- Autonomy elapsed / deadline: 原自主窗口内完成；当时截止
  `2026-07-29T08:54:41Z`
- Git branch / worktree: `exp/hedge-v4-dspark` /
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
- Worker / GPU lane: `4106666` / exact 8×NVIDIA H20
- TP ranks / GPU participation: native r4 与 B0 r1 的 TP/target/draft ranks
  均为 0–7；两臂均有八张物理 GPU 的请求窗口参与证据
- Authorized phase: bounded `P05` only

## Outcome

P05 阶段结论为 `PASS`。生命周期修复后的唯一有效 native calibration r4
32/32 成功、0 retry、5183 completion tokens；strict-rejection trace 精确覆盖
32 个 response RID，得到 484 个正且有限的 barrier `regret/value`。唯一 B0 r1
同样 32/32 成功，逐样本完整 `output_token_ids` 与 native 32/32 相同。
计划定义的线性 q25 独立计算为 `2.0625`，因此冻结唯一正式配置
`g=B=2.0625,m=1,normalized_suffix,block_size=5`。

## Changes

- P05 tooling：`ce5d672`
- sampler stop-race recovery：`6b7145d`
- trace-scope recovery：`eb4962f`
- quiescence recovery：`fe0aea0`
- prefill terminal lifecycle recovery：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36`
- lifecycle wheel identity：
  `ada66253e719cd021cdec369914245b51ff46b61`
- native r4 result：`e58027e927cb4be5f9cc410a6df08fd19531a128`
- calibration/B0/config freeze：`c244651`

## Evidence and artifact paths

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T044309Z-p05-native-calibration-r4
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T051340Z-p05-b0-calibration-r1
artifacts/hedge-dspark/p05-calibration/b0_equivalence.json
artifacts/hedge-dspark/p05-calibration/calibration_values.jsonl
artifacts/hedge-dspark/p05-calibration/calibration_summary.json
artifacts/hedge-dspark/p05-calibration/hedge_config.json
```

- native outputs / trace SHA-256：
  `b5550312da76c86dc68f3b7f0685f4eb1009f7f778be8c24e1d400b382e78b23` /
  `8ffa9e45214c6a40520448c5d7dda098182e66134e809a92e20530fd9a5130f6`
- B0 outputs SHA-256：
  `d59b0e17483c1415dddd9ccee8ed41c22f26ab6fbfb47d4fd3a0d4f9fec3a434`
- B0：1097 proposals；strict/HEDGE accepted `4081/4081`；
  relaxed mismatch、regret、state leak、trace 均为 0。
- reducer：484 positive values，0 dropped；q25 `2.0625`；config fingerprint
  `6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921`。

## Source/config identity

- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- final integration：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36`
- patched tree：
  `69e80df97b815587a5b7b57665c99cd436b2ceb617dc71f31c7e44807ab82422`
- formal wheel：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`
- pure core：
  `4d96f44065c07030ede67484a262006ec149626a`
- checkpoint：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`

## Process, CUDA context and keepalive state

- native r4 登记 server/sampler `71408/71415` 定向停止，contexts none；
  keepalive 恢复为 `80819/80819/80819`，8×10 全卡 100%。
- B0 r1 登记 server/sampler `82443/82450` 定向停止，contexts none；
  keepalive 恢复为 `93521/93521/93521`，8×10 全卡 100%。
- native r4 请求窗口每卡 137 samples；B0 每卡 134 samples；两者均无
  CUDA/NCCL/worker crash。

## First root cause / progress since prior attempt

- native r1：`FAIL_TRACE_SCOPE`，启动 warmup 的额外 RID 会实质改变 q25。
- native r2：`FAIL_PRE_COHORT_QUIESCENCE`，在第一个 cohort 请求前退出，0/32。
- native r3：`FAIL_PREFILL_TERMINAL_LIFECYCLE`，把 leak 收敛到
  `/health max_new_tokens=1` 的 prefill-terminal finish hook 缺口，0/32。
- 最小 lifecycle 修复后 r4 一次通过；没有覆盖或拼接失败数据。

## Main-Agent acceptance recommendation

历史主 Agent已于 `2026-07-29T05:45:29Z` 验收 `PASS`。P08 从原始
JSONL/trace/counters 重跑 reducer，四个冻结 artifact 与 canonical 文件逐字节相同；
本文只修复 standalone handoff 缺口。

## Next eligible phase

历史下一阶段为 `P06`。本文在 P08 追溯重建后停止，不自行进入其他阶段。
