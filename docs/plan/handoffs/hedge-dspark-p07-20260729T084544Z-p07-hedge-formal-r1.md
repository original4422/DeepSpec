# HEDGE DSpark P07 handoff

- Status: `PASS`
- Attempt ID: `20260729T084544Z-p07-hedge-formal-r1`
- Started / finished: `2026-07-29T08:45:44Z` /
  `2026-07-29T09:45:19Z`
- Autonomy elapsed / deadline: session window started
  `2026-07-28T20:54:41Z`; the user removed the original deadline at
  `2026-07-29T07:47:18Z`; current deadline is `NONE`
- Git branch / HEAD / worktree: `exp/hedge-v4-dspark` /
  launcher-start HEAD `ca3f5b4`; P07 tooling `3253062` /
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
- Worker / GPU lane: `4106666` / exact 8×NVIDIA H20
- TP ranks / GPU participation: TP/target/draft ranks 0–7；formal window
  每卡 1909 samples
- Authorized phase: bounded `P07` only

## Outcome

唯一 HEDGE `B>0` formal attempt 完成并由主 Agent验收 `PASS`。10 条 warmup
排除计时，500 条 formal 全部达到终态：

- success / failed / retry：`500 / 0 / 0`
- completion tokens：`75819`
- timed wall seconds：`2263.710352404`
- end-to-end output TPS：`33.493242595936465`
- GSM8K match / mismatch / parse failure：`474 / 13 / 13`
- proposals / proposed drafts / accepted drafts：
  `15386 / 76930 / 60357`
- accepted drafts/proposal：`3.922851943325101`
- acceptance length including bonus：`4.927791498765111`
- accepted by position：`[14779, 13649, 12278, 10688, 8963]`

相对 P06 native，TPS `+5.4412212837109175%`，accepted drafts/proposal
`+7.643116362511315%`，含 bonus acceptance length
`+5.995676056634869%`；GSM8K match rate 从 `95.6%` 到 `94.8%`
（`-0.8` percentage point）。这些是单次运行观察值，不是成功门槛。

## Changes

P07 没有修改 SGLang source、wheel、checkpoint、dataset、HEDGE config 或任何
decode-affecting参数。唯一正式变量是相对 P06 将 HEDGE 从 disabled 切换为：

```text
HEDGE_ENABLED=1
SGLANG_DSPARK_HEDGE_CALIBRATION_TRACE=0
g=B=2.0625
m=1
value_scheme=normalized_suffix
block_size=5
```

没有第二 attempt、resume、append、stitch、并发或重启。phase executor 未
commit/push，也未进入 P08。

## Evidence and artifact paths

- immutable HDFS run：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T084544Z-p07-hedge-formal-r1`
- `formal_outputs.jsonl`：
  `615063928d19a8d5274bc669dc1ce1e7ce538c3b59ba21ce9b49e135d5078668`
- `answer_summary.json`：
  `1d1a1cdd23c4d17a875d28d5b1e5a0152b1c45f7cb6bbf61e3d252e61e448fa0`
- `acceptance_summary.json`：
  `069e8d2b058cf451d8c9c9b3d2f44d1bb32cad6ca1ef4ff101cd98c221498505`
- `hedge_counters.json`：
  `5f0874f54da28145e44a5911b45d8aaab3f058ea5a545bd6a4b8889ee8eca7e0`
- `artifact_validation.json`：
  `76fb72f39c31f0b4ae9b7a8a4f5d4c2902cf004968d67e393379099f1cc58cb2`
- `archive_manifest.json`：
  `397462adbd28aea5e8df8f275c2d1947bf29d297b5c84747ca6bf7c6a5bdb082`

主 Agent从 HDFS 原始文件独立重放 client、HEDGE snapshot、GPU window、
identity、server log、lifecycle、shutdown 和 keepalive validator，并逐项重算
manifest 中 39 个文件的 size/SHA；全部匹配。

## Source/config identity

- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- integration：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36`
- patched tree：
  `69e80df97b815587a5b7b57665c99cd436b2ceb617dc71f31c7e44807ab82422`
- pure core：
  `4d96f44065c07030ede67484a262006ec149626a`
- formal wheel：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`
- checkpoint identity：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`
- formal dataset JSONL：
  `33554b90f751252ced2cfd16333d749f427c84cf025dccef4c7934144e9d5108`
- config SHA/fingerprint：
  `760128b85b8c3dd67e3b4dee512cc302ee59bd2e2a1b3ab3390fd186ade36b71` /
  `6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921`

P06/P07 resolved/runtime identity parity 全部 PASS；差异仅限 phase/arm/attempt/
scratch 与 HEDGE enable/config 字段。

## Process, CUDA context and keepalive state

preflight dedicated keepalive PID/PGID/SID `107326` 的 8×10 每卡
mean/min/max 均 100%。launcher 紧邻暂停后证明 contexts none，登记 server
PID/PGID/SID `109060` 与 sampler `109075`。

formal 终态后仅对这两个登记 process group 定向 SIGTERM；main/cleanup rc=0，
无 external signal。`cuda_contexts_after.txt` 于 `09:44:27Z` 证明
`contexts=none`。dedicated keepalive 恢复为 PID/PGID/SID
`121312/121312/121312`，8×10 每卡 mean/min/max 100%。server log 中 shutdown
后的 `Killed`/detokenizer `-15` 发生在登记 SIGTERM 之后；运行期 crash marker
为空。

## First root cause / progress since prior attempt

P07 live 没有技术失败。它在主 Agent放行前完成四类 static RED→GREEN：
wrapper marker 清理、retry-aware request bounds、snapshot schema/alignment/
score-seam identity，以及逐位置/lifecycle/budget 物理不变量。唯一 live attempt
随后从 load、ready、warmup、formal 到 cleanup/archive 一次通过。

authoritative counters：

- strict/HEDGE accepted：`56642 / 60357`（`+3715`）
- relaxed mismatches：`1427`
- regret charged / remaining / initial：
  `723.75 / 307.5 / 1031.25`
- budget exhaustion / cap trim：`0 / 0`
- initialized / finished / non-natural：`500 / 500 / 1`
- active / state leak：`0 / 0`

## Main-Agent acceptance recommendation

- Status: `PASS`
- Accepted at: `2026-07-29T09:52:49Z`
- Independent result: formal summary、timing、HEDGE counters、P06 identity
  parity、TP8/GPU、server、shutdown/contexts/keepalive、39-file manifest 均
  `PASS`
- Overall route status remains `IN_PROGRESS` until P08 final offline audit

## Next eligible phase

`P08` 最终离线审计已具备入口条件。P08 不启动模型，只读取 P00–P07 原始
artifact，重算最终 JSON/Markdown/delta/manifest，并完成权威实验与进展记录。
