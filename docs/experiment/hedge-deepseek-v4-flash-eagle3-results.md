# HEDGE on DeepSeek-V4-Flash Eagle3 结果报告

> **状态：`IN_PROGRESS`，更新时间 `2026-07-29T08:29Z`。**
> Native 500 条正式结果已经验收；HEDGE B+ 500 条正式 arm 正在运行，
> 当前只有 133/500 的运行心跳，尚无可发布的 B+ 正式结果或路线内差值。
>
> 本文是面向结果阅读的展示报告。数字必须来自固定 artifact 的可重算内容；
> attempt、hash、故障归因与复现命令的唯一权威账本仍是
> [Eagle3 实验记录](./hedge-deepseek-v4-flash-eagle3.md)。若两者暂时不一致，
> 以权威 artifact 和实验记录为准。

## 1. 结论

| 结论项 | 当前结果 |
| --- | --- |
| Native 500 formal | `ACCEPTED/PASS`；500/500 success，0 failure/retry |
| HEDGE `B=0` | `B0_PASS`；32/32 完整输出 token IDs 与 native 相同 |
| 自动校准 | 1486 个正 barrier value；NumPy linear `q25=6.75` |
| 唯一 B+ 配置 | `g=6.75, B=6.75, m=1, value_scheme=normalized_suffix` |
| B+ bounded smoke | PASS；3/3 success，预算生命周期和 `m<=1` 无违例 |
| HEDGE B+ 500 formal | `LIVE / NOT YET ACCEPTED`；08:29Z 心跳 133/500 |
| 路线最终结论 | 待 B+ 500 formal、清理证据和独立重算全部验收后给出 |

目前可以下的结论只有：

1. Eagle3 native 正式基线已经在固定 TP=8、固定 source、固定模型和固定数据上成立。
2. `B=0` 没有改变 32 条 calibration 的完整 token 序列。
3. 正预算参数完全由 calibration 决定，没有读取 formal 500 条结果后回调。
4. B+ 接入和预算记账已通过 bounded smoke。
5. B+ formal 尚未完成，因此不能声称 HEDGE 相对 native 更快、更慢，或质量更高、
   更低。

## 2. 固定实验协议

| 项目 | 固定值 |
| --- | --- |
| Worker / GPU | worker `4099544`，8×NVIDIA H20，TP=8 |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d` |
| SGLang base | `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| SGLang final | `2600c7b16c648d281be060b33ffadc7ae320f7e3` |
| Reviewed patch | SHA-256 `73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf` |
| HEDGE pure core | source `9fb903d676254ea5f5d171051fb15c54f331111c`；publisher `4d96f44065c07030ede67484a262006ec149626a`；Eagle3 import `4cefd0a36ea254e4c14a83f35dc8db15b37a3384` |
| Dataset | `openai/gsm8k` `main/test@740312add88f781978c0658806c59bc2815b9866` |
| Dataset fingerprint | `59ec1b7f9357c7a2` |
| Split | seed `980406` 确定性 shuffle；前 32 条 calibration，随后不重叠 500 条 formal |
| Split manifest | SHA-256 `5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5` |
| Prompt | 原始 question + `Please reason step by step, and put your final answer within \boxed{}.` |
| Generation | 无 system prompt；thinking=false；temperature=0；top_p=1；max_tokens=512 |
| Execution | 严格单请求顺序；proposal tokens=3；internal verify width=4 |
| Server | TP=8；`flashinfer_mxfp4`；context=4096；max-running=1；mem-fraction=0.60 |
| Disabled | CUDA Graph、prefill/draft-extend graph、overlap schedule、radix cache |
| Formal warmup | 每个新服务使用 calibration 固定前 10 条；不计入 formal 时间 |
| Formal timing | 从第 1 条 formal HTTP 发出到第 500 条达到终态；HTTP、生成、排队、retry 全计入 |

Native 与 B+ formal 使用同一最终 SGLang source、相同 server command、模型、数据、
proposal width、请求和计时协议；只切换 HEDGE mode/config。

## 3. 32 条 calibration 如何得到参数

### 3.1 样本如何选择

在固定 GSM8K revision 上对 source indices 执行
`random.Random(980406).shuffle(source_indices)`。shuffle 后前 32 个 source
indices 为：

```text
435, 902, 303, 1168, 403, 611, 608, 977,
229, 1263, 566, 1191, 979, 1032, 297, 1150,
488, 1235, 1266, 75, 720, 331, 992, 177,
983, 467, 127, 114, 973, 1085, 900, 822
```

