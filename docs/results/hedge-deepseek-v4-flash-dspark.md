# HEDGE × DeepSeek-V4-Flash-DSpark 实验结果

> 本文是面向读者的结果视图，数字从冻结的 JSON/HDFS artifacts 派生。
> 唯一审计账本仍是
> [`docs/experiment/hedge-deepseek-v4-flash-dspark.md`](../experiment/hedge-deepseek-v4-flash-dspark.md)；
> 如两者不一致，以原始 artifact 和该审计账本为准。P08 将从最终审计 JSON
> 重算并补齐本文。

## 一页结论

- 状态：`IN_PROGRESS`；32 条 calibration、native 正式 500 与 HEDGE
  `B>0` 正式 500 均已完成并通过主 Agent复验；仅剩 P08 最终离线审计。
- 数据不是新生成或训练数据：固定
  `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866`
  的 `main/test`，用 seed `980406` 确定性 shuffle；前 32 条 calibration，
  随后不重叠的 500 条 formal。
- HEDGE 参数完全由 32 条 calibration 决定：
  `g=q25=2.0625`、`B=g=2.0625`、`m=1`、
  `value_scheme=normalized_suffix`、width/block size 5。
- native 正式 500：500/500 成功、0 retry、74594 completion tokens、
  2348.31919839 秒、31.76484698125425 output TPS。
- HEDGE 正式 500：500/500 成功、0 retry、75819 completion tokens、
  2263.710352404 秒、33.493242595936465 output TPS。
- 路线内观察值：TPS `+5.4412%`，accepted drafts/proposal `+7.6431%`，
  含 bonus acceptance length `+5.9957%`；GSM8K match rate
  `95.6% → 94.8%`（`-0.8` 个百分点）。不会用 formal 结果回调参数。

## 固定身份

| 项目 | 固定值 |
| --- | --- |
| worker / GPU / TP | `4106666` / 8×NVIDIA H20 / TP=8 |
| model | `deepseek-ai/DeepSeek-V4-Flash-DSpark` |
| HF reference revision | `62af8fffb2f7030cac4de2f0169f5b8d1101b646` |
| canonical snapshot | ModelScope `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae` |
| SGLang base | `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` |
| final integration | `e028d2c31658a06b4f5a5ee072d7e21c79d51c36` |
| formal wheel SHA-256 | `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9` |
| proposal width | 5 |
| dataset fingerprint | `59ec1b7f9357c7a2` |
| calibration JSONL SHA-256 | `28a7080565cde90b8cf1db79c88bb463861515fabe3fa7409481802104a6e47d` |
| formal JSONL SHA-256 | `33554b90f751252ced2cfd16333d749f427c84cf025dccef4c7934144e9d5108` |

请求固定为无 system prompt，原 question 追加
`Please reason step by step, and put your final answer within \boxed{}.`
并使用 `enable_thinking=false`、`temperature=0`、`top_p=1`、
`max_tokens=512`。所有请求顺序执行。

## 32 条 calibration：参数怎么来的

### 1. native trace

唯一有效 native calibration attempt：
`20260729T044309Z-p05-native-calibration-r4`。

- 32/32 请求成功，0 retry，5183 completion tokens。
- trace scope 精确覆盖 32 个 response ID。
- 共看到 1097 个 proposal barrier；保留 484 个正且有限的
  `regret/value`，0 dropped。
- native outputs SHA-256：
  `b5550312da76c86dc68f3b7f0685f4eb1009f7f778be8c24e1d400b382e78b23`
- native trace SHA-256：
  `8ffa9e45214c6a40520448c5d7dda098182e66134e809a92e20530fd9a5130f6`

### 2. HEDGE `B=0` 等价核查

唯一 B0 calibration attempt：
`20260729T051340Z-p05-b0-calibration-r1`。

- 32/32 完整输出 token-ID 列表与 native 相同，0 mismatch。
- 0 retry，5183 completion tokens。
- 1097 proposals；strict accepted 与 HEDGE accepted 均为 4081；
  relaxed mismatch、regret charge、state leak 和 trace 均为 0。
- B0 outputs SHA-256：
  `d59b0e17483c1415dddd9ccee8ed41c22f26ab6fbfb47d4fd3a0d4f9fec3a434`

### 3. 自动校准

对 484 个正且有限的首次 strict-rejection `regret/value` 使用固定的
线性插值 q25：

```text
h = (n - 1) * 0.25
q25 = 2.0625
g = q25
B = g
m = 1
```

冻结配置：

```json
{
  "B": 2.0625,
  "block_size": 5,
  "g": 2.0625,
  "m": 1,
  "value_scheme": "normalized_suffix"
}
```

- config fingerprint：
  `6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921`
- config SHA-256：
  `760128b85b8c3dd67e3b4dee512cc302ee59bd2e2a1b3ab3390fd186ade36b71`
- calibration summary SHA-256：
  `8d4f0fd823ad9452883e32f141168e99b306226d326d56fe06c5eaeae743eeee`
- repo artifacts：`artifacts/hedge-dspark/p05-calibration/`

正式 500 条的答案、TPS 或 acceptance 不参与参数选择。

## 正式 500：当前结果

两个正式 arm 都在新启动的同一最终 SGLang identity 上先运行 calibration
固定前 10 条 warmup；warmup 不进入计时和 token 汇总。正式窗口从第 1 个
formal 请求发出前到第 500 个请求终态，HTTP、生成、排队和 retry/backoff
均计入。

