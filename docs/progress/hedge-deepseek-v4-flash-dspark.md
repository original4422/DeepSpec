# HEDGE × DeepSeek-V4-Flash-DSpark 进展

## 最新快照

- 状态：`IN_PROGRESS`
- 快照时间：`2026-07-29T08:23:59Z`（690 分钟 checkpoint 提前 42 秒）
- 自主窗口：始于 `2026-07-28T20:54:41Z`；用户于
  `2026-07-29T07:47:18Z` 明确解除原 `2026-07-29T08:54:41Z` 截止
- elapsed / deadline：持续执行 / `NONE`
- 当前 phase：P00–P06 均已 PASS；P07 `IN_PROGRESS`
- executor / 结论：
  - P00：主 Agent 验收 `PASS`；support commit/push `ebe196608893bd9972e771644ed25d019444d0f3`
  - P01：主 Agent 验收 `PASS`，commit/push `77053dd`
  - P02：主 Agent 验收 `PASS`；新正式 venv 33/33 tests PASS，commit/push `4d96f44065c07030ede67484a262006ec149626a`，READY marker 已发布
  - P03：主验收 `PASS`；integration `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc` 与 identity/progress `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3` 均已 push
  - P04：主 Agent 验收 `PASS`；结果 commit/push `3e10b780264557e84a3cab5c1a196dc7c2a00496`
  - P05：native r1/r2/r3 的三类失败证据保持；最小 engine recovery
    `e028d2c31658a06b4f5a5ee072d7e21c79d51c36` 与新 formal wheel
    `a5c14bd7…71f9` 已主审/push；唯一 native r4 已 32/32、scoped trace、
    TP8/GPU/cleanup/archive 主审 `PASS`；唯一 B0 32/32 完整 token IDs
    等价 PASS；reducer 冻结 `g=B=2.0625,m=1`；commit/push `c244651`
  - P06：formal tooling 138/138 与主 Agent复验 PASS，commit/push `6a74186`；
    唯一 native formal 500/500、0 retry、74594 tokens、31.76484698125425 TPS；
    主 Agent独立重算与 TP8/GPU/HEDGE-off/cleanup/archive 全 PASS
  - P07：static 首轮 targeted 11/11、总回归 149/149；主审追加四项
    fail-closed 修正，marker 已 RED→GREEN，retry 501 fixture 已 RED，
    summary-bound/schema/counter 修正进行中；尚未登录 worker/live
- worker / lane：`4106666` / 全部 8×NVIDIA H20 / 预定 TP=8
- keepalive / server / PID：P06 server/sampler 已定向退出、contexts none；
  dedicated keepalive `107326/107326/107326` 已恢复，8×10 全卡 100%
- 最新 attempt：`20260729T062241Z-p06-native-formal-r1`；preflight/ready PASS，
  10 warmup 排除，500/500 与完整生命周期主审 PASS
- 最新 immutable HDFS artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T062241Z-p06-native-formal-r1`
- Git：worktree `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`；
  branch `exp/hedge-v4-dspark`；上一 checkpoint HEAD/origin clean `5dd7acf`
- commits：P00 support `ebe196608893bd9972e771644ed25d019444d0f3`；P01 protocol
  `77053dd`；pure core `4d96f44065c07030ede67484a262006ec149626a`；integration
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`；P04 result `3e10b780`；
  P05 tooling `ce5d672`；sampler recovery `6b7145d`；trace-scope recovery
  `eb4962f`；failure docs `fd88b69`；quiescence recovery `fe0aea0`；
  r2/recovery experiment `3c37a41`；r3 load heartbeat `9e4aceb`；prefill
  lifecycle recovery `e028d2c`；wheel/identity `ada6625`；calibration freeze
  `c244651`；P06 tooling `6a74186`
- 首要事项：完成 P07 主审四项 static 修正与全回归；PASS 后才启动唯一
  HEDGE B>0 executor
- 下一检查点：`2026-07-29T08:54:41Z`
- 下一 30 分钟动作：完成 retry-aware lifecycle、snapshot identity、物理 counter
  forged gates、回归/主审/tooling commit；随后执行唯一 B>0 preflight

> Recorder 边界：60 分钟 checkpoint 只转录当时已交接的证据；随后 P00 主验收由
> 主 Agent 直接复核 canonical artifacts。文档更新没有改变 keepalive/GPU 运行态。

## 时间线

### 2026-07-28T20:54:41Z — 自主窗口启动

- session attempt：`20260728T205441Z-p00-bootstrap`
- deadline：`2026-07-29T08:54:41Z`
- 权威 lane：worker `4106666` 全部 8 卡，TP=8
- worktree / branch：`DeepSpec-hedge-dspark` / `exp/hedge-v4-dspark`

### 2026-07-28T20:56:10Z — P00 inventory 证据

- `worker_inventory.json` 记录 8 张 `NVIDIA H20`，索引 0–7，inventory gate 通过。
- 当时没有 compute context；尚未启动模型服务。

### 2026-07-28T21:05:17Z — P00 首次环境 attempt

- attempt 在 `2026-07-28T21:10:07Z` 封存。
- 首个根因是 launcher 环境中 `uv: command not found`；未形成
  `environment_identity.json` 或 P00 PASS。

### 2026-07-28T21:10:37Z — P00 env-r1

- env-r1 启动并复用已固定到
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 的独立 SGLang source。
- `2026-07-28T21:16:24Z` evidence 显示该 attempt 因访问 GitHub 时
  `SSL connection timeout` 封存；P00 环境仍未完成。
- 同期 keepalive artifact 为 `PASS`：8 卡各 10 个一秒样本均值 100%，supervisor
  PID/PGID/SID `1697`。

### 2026-07-28T21:12:10Z — P02 handoff

- handoff 状态：`READY_FOR_MAIN_AGENT_REVIEW`。
- 现有两个 CPU-mode 环境中的 33 tests 均通过。
- 最终 P02 PASS 仍明确依赖新 HEDGE venv 重跑、主 Agent 审核、pure-core
  commit/push 和匹配的 HDFS READY marker。

### 2026-07-28T21:18:16Z — 首版 recorder 快照

- P01 已出现固定 revision/seed 的 32 calibration 与 500 formal JSONL、manifest
  和 protocol config；仍无 P01 handoff/tooling test log，故只记为待验收 evidence。
- P00/P01/P02 均未由 recorder 宣称 PASS。

### 2026-07-28T21:24:41Z — 30 分钟 checkpoint

- 实际落盘时间：`2026-07-28T21:25:22Z`，比计划 checkpoint 晚约 41 秒。
- P00：env-r2 `20260728T211739Z-p00-env-r2` 正在从现有 uv cache copy，venv
  约 6.7 GiB，属于实质进展；最近 keepalive gate 记录 supervisor `1697` 且 8 卡
  均为 100%。P00 尚未 PASS，模型 server 尚未启动。
- P01：handoff
  `docs/plan/handoffs/hedge-dspark-p01-20260728T205900Z.md` 已完成；主 Agent
  独立运行 13 tests PASS、`verify-dataset` 18/18 true，另行复算 indices/hash
  全 true。主 Agent review `PASS`，但 P01 尚未 commit。
- P02：主 Agent 独立运行 pinned-torch 33/33 tests，并核对 identity 的 7 个 source
  与 9 个 target hashes 全匹配；阶段仍 pending 新 HEDGE venv rerun、commit/push
  和 READY marker。
