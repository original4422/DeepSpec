# HEDGE × DeepSeek-V4-Flash-DSpark 实验结果

> 本文是面向读者的结果视图，数字从冻结的 JSON/HDFS artifacts 派生。
> 唯一审计账本仍是
> [`docs/experiment/hedge-deepseek-v4-flash-dspark.md`](../experiment/hedge-deepseek-v4-flash-dspark.md)；
> 如两者不一致，以原始 artifact 和该审计账本为准。P08 将从最终审计 JSON
> 重算并补齐本文。

## 一页结论

- 状态：`IN_PROGRESS`；32 条 calibration 与 native 正式 500 已完成，
  HEDGE `B>0` 正式 500 尚未运行。
- 数据不是新生成或训练数据：固定
  `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866`
  的 `main/test`，用 seed `980406` 确定性 shuffle；前 32 条 calibration，
  随后不重叠的 500 条 formal。
- HEDGE 参数完全由 32 条 calibration 决定：
  `g=q25=2.0625`、`B=g=2.0625`、`m=1`、
  `value_scheme=normalized_suffix`、width/block size 5。
- native 正式 500：500/500 成功、0 retry、74594 completion tokens、
  2348.31919839 秒、31.76484698125425 output TPS。
- HEDGE 正式结果与路线内差值：`PENDING`；不会用 formal 结果回调参数。

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
| 状态 | `PASS` | `PENDING` | — |
| 成功 / 失败 / retry | 500 / 0 / 0 | `PENDING` | `PENDING` |
| completion tokens | 74594 | `PENDING` | `PENDING` |
| timed wall seconds | 2348.31919839 | `PENDING` | `PENDING` |
| output TPS | 31.76484698125425 | `PENDING` | `PENDING` |
| proposals | 16045 | `PENDING` | `PENDING` |
| proposed draft tokens | 80225 | `PENDING` | `PENDING` |
| accepted draft tokens | 58473 | `PENDING` | `PENDING` |
| accepted drafts / proposal | 3.644312870052976 | `PENDING` | `PENDING` |
| acceptance length（含 bonus） | 4.64904954814584 | `PENDING` | `PENDING` |
| GSM match / mismatch / parse failure | 478 / 11 / 11 | `PENDING` | `PENDING` |

native 逐位置 accepted draft tokens：

```text
[14904, 13227, 11688, 10119, 8535]
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

`PENDING`。运行完成后，本节将补齐：

- 唯一 attempt 和 artifact/hash；
- TPS、tokens、acceptance 与逐位置统计；
- runtime calls、relaxed mismatches、regret charged、budget exhaustion、
  cap trims、request initialized/finished、active/leak；
- TP8/八卡、cleanup、keepalive 与 archive 证据；
- 相对 native 的路线内差值。

## 限制

- 不设置 TPS、接受长度或 GSM8K 匹配率门槛。
- 不做跨方法绝对性能排名；只比较同一路线、同一最终 identity 的 native 与
  HEDGE `B>0`。
- GSM8K match 是观测指标，不是基础设施成功门禁。
- 当前文档尚未包含 P07 结果，因此不能得出 HEDGE 正预算相对 native 的最终结论。
