# HEDGE on DeepSeek-V4-Flash Eagle3 实验记录

## 实验结果总览

面向结果阅读的独立报告见
[HEDGE × DeepSeek-V4-Flash-Eagle3 实验结果](../results/hedge-deepseek-v4-flash-eagle3.md)；
本文继续作为 attempt、artifact、故障归因和复现证据的唯一权威账本。

> **当前路线结论：Phase 06 `ACCEPTED/PASS`，Phase 07 待最终审计。**
> Native 与 HEDGE B+ 的 500 条正式 arm 均已完成根线程独立重算并发布唯一
> accepted marker；`B=0` 等价性为 `B0_PASS`，正预算参数只由 32 条
> calibration 决定。

### 一眼结论

- **Native 正式结果已成立：** 500/500 请求成功，0 failure/retry，
  74,580 completion tokens，客户端计时 4,411.045604754 秒，
  output TPS `16.9075558683`；GSM8K 488/500 匹配，0 parse failure。
- **Native speculative 指标：** 31,603 proposals、42,477 accepted draft
  tokens，accepted drafts/proposal `1.3440812581`，mean acceptance length
  `2.3440812581`。
- **零预算正确性已成立：** calibration 32/32 的完整输出 token IDs 与 native
  完全相同，结论为 `B0_PASS`。
- **正预算只由 calibration 决定：** `g=q25=6.75`、`B=6.75`、`m=1`、
  `value_scheme=normalized_suffix`；没有根据 formal 结果回调。
- **B+ 接入已通过 bounded smoke：** 3/3 成功，14 个 relaxed proposals
  带来 22 个相对 strict 的额外 accepted drafts；三条 request 的 budget
  continuity、accounting、非负约束和 `m<=1` 均无违例。该 smoke 只证明接入，
  **不是**正式性能或质量结论。
- **B+ 正式结果已成立：** 500/500 success，0 failure/retry，75,224
  completion tokens，客户端计时 4,209.940660915 秒，output TPS
  `17.8681853401`；GSM8K 488/500 匹配，0 parse failure。
- **本次路线内观测差值：** B+ output TPS 比 Native 高 `5.682%`，客户端墙钟低
  `4.559%`，accepted drafts/proposal 高 `8.888%`；两个 arm 的 aggregate
  GSM8K match 均为 488/500。

### 正式 500 条结果与路线内差值

| 指标 | Native formal | HEDGE B+ formal | B+ − Native |
| --- | ---: | ---: | ---: |
| 验收状态 | `ACCEPTED/PASS` | `ACCEPTED/PASS` | — |
| Formal terminal / success | 500 / 500 | 500 / 500 | 0 / 0 |
| Failure / generation retry / trace retry | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Completion tokens | 74,580 | 75,224 | +644（+0.864%） |
| 客户端正式墙钟 | 4,411.045604754 s | 4,209.940660915 s | −201.104943839 s（−4.559%） |
| Output TPS | 16.9075558683 | 17.8681853401 | +0.9606294718（+5.682%） |
| Proposals | 31,603 | 30,332 | −1,271（−4.022%） |
| Accepted draft tokens | 42,477 | 44,392 | +1,915（+4.508%） |
| Accepted draft tokens / proposal | 1.3440812581 | 1.4635368588 | +0.1194556007（+8.888%） |
| Mean acceptance length | 2.3440812581 | 2.4635368588 | +0.1194556007（+5.096%） |
| GSM8K matches | 488/500 | 488/500 | 0 |
| GSM8K mismatches / parse failures | 12 / 0 | 12 / 0 | 0 / 0 |

### 关键门禁与结果 artifact