- Git 节点：本 checkpoint 记录时 core/integration/config/result commit 仍为空；
  commit/push 由主 Agent 单独处理。

### 2026-07-28T21:54:41Z — 60 分钟 checkpoint

- 记录开始时间：`2026-07-28T21:54:47Z`，比计划 checkpoint 晚约 6 秒；为纳入
  紧随其后的 P00 keepalive 迁移与 P02 commit/marker evidence，最终证据快照于
  `2026-07-28T21:56:44Z` 完成，约晚 2 分 03 秒。
- P00 env/source：env-r2 `20260728T211739Z-p00-env-r2` 已完成
  `uv sync --frozen` 与 `uv pip check`（201 packages compatible）并 PASS。
  `/home/tiger/venvs/hedge-v4-dspark` 固定为 Python 3.11、
  torch `2.11.0+cu130`、SGLang `0.5.16`、sglang-kernel `0.4.5+cu130`、
  FlashInfer `0.6.14`、Triton `3.6`、NCCL `2.28.9`；独立 SGLang source
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 双侧 clean。
- P00 checkpoint：checkpoint r1 PASS，记录 75 files、48 shards、
  166898666759 bytes，按计划未做全量 hash；canonical
  `checkpoint_identity.json` 已原子发布。首轮 checker-scope FAIL 保留在
  `checkpoint-attempts/...scope-failed/`。
- P00 operational：worker `4106666` 仍为精确 8×H20、无未知 GPU task。
  keepalive 已从历史只读 runtime 定向迁移到
  `/home/tiger/venvs/hedge-v4-dspark/bin/python`：旧 PID/PGID/SID
  `1697/1697/1697` 精确停止后 CUDA contexts 为 none，新 supervisor
  `4730/4730/4730` 的 10×1 秒八卡门禁 PASS；证据为
  `keepalive-migration/keepalive_migration.json`。SGLang server/model 从未启动。
  P00 仍缺 CUDA links/probe、session/worker final state 和 handoff，因此仍是
  `IN_PROGRESS`。
- P01：主 Agent 已完成 13 tests、18/18 verifier、indices/hash 独立复核并验收
  PASS；commit/push 为 `77053dd`。
- P02：主 Agent 已在新正式 venv 独立运行 33/33 tests PASS；历史 pinned venv tests
  与 identity hashes 也 PASS。pure-core commit/push 为
  `4d96f44065c07030ede67484a262006ec149626a`（parent `77053dd`）；READY marker
  已原子发布到
  `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/hedge-core.json`，
  SHA-256
  `c9c09cd23655e395d3f3b85cbc7e1740194f9e4e174938cb5f54594afe31b80c`。
  P02 已由主 Agent验收 `PASS`。
- server / GPU experiment：`NOT_STARTED`；无 TP rank 或模型参与证据。

### 2026-07-28T22:01:31Z — P00 主验收

- canonical `session.json` 于 `2026-07-28T21:58:38.374346Z` finalized，
  `status=PASS`，worker/checkpoint/environment/SGLang base/CUDA link/keepalive/
  no-model-server checks 全部为 true。
- CUDA `lib64` guarded links 与秒级 `cc` link probe PASS；第二次 guarded pass
  两个 link 均为 `verified`。
- final inventory 没有 SGLang/model server；新 venv keepalive supervisor
  PID/PGID/SID `4730/4730/4730`，八卡 10×1 秒逐卡 mean/min/max 均为 100%。
- 主 Agent 已复算 session 引用 artifact 的 SHA-256、检查 P00 脚本 shell/Python
  语法，并验收 P00 为 `PASS`。下一 eligible phase 为 P03。

### 2026-07-28T22:24:41Z — 90 分钟 checkpoint

- 首个 patch 因文档已更新到 `22:01:31Z` 而上下文失配，未产生部分修改；重新
  对齐基线后于 `22:25:43Z` 开始落盘，并等待纳入主 Agent 最新 operational 复核，
  最终快照时间为 `2026-07-28T22:27:14Z`，较计划晚 2 分 33 秒。
- P00/P01/P02 均 PASS。P00 support commit/push 为
  `ebe196608893bd9972e771644ed25d019444d0f3`；P01 protocol 为 `77053dd`；
  pure core 为 `4d96f44065c07030ede67484a262006ec149626a`，READY marker 保持发布。
- P03 `IN_PROGRESS`：executor 使用 codebase-design 将接入收敛到唯一
  `DSparkHedgeAdapter` deep seam。TP>1 native logits processor 已先
  all-gather，设计复用 full-vocab `next_token_logits` 做 device compact
  max/gather，不新增 collective；bulk snapshot 复用 `/get_internal_state`
  的 `dspark_info_record`/clear。
- fixed external SGLang source 有预期未提交改动：
  `serving_chat.py`、`dspark_verify.py`、`dspark_worker_v2.py`、新
  `hedge_dspark.py` 与 byte-identical 注入的 `hedge_spec`。已草拟 native
  verify/finalize/lifecycle/bulk dump 及 non-streaming output token IDs 接入。
- 主审要求的严格 `HEDGE_ENABLED=0|1`、独立 trace flag、disabled + trace-off
  direct native branch 与 active 精确 static mode 均已修复；首轮 20/20 CPU
  tests PASS。executor 随后新增 native executor direct-call fixture，完整总回归、
  `integration.patch`、identity 与 wheel 尚未验收。当前无外部 blocker。
- P03 executor 未登录 worker、未碰 GPU/keepalive，未启动 server/model。
- operational heartbeat：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap/operational-heartbeats/20260728T220619Z-p03-cpu-build/`；
  worker-list SHA-256
  `bda700d189777343cbf7183fecb0b72884b418bd19365f96c99be7ee99516e8e`，
  keepalive JSON SHA-256
  `ef2f0f0417f714adbe63eb6726781fbe2b934cf08e527e8a57a34df1878ed87e`。
  证据记录 worker `4106666` 精确 8×H20、PID/PGID/SID
  `4730/4730/4730`、8 卡 10×1 秒均 100%，模型未启动。
- 主 Agent 在 `22:26:35Z–22:27:14Z` 又只读复核 `mlx worker list` 与 remote
  keepalive status：worker `4106666` 仍精确 8×H20，PID/PGID/SID
  `4730/4730/4730`，8 卡 10×1 秒 mean/min/max 均为 100%，各占 815 MiB，
  无模型 server。该 keepalive 是 operational load，不是正式实验负载或结果。

### 2026-07-28T22:54:41Z — 120 分钟 checkpoint

- 实际落盘时间：`2026-07-28T22:56:06Z`。两次 patch 均因主线程并发更新导致
  context mismatch，均未产生部分修改；重新对齐当前基线后较计划晚 1 分 25 秒。
- 当前 HEAD 已 push：`7c2ac5a`。P00/P01/P02 保持 PASS；P03 仍为
  `IN_PROGRESS`，尚未验收或 commit/push。
- P03 executor handoff 于 `2026-07-28T22:51:58Z` 标记 PASS。第一版
  22/22 + 33/33 + 13/13、clean replay patch `58174e…` / tree `996fbf…`、
  wheel `2f267…` 后续因 trace overflow 与 Python build deps 未入 uv lock 被修正；
  旧 wheel 已标为 `PASS_SUPERSEDED`。
- exact `p03-build` group 已由 uv 写入 `pyproject.toml` / `uv.lock`，固定
  `build==1.5.0`、`setuptools==81.0.0`、`setuptools-rust==1.13.0`、
  `setuptools-scm==10.2.1`、`wheel==0.47.0`。pyproject SHA 前缀
  `2ef3e7…`、uv.lock `0524523…`、build script `5553c8…`；lock check、
  frozen group sync/check PASS。
- locked07 formal wheel 已 clean replay 构建并通过 uv 安装，SHA-256
  `f2054c32025182ea8b4e57731ffa9d0150a40d5ac296f34e93c9b124181c7262`，
  14,646,094 bytes；raw log SHA 前缀 `133da0…`。22/22 integration、
  33/33 pure core、13/13 protocol、非 DeepSpec CWD import、9/9 hashes 与
  manifest cross-check 均 PASS；六个规定 manifests/log 和 handoff 已更新。
- 主 Agent clean replay、22 tests、lock dry-run、wheel RECORD 独立复验均 PASS，
  但 staged `git diff --check` 对 `integration.patch` 中 14 个 unified-diff 空
  context 行报 trailing whitespace。P03 已 followup 重生 artifact-only
  zero-context/full-index patch 并 clean replay；源码 tree、9 files 和 formal
  wheel 预计不变。最终 artifact clean gate 尚未返回，因此不得写为验收 PASS。
- `22:48Z` operational heartbeat 位于
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap/operational-heartbeats/20260728T224800Z-p03-locked-rebuild/`；
  记录 worker `4106666` 精确 8×H20、PID/PGID/SID `4730/4730/4730`、
  8 卡 10×1 秒均为 100%，无模型 server。这是 operational load，不是正式实验
  负载或结果。

