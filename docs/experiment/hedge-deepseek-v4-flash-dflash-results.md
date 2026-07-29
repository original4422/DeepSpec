# DFlash × HEDGE 实验结果

> 这是一份面向结果阅读的摘要。开发过程、attempt 故障归因和恢复记录见
> [权威实验日志](./hedge-deepseek-v4-flash-dflash.md)；本页只展示参数来源、
> 协议结论和正式指标。任何尚未完成的项目都明确标为 `NOT_RUN` 或 `RUNNING`。

最后更新：`2026-07-29T12:34:16Z`

## 一句话结论

实验仍在进行中。32 条 native calibration 已完成并冻结
`q25=12.5`，因此正式 HEDGE 参数为
`B=12.5, g=12.5, m=1, value_scheme=normalized_suffix`。
32 条 protocol `B=0` 已与 native 达成 32/32 完整 output token-ID 一致，
结论为 `B0 PASS`。native 500 条正式 arm 已完成：500/500 success、0 retry、
74,802 completion tokens、9897.839411616 秒、E2E output TPS
`7.55740691369605`；HEDGE `B>0` 500 条尚未运行，因此路线内差值仍待 C4。

## 当前结果总览

| 项目 | 数据量 | 状态 | 结果 |
| --- | ---: | --- | --- |
| native calibration | 32 | `PASS` | 32/32 成功；`q25=12.5` |
| protocol `B=0` | 32 | `PASS` | 32/32 完整 output token IDs 相同 |
| native formal | 500 | `PASS` | 500/500 success；74,802 tokens；9897.839 s；7.5574 output tok/s；484/16/0 |
| HEDGE `B>0` formal | 500 | `NOT_RUN` | 尚无正式指标 |

## 固定实验身份

| 项目 | 固定值 |
| --- | --- |
| Hardware | worker `4099543`，8×NVIDIA H20，TP=8 |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` |
| Draft | `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483` |
| SGLang final SHA | `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1` |
| Dataset | `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866` |
| Split | seed `980406` 确定性 shuffle；前 32 条 calibration，随后不重叠 500 条 formal |
| Decode | 单请求顺序；temperature `0`，top_p `1`，max_tokens `512` |
| Proposal | DFlash model block `8`，即每个 proposal 最多 `7` 个 draft candidates |

## 参数怎样由 32 条 calibration 得到

对 32 条 calibration 运行 strict native DFlash。在每次 standard verification
的首个 strict-rejection barrier 记录：

```text
regret = max(target top logit - draft-token logit, 0)
value  = normalized_suffix_value
ratio  = regret / value
```

只保留正且有限的 `ratio`，再使用 NumPy `2.3.5`
的线性分位数 `quantile(values, 0.25, method="linear")`：

| 校准指标 | 数值 |
| --- | ---: |
| 请求成功 / 失败 / retry | 32 / 0 / 0 |
| completion tokens | 5016 |
| 答案 match / mismatch / parse failure | 31 / 1 / 0 |
| first-rejection trace rows | 4991 |
| dropped trace rows | 0 |
| 正且有限、可复算的 ratio | 4991 / 4991 |
| linear q25 | **12.5** |

由此一次性冻结：

| 用途 | B | g | m | value scheme | draft candidates |
| --- | ---: | ---: | ---: | --- | ---: |
| protocol `B=0` 核查 | 0 | 12.5 | 1 | `normalized_suffix` | 7 |
| HEDGE `B>0` 正式 arm | 12.5 | 12.5 | 1 | `normalized_suffix` | 7 |

正式 HEDGE config 的 canonical SHA-256 为
`ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746`。
`B=0` 派生 config 的 canonical SHA-256 为
`09fd47e2aca30c8ec558662f0f3e4ddbaea1894664219343248ca1fedc52b3ef`。
这些参数不会根据 500 条 formal 结果回调。

校准 artifact：

- [C1 acceptance](./artifacts/hedge-deepseek-v4-flash-dflash/continuation-c1/continuation_c1_acceptance.json)
- HDFS run：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d5-native-20260729T073139Z-a01`
- HDFS manifest：44/44 PASS；SHA-256
  `aedade1ec2bdabbc4d426f177d07d61deca8f370f3ec2eb401bba8ad39e4b3b2`

## Protocol B=0 结果

只有相同最终 source、模型、prompt 和 generation config 下的 32/32 完整 output
token IDs 全同，才能记为 `B0 PASS`。