| 项目 | 结果 / 路径 |
| --- | --- |
| B0 | `B0_PASS`；32/32 完整 token IDs 零差异 |
| 自动校准 | `g=B=6.75,m=1`；calibration SHA-256 `836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60` |
| Native accepted artifact | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02` |
| Native accepted marker | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-native-formal.complete.json` |
| B+ bounded smoke | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052500Z-phase-04-bplus-smoke-01` |
| B+ accepted artifact | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080100Z-phase-06-bplus-formal-01` |
| B+ accepted marker | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-bplus-formal.complete.json`；SHA-256 `7f6a95dc7e98b87c7de242887f32459bfa00050f67c0373e61f00f265661a812` |

## 执行状态与证据摘要

> **状态：`PHASE_06_BPLUS_FORMAL_ACCEPTED`；Phase 07 待执行。**
> DSpark 发布的 pure core 已以 Eagle3 commit
> `4cefd0a36ea254e4c14a83f35dc8db15b37a3384` 导入；10 个 canonical 文件与
> publisher commit `4d96f44065c07030ede67484a262006ec149626a` 逐字节一致。
> 同 hash 的四个 runtime core 文件已可复现注入固定 SGLang base，aggregate
> `53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815`。
> Eagle3 adapter、request budget lifecycle、rank-0 bounded proposal trace、
> scheduler clear/drain control 与客户端 fail-closed trace 归属已完成。
> 完整 13-file SGLang candidate patch SHA-256 为
> `13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945`，
> clean fixed-base replay 与联合回归均 PASS。主 Agent 已提交精确
> candidate，并由 identity finalizer 冻结 `sglang_final_sha` 为 `90c8558721de37ed0dc12802f29253ba52b873bc`；
> committed tree、patch、core 与 uv lock identity 均 PASS。Phase 03 source
> gate 已完成并经主 Agent 验收；Phase 04 已在同一最终 source 上启动。
>
> Phase 04 preflight 于 `2026-07-29T03:39Z` 复核 worker `4099544`、
> operational keepalive owner `315671` 与 8×10 样本逐卡 100%。native
> attempt 01 已到达 TP0–7、八卡 context、Eagle3 aux trace 与 HTTP ready，但在
> runner 前因执行中的 repo script 被 `apply_patch` 改写而触发 Bash 混合字节解析，
> 判定 `INVALID_ORCHESTRATION_MUTATION`，不构成 32 条结果。登记 SIGTERM 后
> 0 context，keepalive 新 owner `321562` 已恢复 8×10 每卡 100%。
> 冻结工具后的 native retry 02 再次达到 TP0–7、精确八卡 context 和 HTTP ready，
> 但 32/32 条都在 generation 前的 trace clear fail closed，0 次 generation。
> live 证据把 blocker 缩小到实际 registry seam：当前
> `enable_multi_layer_eagle=false` 选择 `EAGLEWorkerV2`，而 Phase 03 HEDGE
> lifecycle/observability 只接入了 `MultiLayerEagleWorkerV2`。服务已登记
> SIGTERM、无 KILL fallback，0 context 后 keepalive owner `328407` 恢复，
> 8×10 样本逐卡 100%。Phase 03 frozen authority 保持不变。最小 recovery 已由
> 主 Agent 独立审计并在 SGLang 本地提交为
> `2600c7b16c648d281be060b33ffadc7ae320f7e3`（未 push）；14-file fixed-base
> patch SHA-256 为
> `73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf`。
> post-commit source identity 与 17-file live-tool freeze 02 均已封存、自校验
> PASS；主 Agent再次复跑 DeepSpec 19/19、bash/pycompile 并确认 source clean。
> native retry 03 已在该冻结 source/tooling 上完成并由主 Agent 独立验收：
> 32/32 terminal、generation、trace success，0 retry/failure，5034 completion
> tokens，2116 proposal rows，32 个 unique sample IDs；38 个 artifact hash
> 逐项一致。请求窗口八卡均有 245 个样本、max utilization 93–97%、显存约
> 60.2–60.55 GiB，TP0–7 load 与 aux evidence 完整。登记 SIGTERM、
> `kill_fallback=false`，随后 0 CUDA context；keepalive owner `335940`
> 已恢复并通过 8×10 每卡 100%。
> 独立 `B=0` arm 同样完成 32/32、0 retry/failure；与 native 的 32 份完整
> token IDs 零差异，判定 `B0_PASS`。1486 个正 barrier 的 NumPy linear q25
> 已冻结为 `g=B=6.75,m=1`。唯一 bounded B+ 3-sample smoke 已完成：
> 3/3 terminal、generation、trace success，0 retry/failure，441 completion
> tokens、173 proposal rows、3 个 unique sample IDs；14 个 relaxed proposals
> 带来 22 个相对 strict 的额外 accepted drafts。三条 request 分别消费
> `6.75/6.75/6.375` risk budget，结束余额为 `0/0/0.375`，budget continuity、
> accounting、非负约束与 `m<=1` 均无违例。Phase 04 判定 COMPLETE/PASS；
> Phase 05 one-shot native formal 工具已完成根线程离线审计：
> 10 条固定 calibration warmup 后严格顺序 500 条 formal、最多 3 次总 attempt、
> 从首个 formal HTTP request 发出到第 500 条终态的单调时钟边界、完整 response /
> token IDs / proposal trace、可重算 TPS/acceptance，以及 HDFS 防覆盖和 accepted
> marker 防重均已固定。14-file tooling freeze 03 manifest SHA-256 为
> `625bc7f550bff9d02b004ac50f02a25e3f880db3422a465d6f9235a0eb66642d`，
> 自校验无差异；Phase 04 native server command/environment/source identity
> 逐字一致。正式 native 仍 pending，完整 500 条只先形成 candidate，待根线程验收
> 8 卡/rank/crash/hash/cleanup/keepalive 后才发布唯一 accepted marker。
> 首个 formal attempt `20260729T055400Z-phase-05-native-formal-01` 已从新服务达到
> HTTP ready、TP0–7 和八卡模型 context，但 runner 在 warmup 前因缺少 repo-root
> import bootstrap 报 `ModuleNotFoundError: deepspec`；因此 0 warmup、0 formal，
> 正式计时未开始，判定为 incomplete orchestration attempt。登记 SIGTERM、
> `kill_fallback=false`，0 CUDA context 后 keepalive owner `354555` 恢复为
> 8×10 每卡 100%。单变量修复只加入与 Phase 04 相同的 import bootstrap；
> repo 外 cwd 回归已 RED→GREEN。新 freeze 04 manifest SHA-256 为
> `e4a9bd2e25c959a449577889b504e1d9a7c3cc71e7fd6710ef815812f7640240`，
> 根线程 self-verify 无差异。retry 02 在同一冻结 source/config 上完成
> 10/10 warmup 与 500/500 formal：0 failure、0 generation retry、0 trace retry，
> 共 74,580 completion tokens，正式单调时钟 4,411.045604754 秒，
> output TPS `16.9075558683`；488/500 答案匹配、0 parse failure。31,603 个
> proposals 接受 42,477 个 draft tokens，accepted/proposal `1.3440812581`，
> mean acceptance length `2.3440812581`。TP0–7 target/draft load、aux trace
> 与正式窗口八卡参与证据完整；无未处理 crash。39 个 artifact hash 独立重算
> 一致，登记 SIGTERM、无 KILL fallback、0 model context 后 keepalive owner
> `364528` 恢复并通过 8×10 每卡 100%。根线程于
> `2026-07-29T07:42:58Z` 发布唯一 accepted marker，Phase 05 判定
> `ACCEPTED/PASS`。Phase 06 已冻结独立 B+ formal 工具：唯一配置为
> `enabled,g=B=6.75,m=1,value_scheme=normalized_suffix`，server command、
> source、model、dataset、proposal width、10+500 与计时协议均与 native 相同。
> 15-file freeze 01 manifest SHA-256 为
> `edc17c791fd0349163708b3dc649abde082af5ac76e1a06dd2c49962a09792d5`；
> 根线程 scoped 26 tests、bash/pycompile、freeze self-verify、native/B+ command
> identity 与 marker-absent gate 均 PASS。历史 Phase 05 mock test 在 native
> accepted marker 发布后会按其 pre-accept 默认门禁主动失败；该 frozen test
> 不为 post-accept 状态改写，Phase 06 的实际依赖与独立测试不受影响。
> 唯一 B+ attempt `20260729T080100Z-phase-06-bplus-formal-01` 已完成
> 10/10 warmup 和 500/500 formal success，0 failure、generation retry 与
> trace retry；共 75,224 completion tokens，正式单调时钟
> 4,209.940660915 秒，output TPS `17.8681853401`。30,332 个 proposals
> 接受 44,392 个 draft tokens，accepted/proposal `1.4635368588`，mean
> acceptance length `2.4635368588`。其中 2,121 个 relaxed proposals 相对
> strict 多接受 3,782 个 drafts；500 条 request 总计消费 3,120 risk budget，
> 196 条最终余额为 0，continuity、accounting、非负与 `m<=1` 违例均为 0。
> GSM8K 为 488/500 match、12 mismatch、0 parse failure。根线程逐行重算
> 500 份完整 response/token IDs、30,332 个 flattened proposal rows、答案、
> timing、acceptance 和预算，均与 summary 一致；39 个 artifact size/hash
> 零差异。TP0–7 target/draft/NCCL/aux evidence 完整，正式请求结束前无
> CUDA/NCCL/Traceback/worker crash。第 500 条 response 后才登记 SIGTERM，
> `kill_fallback=false`，0 context 后 keepalive owner `378796` 恢复并通过
> exact-eight 10×1 秒逐卡 100%。根线程于
> `2026-07-29T09:36:27Z` 发布 accepted marker，SHA-256 为
> `7f6a95dc7e98b87c7de242887f32459bfa00050f67c0373e61f00f265661a812`。
>
> **自主窗口（UTC）：** T0 `2026-07-28T20:56:27Z`；
> 实现门槛 `2026-07-29T05:56:27Z`；硬停止 `2026-07-29T08:56:27Z`。
> 上述为原始计划窗口；用户于 `2026-07-29T07:47Z` 明确取消后续截止时间，
> 授权继续朝完整目标执行，因此 Phase 06/07 不再受该硬停止约束。
>
> **权威 Phase 00 artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01`
>
> **权威 Phase 01A artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T211500Z-phase-01a-acquisition-01`
>
> **权威 Phase 01B artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T232000Z-phase-01b-final-17`
>
> **权威 Phase 02 target artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235505Z-phase-02-target-diagnostic-02`
>
> **权威 Phase 02 native/TDD artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T002900Z-phase-02-tdd-native-adapter-01`
>
> **权威 Phase 02 native live artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T012234Z-phase-02-native-smoke-02`
>
> **权威 Phase 03 handoff artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T030500Z-phase-03-hedge-adapter-01`
>
> **权威 Phase 04 recovery artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T042500Z-phase-04-eagle-worker-recovery-01`
>
> **权威 Phase 04 post-commit source identity：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T043100Z-phase-04-source-identity-01`
>
> **权威 Phase 04 live-tool freeze 02：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T043500Z-phase-04-tooling-freeze-02`
>
> **权威 Phase 04 native calibration artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T044000Z-phase-04-native-calibration-03`
>
> **权威 Phase 04 B0 calibration artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T050000Z-phase-04-b0-calibration-01`
>
> **权威 Phase 04 frozen calibration artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052000Z-phase-04-calibration-01`
>
> **权威 Phase 04 B+ bounded smoke artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T052500Z-phase-04-bplus-smoke-01`
>
> **权威 Phase 05 tooling freeze 03：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T055500Z-phase-05-tooling-freeze-03`
>
> **Phase 05 incomplete native attempt 01：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T055400Z-phase-05-native-formal-01`
>
> **权威 Phase 05 tooling freeze 04：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T060800Z-phase-05-tooling-freeze-04`
>
> **权威 Phase 05 native formal artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02`
>
> **Phase 05 accepted marker：**
> `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-native-formal.complete.json`
>
> **权威 Phase 06 tooling freeze 01：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080000Z-phase-06-tooling-freeze-01`
>
> **权威 Phase 06 B+ formal artifact：**
> `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080100Z-phase-06-bplus-formal-01`
>
> **Phase 06 accepted marker：**
> `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-bplus-formal.complete.json`