### 2026-07-28T23:01:56Z — P03 主验收

- artifact-only followup 完成：zero-context patch SHA-256 `8e8cc840...`，
  applicator SHA-256 `e884d57a...`；clean replay manifest `57328fd1...`，
  patched tree 保持 `996fbfd6...`，9 个 source/core 文件与 formal wheel build
  source 逐字节一致，因此无需重建 wheel。
- 主 Agent 在 `/tmp/deepspec-p03-main-verify.hok7bb` 独立重放 patch，manifest
  hash/tree 均一致，并重跑 22/22 integration、33/33 core、13/13 protocol；
  `uv lock --check`、JSON/shell/Python syntax、真实 staged whitespace gate
  均 PASS。
- P03 验收为 `PASS`；integration commit
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc` 已 push。P04 八卡
  integration smoke 具备进入条件。

### 2026-07-28T23:24:41Z — 150 分钟 checkpoint

- `2026-07-28T23:24:56Z` 开始落盘；首个 progress+experiment 合并 patch 因
  experiment 底部并发更新而整体 context mismatch，未产生部分修改。拆分为两份
  独立 patch 后于 `2026-07-28T23:27:21Z` 完成，较计划晚 2 分 40 秒。
- P03 保持主验收 PASS。主 Agent zero-context clean replay manifest
  `57328fd1…`、tree `996fbf…` 与 22/22 integration、33/33 core、13/13
  protocol 均 PASS。integration commit
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc` 和 identity/progress commit
  `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3` 均已 push。
