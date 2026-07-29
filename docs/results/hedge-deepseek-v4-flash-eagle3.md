# HEDGE × DeepSeek-V4-Flash-Eagle3 实验结果

> **状态：`COMPLETE`；Phase 07 最终审计于
> `2026-07-29T09:55:59Z` PASS。**
> Native 与 HEDGE B+ 的 500 条正式结果均已完成根线程独立重算并发布 accepted
> marker；marker、artifact/hash、停机语义、共享 target、Git 边界与当前
> exact-eight keepalive 已再次只读交叉核对。
>
> 本文是面向读者的结果视图，数字从冻结的 JSON/HDFS artifacts 派生。attempt、
> 故障归因和复现证据的权威账本见
> [实验记录](../experiment/hedge-deepseek-v4-flash-eagle3.md)。

## 一页结论

- Native formal 与 HEDGE B+ formal 均为 500/500 success，0 failure、
  generation retry 和 trace retry。
- 32 条 calibration 的 HEDGE `B=0` 与 native 完整输出 token IDs 32/32
  相同，结论为 `B0_PASS`。
- 正预算只由 calibration 决定：1,486 个正
  `regret/value` 的 NumPy linear `q25=6.75`，因此唯一配置为
  `g=6.75, B=6.75, m=1, value_scheme=normalized_suffix`；没有依据
  formal 结果回调。
- 在这一次冻结的路线内正式实验中，HEDGE B+ 的 output TPS 为
  `17.8681853401`，Native 为 `16.9075558683`，绝对增加
  `0.9606294718`，相对增加 `5.682%`；客户端正式墙钟减少
  `201.104943839` 秒，即 `4.559%`。
- Accepted draft tokens/proposal 从 `1.3440812581` 增至
  `1.4635368588`，相对增加 `8.888%`；mean acceptance length 从
  `2.3440812581` 增至 `2.4635368588`。
- 两个 arm 的 GSM8K aggregate 均为 488/500 match、12/500 mismatch、
  0 parse failure。样本级状态有 494/500 相同，另有 3 条由 mismatch 变为
  match、3 条由 match 变为 mismatch。
- B+ 的 30,332 个 proposals 中有 2,121 个 relaxed proposals，共比 strict
  多接受 3,782 个 draft tokens；500 条 request 的预算总消费为 3,120，
  196 条耗尽预算，预算连续性、记账、非负约束和 `m<=1` 的违例均为 0。
- 这是每个 arm 各一次的冻结正式运行，不提供重复实验置信区间；因此上述百分比是本次
  路线内观测差值，不外推为跨方法绝对排名。

## 固定身份

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

## 32 条 calibration：参数怎么来的

### 0. 固定样本

在固定 GSM8K revision 上对 source indices 执行
`random.Random(980406).shuffle(source_indices)`。shuffle 后前 32 个 source
indices 为：

```text
435, 902, 303, 1168, 403, 611, 608, 977,
229, 1263, 566, 1191, 979, 1032, 297, 1150,
488, 1235, 1266, 75, 720, 331, 992, 177,
983, 467, 127, 114, 973, 1085, 900, 822
```

随后 500 个 shuffled indices 构成 formal partition，与 calibration 的
`overlap_count=0`。完整问题、标准答案、request messages 和 500 个 formal
indices 保存在 split manifest。

### 1. Native trace

唯一有效 native calibration attempt 为
`20260729T044000Z-phase-04-native-calibration-03`：

- 32/32 success，0 failure、generation retry 和 trace retry；
- 5,034 completion tokens、2,116 proposal rows、1,491 个首次
  strict-rejection barriers；
- GSM8K 31/32 match，0 parse failure；
- outputs SHA-256：
  `163450d5740412394124cd775ae9d1f97e8e004ce1777124faf84d12571a7b96`；
- trace SHA-256：
  `9e849ad95bbe5b64f30f78c896bbe512fe8f947bb257f9b441a3b0870f3d6bc7`；
- artifact manifest SHA-256：
  `27c70024f74acbc73bc1ee5f55f6a6eb7ac86203ba0ec447a3cd49cd426a4887`。

### 2. HEDGE `B=0` 等价核查

唯一 B0 calibration attempt 为
`20260729T050000Z-phase-04-b0-calibration-01`：

- 32/32 success，0 failure、generation retry 和 trace retry；
- 5,034 completion tokens、2,116 proposal rows、1,491 个首次
  strict-rejection barriers；
- 32/32 完整输出 token-ID 列表与 native 相同，不是只比较最终答案；
- GSM8K 31/32 match，0 parse failure；
- outputs SHA-256：
  `3e2e9364da7e45d9905dee0543d69a2d1e9375925365ff57d4e714bbaee9bf19`；