## 固定身份与复现配置

| 配置 | 值 |
| --- | --- |
| Lane | worker `4099544`, 8×H20, TP=8 |
| B0 status | `B0_PASS`；32/32 完整 token IDs 与 native 相同 |
| `g=q25` | `6.75` |
| `B` | `6.75` |
| `m` | 1 |
| Proposal tokens | 3 |
| Dataset seed | 980406 |
| Formal samples | 500 |
| DeepSpec source | branch `exp/hedge-v4-eagle3`; Phase 00 base `cac6c78d88df97d395406fe831f573df3016e7f7` |
| SGLang source | `/home/tiger/src/sglang-hedge-v4-eagle3`; fixed base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`; Phase 03 frozen patch/SHA 保持 `13fb7ced…3945` / `90c8558721de37ed0dc12802f29253ba52b873bc`; Phase 04 recovery local commit `2600c7b16c648d281be060b33ffadc7ae320f7e3`（未 push），14-file canonical patch `73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf`，canonical manifest `96f7a392eb3d9d01ae9070d1e45d5968cf97aad7fee10f0f6e30cef943cb8cae` |
| Target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`; 73 regular files，`159630041626` bytes，manifest `af6f274af9b0b257a6b910ae9b8ac4d0e1dd0a0bbcd96898fc6772c7e158facd`，published |
| Draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d`; 7 regular files，`1858538499` bytes，manifest `dfa6b2de48c46f4fda0cf7070466d35e6bd3df44b84ba0363616cc0f1f6020a0`，published |
| HEDGE core | source `9fb903d676254ea5f5d171051fb15c54f331111c`；DSpark publisher `4d96f44065c07030ede67484a262006ec149626a`；Eagle3 import `4cefd0a36ea254e4c14a83f35dc8db15b37a3384`；10-file byte identity 与 33 tests PASS |
| Formal artifacts | native `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02`，manifest `f9759d5e1826a752221b55367bb873db2ea1d72959092d52112675566105f8c1`，marker `0ce403530e58cdebb1cbbe9dd0d3c0ae534ecd697947f4348ea4e66d9aa7aea4`；B+ `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T080100Z-phase-06-bplus-formal-01`，manifest `09a341ac5d454cda191814d1970d748d0f1494deb284c0d419e601d7e70b7a1b`，marker `7f6a95dc7e98b87c7de242887f32459bfa00050f67c0373e61f00f265661a812` |
| Phase 01B runtime | Python 3.11；Torch `2.11.0+cu130`；CUDA `13.0`；NCCL `2.28.9`；FlashInfer `0.6.14`；Triton `3.6.0`；sglang-kernel `0.4.5+cu130`；201 packages，`uv pip check` PASS |
| Dataset split | GSM8K revision `740312add88f781978c0658806c59bc2815b9866`，fingerprint `59ec1b7f9357c7a2`；seed `980406`；32 calibration + 500 formal，overlap 0 |
| Runner fixture | 10 warmup + 500 formal，500 terminal/500 success/5 generation retries，最大 in-flight 1；Phase 03 另覆盖 generation 前 clear、成功后 drain、trace-only retry、不重发成功 generation、精确 response ID 归属和正式 timing 边界 |
| Phase 01C contract | logical `[1,21,40]` → hook `[2,22,41]` → 4-stream mean → `[N,3,4096]` → runner `[N,12288]`; 3 CPU tests PASS |
| Phase 01C research | `docs/research/hedge_eagle3_phase01c/eagle3_compatibility_research.md` |
| Phase 02 target | TP0–7、46/46 shards、packed FP4 `flashinfer_mxfp4`、八卡 context/API PASS；非正式 diagnostic |
| Phase 02 native | 3/3 terminal、6 completion tokens、proposal `3` / internal verify `4`、accepted `0/9`；八 rank Eagle3 aux trace PASS；非正式 smoke |
| Key commits | Phase 00 bootstrap `9369479acb6cbd88ae98a6e04446c6d50134feae`；Phase 01C contract `a8d913e8f200f02519a446ea77fcb235f2c76681`；Phase 01A publication `bb6ae8a92eac8c7d5a130b247835a01c70fe891b`；Phase 01B runtime `dccbb219faf25fa803cc27e26f59cc1b9786b9f4`；Eagle3 pure-core import `4cefd0a36ea254e4c14a83f35dc8db15b37a3384`；Phase 03 integration `d8ec6fcb9d90e57a9b5f8804c084a18b57bd60dd`（均已 push） |

## Phase 00：bootstrap 与 operational ownership

### 独立身份

| 资源 | Phase 00 结果 |
| --- | --- |
| DeepSpec worktree | `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3` |
| DeepSpec branch | `exp/hedge-v4-eagle3` |
| SGLang source path | `/home/tiger/src/sglang-hedge-v4-eagle3`，已确认无路径冲突，留给 Phase 01B 建立 |
| uv env path | `/home/tiger/venvs/deepspec-hedge-v4-eagle3`，已确认无路径冲突，本阶段未创建 |
| HTTP port | `31001`，Phase 00 reservation 时无 listener |
| Worker state | `/home/tiger/.deepspec-hedge-v4-eagle3`，仅有 session owner marker |
| Worker scratch | `/tmp/deepspec-hedge-v4-eagle3`，仅有 session owner marker |
| HDFS root | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3` |
| Coordination | `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-20260728T205627Z` |