| Native samples | B0 samples | 完整 token IDs 全同 | 首个差异样本 | 首个差异位置 | 状态 |
| ---: | ---: | --- | --- | --- | --- |
| 32 | 32 | `32/32` | — | — | `PASS` |

B0 arm 为 32/32 terminal success、0 failure、0 retry，逐行
`request_index/cohort_position/dataset_index/prompt` identity 与顺序均一致。
终态 snapshot 有 4991 个 proposals，strict 与 HEDGE accepted draft tokens 均为
0，relaxed mismatch、charged regret、active request state 和 state leak 均为 0；
因此首个最小反例为 `NOT_APPLICABLE`。

B0 artifact：

- [C2 acceptance](./artifacts/hedge-deepseek-v4-flash-dflash/continuation-c2/continuation_c2_acceptance.json)
- HDFS run：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d5-b0-20260729T083442Z-a01`
- HDFS manifest：47/47 PASS；SHA-256
  `321ab6047fe22795e1c4c1a697e1742ba556618fe7900de1ef4a7a6f820426d5`

## 正式 500 条结果

每个 arm 使用 fresh server，先运行固定 10 条 warmup（不计时），随后只进行一次
500 条顺序正式运行。计时从第 1 条 formal 请求发出到第 500 条达到终态；
HTTP、生成、排队与 retry 均计入。`E2E TPS = completion tokens / timed wall sec`。
accepted drafts 只统计 0–7 个 draft candidates，不含 bonus/current token。

| Arm | HEDGE | B / g / m | Samples | Success / Fail | Mean accepted drafts / proposal | Acceptance length / position stats | Completion tokens | Timed wall sec | E2E output TPS | Match / Mismatch / Parse fail | Retries | Result class |
| --- | --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| native | off | — | 500 | 500 / 0 | 0.0 | histogram `[74302,0,0,0,0,0,0,0]`；position 1–7 rates 全 0；含 current 的 mean length `1.0067292939624775` | 74802 | 9897.839411616 | 7.55740691369605 | 484 / 16 / 0 | 0 | `CANONICAL PASS` |
| HEDGE B+ | on | 12.5 / 12.5 / 1 | 500 | — | — | — | — | — | — | — | — | `NOT_RUN` |

native arm 共记录 74,302 个 proposal、520,114 个 proposed draft tokens；
accepted draft tokens 为 0，逐位置 accepted draft tokens 均为 0。TP0–7 均完成
初始化；八张 H20 在 formal 期间各有 14,405 个采样点、峰值利用率均为 99%，
最低模型显存为 92,905–93,145 MiB。日志在 owned shutdown 前未发现未处理的
CUDA、NCCL、Python traceback 或 worker crash。

native formal artifact：

- [C3 acceptance](./artifacts/hedge-deepseek-v4-flash-dflash/continuation-c3/continuation_c3_acceptance.json)
- HDFS run：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d6-native-20260729T093000Z-a01`
- HDFS manifest：46/46 PASS；SHA-256
  `a1c1a1e44ec66e21cb0ab5455aa42f011768c096bea25c81cf59c34b8b26eef4`
- cleanup/context-clear `PASS`；fresh keepalive PID/PGID/SID `239449`，
  8×10×1 秒 gate 最低逐卡均值 `40.0%`

## 路线内差值

| 指标 | Native | HEDGE B+ | B+ − Native | 相对变化 |
| --- | ---: | ---: | ---: | ---: |
| Mean accepted drafts / proposal | 0.0 | — | — | — |
| Completion tokens | 74802 | — | — | — |
| Timed wall sec | 9897.839411616 | — | — | — |
| E2E output TPS | 7.55740691369605 | — | — | — |
| Answer matches | 484 | — | — | — |
| Retries | 0 | — | — | — |

在两个 500 条 arm 都封存并通过可复算验收前，本表不填推测值，也不做跨路线绝对
TPS 排名。

## 结果解释边界

- calibration 的 32 条结果用于冻结参数，不是正式吞吐 benchmark。
- GSM8K match 数只展示，不是成功门槛。
- 不设置 TPS、接受长度或匹配率门槛。
- 如果 `B0 FAIL`，后续正式数字仍可运行和展示，但只能称为探索性结果。
- 所有正式数字都必须链接到包含完整响应、token IDs、逐请求计时、GPU samples、
  counters、manifest 和 cleanup 证据的 sealed artifact。