随后 500 个 shuffled indices 构成 formal partition，和 calibration
`overlap_count=0`。完整问题、标准答案、request messages 和 500 个 formal indices
保存在 split manifest，不在本报告重复粘贴。

### 3.2 Native 与 `B=0` 的 32 条结果

| 指标 | Native calibration | HEDGE `B=0` calibration |
| --- | ---: | ---: |
| Terminal / success | 32 / 32 | 32 / 32 |
| Failure / generation retry / trace retry | 0 / 0 / 0 | 0 / 0 / 0 |
| Completion tokens | 5,034 | 5,034 |
| Proposal rows | 2,116 | 2,116 |
| Strict-rejection barriers | 1,491 | 1,491 |
| GSM8K matches | 31/32 | 31/32 |
| Parse failures | 0 | 0 |
| 完整输出 token IDs | reference | 32/32 与 native 相同 |

因此 `b0_comparison.json` 得到：

```text
compared=32
first_mismatch=null
status=B0_PASS
```

这里的门禁是完整输出 token IDs，而不是只比较最终答案。`B0_PASS` 证明启用 HEDGE
但不给风险预算时，calibration 输出与 native 相同。

### 3.3 从 barrier 计算 `g`

对 32 条 calibration 的 strict-rejection trace，取每个首次 strict-rejection
barrier 的正值：

```text
regret = max(target_top_logit - draft_token_logit, 0)
value  = normalized_suffix
ratio  = regret / value
```

Eagle3 的 3 个 draft candidate 在 `normalized_suffix` 下对应 value
`[1, 2/3, 1/3]`。1,491 个 strict-rejection barriers 中有 1,486 个正 ratio，
这些值才进入 quantile。其分布检查为：

| 统计量 | `regret/value` |
| --- | ---: |
| Count | 1,486 |
| Min | 0.25 |
| Q25 | 6.75 |
| Median | 19.125 |
| Max | 112.5 |

量化方法固定为 NumPy `quantile(..., 0.25, method="linear")`。对 `n=1486`，
零基插值位置为：

```text
h = (n - 1) × 0.25 = 371.25
sorted_values[371] = 6.75
sorted_values[372] = 6.75
q25 = 6.75
```

所以 gate 固定为 `g=q25=6.75`。

### 3.4 为什么 `B=6.75`、`m=1`

计划预先规定：

- `g=q25`；
- 每条 request 的持续风险预算 `B=g`；
- 每个 proposal block 最多一个 relaxed mismatch，即 `m=1`；
- `value_scheme=normalized_suffix`。

因此唯一 formal 配置是：

```json
{
  "g": 6.75,
  "B": 6.75,
  "m": 1,
  "value_scheme": "normalized_suffix"
}
```

冻结身份：

| 项目 | SHA-256 |
| --- | --- |
| Calibration | `836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60` |
| Formal B+ config | `87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a` |

没有使用 formal 500 条的任何结果选择或修改这些参数。

### 3.5 B+ bounded smoke 门禁

正式 500 条前只运行一次 3 条 bounded smoke：

| 指标 | 结果 |
| --- | ---: |
| Terminal / success | 3 / 3 |
| Failure / retry / trace retry | 0 / 0 / 0 |
| Completion tokens | 441 |
| Proposal rows | 173 |
| Strict-rejection barriers | 124 |
| Relaxed proposals | 14 |
| 相对 strict 的额外 accepted drafts | 22 |
| 三条 request budget spent | 6.75 / 6.75 / 6.375 |
| 三条 request final remaining | 0 / 0 / 0.375 |
| Budget / continuity / nonnegative / `m<=1` violations | 0 |

该 smoke 只验证正预算路径和记账，不作为正式 TPS、acceptance 或 GSM8K 结论。

## 4. 500 条正式实验

### 4.1 核心结果与路线内差值

| 指标 | Native formal | HEDGE B+ formal | B+ − Native |
| --- | ---: | ---: | ---: |
| 验收状态 | `ACCEPTED/PASS` | `LIVE / NOT YET ACCEPTED` | — |
| Terminal / success | 500 / 500 | 133 / 500（08:29Z 心跳） | 待完成 |
| Failure / generation retry / trace retry | 0 / 0 / 0 | 当前 0 / 0 / 0 | 待完成 |
| Completion tokens | 74,580 | 待完成 | 待完成 |
| 客户端正式墙钟 | 4,411.045604754 s | 待完成 | 待完成 |
| Output TPS | 16.9075558683 | 待完成 | 待完成 |
| Proposals | 31,603 | 待完成 | 待完成 |
| Accepted draft tokens | 42,477 | 待完成 | 待完成 |
| Accepted draft tokens / proposal | 1.3440812581 | 待完成 | 待完成 |
| Mean acceptance length | 2.3440812581 | 待完成 | 待完成 |
| GSM8K matches | 488/500 | 待完成 | 待完成 |
| GSM8K mismatches | 12/500 | 待完成 | 待完成 |
| Parse failures | 0 | 待完成 | 待完成 |