### Worker 与进程结论

`mlx worker list` 再次显示 `4099544` 为 8×`NVIDIA-H20`。远端只读采集记录
hostname `g340-cd51-4b00-adb3-18a1-dd47-fb`，物理 GPU index `0..7` 均为
NVIDIA H20、每卡 `97871 MiB`、compute capability `9.0`。完整 UUID 和拓扑见
`worker_inventory.json` 与 `raw/gpu_topology.stdout.txt`。

采集时 `compute_pid_count=0`、`keepalive_candidate_pid_count=0`，所以没有旧任务需要
分类或等待。`existing_processes.json` 明确记录空进程集合和 `signal_sent=false`。
本阶段没有把空闲 worker 或显存占用写成 operational keepalive 成功；8 卡 keepalive
入口和 owner schema 只完成离线准备，尚未执行 10×1 秒逐卡门禁。

### 容量

只读 `df -B1` 记录：

- worker `/tmp`：总计 `3779301580800` bytes，可用 `3442749816832` bytes；
- HDFS：可用 `1124800395214848` bytes（FUSE 报告值，仅作容量观察）；
- shared filesystem：总计 `262092619776` bytes，可用 `121047613440` bytes。

### Phase 00 artifact

下列文件位于同一持久 run 目录：

- `bootstrap.json`
- `worker_inventory.json`
- `existing_processes.json`
- `worker_assignment.json`
- `deadlines.json`
- `phase-00-handoff.md`
- `namespace_bootstrap.json`
- `raw_commands.json` 与 `raw/` 全量命令输出

### Attempt 历史

| Attempt | Phase/mode | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- | --- |
| `20260728T205627Z-phase-00-bootstrap-01` | Phase 00 / CPU-only bootstrap | 新建 Eagle3 独立身份并只读 inventory | PASS，主 Agent 已验收 | 4099544 准确 8×H20 且两次 inventory 均无 compute PID/keepalive；未发 signal | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01` |
| `phase-01c-contract` | Phase 01C / CPU-only research + fixture | 固定 checkpoint、SGLang 与一手实现上建立 aux interface | PASS，主 Agent 复跑 3 tests | blocker 顺序缩小为 guard → V4 capture；TP ownership 明确保留到 Phase 02 live assertion | `docs/research/hedge_eagle3_phase01c/` |
| `20260728T223200Z-phase-01b-keepalive-05` | Phase 01B / operational keepalive | 首次用 lane-local torch/CUDA 闭包启动 8 卡 keepalive | FAIL，前后均为 0 context | `LD_LIBRARY_PATH` 误用 `/usr/local/cuda/compat`，CUDA 13 runtime 只看到宿主 driver 12.6；未叠加进程 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T223200Z-phase-01b-keepalive-05` |
| `20260728T223600Z-phase-01b-keepalive-06` | Phase 01B / operational keepalive | 唯一变化为已验证私有 CUDA 13 compat prefix | PASS，active | 8×10 样本逐卡 mean=100%；精确 owner/descendants、UUID、环境与设备用户证据通过 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T223600Z-phase-01b-keepalive-06` |
| `20260728T211500Z-phase-01a-acquisition-01` | Phase 01A / pinned acquisition | 双 keepalive gate 后启动唯一 target/draft 下载 | PASS，主 Agent 已验收 | 两个 provider commit/OID、manifest、size、index/config/tokenizer 和 HDFS entity 均通过；target marker 最后发布；0 symlink/hardlink | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T211500Z-phase-01a-acquisition-01` |
| `20260728T224200Z-phase-01b-full-env-07` → `...224500Z...-08` → `...224800Z...-09` | Phase 01B / isolated runtime | 每次只补齐当前缺失的 Rust，再补 pinned protoc | PASS | blocker 依次从缺 Rust 迁移至缺 protoc，最后 frozen sync、editable source import 与 `uv pip check` PASS | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T224800Z-phase-01b-full-env-protoc-09` |
| `20260728T230000Z-phase-01b-dataset-11` → `...230100Z...-12` | Phase 01B / pinned dataset | 仅修正本地 revision 常量的尾字符 | PASS | provider 对错误 revision fail-closed；固定 revision、fingerprint、确定性 split 与 request contract 经独立重算一致 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T230100Z-phase-01b-dataset-revision-12` |
| `20260728T230600Z-phase-01b-fixtures-13` → `...231000Z...-14` → `...231700Z...-15` | Phase 01B / runner/process fixtures | 先增加差异诊断，再仅对 lane-local loopback bypass inherited proxy | PASS | 定位 `HTTP_PROXY` 劫持 loopback；10+500、retry、B0、q25、答案解析和精确 PGID cleanup 全部通过 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T231700Z-phase-01b-fixtures-proxy-bypass-15` |
| `20260728T232000Z-phase-01b-final-17` | Phase 01B / authoritative seal | required artifacts 采用 temp→fsync→hash→atomic replace→post-validate | PASS，主 Agent 已验收 | 初次封存暴露 runner summary 零长度竞态；修复后 6 个 artifact 的 size/hash 与 manifest 全部独立复算一致，无 empty SHA | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T232000Z-phase-01b-final-17` |

## Phase 02：target diagnostic 与 native Eagle3 smoke

### 最小实现与可复现封存

Phase 02 按 TDD 完成 DeepSeek-V4 Eagle3 native adapter。目标模型的 logical layers
`[1,21,40]` 映射到 after-layer hooks `[2,22,41]`；每个原始 mHC tensor
`[N,4,4096]` 以 BF16 沿 stream 维求均值，按 logical layer 排序为
`[N,3,4096]`，再交付 runner 所需的 `[N,12288]`。实现明确隔离 DSpark capture，
并为每个 TP rank 只发一次 shape/dtype/device/checksum trace。