- trace SHA-256：
  `88cb6026f89d4157cf2e04ccc3a28b6a093f2e053bbf37c05b43696ea116ce38`；
- artifact manifest SHA-256：
  `635913dd19bbf43a8a3063244d28eff394f09e36459126dfbcaedc51cc63fa12`。

`b0_comparison.json` 的重算结果为：

```text
compared=32
first_mismatch=null
status=B0_PASS
```

### 3. 自动校准

对 32 条 calibration 的 strict-rejection trace，取每个首次 strict-rejection
barrier 的正值：

```text
regret = max(target_top_logit - draft_token_logit, 0)
value  = normalized_suffix
ratio  = regret / value
```

Eagle3 的 3 个 draft candidate 对应 value `[1, 2/3, 1/3]`。1,491 个
strict-rejection barriers 中有 1,486 个正 ratio。分布检查为：

```text
count=1486
min=0.25
q25=6.75
median=19.125
max=112.5
```

量化方法固定为 NumPy `quantile(..., 0.25, method="linear")`：

```text
h = (1486 - 1) × 0.25 = 371.25
sorted_values[371] = 6.75
sorted_values[372] = 6.75
q25 = 6.75
```

计划预先规定 `g=q25`、`B=g`、`m=1` 和
`value_scheme=normalized_suffix`，所以唯一 formal 配置是：

```json
{
  "g": 6.75,
  "B": 6.75,
  "m": 1,
  "value_scheme": "normalized_suffix"
}
```

- Frozen calibration identity：
  `836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60`。
- Calibration artifact SHA-256：
  `9af2cff0cc176ef16c7552c54817b2cfb66f5224463ac15730e6eae04a837474`。
- Formal B+ config SHA-256：
  `87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a`。

没有使用 formal 500 条的任何结果选择或修改这些参数。

### 4. B+ bounded smoke 门禁

正式 500 条前只运行一次 3 条 bounded smoke：

- 3/3 terminal/success，0 failure、generation retry 和 trace retry；
- 441 completion tokens、173 proposal rows、124 个 strict-rejection
  barriers；
- 14 个 relaxed proposals，相对 strict 多接受 22 个 drafts；
- 三条 request budget spent 为 `6.75 / 6.75 / 6.375`；
- final remaining 为 `0 / 0 / 0.375`；
- budget continuity、accounting、nonnegative 和 `m<=1` violations 均为 0。

该 smoke 只验证正预算路径和记账，不作为正式 TPS、acceptance 或 GSM8K 结论。

## 正式 500 条结果

正式结果统一放在下面这一张竖向对比表中；最左列是指标，后三列分别是两个 arm 和
路线内差值。

| 指标 | Native formal | HEDGE B+ formal | B+ − Native |
| --- | ---: | ---: | ---: |
| 验收状态 | `ACCEPTED/PASS` | `ACCEPTED/PASS` | — |
| Terminal / success | 500 / 500 | 500 / 500 | 0 / 0 |
| Failure / generation retry / trace retry | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Completion tokens | 74,580 | 75,224 | +644（+0.864%） |
| 客户端正式墙钟 | 4,411.045604754 s | 4,209.940660915 s | −201.104943839 s（−4.559%） |
| Output TPS | 16.9075558683 | 17.8681853401 | +0.9606294718（+5.682%） |
| Proposals | 31,603 | 30,332 | −1,271（−4.022%） |
| Strict accepted draft tokens | 42,477 | 40,610 | −1,867（−4.395%） |
| Accepted draft tokens | 42,477 | 44,392 | +1,915（+4.508%） |
| Accepted draft tokens / proposal | 1.3440812581 | 1.4635368588 | +0.1194556007（+8.888%） |
| Mean acceptance length | 2.3440812581 | 2.4635368588 | +0.1194556007（+5.096%） |
| Acceptance length 1 / 2 / 3 / 4 | 12,111 / 5,813 / 4,373 / 9,306 | 10,454 / 5,445 / 4,352 / 10,081 | −1,657 / −368 / −21 / +775 |
| Draft position 0 accepted / rate | 19,492 / 0.6167768883 | 19,878 / 0.6553474878 | +386 / +3.8571 pp |
| Draft position 1 accepted / rate | 13,679 / 0.4328386546 | 14,433 / 0.4758341026 | +754 / +4.2995 pp |
| Draft position 2 accepted / rate | 9,306 / 0.2944657153 | 10,081 / 0.3323552684 | +775 / +3.7890 pp |
| Relaxed proposals / mismatches | 0 / 0 | 2,121 / 2,121 | +2,121 / +2,121 |
| 相对 strict 的额外 accepted drafts | 0 | 3,782 | +3,782 |
| Checked requests / budget-unchecked failures | N/A | 500 / 0 | N/A |
| Total budget spent / exhausted requests | N/A | 3,120.0 / 196 | N/A |
| Budget continuity / accounting / nonnegative violations | N/A | 0 / 0 / 0 | N/A |
| Proposals exceeding `m=1` | N/A | 0 | N/A |
| GSM8K matches | 488/500（97.6%） | 488/500（97.6%） | 0（0 pp） |
| GSM8K mismatches | 12/500 | 12/500 | 0 |
| Parse failures | 0 | 0 | 0 |
| 样本级 answer-match 状态 | 基准 | 494/500 与 Native 相同 | 3 条改善 / 3 条退化 |