| 指标 | native | HEDGE `B>0` | 差值 |
| --- | ---: | ---: | ---: |
| 状态 | `PASS` | `PASS` | — |
| 成功 / 失败 / retry | 500 / 0 / 0 | 500 / 0 / 0 | 0 / 0 / 0 |
| completion tokens | 74594 | 75819 | +1225（+1.6422%） |
| timed wall seconds | 2348.31919839 | 2263.710352404 | -84.608845986（-3.6030%） |
| output TPS | 31.76484698125425 | 33.493242595936465 | +1.7283956146822135（+5.4412%） |
| proposals | 16045 | 15386 | -659（-4.1072%） |
| proposed draft tokens | 80225 | 76930 | -3295（-4.1072%） |
| accepted draft tokens | 58473 | 60357 | +1884（+3.2220%） |
| accepted drafts / proposal | 3.644312870052976 | 3.922851943325101 | +0.2785390732721247（+7.6431%） |
| acceptance length（含 bonus） | 4.64904954814584 | 4.927791498765111 | +0.27874195061927143（+5.9957%） |
| GSM match / mismatch / parse failure | 478 / 11 / 11 | 474 / 13 / 13 | -4 / +2 / +2 |

native 逐位置 accepted draft tokens：

```text
[14904, 13227, 11688, 10119, 8535]
```

HEDGE 逐位置 accepted draft tokens、相对 native 差值与 proposal 接受率：

```text
counts = [14779, 13649, 12278, 10688, 8963]
delta  = [-125, +422, +590, +569, +428]
rates  = [0.960549, 0.887105, 0.797998, 0.694657, 0.582543]
```

### native 运行证据

- attempt：`20260729T062241Z-p06-native-formal-r1`
- immutable artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T062241Z-p06-native-formal-r1`
- `formal_outputs.jsonl` SHA-256：
  `ecd9952536a860836babc3451e066b4ea164b0e520e263bfc5c200f46e902607`
- `answer_summary.json` SHA-256：
  `85564471483224bee25e33ba93b75ee06a019ded4ede959be4fb70b26a351cab`
- `acceptance_summary.json` SHA-256：
  `bc28fceeaf046236de6f87c034ffb0eccebd2b4f9da480f592fb100bdd433cb0`
- archive manifest SHA-256：
  `f0014a88b05761b47a85b841d052a13a2e6d6d4baa21bf4f3640b4e7c96beca7`
- TP/target/draft ranks 0–7 全部加载；八卡 formal window 各有 1982
  samples，最低模型显存 79619–80099 MiB，最大利用率 99–100%。
- 无 CUDA/NCCL/worker crash；定向停止后 contexts none；keepalive
  8×10 全卡 100%。
- native arm 中 HEDGE disabled、config `null`，HEDGE proposal/active/leak
  counters 均为 0。

### HEDGE `B>0`

唯一 attempt：
`20260729T084544Z-p07-hedge-formal-r1`。

- immutable artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T084544Z-p07-hedge-formal-r1`
- `formal_outputs.jsonl` SHA-256：
  `615063928d19a8d5274bc669dc1ce1e7ce538c3b59ba21ce9b49e135d5078668`
- `answer_summary.json` SHA-256：
  `1d1a1cdd23c4d17a875d28d5b1e5a0152b1c45f7cb6bbf61e3d252e61e448fa0`
- `acceptance_summary.json` SHA-256：
  `069e8d2b058cf451d8c9c9b3d2f44d1bb32cad6ca1ef4ff101cd98c221498505`
- `hedge_counters.json` SHA-256：
  `5f0874f54da28145e44a5911b45d8aaab3f058ea5a545bd6a4b8889ee8eca7e0`
- archive manifest SHA-256：
  `397462adbd28aea5e8df8f275c2d1947bf29d297b5c84747ca6bf7c6a5bdb082`

HEDGE authoritative counters：

| counter | 值 |
| --- | ---: |
| runtime calls / proposals | 15386 |
| strict accepted draft tokens | 56642 |
| HEDGE accepted draft tokens | 60357 |
| HEDGE 相对 strict 新增 accepted | 3715 |
| relaxed mismatches | 1427 |
| regret charged / remaining / initial | 723.75 / 307.5 / 1031.25 |
| budget spent | 70.1818181818% |
| budget exhaustion / cap trim | 0 / 0 |
| initialized / finished / non-natural | 500 / 500 / 1 |
| active request states / state leaks | 0 / 0 |

`charged + remaining = initial = 500 × B = 1031.25` 精确成立。HEDGE
snapshot 固定 `counter_schema_version=1`、candidate alignment 和 native
full-vocab score seam；calibration trace 在正式 arm 中关闭。

TP/target/draft ranks 0–7 全部加载；八卡 formal window 各有 1909 samples，
最低模型显存 79621–80101 MiB，最大利用率均 99%；没有运行期
CUDA/NCCL/worker crash。定向停止后 contexts none；keepalive 恢复为 PID
`121312`，8×10 全卡 mean/min/max 100%。归档中的 39 个 manifest 项已由
主 Agent逐项重算 size/SHA 并全部匹配。

P06/P07 中 15/500 条完整输出 token-ID 列表相同，485/500 不同；答案 outcome
迁移为：472 `match→match`、4 `match→mismatch`、2
`match→parse_failure`、2 `mismatch→match`、9 `mismatch→mismatch`、
11 `parse_failure→parse_failure`。这些都是观察值，不是通过门槛。

## 限制

- 不设置 TPS、接受长度或 GSM8K 匹配率门槛。
- 不做跨方法绝对性能排名；只比较同一路线、同一最终 identity 的 native 与
  HEDGE `B>0`。
- GSM8K match 是观测指标，不是基础设施成功门禁。
- 每个正式 arm 只运行一次，不报告方差或置信区间；观察到的路线内差值不能外推为
  跨硬件、跨方法或生产吞吐结论。
- P08 尚未生成最终审计 JSON/manifest，因此总体状态暂不标记 `COMPLETE`。