SGLang tracked runtime patch 为 `19290` bytes，SHA-256
`64ce797b2a4ac5f668557fb481f9577c4a72baf601c5350eee03dd4ad7e60fe2`；
source-side test 为 `9671` bytes，SHA-256
`2f32eecbe96c104352b9e9793da519abd339408044bc15b9a3c4994f3af5232b`。
两者已固化到 `patches/hedge_eagle3_phase02/`，并在固定 base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 的临时 clean worktree 上通过
`git apply --check` 和 11/11 tests；重放日志为
`canonical_clean_replay.log`，SHA-256
`99e52acf0c9e7c439ced3d525197e1deb948d2979a6d51c0635d63ac547a6024`。

native attempt 01 暴露 draft backend 继承错误：target 合法使用 `dsv4`，但
`LlamaForCausalLMEagle3` draft 的 `head_dim=128` 被送入只接受 DeepSeek-V4
`head_dim=512` 的 DSV4 backend assertion。单变量修复是只为 draft 显式设置
`flashinfer`，target 保持 `dsv4`。Phase 01B 的三臂配置源同时固定这一字段，保证后续
native、`B=0` 和 `B>0` 使用相同 decode-affecting server config。最终离线回归：
SGLang 11/11、Phase 01C 3/3、Phase 01B 6/6、Phase 02 safety 14/14 与 mock
10 warmup + 500 formal 全部 PASS；日志为 `offline_final_v3.log`，SHA-256
`b36b335cee4a615f3309a232b9740cb8c28b4afe925d675d0be33317701d9bdc`。

### Live 证据

target-only attempt 02 是隔离 diagnostic，不是 baseline：TP0–7 全部初始化，
46/46 target shards 加载完成，packed FP4 使用 `flashinfer_mxfp4`；八张物理 H20
均有 context/模型显存和请求期活动，OpenAI-compatible API 返回 HTTP 200 非空结果，
且无未处理 CUDA/NCCL/worker crash。

native attempt 02 使用相同 target、固定
`SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1` draft、TP=8、proposal tokens `3`
与 internal verify width `4`。TP0–7 均加载 `LlamaForCausalLMEagle3`，各 rank
明确记录 target `dsv4`、draft `flashinfer`，以及一次 Eagle3 aux trace：
raw shapes 均为 `[[4,4,4096]]*3`，structured `[4,3,4096]`，runner
`[4,12288]`，dtype BF16，device 分别为 local `cuda:0..7`。

服务 ready 后 3/3 顺序请求均 HTTP 200，保存完整响应和 output token IDs；共
6 completion tokens。三次 request 都有 `verify_count=1`、proposed draft
tokens `3`、accepted draft tokens `0`、histogram `[1,0,0,0]`，因此合计
accepted `0/9`。这是短回答基础设施 smoke，不是质量/性能评测；计划没有 acceptance
门槛，`0/9` 不影响 Phase 02 native bring-up PASS，也不能据此外推 calibration 或
formal arm。

native 请求窗口合计仅约 1 秒，1 秒粒度 sampler 在该切片捕获到 7/8 GPU 非零
utilization，GPU4 恰好漏采；因此不声称“精确请求窗口 sampled utilization 8/8”。
八卡参与结论由 TP0–7 各自的 forward aux trace、八张卡的 CUDA context/模型显存，
以及全服务期每卡 maximum utilization `100%` 共同支持。

server 登记身份为 `PID/PGID/SID=303437/303437/303437`。结束时仅向该 process
group 发送 SIGTERM，无 KILL fallback；随后验证八卡 CUDA context 为空。keepalive
恢复为 owner `315671`，准确 8 个 owned workers/context，8×10 个 1 秒样本逐卡
utilization 均为 `100%`。

### Attempt 历史