`Output TPS = completion tokens / 客户端正式墙钟`。Acceptance length 包含最终
target token，因此等于 accepted draft tokens/proposal 加 1。

### Native 运行证据

- 10/10 warmup 完成后才开始 formal timing；
- TP0–7 target/draft load、NCCL rank 和 Eagle3 aux trace 完整；
- 正式 ready-window 每卡 3,814 个 GPU 样本，逐卡 max utilization 97–99%；
- 模型显存约 60,200–60,700 MiB/卡；
- 39 个 artifact 的 size/hash、flattened trace 和 summary 独立重算零差异；
- 无未处理 CUDA、NCCL 或 worker crash；
- registered SIGTERM、无 KILL fallback、0 model context 后恢复 exact-eight
  keepalive，10×1 秒逐卡 100%。

### HEDGE B+ 运行证据

- 10/10 warmup 后严格顺序完成 500/500 formal；510 个 chat、510 个 clear 和
  510 个 trace HTTP 请求全部为 200；
- 500 份完整 response/token IDs 与 30,332 个 proposal rows 均已封存；
- flattened trace 与每条 response 内 trace 逐行完全相同；
- 500 条 request 的预算从 `B=6.75` 开始，逐 proposal continuity、
  `remaining_after=remaining_before-spent`、非负和 `m<=1` 全部通过；
- TP0–7 target/draft load、NCCL rank 和 Eagle3 aux trace 完整；
- 保守 formal-window 每张卡各有 3,546 个 GPU 样本，逐卡 max utilization
  均为 98%，模型显存不低于 60,267 MiB；
- 正式请求结束前 CUDA/NCCL/Traceback/worker crash 精确错误模式均为 0；
- 39 个 artifact 的 size/hash、summary、答案、计时与 acceptance 指标经根线程
  独立重算零差异；
- 第 500 条 response 完成后才向登记 process group 发送 SIGTERM，
  `kill_fallback=false`；随后 0 CUDA context，keepalive owner `378796`
  恢复 exact-eight，10×1 秒逐卡 100%。

## Artifact 与 hash