- P04 为 `IN_PROGRESS`，但模型/server 从未启动，B0 仍为 `NOT_RUN`。首次 executor
  read-only preflight PASS：worker `4106666` 精确 8×H20、无未知任务、
  keepalive PID/PGID/SID `4730/4730/4730`、8 卡 10×1 秒均 100%。artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T230700Z-p04-preflight/worker_inventory.json`。
- 原计划 attempts `20260728T230647Z-p04-native-smoke-r1` 与对应 B0 attempt 均未
  运行。首次 executor 在 preflight 后两 turn 无落盘，被主 Agent 中断并重分配；
  全程未暂停 keepalive、未操作 GPU。这是调度事件，不是实验 blocker。
- 当前独立 `p04_tooling` executor 只做静态 8 卡 lifecycle/client/sampler/
  validator/tests，不登录 worker。截至 checkpoint，仅新增未提交
  `scripts/hedge_dspark_p04_prepare.py` 与
  `tests/hedge_dspark_p04/test_tooling.py`。
- native fixed flags/env/no-config、B0 exact config path/bytes、exact 8×H20 inventory
  三个离线契约测试已完成 red→green；engine identity 测试实现刚写完，待复跑。
  当前无 blocker，tooling 尚未验收。
- 主 Agent `23:06Z` 额外只读复核 lane/keepalive：首次漏传 worker-id 被脚本
  fail-closed 拒绝且无状态变化，随后正确 status PASS；worker `4106666`
  精确 8×H20，PID/PGID/SID `4730/4730/4730`，8 卡 10×1 秒均 100%，无 server。
  这些是 operational evidence，不是正式实验负载或结果。

### 2026-07-28T23:54:41Z — 180 分钟 checkpoint

- 实际状态快照始于 `2026-07-28T23:54:50Z`，较计划 checkpoint 晚 9 秒。
- P04 静态 tooling executor 已完成 handoff，未登录 worker、未暂停 keepalive、
  未启动模型/server，也未宣称 GPU smoke PASS。新增 exact native/B0 lifecycle、
  fixed request client、8-GPU sampler、进程归属 guard、artifact validator 与
  immutable archive 工具。
- executor 离线证据为 20/20 tests PASS（0 failure / 0 error，0.877 秒），
  `bash -n`、Python compile/import、contract JSON 与 whitespace checks 均 PASS；
  evidence：
  `artifacts/hedge-dspark/p04-tooling/tooling_test.log`。
- 主 Agent 独立重跑同一 20/20 tests PASS（0.936 秒），并复核 lifecycle contract：
  native 不写 HEDGE config；B0 固定
  `B=0,g=1e30,m=5,value_scheme=normalized_suffix,block_size=5`；formal wheel
  实际 SHA、installed import path、patched-tree identity、PID/PGID/SID/start-ticks/
  cmdline/hostname 与 early-exit fail-closed 规则均进入门禁。
- 首次直接执行非 executable shell 文件的 contract 命令仅得到本地
  `Permission denied`；运行合同本来固定为 `bash <absolute-script-path>`。
  主 Agent 随即按该固定调用方式复验，contract JSON PASS；这未触碰 worker，
  不是模型 attempt 或实验 blocker。
- P04 仍为 `IN_PROGRESS`：静态 tooling 尚待独立 Git 节点 commit/push，随后才可
  分配 native runtime executor。B0、模型参与和所有 P04 GPU attempt 仍为
  `NOT_RUN`。

### 2026-07-29T00:16:20Z — P04 native r2 与 formal-wheel recovery

- P04 静态 tooling 已经主 Agent验收并由
  `210b2815b8cdb1905a5ad57e8b565319567f8405` commit/push。
- 唯一 native r2 `20260728T235900Z-p04-native-smoke-r2` 在
  `preflight_identities` FAIL；HDFS artifact 完整封存且 archive PASS。唯一 false
  checks 是 formal wheel exists/size/actual SHA：manifest build path 属于开发机
  `/tmp`，worker 独立 NVMe 中不存在。其余 installed/source/RECORD/toolchain/
  checkpoint/inventory checks 均 PASS。
- r2 在 pause keepalive / server start 之前退出；模型、请求、TP ranks 和 sampler
  均未启动，也没有 signal。keepalive 从未暂停，after gate 为
  `4730/4730/4730`、8 卡各 10 样本 100%。失败已如实记录并由
  `4d8d124` commit/push。
- recovery executor 先建立 exact regression：修复前 1 test FAIL，修复后同一
  test PASS；valid build + corrupt persistent 仍 FAIL，证明没有 fallback。
  exact 14,646,094-byte / SHA-256 `f2054c...c7262` wheel 经唯一 HDFS staging
  no-clobber rename 发布到 hash-named persistent path，source 保留、staging
  已消失。
- executor 与主 Agent分别在 worker `4106666` 运行 read-only engine/keepalive
  probe：两次均 `engine PASS`、`false_checks=[]`，worker-local build path
  不存在而 persistent size/hash 精确匹配；keepalive 未 pause，8×10 全 100%。
  完整 22/22 tests 和 shell/JSON/compile/import/contract/diff/debug gates PASS。
- 单变量 recovery commit/push：
  `ddc372b5118595d15bfc217e7c3529c0bf86c852`。P04 仍 `IN_PROGRESS`；
  下一步仅运行新的 native attempt，主验收 PASS 前不运行 B0。

### 2026-07-29T00:24:41Z — 210 分钟 checkpoint

- 状态快照于 `2026-07-29T00:24:29Z` 提前 12 秒取得，避免正在运行的长模型命令
  跨过进展检查点而没有心跳。recovery docs commit/push 为 `7402fd5`。
- 唯一 native r4 `20260729T001700Z-p04-native-smoke-r4` 正在 worker
  `4106666` 前台运行。preflight fixed port、checkpoint identity、engine identity
  均 PASS；keepalive before 为 `4730/4730/4730`、8×10 全 100%。
- keepalive 于 `00:19:59Z` pause，`00:20:03Z` 证明 contexts none 后紧邻启动
  server；PID/PGID/SID `7941/7941/7941` 与完整命令已登记，sampler 持续覆盖
  8 个固定 GPU UUID。主 Agent在 foreground session 外持续确认 worker 在线。
- server 已解析 `DeepseekV4ForCausalLM`，确认固定 checkpoint 内置 DSpark draft；
  日志打印 TP=8、`speculative_algorithm='DSPARK'`、block size 5、target/draft
  `flashinfer_mxfp4`，CUDA graph/overlap/radix 均 disabled。当前仍在 TP worker/
  权重加载前段，尚未 ready、未发请求，没有已知 error 或 cleanup。
- 本 checkpoint 不构成 native PASS、八 rank 参与证明、API 成功或 P04 验收；
  B0 仍 `NOT_RUN`。

### 2026-07-29T00:54:41Z — 240 分钟 checkpoint

- 状态快照始于 `2026-07-29T00:52:12Z`。native r4
  `20260729T001700Z-p04-native-smoke-r4` 已完成并完整封存到同名 HDFS run
  目录；没有运行第二个 attempt，B0 仍为 `NOT_RUN`。
- 服务在 1726.254 秒冷启动后 ready；TP0–TP7 均完成初始化，48/48 target
  shards 已加载，日志确认 target/draft 均为 `flashinfer_mxfp4`。固定 native
  smoke 请求成功返回 91 个 completion token，`api_smoke.json` 与
  `hedge_counters.json` 均 PASS；native HEDGE disabled/config-null 证据成立。
- r4 整体仍记为 `FAIL_VALIDATION`，不记作 native PASS：live validator 的唯一
  blocker 是 `GPU sampling cadence departed from the one-second sampler`。当前
  正在只读量化 archived `gpu_samples.csv`，区分全局冷启动期间的调度抖动与真实
  漏采；修正前不运行 B0。
- 这不是 server/API crash 或远程登录中断。失败路径已按登记的 PID/PGID/SID
  定向停止 server 与 sampler，证明 CUDA contexts none；无外部 signal。随后恢复
  dedicated keepalive，新 PID/PGID/SID `21792/21792/21792`，8 卡各 10 个样本
  mean/min/max 均为 100%。`archive_manifest.json` PASS。

### 2026-07-29T01:02:57Z — P04 native r4 validator recovery

- archived CSV 的只读量化证明 1419 个 ordinal 从 0 连续到 1418，共 11352 行；
  每组精确 8 行/8 个固定 UUID，monotonic timestamp 严格递增。旧 cadence gate
  失败只来自全局 10 个间隔略大于 2.5 秒，最大 2.687626856 秒。
- 固定 API 请求窗口有 9 组完整样本，最大间隔 1.199117809 秒；八卡都有约
  79.6–80.1 GiB 模型显存，最大利用率 85%–99%。因此根因收敛为全局冷 JIT/
  cleanup 调度抖动触发了计划外 validator 硬门槛，不是漏 ordinal、漏 GPU、模型
  或请求失败。
- recovery executor 先以完整 8-row fixture 得到 exact RED，再只把 cadence
  hard-fail 改为 global/request-window 诊断统计；连续 ordinal、exact UUID/row、
  strict timestamp、request bracket/sample 与八卡活动/显存门禁全部保留。缺
  ordinal/row、非单调、无 request sample、未 bracket 五类反例仍 fail-closed。
- executor 与主 Agent各自得到 33+13+22+24=92/92 tests PASS；修复后对 r4
  临时只读副本 replay 为 PASS。原 HDFS `live_validation.json`/shutdown FAIL
  保持不可变；主 Agent将 r4 记为 `RECOVERED_PASS`。非 decode recovery
  commit/push：
  `37a8d37470660cca34a5d14efe2e84553fa6ec38`。
- 主 Agent再次远端核查 worker `4106666` dedicated keepalive：
  `21792/21792/21792`，8×10 全卡 mean/min/max 100%。唯一 B0 smoke executor
  已派发；不重跑 native，也不提前进入 P05。
- B0 executor 首次把 keepalive status/start 误执行在开发机 namespace；本地
  status 为 STOPPED，start 因本地 GPU busy 在 idle gate 立即拒绝，没有 PID、
  signal 或远端状态变化。主 Agent纠偏后，executor 经
  `mlx worker login 4106666 -- bash <absolute-script>` 复核远端仍为
  `21792/21792/21792`、8×10 全 100%，随后才启动唯一 B0 attempt
  `20260729T010603Z-p04-b0-r1`。

### 2026-07-29T01:24:41Z — 270 分钟 checkpoint

- 状态快照于 `2026-07-29T01:22:52Z` 提前取得。cadence recovery implementation
  `37a8d37` 与 native recovery docs `d436feb` 均已 push，worktree clean。
- 唯一 B0 attempt `20260729T010603Z-p04-b0-r1` 正在 worker `4106666`
  前台运行；preflight/远端 keepalive 8×10 PASS 后由 launcher 紧邻 pause，
  CUDA contexts clear 后启动。server PID/PGID/SID `23064/23064/23064`、
  start ticks `195862198`，process guard 与前台 launcher 均仍存活。
- TP0–TP7 distributed/NCCL 初始化完成；target 与
  `DeepseekV4ForCausalLMDSpark` draft 均完成 48/48 shards。八 rank 都确认
  target/draft `flashinfer_mxfp4` 与 `Mxfp4FlashinferCutlassMoEMethod`，
  MHC prewarm 完成；八个 CUDA contexts 已逐 UUID 覆盖固定 8 张 H20。
- 当前将进入 draft MXFP4/attention/DeepGEMM JIT，尚未 server ready、未发固定
  请求、未产生 B0 counter 或 PASS 结论。日志尾部无 ERROR/Traceback/CUDA/NCCL/
  worker crash；没有第二 attempt 或额外 GPU 负载。keepalive 仍处于 attempt
  生命周期内的预期 `PAUSED`，结束路径负责定向清理并恢复。

### 2026-07-29T01:30:12Z — P04 B0 与阶段验收

- 唯一 B0 `20260729T010603Z-p04-b0-r1` launcher rc=0；HDFS 同名 immutable
  run 有 33 files，API/counters/live/artifact/shutdown/archive 与 keepalive
  after 全 PASS。没有重试或第二 attempt。
- 固定 B0 config bytes、mode enabled 均精确；25 proposals、
  `verify_num_draft_tokens=6`、strict/HEDGE accepted 75/75，relaxed mismatch、
  regret charged、state leak 均为 0。API 首次成功返回 91 completion tokens/IDs。
- 主 Agent独立比较 native r4 和 B0 r1 的 91 个完整 token IDs 逐项相同，
  canonical JSON SHA-256
  `b7288ead4694ee70156e7d90c5fd63118b4f46e1347d7f263ddc1472ed8649db`。
  这只验收单请求 P04 smoke，不替代 P05 的 32 条等价核查。
- TP/target/draft ranks 均为 0–7，两次 48/48；请求期每个固定 UUID 有 3 个
  sample，显存 79,573–80,053 MiB、最大利用率 82%–99%，crash markers 为空。
  最终 CSV 935 个连续 ordinal/7480 行，每组精确 8 卡、strict monotonic。
- server/sampler 只按登记 identity 定向 SIGTERM；main/cleanup rc=0、contexts
  none、无外部 signal。keepalive 恢复为 `32894/32894/32894`，attempt 内与
  executor 独立核查均 8×10 全卡 100%。
- 主 Agent验收 P04 `PASS`：native r4 `RECOVERED_PASS` + B0 r1 `PASS` 已满足
  计划全部 P04 门禁。下一 eligible phase 为 P05 calibration；正式 32/500
  仍未运行。

### 2026-07-29T01:54:41Z — 300 分钟 checkpoint

- P04 阶段结果与主验收已由 `3e10b780264557e84a3cab5c1a196dc7c2a00496`
  commit/push；计划状态已切换为 P05 `IN_PROGRESS`，P06–P08 未开始。
- 独立 P05 executor 依 `tdd` skill 在公共 CLI/artifact/reducer seam 做离线
  vertical RED→GREEN；尚未登录 worker、pause keepalive、启动模型或创建 HDFS
  attempt。当前只新增 P05 attempt/client/prepare/reduce/validate 工具与测试，
  未改 docs/index、SGLang source 或 wheel。
- 首个 launcher contract 在文件不存在时 rc=127 RED，最小
  `--print-contract` 后 GREEN；随后 resolver 锁定 calibration SHA
  `28a708…e47d`、32 个原始 index/order/prompt bytes、native-trace env 与 P04
  exact B0 config bytes。
- runner/trace 与 q25 reducer 当前行为 gate 12/12 GREEN：32 个 frozen prompt
  经 mock HTTP 边界发出，原始 token IDs 原样保存；trace capacity=65536、
  dropped=0；worked example `[1,2,3,5]` 按计划公式得到 q25=1.75。错误 worker、
  broad cleanup、trace overflow/empty、B0 relaxed token、非法 ratio/q25 和完整
  token-ID mismatch 均 fail-closed。
- `bash -n`、4 个 Python module compile、launcher contract JSON 与
  `git diff --check` PASS；executor 尚在补 failure artifact/全回归与清理
  bytecode。主 Agent要求每个真实 attempt 在 preflight 生成当时 UTC ID并先证明
  NVMe/HDFS 不存在，不采用预写的未来 timestamp。
- 主 Agent `01:51Z` 远端独立核查 worker `4106666` keepalive
  `32894/32894/32894`，8×10 全卡 mean/min/max 100%，每卡 815 MiB；P05 GPU
  preflight 仍未放行。

### 2026-07-29T02:24:41Z — 330 分钟 checkpoint

- 本快照于 `02:24:11Z` 提前 30 秒落盘，避免唯一 P05 native-trace 长命令跨过
  checkpoint 而没有过程心跳；进行中状态不构成 P05 PASS。
- P05 离线 tooling 已由 executor 和主 Agent分别得到 106/106 fresh-process tests
  PASS，shell/Python/contract/whitespace gates 均 PASS；7 个小文件已由
  `ce5d67216953f3fceaec38ce2469ba47582d4e8d` commit/push，运行前 worktree
  clean 且 upstream 同步。
- 唯一 native-trace attempt 为
  `20260729T020144Z-p05-native-calibration-r1`。preflight 确认 worker
  `4106666` 精确 8×H20、NVMe/HDFS 目标均不存在，keepalive
  `32894/32894/32894` 的 8×10 gate 全卡 100%。
- keepalive 于 `02:02:34Z` 暂停，`02:02:36.889676Z` 证明 contexts none 后
  紧邻启动 server `34445/34445/34445` 与 sampler `34452/34452/34452`。
  TP0–TP7 全部初始化；target 48/48 shards、八 rank
  `flashinfer_mxfp4 / Mxfp4FlashinferCutlassMoEMethod` 均有日志证据。
- server 于 `02:20:24Z` ready，32 条固定 calibration 于 `02:20:31Z` 开始
  顺序请求；最近 executor 只读快照为 31/32。sampler 已超过 1064 个 ordinal，
  每组仍为 8 个固定 UUID；无 Traceback、CUDA OOM、NCCL ERROR 或 worker crash
  marker。
- attempt 尚未完成 validator、定向 cleanup、contexts-none、keepalive 恢复或
  immutable HDFS archive，故 native trace 尚未由主 Agent验收；B0 未启动。

### 2026-07-29T02:54:41Z — 360 分钟 checkpoint

- 恢复结论于 `02:50:06Z` 提前固化，确保新的长模型 attempt 前先提交 r1 的真实
  failure 与两项单变量修复；这不是把 r1 改写为成功。
- native r1 已完成并 immutable 归档，但主 Agent验收为 `FAIL_TRACE_SCOPE`。
  32/32 请求成功、0 retry、5183 completion tokens；TP/target/draft ranks
  0–7、两次 48/48、请求期每卡 149 samples、cleanup/contexts/keepalive 成立。
- 主 Agent逐条复核 32 个冻结 dataset identity、prompt/request bytes 与完整 token
  IDs 全部 PASS；35 个 archive 条目的 size/SHA 与 exact file set 全匹配。这些
  有效证据不能抵消 trace scope 与 sampler terminal status 的失败。
- trace 有 488 行/33 RID；32 个真实 output RID 对应 484 行，额外 warmup RID
  `505959725a104b34a193d3f481be36ac` 对应 4 行。全量 q25
  `2.083333333333333`，cohort-only q25 `2.0625`，故 r1 参数不采用。
- sampler 在请求完成、live validator PASS、server 定向停止之后，恰于 sampler
  PGID SIGTERM 边界把受信号打断的 `nvidia-smi` query 写成 FAIL。旧 finalizer
  漏验该文件；r1 的原 artifact 保持不变。
- sampler recovery `6b7145d` 与 trace-scope recovery `eb4962f` 已分别
  commit/push。前者只在 stop 已请求时把 query interruption 视为 clean stop，并
  新增 sampler terminal status/count 门禁；后者在 cohort 前 clear+验零，并由
  client/reducer 两层以 32 个 response RID fail-closed 封闭 trace。
- executor 和主 Agent最终相关回归均为 118/118 PASS；旧 r1 被两个新 gate 精确
  拒绝，strict reducer 没有创建 output directory。修复不改 SGLang wheel、
  checkpoint 或 decode 配置。
- r1 结束后 keepalive 更新为 `44844/44844/44844`；主 Agent `02:35Z` 远端复核
  worker `4106666` 仍为 exact 8×H20、8×10 全卡 100%，每卡 815 MiB。P05 B0
  仍未启动；下一动作是从 HEAD `eb4962f` 动态创建 scoped native r2。

### 2026-07-29T03:24:41Z — 390 分钟 checkpoint

- 实际快照于 `03:25:14Z` 落盘，晚 33 秒。唯一 native r2
  `20260729T025543Z-p05-native-calibration-r2` 验收为
  `FAIL_PRE_COHORT_QUIESCENCE`，没有被写成 calibration 成功。
- server ready 后，严格 client 先执行 trace clear，POST 返回 `[true]`；紧接的
  `/server_info` 仍报告 `active_request_states=1`、`state_leaks=1`。证据定位为
  SGLang 内建 startup warmup 仍在运行；clear 只清 arm metrics，不删除 live request
  state。门禁在第一个 cohort 请求前正确失败，因此输出为 0/32、trace 为 0。
- 失败不是模型 crash：target/draft TP rank 0–7 均加载，固定
  `flashinfer_mxfp4` / `Mxfp4FlashinferCutlassMoEMethod` 后端成立，日志无未处理
  CUDA、NCCL、OOM 或 worker crash。
- r2 live-prove 了 sampler recovery：terminal status 为 `stopped`，923 个连续
  ordinal 与 `sample_count=923` 精确相等，CSV 为 7,384 行且无 traceback。
- 登记的 server `47022` 与 sampler `47029` 已定向清理，随后 contexts none；
  keepalive 恢复为 `57902/57902/57902`，8×10 全卡 100%。immutable archive
  manifest 34 项 size/hash 全匹配；artifact validator 因缺 32 outputs/trace 按预期
  FAIL。
- 当前由 bounded CPU executor 用 TDD 实现
  `wait quiescent → clear → exact-zero verify`：startup warmup 只触发有界等待，
  永久 active/race/identity/HTTP 错误保持 fail-closed，不放宽 state-leak 门禁。
  native r3 与 P05 B0 均尚未启动。

### 2026-07-29T03:54:41Z — 420 分钟 checkpoint

- 实际快照于 `03:55:00Z` 落盘，晚 19 秒。quiescence recovery 已由 bounded
  executor 和主 Agent分别完成 fresh-process 回归；主复验 P05 24、P04 29、
  protocol+core 46、integration 22，合计 121/121 PASS，另有 compile、shell 与
  diff gates PASS。代码 `fe0aea0`、权威 r2/recovery experiment `3c37a41` 均已
  commit/push。
- 唯一 native r3 为
  `20260729T033920Z-p05-native-calibration-r3`。preflight 固定
  HEAD/origin `3c37a41ef0bf80f83399ca16b29b85c94e282e87` 且 clean，
  `fe0aea0` 为 ancestor；worker `4106666` 精确 8×H20，NVMe/HDFS 目标均预先
  ENOENT，keepalive `57902/57902/57902` 的 8×10 gate 全卡 100%。
- keepalive 于 `03:40:38Z` 暂停，`03:40:41.234729Z` 证明 contexts none 后
  紧邻启动登记 server `59735/59735/59735` 与 sampler
  `59742/59742/59742`。TP0–TP7 已全部 distributed init；target 48/48 shards
  已读完，各 rank 确认
  `flashinfer_mxfp4 / Mxfp4FlashinferCutlassMoEMethod`，目前仍在固定 SM90
  CUTLASS expert prepare。
- sampler 最近快照为 630 个连续 ordinal、5,041 CSV 行，每组精确 8 GPU。
  server foreground/identity 存活，日志无 Traceback、CUDA/NCCL、OOM 或 worker
  crash marker；attempt 尚未 ready，故 quiescence handshake、32 条请求、q25、
  cleanup、archive 与 keepalive 恢复均尚未完成，不能宣称 r3 或 P05 PASS。
- P05 B0 继续锁住；冷加载期间没有其他 GPU load、第二 attempt 或 decode/source
  改动。

### 2026-07-29T04:24:41Z — 450 分钟 checkpoint

- 实际快照于 `04:21:10Z` 提前 3 分 31 秒落盘。唯一 native r3
  `20260729T033920Z-p05-native-calibration-r3` 已 immutable 封存，并验收为
  `FAIL_PREFILL_TERMINAL_LIFECYCLE`，不是 calibration PASS。
- server 于 `03:58:44Z` ready；新握手随后运行整整 120 秒/120 polls。每次都稳定
  报告 `requests_initialized=2`、`requests_finished=1`、
  `requests_non_natural=1`、`active_request_states=state_leaks=1` 与 4 行启动
  trace；因此 `clear_attempts=0`，客户端没有 POST clear，也没有发送任何 cohort
  请求。32 条输出为 0、scoped q25 未定义。
- TP0–TP7 target/draft 加载与固定 `flashinfer_mxfp4` 后端均成立，日志无
  CUDA/NCCL/OOM/worker crash。sampler terminal 为 `stopped`，
  `sample_count=1027` 与 CSV ordinal 精确相等；登记 server/sampler 定向停止，
  contexts none，34 项 archive size/hash 全匹配。
- 主 Agent与 bounded executor 对固定 SGLang source 的控制流核对确认：默认
  `/health` 会生成 `max_new_tokens=1`；该请求在 generation prefill 的
  `req.update_finish_state()` 后已终态，但旧 prefill 分支没有调用 speculative
  worker 的 `note_request_finished`，而 decode 分支有。启动 warmup 的较长请求进入
  decode 并正常释放，恰好解释 2 initialized / 1 finished / 1 leak。
- TDD fixture 先得到确定性 RED（finish events 为空且 adapter active=1），最小
  GREEN 只在 prefill 终态、KV release 前调用一次与 decode 相同的 lifecycle hook。
  主 Agent独立复验 integration 23/23、pure core 33/33、protocol 13/13；
  独立 clean replay 得到 patch SHA `a4077b9f…10c52`、10-file tree
  `69e80df9…2422`，与 executor manifest 精确相同。
- recovery commit/push 为
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36`。旧 formal wheel
  `f2054c…` 未被改写且明确 superseded；bounded CPU executor 正在按 P03 锁定流程
  重建/发布/uv 安装新 wheel。完成身份主审前不启动 r4。