| Attempt | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- |
| `20260728T235315Z-phase-02-target-diagnostic-01` | 首次 target-only 编排 | FAIL CLOSED | `/proc/stat` 本地 Python one-liner 转义语法错误；服务未 ready，无模型结论；定向 SIGTERM、0 context、keepalive 恢复 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235315Z-phase-02-target-diagnostic-01` |
| `20260728T235505Z-phase-02-target-diagnostic-02` | 仅修正 sampler 编排语法 | PASS diagnostic | TP0–7、46/46 shards、packed FP4 backend、八卡参与和 HTTP 200 均证实；不作为 baseline | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T235505Z-phase-02-target-diagnostic-02` |
| `20260729T002900Z-phase-02-tdd-native-adapter-01` | test-first 实现 aux adapter 与 native harness | PASS offline | patch/test 固化；draft backend inheritance 由专用 RED→GREEN 缩小并修复；clean-base replay 11/11 PASS | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T002900Z-phase-02-tdd-native-adapter-01` |
| `20260729T010230Z-phase-02-native-smoke-01` | 首次 target+draft native 启动 | FAIL CLOSED | draft 误继承 target `dsv4`，`head_dim=128` 触发 DSV4 `head_dim=512` assertion；精确清理、0 context、keepalive 恢复 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T010230Z-phase-02-native-smoke-01` |
| `20260729T012234Z-phase-02-native-smoke-02` | 唯一变化为 draft backend `flashinfer` | PASS native smoke | 8 ranks target+draft/aux trace、3/3 HTTP 200、token IDs 与 acceptance trace 完整；accepted `0/9` 非质量门槛；无未处理 crash | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T012234Z-phase-02-native-smoke-02` |

## Phase 03：pure core 注入与 Eagle3 HEDGE adapter

### Core 与 source provenance

本路线没有复制 HEDGE 仓库中的 Qwen 编排、ticket、untracked docs/assets 或历史结论。
HEDGE source identity 固定为
`9fb903d676254ea5f5d171051fb15c54f331111c`；DSpark 发布 commit
`4d96f44065c07030ede67484a262006ec149626a` 的 10 个 pure-core tracked 文件，
与本路线 cherry-pick 后的
`4cefd0a36ea254e4c14a83f35dc8db15b37a3384` 逐文件 byte-identical，canonical
33/33 tests PASS。注入 SGLang 的四个 runtime 文件也逐字节等于两边 canonical
版本，aggregate SHA-256 为
`53ce6f3a4bb8d2ac6cc6a531f565455e15a7021fc2cce0a446ef3c1e7352a815`。

完整 SGLang final candidate 从固定 base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 生成，覆盖 Phase 02 native V4 aux
adapter、pure core、Eagle3 HEDGE glue、scheduler control 和两个 source test，
共 13 个文件、125075 bytes，patch SHA-256
`13fb7cedb5f87c8e912c77501139f7c9092b039294cd0213b0be340272d73945`。
临时 clean worktree 的 `git apply --check`、`git diff --check`、11 个 aux tests
与 21 个 HEDGE tests 均 PASS；重建完整 patch 后 hash 不变。主 Agent 还独立复跑
相同 13-file candidate，patch hash、injection aggregate 与 `uv.lock`
`b4c369d005163398e823c3a5eba939d913098a7242ddf16591c89857be7db946`
均一致，11+21 tests PASS。两次 replay log 因临时 worktree 绝对路径不同而 hash
不同；候选 patch 内容未变。

### Adapter 与观测协议

adapter 固定 proposal width `3`、internal verify width `4` 和 greedy top-k-one
chain，在 native strict verification 首次拒绝位置调用 pure-core
`choose_prefix_batch`。`disabled` 直接委托 native verifier，不分配或改变 risk
budget；`b0` 固定 `B=0,g=0,m=1`；`enabled` 固定 `B=g>0,m=1`。per-request
budget 绑定稳定 request-pool slot，并覆盖 reorder、slot reuse、natural finish、
cancel/abort 与 drain 后 serial mapping 清理。

proposal trace 只在 TP rank 0 保存有界 device ring；其余 rank 的 capacity 为 0，
静态早退且不记 dropped rows。schema 保存 aligned draft/target token IDs 与 logits、
regret、normalized-suffix value、strict/HEDGE accepted drafts、commit length、首次
strict barrier、budget before/after 和 request identity。scheduler
`/set_internal_state` 只接受 Eagle3 clear hook，`/server_info` 返回 trace envelope；
非 Eagle3 或缺 hook 时 fail closed。

客户端在每次 generation attempt 前 clear；generation 成功后按 response
`id == choices[0].meta_info.id` 精确 drain。trace-only retry 不重发已经成功的
generation，记录 generation/trace 各自状态与 retry；dropped rows、非单 DP、
3→4 shape 不符、active request state 非零或缺少当前 response ID 均 fail closed。
旧请求 foreign rows 可观测但不能冒充当前请求。正式计时从第一条 formal generation
实际发出开始，到最后一条 terminal record（包括最终 drain/retry）结束。

三臂 resolved config 的 TP、proposal width、target/draft、backend、graph/cache、
request 与 trace control 字段完全相同；只允许 HEDGE mode/config 和对应
enable/B/g 字段按 native、B0、B+ 变化。trace capacity 固定 `1024`，
`SGLANG_RAGGED_VERIFY_MODE=static`，`max_running_requests=1`，
`mem_fraction_static=0.60`。

### 离线验收与限制

- SGLang source：aux 11/11、HEDGE adapter/worker/scheduler 21/21 PASS；
- DeepSpec：pure core 33/33、Phase 03 15/15、Phase 01B tools 6/6、
  Phase 01C contract 3/3、Phase 02 safety 14/14 PASS，总计 71/71；
- 10 warmup + 500 formal mock runner：500/500 terminal success，
  5 generation retries，maximum in-flight 1，PASS；
- SGLang base→final `git diff --check` 与 Phase 03 Python `py_compile`
  PASS；DeepSpec staged code/docs 在排除 immutable nested
  `patches/hedge_eagle3_phase03/sglang-final-candidate.patch` 后
  `git diff --check` PASS。全量外层 staged check 的 20 条 trailing-whitespace
  warning 均来自该 canonical unified patch 的单空格 blank context marker
  被外层 added-file diff 显示为 `+ `；不是 SGLang source whitespace defect，
  不得为消除 warning 改写 patch bytes；
- Phase 02 backend-route 正交测试改用已审阅的 Phase 02
  `source_identity` fixture，以免 Phase 03 合法新增文件触发历史 gate；
  `resolver.assert_source_state` 实现与独立 source-drift 负向测试均未修改并继续 PASS。
- 首次真实 freeze 后的回归暴露 finalizer fixture 仍假设 authority files 含 pending
  placeholder；TDD 修正后，pending→frozen 保持原文案覆盖，同一真实 SHA 重跑
  byte-identical 且保留原 `finalized_at_utc`，另一 SHA 在任何写入前 fail closed。
  frozen SHA `90c8558721de37ed0dc12802f29253ba52b873bc` 的完整 CLI 重放 PASS，
  本地 authority hashes 不变，HDFS authority files 再次一致。

本阶段未运行模型或 GPU，因此不产生 B0、calibration、acceptance、TPS 或 GSM8K
结论。operational keepalive 未被暂停或替换。manifest 状态为
`FINAL_CANDIDATE_FROZEN`，final SHA `90c8558721de37ed0dc12802f29253ba52b873bc` 已通过确定性 identity
核验；Phase 03 source freeze PASS，主 Agent 验收后可进入 Phase 04。

### Attempt 历史

| Attempt | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- |
| `20260729T030500Z-phase-03-hedge-adapter-01` | 从已验收 native source 导入 byte-identical pure core，并接入 Eagle3-specific adapter/control/runner | FINAL SOURCE FROZEN PASS；final commit 90c8558721de37ed0dc12802f29253ba52b873bc | 真实 verifier 的第二返回值必须保持 drafts-only，最终 bonus 只在 `eagle_sample` 加一次；历史 Phase 02 source identity test 已正交隔离，全部联合回归收敛 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T030500Z-phase-03-hedge-adapter-01` |
| `phase-03-finalizer-idempotence-correction` | 唯一变化为冻结状态下 finalizer 的 identity state machine 与对应 fixture | PASS；DeepSpec 71/71 | 真实 frozen repo 不再误走 pending 文案转换；same SHA no-op、different SHA pre-write reject，SGLang candidate 未改 | 同上 authoritative Phase 03 artifact |

## Phase 04：calibration live 与 bounded recovery

### Native attempt 历史