`Output TPS = completion tokens / 客户端正式墙钟`。差值列在 B+ accepted 后统一按
`B+ - Native` 重算；TPS、acceptance 和 match 同时给绝对差，适用时再给相对百分比。

### 4.2 Native acceptance 明细

| Acceptance length | Proposal count |
| ---: | ---: |
| 1 | 12,111 |
| 2 | 5,813 |
| 3 | 4,373 |
| 4 | 9,306 |

其中 acceptance length 包含最终 target token；accepted draft tokens 为
`acceptance length - 1`。对应 draft-token 分布是 0/1/2/3：
12,111 / 5,813 / 4,373 / 9,306。

| Draft position | Accepted | Acceptance rate |
| ---: | ---: | ---: |
| 0 | 19,492 | 0.6167768883 |
| 1 | 13,679 | 0.4328386546 |
| 2 | 9,306 | 0.2944657153 |

### 4.3 HEDGE B+ budget 明细

下列项目只在 B+ 500 条完成、artifact 封存并由根线程独立重算后填写：

| 指标 | HEDGE B+ formal |
| --- | ---: |
| Relaxed proposals | 待完成 |
| Relaxed mismatches | 待完成 |
| 相对 strict 的额外 accepted drafts | 待完成 |
| Checked successful requests | 待完成 |
| Failed requests without budget trace | 待完成 |
| Total budget spent | 待完成 |
| Requests exhausting budget | 待完成 |
| Final remaining budget distribution | 待完成 |
| Continuity / accounting / nonnegative violations | 待完成 |
| Proposals exceeding `m=1` | 待完成 |

运行中的 133/500 只是健康心跳，不计作正式结果，也不用于参数调整。

### 4.4 Native 运行与 GPU 证据

- 10/10 warmup 完成后才开始 formal timing。
- 500/500 formal 全部达到终态，0 failure、0 generation retry、0 trace retry。
- TP0–7 target/draft load 和 Eagle3 aux trace 完整。
- 正式 ready-window 每卡 3,814 个 GPU 样本；逐卡 max utilization 97–99%。
- 模型显存约 60.2–60.7 GiB/卡。
- 无未处理 CUDA、NCCL 或 worker crash。
- registered SIGTERM、无 KILL fallback、0 model context 后恢复 exact-eight
  keepalive，10×1 秒逐卡 100%。

B+ 的对应证据待 live attempt 完成后在本节并列补齐。

## 5. Artifact 与可重算入口

| 内容 | 路径 / identity |
| --- | --- |
| Dataset split | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T230100Z-phase-01b-dataset-revision-12/gsm8k_split_manifest.json` |
| Native calibration 32 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T044000Z-phase-04-native-calibration-03` |
| B0 calibration 32 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T050000Z-phase-04-b0-calibration-01` |
| Frozen calibration | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052000Z-phase-04-calibration-01` |
| B+ bounded smoke | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052500Z-phase-04-bplus-smoke-01` |
| Native formal accepted | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02` |
| Native summary SHA-256 | `def6fc7b6ae74200df2c4052cdd1abfcdfe12db5b54a4acc08ea2093177a7b52` |
| Native artifact manifest SHA-256 | `f9759d5e1826a752221b55367bb873db2ea1d72959092d52112675566105f8c1` |
| Native accepted marker | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-native-formal.complete.json` |
| B+ formal live | worker scratch `/tmp/deepspec-hedge-v4-eagle3/20260729T080100Z-phase-06-bplus-formal-01` |
| B+ accepted marker | 待验收后发布；当前必须不存在 |

## 6. 解释限制

- Native 和 B+ 各只允许一次 accepted formal 500 运行；这是确定性协议内的单次
  路线内对比，不提供多次重复实验的置信区间。
- 不设置 TPS、acceptance length 或 GSM8K match 门槛。
- GSM8K match 只展示，不把质量门槛反向用于挑选参数。
- 不做跨 DSpark/Eagle3/DFlash 的绝对 TPS 排名。
- B+ 未 accepted 前，本报告保持 `IN_PROGRESS`，所有 B+ final 单元格保持
  `待完成`。