- r3 清理后 dedicated keepalive 为 `69805/69805/69805`；主 Agent `04:19Z`
  重新运行 `mlx worker list` 与远端 status，确认仍是分配的 exact 8×H20，
  8×10 全卡 mean/min/max 100%、每卡 815 MiB，无模型 server。P05 B0 未运行。

### 2026-07-29T04:54:41Z — 480 分钟 checkpoint

- 实际快照于 `04:50:06Z` 提前 4 分 35 秒落盘。bounded CPU executor 从 exact
  base `fdebc938…`、repair `e028d2c…`、patch `a4077b9f…10c52` 重放并构建新
  formal wheel；10-file replay tree 仍为 `69e80df9…2422`。
- 新 wheel 为 14,646,093 bytes / SHA-256
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`。
  ZIP、3,671-row RECORD、replay→primary source→wheel→installed 10-file hashes
  与 4 个 non-repo-CWD imports 全 PASS。
- HDFS hash-named entity 通过唯一 staging 与
  `renameat2(RENAME_NOREPLACE)` no-clobber 发布；source/staging/final size/hash
  一致，staging 已消失。旧 `f2054c…` wheel 保留且复验未变；formal venv 只用 uv
  从新 persistent entity 重装。
- executor 与主 Agent各自得到 P04/P05 53/53 tests PASS；主 Agent runtime probe
  `status=PASS,false_checks=[]`，新旧 HDFS wheel size/hash、uv lock、compile、
  JSON/diff gates 均成立。wheel/identity commit/push 为
  `ada66253e719cd021cdec369914245b51ff46b61`。
- 唯一 native r4
  `20260729T044309Z-p05-native-calibration-r4` 的 preflight 确认 HEAD/origin
  `ada6625` 且 clean、worker `4106666` exact 8×H20、HDFS/NVMe target ENOENT，
  keepalive `69805/69805/69805` 的 8×10 gate 全卡 100%。
- launcher 已按 lifecycle 顺序通过 pause 与 contexts-none，登记 launcher
  `71219`、server `71408`、sampler `71415`；wait-ready client `71430` 绑定
  server start ticks `197165743`、固定 port `31066`。当前仍在模型冷加载，尚未
  ready、handshake 或发送 32 条请求，故不能宣称 r4/P05 PASS。
- 一次只读 status snapshot 写入
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/_monitor-20260729T044309Z-p05-native-calibration-r4/status-0446.txt`；
  该通用 monitor 在 active-load `nvidia-smi` 段 rc=1，没有 signal/环境修改，
  正式 launcher/sampler 仍存活。没有 retry、第二服务或 B0。