| 内容 | 路径 / identity |
| --- | --- |
| Dataset split | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T230100Z-phase-01b-dataset-revision-12/gsm8k_split_manifest.json` |
| Dataset split SHA-256 | `5d4654dae6d867b0b81c9f4a9c96860603e29fc6a6d3cc29d275d3fdc645a0e5` |
| Native calibration 32 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T044000Z-phase-04-native-calibration-03` |
| Native calibration outputs / trace / manifest SHA-256 | `163450d5740412394124cd775ae9d1f97e8e004ce1777124faf84d12571a7b96` / `9e849ad95bbe5b64f30f78c896bbe512fe8f947bb257f9b441a3b0870f3d6bc7` / `27c70024f74acbc73bc1ee5f55f6a6eb7ac86203ba0ec447a3cd49cd426a4887` |
| B0 calibration 32 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T050000Z-phase-04-b0-calibration-01` |
| B0 outputs / trace / manifest SHA-256 | `3e2e9364da7e45d9905dee0543d69a2d1e9375925365ff57d4e714bbaee9bf19` / `88cb6026f89d4157cf2e04ccc3a28b6a093f2e053bbf37c05b43696ea116ce38` / `635913dd19bbf43a8a3063244d28eff394f09e36459126dfbcaedc51cc63fa12` |
| Frozen calibration artifact | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052000Z-phase-04-calibration-01/calibration.json` |
| Calibration artifact / frozen identity / B+ config SHA-256 | `9af2cff0cc176ef16c7552c54817b2cfb66f5224463ac15730e6eae04a837474` / `836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60` / `87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a` |
| B+ bounded smoke | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052500Z-phase-04-bplus-smoke-01` |
| B+ smoke manifest SHA-256 | `6668721d8173cc62d984e729faf4d8dbc1c4b63dbffefc5ea0894171d6b64b9d` |
| Native formal accepted | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02` |
| Native summary / outputs / trace SHA-256 | `def6fc7b6ae74200df2c4052cdd1abfcdfe12db5b54a4acc08ea2093177a7b52` / `55e47216668224b1588356b5510d4c3ba04ca8f8f4ee838647a0dd158e399c00` / `d79441cd62d332421760c44b70e0168281b06c61bd552cf3df2486df9a09fe18` |
| Native artifact manifest SHA-256 | `f9759d5e1826a752221b55367bb873db2ea1d72959092d52112675566105f8c1` |
| Native accepted marker | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-native-formal.complete.json` |
| Native accepted marker SHA-256 | `0ce403530e58cdebb1cbbe9dd0d3c0ae534ecd697947f4348ea4e66d9aa7aea4` |
| B+ formal accepted | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080100Z-phase-06-bplus-formal-01` |
| B+ summary / outputs / trace SHA-256 | `2800474a2a8eb59bb217ed988502c446c24be1e2aa30d50d0edd13f6374baad9` / `062c19f6573eaaf709fe2638f74cc4bbda2d19956811827bf25d4eb89bb90b44` / `cb0c90da0ba686beaae6aedb72815f49de27b33f2b0fedcb07736c2e7474ca16` |
| B+ formal result / artifact manifest SHA-256 | `d5ad2dbd8139b590073c945a2e881cf257d03cc47188012a217ac81d1dde0f43` / `09a341ac5d454cda191814d1970d748d0f1494deb284c0d419e601d7e70b7a1b` |
| B+ tooling freeze SHA-256 | `edc17c791fd0349163708b3dc649abde082af5ac76e1a06dd2c49962a09792d5` |
| B+ accepted marker | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-bplus-formal.complete.json` |
| B+ accepted marker SHA-256 | `7f6a95dc7e98b87c7de242887f32459bfa00050f67c0373e61f00f265661a812` |

## 只读复核命令

下面的命令只读取 accepted marker、正式 summary、停机/context 证据与共享 target
marker；不会启动服务、暂停 keepalive 或重读 checkpoint 权重：

```bash
EAGLE3_NATIVE_DIR=/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02
EAGLE3_BPLUS_DIR=/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080100Z-phase-06-bplus-formal-01
EAGLE3_COORD=/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4

sha256sum \
  "$EAGLE3_COORD/eagle3-native-formal.complete.json" \
  "$EAGLE3_COORD/eagle3-bplus-formal.complete.json"
python -m json.tool "$EAGLE3_NATIVE_DIR/summary.json"
python -m json.tool "$EAGLE3_BPLUS_DIR/summary.json"
python -m json.tool "$EAGLE3_NATIVE_DIR/shutdown.json"
python -m json.tool "$EAGLE3_BPLUS_DIR/shutdown.json"
python -m json.tool "$EAGLE3_NATIVE_DIR/cuda_contexts_after.json"
python -m json.tool "$EAGLE3_BPLUS_DIR/cuda_contexts_after.json"
python -m json.tool \
  "$EAGLE3_COORD/target-deepseek-v4-flash-60d8d70770c6776ff598c94bb586a859a38244f1.complete.json"
mlx worker list
git status --short --branch
git diff --check
```

正式运行的完整 server command、显式环境、source/model identity 和 generation
协议分别封存在两个 artifact 的 `resolved_config.json`；39-file 内容清单及 hash
封存在各自的 `artifact_manifest.json`。

## 限制

- Native 和 B+ 各只允许一次 accepted formal 500 运行；这是确定性协议内的单次
  路线内对比，不提供多次重复实验的置信区间。
- Completion token 数不同，因此 TPS 与墙钟差值应同时阅读；TPS 使用各 arm
  实际 completion tokens 计算。
- 两个 arm 的 aggregate match 数相同，但不是完全相同的 12 条 mismatch：
  3 条改善、3 条退化。
- 不设置 TPS、acceptance length 或 GSM8K match 门槛。
- GSM8K match 只展示，不把质量门槛反向用于挑选参数。
- 不做跨 DSpark/Eagle3/DFlash 的绝对 TPS 排名。
- Phase 07 只读终审确认 worker `4099544` 仍为 8×H20，当前 operational
  keepalive owner `378796` 为 exact-eight，10×1 秒逐卡均为 100%；它不是实验负载，
  也不进入正式指标。
