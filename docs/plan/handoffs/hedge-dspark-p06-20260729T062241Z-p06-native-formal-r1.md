# HEDGE DSpark P06 handoff（追溯重建）

- Status: `PASS`
- Retrospective evidence reconstruction: `true`
- Contemporaneous standalone executor handoff: `not written`
- Reconstruction basis: immutable P06 artifact、当时的
  `docs/experiment` / `docs/progress` 结论与已 push Git 节点；本文不是冒充当时
  executor 写下的 contemporaneous handoff
- Attempt ID: `20260729T062241Z-p06-native-formal-r1`
- Started / finished: `2026-07-29T06:22:41Z` /
  主 Agent于 `2026-07-29T07:32:56Z` 完成验收
- Autonomy elapsed / deadline: 原自主窗口内完成；当时截止
  `2026-07-29T08:54:41Z`
- Git branch / worktree: `exp/hedge-v4-dspark` /
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
- Worker / GPU lane: `4106666` / exact 8×NVIDIA H20
- TP ranks / GPU participation: TP/target/draft ranks 0–7；formal window
  每张 GPU 1982 samples
- Authorized phase: bounded `P06` only

## Outcome

唯一 native formal attempt 有效并通过主 Agent验收。10 条 warmup 排除计时，
500 条正式请求全部终态；没有第二 attempt、续跑、拼接或因 TPS 重跑。

- success / failed / retry：`500 / 0 / 0`
- completion tokens：`74594`
- timed wall seconds：`2348.31919839`
- output TPS：`31.76484698125425`
- proposals / proposed / accepted drafts：
  `16045 / 80225 / 58473`
- accepted drafts/proposal：`3.644312870052976`
- acceptance length including bonus：`4.64904954814584`
- GSM8K match / mismatch / parse failure：`478 / 11 / 11`

## Changes

- P06 formal tooling commit：`6a74186`
- P06 result commit：`9134825`
- P06 没有修改 SGLang source、wheel、checkpoint、dataset、proposal width 或
  P05 frozen config；formal arm 唯一变量是 `HEDGE_ENABLED=0`。

## Evidence and artifact paths

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T062241Z-p06-native-formal-r1
```

- `formal_outputs.jsonl` SHA-256：
  `ecd9952536a860836babc3451e066b4ea164b0e520e263bfc5c200f46e902607`
- `answer_summary.json` / `acceptance_summary.json`：
  `85564471483224bee25e33ba93b75ee06a019ded4ede959be4fb70b26a351cab` /
  `bc28fceeaf046236de6f87c034ffb0eccebd2b4f9da480f592fb100bdd433cb0`
- archive manifest：39 files；SHA-256
  `f0014a88b05761b47a85b841d052a13a2e6d6d4baa21bf4f3640b4e7c96beca7`
- P08 独立重放 client、timing、answer、acceptance、GPU、server、lifecycle、
  shutdown、keepalive 与 39-file size/SHA 全部 `PASS`。

## Source/config identity

- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- integration / patched tree：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36` /
  `69e80df97b815587a5b7b57665c99cd436b2ceb617dc71f31c7e44807ab82422`
- pure core：
  `4d96f44065c07030ede67484a262006ec149626a`
- formal wheel：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`
- checkpoint：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`
- dataset JSONL：
  `33554b90f751252ced2cfd16333d749f427c84cf025dccef4c7934144e9d5108`
- HEDGE：disabled，runtime config `null`

## Process, CUDA context and keepalive state

- 登记 server/sampler `94985/94992` 仅按 PID/PGID identity 定向 SIGTERM；
  main/cleanup rc=0，无 external signal。
- `cuda_contexts_after.txt` 证明 contexts none。
- dedicated keepalive 恢复为 `107326/107326/107326`，8×10 每卡
  mean/min/max 100%。
- TP/target/draft ranks 0–7；formal window 每卡 1982 samples，最低模型显存
  79619–80099 MiB，最大利用率 99–100%；无运行期 crash marker。

## First root cause / progress since prior attempt

P06 没有技术失败 attempt。formal tooling 在 live 前完成 138/138 回归与真实 P05
acceptance replay；唯一 live attempt 从 preflight、load、warmup、500 formal 到
cleanup/archive 一次通过。

## Main-Agent acceptance recommendation

历史主 Agent已于 `2026-07-29T07:32:56Z` 验收 `PASS`。P08 从 immutable
artifact 独立重算保持相同结论；本文只修复 standalone handoff 缺口。

## Next eligible phase

历史下一阶段为 `P07`。本文在 P08 追溯重建后停止，不自行进入其他阶段。