### 2026-07-29T05:10:24Z — P05 scoped native r4 主验收

- 唯一 native r4
  `20260729T044309Z-p05-native-calibration-r4` launcher rc=0；没有 retry、第二
  server 或 B0。immutable HDFS archive 的 live/artifact/shutdown/archive
  status 全为 `PASS`。
- lifecycle repair 已消除 r3 的 prefill-terminal leak。握手第一次 poll 即为
  `active_request_states=state_leaks=0`；startup 两个请求均已 finished。唯一
  clear 返回 `[true]`，第二次 poll 证明 counters exact zero，随后才发送 cohort。
- calibration 32/32 首次成功、0 retry、5183 completion tokens；outputs SHA-256
  `b5550312da76c86dc68f3b7f0685f4eb1009f7f778be8c24e1d400b382e78b23`。
  32 个 cohort position、response ID、非空完整 token-ID 列表与 token counts
  全部成立。
- scoped trace 为 484 行，SHA-256
  `8ffa9e45214c6a40520448c5d7dda098182e66134e809a92e20530fd9a5130f6`。
  484 个 ratio 全部正且有限；32 个 trace RID 与 32 个 output RID 集合精确相同，
  无 extra/missing，capacity 65536、dropped=0。主 Agent按
  `h=(n-1)*0.25` 线性插值独立复算 q25=`2.0625`。