| Attempt | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- |
| `20260729T034000Z-phase-04-native-calibration-01` | 首次用 Phase 04 runner 启动 native 32 | INVALID；0 outputs | live repo script 被改写，运行中的 Bash 混读旧 offset 与新 bytes；属于 orchestration mutation，不是模型或 SGLang crash | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T034000Z-phase-04-native-calibration-01` |
| `20260729T040000Z-phase-04-native-calibration-02` | 16-file tooling freeze 校验 PASS 后原样重试 | FAIL CLOSED；32 terminal、0 generation、32 trace failures、64 trace retries | HTTP ready 后每次 pre-generation clear 都返回 `eagle3_hedge_clear_info_records requires an Eagle3 draft worker`；resolved config 的 `enable_multi_layer_eagle=false` 使 registry 选择缺少 HEDGE hooks 的 `EAGLEWorkerV2`，而不是已接入的 `MultiLayerEagleWorkerV2` | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T040000Z-phase-04-native-calibration-02` |
| `20260729T044000Z-phase-04-native-calibration-03` | 唯一变化为使用已审计的 concrete-worker recovery source 与 freeze 02 原样重试 | PASS；32/32 terminal/generation/trace success，0 retry/failure | blocker 已解除；5034 completion tokens、2116 proposal rows、32 unique sample IDs，38 个 artifact hash 精确一致；主 Agent 独立验收通过 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T044000Z-phase-04-native-calibration-03` |

retry 02 的服务命令、checkpoint、TP=8、proposal `3` / internal verify `4` 和
decode 配置与冻结 preflight 一致；TP0–7 全部初始化，八卡均有约 60.4 GiB model
context。runner 正确把 clear 失败记录为终态，不把 0 次 generation 冒充 native
结果。服务收尾使用登记 PGID 的 SIGTERM，`kill_fallback=false`；随后
`cuda_contexts_after.json` 为 `PASS` 且 contexts 空。恢复后的 keepalive owner
`328407` 通过 8×10 样本逐卡 mean=100%。

这是 blocker 迁移：runner/API shape 和 frozen tooling 已在真实服务上工作到 clear
control；缺口被缩到 registry 实际选择的 concrete worker。recovery 只允许把同一
HEDGE adapter 的 bind/verify/finish/dump/clear public lifecycle 接入
`EAGLEWorkerV2`，不改变 proposal、server command、core 语义或 Phase 03 frozen
authority。新 source patch、测试和 identity 作为独立 Phase 04 recovery artifact
交主 Agent审核；审核/提交前不再启动 GPU attempt。

recovery 采用四个 bounded RED→GREEN seam：registry-selected worker lifecycle、
仅 Eagle3 构造 adapter、prefill target forward 前 `bind_batch`、shared verifier
传入同一 adapter；disabled native delegation 和单层 worker 原有
`finalize_tree_path=true` 均保持。主 Agent审计后把两文件 recovery 本地提交为
`2600c7b16c648d281be060b33ffadc7ae320f7e3`，SGLang worktree clean。新的
`patches/hedge_eagle3_phase04/` authority 固定 14-file patch
`73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf`
与 manifest
`96f7a392eb3d9d01ae9070d1e45d5968cf97aad7fee10f0f6e30cef943cb8cae`；
Phase 03 local/HDFS patch 仍为 `13fb7ced…3945`，未被改写。

post-commit source identity 位于
`20260729T043100Z-phase-04-source-identity-01`，自包含 patch hash 与 canonical
一致。live-tool freeze 02 位于
`20260729T043500Z-phase-04-tooling-freeze-02`，manifest SHA-256
`6470fa217af2f9a0cb3d3e899f629ecbe56d8ecb582ed2dde63312057e7e01ce`；
17 个文件 self-verify `file_differences=[]`，三 arm server command 逐字一致。
executor 回归为 DeepSpec Phase 03+04 19/19、source aux 11/11、HEDGE 25/25；
主 Agent另行复核 source SHA/patch、freeze self-check、DeepSpec 19/19 与
bash/pycompile 全部 PASS。

native retry 03 使用 SGLang final SHA
`2600c7b16c648d281be060b33ffadc7ae320f7e3`、14-file patch
`73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf`
和 freeze 02 未变配置。32 条 calibration 全部 generation 与 trace 成功，0
generation/trace retry、0 failure，最大 in-flight 为 1；完整输出与 token IDs、
5034 completion tokens、2116 proposal rows 和 32 个 unique sample IDs 均已封存。
artifact manifest 的 38 个文件 size/hash 经主 Agent 独立重算全部一致。

TP0–7 均完成 target 与 `LlamaForCausalLMEagle3` load，并保留 aux evidence。
请求窗口八张物理 H20 各有 245 个 sampler 样本，逐卡 maximum utilization 为
93–97%，模型显存约 60.2–60.55 GiB。服务只向登记 process group 发送 SIGTERM，
`kill_fallback=false`；随后 CUDA context 精确为空。operational keepalive 恢复为
owner `335940`，独立 8×10 gate 的逐卡 utilization 均为 100%。

独立 B0 arm 使用完全相同的 SGLang source、server command、checkpoint、TP=8、
proposal `3` / internal verify `4`；唯一预期差异为 HEDGE mode/config：
`B=0,g=0,m=1,value_scheme=normalized_suffix`。32/32 terminal/generation/trace
success，0 retry/failure，5034 completion tokens、2116 proposal rows、32 个
unique sample IDs。主 Agent逐项比较 native/B0 完整 token IDs，mismatch count
为 0，故 `B0_PASS`。trace 中有 1486 个正 strict-rejection barrier 可进入固定
q25 计算。B0 artifact manifest 的 38 个 size/hash 全部匹配；请求窗口每卡 249 个
采样，八卡 max utilization 95–98%。TP0–7 load/aux evidence 完整，无未处理
CUDA/NCCL/worker crash。登记 SIGTERM、`kill_fallback=false`、0 context 后，
keepalive owner `342599` 通过 8×10 每卡 100%。

离线 calibration 对两份 frozen JSONL 正式重算 `B0_PASS`，从 1486 个正
`regret/value` 以 NumPy `method=linear` 得到 q25=`6.75`，故唯一正预算配置为
`g=B=6.75,m=1,value_scheme=normalized_suffix`。frozen calibration SHA-256
为 `836ca7c46274cfa3546f5f36d8b1e49e51edd68db2d125b2dbfe57c1075e2e60`，
B+ config SHA-256 为
`87a41b12f62059126b9e7d8f13b8b80cedc31e7de1f23655c93a60b4ff3e131a`。
主 Agent独立重算 q25 与 canonical calibration hash 均一致。live resolver 继续
单独强制最终 SGLang SHA `2600c7b…` 与 patch `73de4048…`；校准未触碰 GPU，
keepalive 持续运行。

唯一 bounded B+ smoke 使用同一 freeze 02、最终 SGLang
`2600c7b16c648d281be060b33ffadc7ae320f7e3`、canonical patch
`73de40486eae43901c84d60a9baa2c89026a416359dce89761b8ff9e7fc432cf`
和与 native/B0 逐字相同的 server command；仅 HEDGE mode/config 切换为
`enabled`、`B=g=6.75,m=1,value_scheme=normalized_suffix`。结果为 3/3
terminal/generation/trace success，0 retry/failure，441 completion tokens、
173 proposal rows、3 个 unique sample IDs，答案 3/3 匹配且 0 parse failure。
38 个 artifact 的 size/hash 经主 Agent独立重算全部一致。

live proposal trace 证明跨 request 持续预算实际生效：14 个 relaxed proposals
相对 strict verifier 多接受 22 个 drafts；三条 request 的累计 spend 分别为
`6.75/6.75/6.375`，最终 remaining 分别为 `0/0/0.375`。逐 proposal 的
before/after continuity、`remaining_after = remaining_before - spent`、
remaining 非负与每 block `relaxed_mismatches<=1` 均无违例。

TP0–7 target/draft load 与 Eagle3 aux evidence 完整。请求窗口八张卡各有 20 个
sampler 样本，除 GPU3 的短窗口 maximum utilization 为 21% 外，其余为 93–98%；
八卡均保持约 60.2–60.5 GiB 模型显存，且 TP/context/aux 证据完整，因此该短采样
不构成 rank 缺席。服务仅向登记 process group 发送 SIGTERM，
`kill_fallback=false`；随后 CUDA context 精确为空。operational keepalive
恢复为 owner `348863`，准确 8 个 owned worker/context，8×10 样本逐卡
utilization 均为 100%。

## Phase 05：Native formal 500

### Attempt 历史

| Attempt | 单一变化 | 结果 | 根因/新证据 | Artifact |
| --- | --- | --- | --- | --- |
| `20260729T055400Z-phase-05-native-formal-01` | 首次使用冻结 one-shot formal wrapper | INCOMPLETE；0 warmup / 0 formal | repo 外 cwd 缺少 import bootstrap，runner 在请求前报 `ModuleNotFoundError: deepspec`；正式计时未开始，不构成 formal 结果 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T055400Z-phase-05-native-formal-01` |
| `20260729T061100Z-phase-05-native-formal-02` | 唯一变化为加入与既有 runner 相同的 repo-root import bootstrap | `ACCEPTED/PASS`；10 warmup + 500/500 success | 74,580 tokens、4,411.045604754 秒、16.9075558683 TPS；完整 trace/hash/GPU/cleanup/keeper 经根线程独立验收 | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260729T061100Z-phase-05-native-formal-02` |

retry 02 使用最终 SGLang SHA
`2600c7b16c648d281be060b33ffadc7ae320f7e3`、TP=8、proposal width 3、
internal verify width 4 和固定请求协议。500 条全部成功，0 failure、
generation retry、trace retry；GSM8K 488 match、12 mismatch、0 parse
failure。31,603 个 proposals 接受 42,477 个 draft tokens，
accepted/proposal `1.3440812581`，mean acceptance length
`2.3440812581`。

39 个 artifact 的 size/hash、flattened trace、答案、计时和 summary 经根线程
独立重算无差异。TP0–7 target/draft/NCCL/aux evidence 完整，正式窗口八卡参与，
无未处理 CUDA/NCCL/worker crash。第 500 条达到终态后才登记 SIGTERM，
`kill_fallback=false`；0 context 后 exact-eight keepalive 恢复。accepted marker
于 `2026-07-29T07:42:58Z` 发布，SHA-256
`0ce403530e58cdebb1cbbe9dd0d3c0ae534ecd697947f4348ea4e66d9aa7aea4`。

## Phase 06：HEDGE B+ formal 500

唯一 B+ formal 工具在
`20260729T080000Z-phase-06-tooling-freeze-01` 冻结，15 个文件 self-verify
无差异，freeze SHA-256
`edc17c791fd0349163708b3dc649abde082af5ac76e1a06dd2c49962a09792d5`。
Native 与 B+ 的 server command 逐字相同；source、target/draft revisions、TP、
proposal width、warmup、formal split、请求与计时协议均相同，只切换：

```text
SGLANG_EAGLE3_HEDGE_MODE=enabled
g=6.75
B=6.75
m=1
value_scheme=normalized_suffix
```

唯一 attempt `20260729T080100Z-phase-06-bplus-formal-01` 完成 10/10 warmup
和 500/500 formal success，0 failure、generation retry、trace retry。
正式结果为 75,224 completion tokens、4,209.940660915 秒、output TPS
`17.8681853401`；GSM8K 488 match、12 mismatch、0 parse failure。

30,332 个 proposals 接受 44,392 个 draft tokens，accepted/proposal
`1.4635368588`，mean acceptance length `2.4635368588`。Strict verifier
本身接受 40,610 个 drafts；2,121 个 relaxed proposals 相对 strict 多接受
3,782 个 drafts。500 条 request 的 budget trace 均可检查，总消费 3,120，
196 条最终余额为 0；budget continuity、accounting、nonnegative 和每 block
`m<=1` 违例均为 0。

根线程独立重算了 500 条 source order、完整 response/token IDs、答案解析、
正式 timing、30,332 个 proposal rows、flattened trace、acceptance distribution
与逐 request budget；summary 和 39 个 manifest artifact 的 size/hash 均零差异。
关键 hash 为：

```text
summary             2800474a2a8eb59bb217ed988502c446c24be1e2aa30d50d0edd13f6374baad9
request_outputs     062c19f6573eaaf709fe2638f74cc4bbda2d19956811827bf25d4eb89bb90b44
acceptance_trace    cb0c90da0ba686beaae6aedb72815f49de27b33f2b0fedcb07736c2e7474ca16
artifact_manifest   09a341ac5d454cda191814d1970d748d0f1494deb284c0d419e601d7e70b7a1b
formal_result       d5ad2dbd8139b590073c945a2e881cf257d03cc47188012a217ac81d1dde0f43
```

TP0–7 target/draft/NCCL/aux evidence 完整；保守 formal-window 每卡各有
3,546 个 GPU samples、max utilization 均为 98%，显存不低于 60,267 MiB。
正式请求结束前精确错误模式下的 CUDA/NCCL/Traceback/worker crash 均为 0。
第 500 条 response 后才登记 SIGTERM，`kill_fallback=false`；0 context 后
keepalive owner `378796` 恢复 exact-eight，10×1 秒逐卡 100%。

accepted marker 于 `2026-07-29T09:36:27Z` 发布：

```text
/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/eagle3-bplus-formal.complete.json
SHA-256 7f6a95dc7e98b87c7de242887f32459bfa00050f67c0373e61f00f265661a812
```

本次路线内差值为：completion tokens `+644`（`+0.864%`），客户端墙钟
`-201.104943839` 秒（`-4.559%`），output TPS `+0.9606294718`
（`+5.682%`），accepted draft tokens/proposal `+0.1194556007`
（`+8.888%`），GSM8K aggregate match 差值为 0。完整单表与 artifact/hash
入口见独立[结果报告](../results/hedge-deepseek-v4-flash-eagle3.md)。

## 下一步

Phase 06 已 `ACCEPTED/PASS`。下一阶段只执行 Phase 07：独立交叉审计 Native/B+
marker、artifact/hash、结果报告、复现命令和限制，确认 exact-eight keepalive
仍健康，完成最终文档/commit/push 收尾；不再运行新的 formal arm。
