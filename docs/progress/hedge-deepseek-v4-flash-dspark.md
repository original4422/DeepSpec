# HEDGE × DeepSeek-V4-Flash-DSpark 进展

## 最新快照

- 状态：`IN_PROGRESS`
- 快照时间：`2026-07-28T23:27:21Z`（首个合并 patch 上下文失配后拆分落盘，较计划晚 2 分 40 秒）
- 自主窗口：`2026-07-28T20:54:41Z` → `2026-07-29T08:54:41Z`
- elapsed / deadline：`02:32:40` / `2026-07-29T08:54:41Z`
- 当前 phase：P00–P03 均已 PASS；P04 `IN_PROGRESS`
- executor / 结论：
  - P00：主 Agent 验收 `PASS`；support commit/push `ebe196608893bd9972e771644ed25d019444d0f3`
  - P01：主 Agent 验收 `PASS`，commit/push `77053dd`
  - P02：主 Agent 验收 `PASS`；新正式 venv 33/33 tests PASS，commit/push `4d96f44065c07030ede67484a262006ec149626a`，READY marker 已发布
  - P03：主验收 `PASS`；integration `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc` 与 identity/progress `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3` 均已 push
  - P04：静态 tooling executor `IN_PROGRESS`；模型/server 从未启动，native/B0 attempts 均未运行
- worker / lane：`4106666` / 全部 8×NVIDIA H20 / 预定 TP=8
- keepalive / server / PID：P04 read-only preflight 与主 Agent `23:06Z` 复核均记录 worker `4106666` 精确 8×H20、PID/PGID/SID `4730/4730/4730`、8 卡 10×1 秒均 100%；模型 server `NOT_STARTED`
- 最新 attempt：`20260728T230700Z-p04-preflight`；计划 native/B0 attempts 尚未运行
- HDFS artifact：`/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap`
- Git：worktree `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`；branch `exp/hedge-v4-dspark`；HEAD/pushed `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3`
- commits：P00 support `ebe196608893bd9972e771644ed25d019444d0f3`；P01 protocol `77053dd`；pure core `4d96f44065c07030ede67484a262006ec149626a`；integration `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`；P03 identity/progress `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3`；config / result 尚未创建
- 首要事项：先完成并由主 Agent验收静态 8 卡 lifecycle/client/sampler/validator/tests 门禁，之后才允许 native attempt；这不是实验 blocker
- 下一检查点：`2026-07-28T23:54:41Z`
- 下一 30 分钟动作：完成 P04 tooling engine-identity test 复跑及其余静态门禁；
  主审通过前不暂停 keepalive、不启动 native/B0 attempt

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