- TP、target 与 draft rank 均为 0–7，两次 48/48 load marker，无 crash marker。
  请求窗口每卡 137 samples，模型显存 79,571–80,051 MiB，最大利用率
  98%–99%。server `71408` 与 sampler `71415` 定向停止，contexts none；
  keepalive 恢复为 `80819/80819/80819`，8×10 全卡 100%。
- r4 已具备 P05 B0 入口条件。q25 目前只是 native 候选值；必须等唯一 B0 32 条
  完整 token-ID 等价 PASS 后，才运行 reducer 并冻结 `g=B=q25,m=1`。

### 2026-07-29T05:24:41Z — 510 分钟 checkpoint

- 实际快照于 `05:22:26Z` 提前 2 分 15 秒落盘。native r4 PASS 已作为关键节点
  commit/push：`e58027e927cb4be5f9cc410a6df08fd19531a128`。
- 唯一 P05 B0 attempt 为
  `20260729T051340Z-p05-b0-calibration-r1`。preflight 确认 HEAD/origin clean、
  r4 入口四类 validator 全 PASS、worker `4106666` exact 8×H20、HDFS/NVMe
  新目标 ENOENT、port 31066 可用、engine probe 无 false check。
- 启动前 dedicated keepalive `80819/80819/80819` 的 8×10 gate 每卡
  mean/min/max 100%。launcher 按生命周期暂停 keepalive并登记唯一 launcher
  `82254`、server `82443`、sampler `82450`；TP0–7 scheduler 均是同一 server
  PGID `82443` 的子进程。
- 当前 stage 为 `wait_ready`；尚未执行 quiescent→clear→exact-zero handshake，
  也尚未发送 32 条请求。没有 retry、第二 launcher/server/sampler 或 reducer。
  q25=`2.0625` 仍只是 native 候选值。

### 2026-07-29T05:45:29Z — P05 B0、reducer 与阶段主验收

- 唯一 P05 B0
  `20260729T051340Z-p05-b0-calibration-r1` launcher rc=0。服务
  `05:34:55Z` ready；32 条于 `05:34:57Z`–`05:37:38Z` 全部首次成功，
  0 failed/retry、5183 completion tokens。
- pre-cohort 唯一 clear 返回 `[true]` 并 verified exact zero。最终
  1097 proposals，HEDGE accepted 4081 与 strict accepted 4081 相同；
  relaxed mismatch、regret、active state/state leak、trace
  seen/stored/dropped 全为 0。
- B0 TP/target/draft rank 0–7、八卡各 134 个 request-window samples、无 crash。
  server `82443`、sampler `82450` 定向停止，contexts none；keepalive 恢复为
  `93521/93521/93521`，8×10 全卡 100%。live/artifact/shutdown/archive PASS。
- 主 Agent与唯一 reducer 对 native r4/B0 r1 的完整 token-ID 列表比较均为
  32/32 equal、mismatch=0；两臂 completion-token sum 都是 5183。B0 outputs
  SHA-256 `d59b0e17…3a434`。
- reducer 只运行一次，在 absent directory 创建四个小型 artifact。484 个正且
  有限值、1097 seen/484 stored/0 dropped，线性 q25=`2.0625`。正式冻结
  `B=g=2.0625,m=1,normalized_suffix,block_size=5`，fingerprint
  `6e6f0ef3e1b715aa0b036d856186cc2ab1612580c96bea7fb65327b259fbd921`；
  无 counterexample。
- executor reducer tests 6/6 PASS；主 Agent独立 P05 24/24、syntax/diff gates
  PASS。P05 主验收 `PASS`，下一 eligible phase 为 P06 native formal。

### 2026-07-29T05:54:41Z — 540 分钟 checkpoint

- 实际快照于 `05:53:06Z` 提前 1 分 35 秒落盘。P05 四个 freeze artifact 与权威
  记录已 commit/push：
  `c244651`。从该节点起 SGLang source/wheel、checkpoint、proposal width 与
  `B=g=2.0625,m=1` 正式冻结；500 条结果不得反向调参。
- P06 独立 executor 已按 `tdd` 进入 formal-tooling 子阶段，当前在 worktree
  创建 P06 tests/prepare 草案，尚未交付完整 GREEN implementation。
  它未登录 worker、未触碰 GPU/keepalive/model，也未启动 live attempt。
- lane 最新已验收 operational 状态仍是 B0 cleanup 后 dedicated keepalive
  `93521/93521/93521`，8×10 全卡 100%，contexts none。P06 live preflight
  尚未开始。

### 2026-07-29T06:24:41Z — 570 分钟 checkpoint

- 实际快照于 `06:24:05Z` 提前 36 秒落盘。P06 executor 完成最小 formal
  tooling：16 个 P06 tests 与 P04/P05/protocol/integration/core 回归合计
  138/138 PASS；主 Agent独立 P06 16、P04 29、P05 24、protocol 13 及
  syntax/lock/contract/diff gates 均 PASS。
- 真实 P05 native r4 raw-response replay 复算 1097 proposals、5485 proposed、
  4081 accepted、1102 target/bonus tokens、5183 completion tokens，证明新
  `spec_*` client normalization 可用于 formal acceptance summary。
- canonical formal artifacts、warmup 排除、500 精确计时、formal-only GPU window、
  HEDGE off、定向 lifecycle 与 immutable archive 已冻结在 commit/push
  `6a74186`。它不改变 SGLang wheel、engine source 或 P05 config。
- 唯一 P06 live executor 已派发，当前仍在 read-only preflight；尚未分配
  attempt ID、暂停 keepalive或启动模型，因此没有 500 条结果。

### 2026-07-29T06:54:41Z — 600 分钟 checkpoint

- 实际快照于 `06:54:23Z` 提前 18 秒落盘。唯一 P06 attempt
  `20260729T062241Z-p06-native-formal-r1` preflight PASS：worker
  `4106666` exact 8×H20、HEAD ancestry、engine/wheel/checkpoint/P05 freeze、
  calibration/formal bytes、runner contract、HDFS/NVMe新路径与 port 均成立。
- 启动前 keepalive `93521/93521/93521` 的 8×10 gate 全卡 100%、每卡
  815 MiB；process inventory 只有本项目 keepalive。launcher 按生命周期
  pause、contexts-none 后启动唯一 TP=8 服务。
- 服务已 ready；10 条 warmup 与 post-warmup clear 位于计时窗外。唯一 client
  `104073` 已进入 formal 500，launcher `94709` 与 sampler `94992` ownership
  稳定；`06:54:21Z` 只读 checkpoint 为 123/500。当前没有第二
  attempt/service、续跑或拼接。
- 500 尚未全部终态，formal timing/summary/TPS、GPU formal-window、
  cleanup/archive 仍待完成，因此本 checkpoint 不宣称 P06 PASS。

### 2026-07-29T07:24:41Z — 630 分钟 checkpoint

- 实际快照于 `07:24:47Z` 延后 6 秒落盘。唯一 P06 formal client 在没有重启、
  拼接、配置变更或控制 signal 的情况下，于 `07:24:13Z` 达到 500/500。
- `07:24:31Z` launcher `94709` 仍存活；client `104073` 与 sampler `94992`
  已自然退出，生命周期已迁移到 validator/cleanup/archive。此时没有第二
  attempt/service。
- 500 行完成并不单独构成 P06 PASS：formal summary/TPS/acceptance 重算、
  formal-only 八卡窗口、HEDGE off、contexts-none、keepalive 8×10 和 immutable
  archive 均等待 launcher 终态及主 Agent独立验收。

### 2026-07-29T07:32:56Z — P06 主 Agent验收

- 唯一 P06 launcher rc=0，live/artifact/shutdown/archive 均 PASS。主 Agent从
  immutable HDFS 重新读取 10 warmup + 500 formal：500/500 success、0 retry、
  74594 completion tokens、2348.31919839s、31.76484698125425 output TPS；
  formal SHA `ecd9952536a860836babc3451e066b4ea164b0e520e263bfc5c200f46e902607`。
- acceptance 独立重算：16045 proposals、80225 proposed draft tokens、58473
  accepted，accepted/proposal `3.644312870052976`，含 bonus acceptance length
  `4.64904954814584`，逐位置 `[14904,13227,11688,10119,8535]`。
- HEDGE disabled/config null、proposal/active/leak counters 均 0；TP/target/draft
  rank 0–7、formal-window 八卡参与及无 crash PASS。server/sampler 定向退出、
  contexts none；keepalive `107326` 的 8×10 全卡 100%。
- archive manifest 39/39 的文件集合、size 与 SHA 独立重算全匹配。P06 `PASS`，
  P07 入口成立；P06 executor 已停止，未启动第二 attempt。

### 2026-07-29T07:47:18Z — 用户解除原截止

- 用户明确“现在没有截止时间，你往前执行就行”。原
  `2026-07-29T08:54:41Z` 只保留为历史 12 小时窗口边界，不再触发停止或收尾。
- P07/P08 继续按冻结计划执行；该授权不改变 worker/lane、source/wheel/model、
  dataset/config、单次正式 arm、进程清理、keepalive、证据或提交纪律。

### 2026-07-29T07:54:41Z — 660 分钟 checkpoint

- 实际快照于 `07:54:18Z` 提前 23 秒落盘。P07 bounded executor 已完成治理、
  计划与 TDD 阅读；static prepare/client/validator/attempt/tests 文件已齐，
  当前仅在本地执行 fail-closed 与全回归，未登录 worker或启动 live。
- 第一轮 RED→GREEN 冻结 HEDGE-on config/counter/lifecycle seam；第二轮真实
  P06 identity parity 发现 disposable `build_path_exists` 的归档/现场瞬时差异。
  修正仅排除该瞬时字段，wheel bytes/hash、installed content、source/core、
  checkpoint 与 decode contract 仍为硬门禁。
- lane 保持 P06 收尾后 dedicated keepalive `107326`；本 checkpoint 不宣称
  P07 tooling PASS，也没有 P07 attempt ID。

### 2026-07-29T08:24:41Z — 690 分钟 checkpoint

- 实际快照于 `08:23:59Z` 提前 42 秒落盘。P07 static 首轮 targeted 11/11；
  P07/P06/P05/P04/protocol/integration/core 合计 149/149，syntax/contract/
  uv lock/diff 及 P06 immutable formal artifact replay 均 PASS。
- 主 Agent未直接放行 live，追加四项实际 finding：wrapper marker 不得继承进
  server；正式 counter 必须兼容协议允许的 retry；snapshot 必须固定
  counter schema/candidate alignment/score seam；逐位置/lifecycle/budget 等
  counter 必须满足物理不变量。
- marker 泄漏已 RED→GREEN；带一次 retry 的 500-record fixture 证明旧
  exact-500 门禁误拒 initialized=501，summary-bound 修正进行中；其余两类
  forged fixture 尚待 RED→GREEN。executor 仍 static-only，lane 保持 keepalive。
- 用户指出 P06 500 结果在 docs 中不醒目；`docs/experiment/` 已新增
  `P06 native 正式 500 结果` 专节，列出完整指标、hash、文件名与 HDFS 路径。
