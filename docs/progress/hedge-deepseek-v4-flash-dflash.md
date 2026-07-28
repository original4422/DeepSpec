# DFlash × HEDGE 进展

当前标签：`IN_PROGRESS`

- Timebox：`2026-07-28T20:55:58Z` → `2026-07-29T08:55:58Z`；若 B0 未完成，`2026-07-29T05:55:58Z` 停止实现。
- 已用/剩余：约 `2h29m`；距 9 小时实现停止点约 `6h31m`，距 12 小时硬停止约 `9h31m`。
- 当前 phase：D1A 下载/发布执行中；D2 native 接入已通过主 Agent 验收并以 `37a881a` 推送。
- Worker：`4099543`，`g340-cd51-4b00-4d69-9088-7ae6-6253`，8×H20。
- Keepalive：`HEALTHY`；PID/PGID `34059`；23:23Z 重新执行 10×1 秒门禁，逐卡平均利用率仍均为 100%。
- Eagle target marker：`READY`；23:04:53Z 发布的 immutable marker、provider commit/OID、manifest SHA、formal entity、46-shard index、config/tokenizer、73 files/159,630,041,626 bytes 与零 symlink/hardlink 已由主 Agent 只读复核 PASS。
- Draft：primary D1A attempt `dflash-d1a-primary-20260728T213507Z` 首次传输到约 3.40/3.61 GB 后，同一 `curl --retry --continue-at -` 进程从调用时的初始 offset 重启并把 partial 回落至约 64 MB；`/proc` I/O、PID/inode 与 byte trajectory 已固定为 retry-reset 证据。当前第二 pass 在 23:24Z 已重新增长到 2,875,670,528/3,607,596,760 bytes（79.7%），同 PID/inode 且未再次下降；不打断当前 pass，若再次回落则单变量切换到外层 bounded resume。safetensors header contract 仍 PASS，fallback disabled。
- DSpark pure-core pointer：`READY`；主 Agent 已验证 `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/hedge-core.json`、commit `4d96f44065c07030ede67484a262006ec149626a`、parent `77053dd3ea84bb1c8dde7971f5f12759c1375e1f`、HEDGE source `9fb903d676254ea5f5d171051fb15c54f331111c`、10 个逐文件 hash 与 33 tests PASS。按计划尚未 cherry-pick，须等 D3 后由 D4 executor 消费。
- 当前 blocker：D3 只剩 D1A draft 尚未完成 HDFS 发布；target、native source/env、dataset 与 pure core 均已 READY。
- 下一检查点：完成 D1A 下载、校验、HDFS staging 与主验收；随后调度独立 D3 executor，紧邻模型启动暂停 keepalive 并执行 TP8 native smoke。

| UTC | Phase | 动作 | 结论 | Artifact | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 2026-07-28T20:55:58Z | D0 | 固定 T0、branch/worktree/lane identity | 独立资源无冲突 | `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/lane_identity.json` | 只读 worker preflight |
| 2026-07-28T21:06:55Z | D0 | 二次只读 inventory | 8×H20 空闲，无 legacy compute task，端口 31457 空闲 | `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/preflight.json` | 启动 lane keepalive |
| 2026-07-28T21:08:47Z | D0 | 8 卡 sustained keepalive gate | PASS，GPU0–7 均值 100% | `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/keepalive_gpu_samples.csv` | 保持运行，交付 D0 |
| 2026-07-28T21:10:00Z | D0 | 只读 coordination pointer 检查 | target/core pointers 均 WAIT | `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/session_manifest.json` | 主 Agent 验收 |
| 2026-07-28T21:18:00Z | D0 | 主 Agent 直接复核 JSON、CSV、脚本、远端 keepalive 与 DSpark worktree | D0 PASS；80 条采样与跨 artifact identity 一致，远端 keepalive HEALTHY，未混入 DSpark 改动 | `docs/plan/handoffs/dflash-phase-d0-handoff.md` | 提交治理基线并调度 D1A/D1B/D1C |
| 2026-07-28T21:26:24Z | D1A/D1B/D1C | 30 分钟 checkpoint：三阶段并行；复核 canonical pointers 与 shared index | D1B 已固定 SGLang base 并在 uv sync，D1C 已进入 harness TDD；D1A 运行中；keepalive HEALTHY；target/core 仍 WAIT；index 无他人 staged change | `c11fe2a`、各 D1 executor 运行状态 | 完成并逐项验收三个 D1 handoff |
| 2026-07-28T21:49:36Z | D1C | 主 Agent 复算 shared manifest、shuffle、artifact hash并复跑 13 个 mock tests；纠正计划外 logprob 请求后复验 | D1C PASS；32/500 无重叠，正式请求从 `meta_info.output_token_ids` 取 token IDs，13 tests OK | `docs/plan/handoffs/dflash-phase-d1c-handoff.md` | 提交 D1C 关键节点；继续 D1A/D1B |
| 2026-07-28T21:56:49Z | D1A/D1B | 60 分钟 checkpoint：直接复核 D1B env/source/contract，检查 D1A heartbeat 与 canonical pointers | D1B PASS、D1C 已以 `1bcc655` push；D1A 31.5% 且无 retry/error；keepalive HEALTHY；target/core 仍 WAIT；index 无他人 staged change | `docs/plan/handoffs/dflash-phase-d1b-handoff.md`、D1A heartbeat | progress-only commit 后提交 D1B，并调度 D2 |
| 2026-07-28T22:26:00Z | D1A/D2 | 90 分钟 checkpoint：复核 worker 与 10×1 秒 keepalive gate，检查 D1A heartbeat、D2 测试及 coordination pointers | worker 仍为 8×H20、八卡均值 100%；D1A 78.9% 且无 retry/error；D2 已有 primary 5/5、overlap 7 tests（1 CUDA-only skip）、chat 82/82 和四组既有 config/registry tests 全部 PASS，handoff 收尾中；pure core READY，target 仍 WAIT | D1A heartbeat；`hedge-core.json`；D2 executor 测试回报 | 只提交本 progress 文件；随后验收 D1A/D2，target 就绪前不进入 D3 |
| 2026-07-28T22:53:00Z | D1A/D2 | 2 小时 checkpoint：主验 D2 reproducible patch/测试/identity；审计 D1A partial 回落并继续监控第二 pass；复核 coordination pointers | D2 PASS 并以 `37a881a` push；D1A 首次约 3.40 GB 后因同一 curl internal retry 从初始 offset 重启，证据已固定，第二 pass 约 1.01/3.61 GB 且单调；keepalive PID `34059` 健康；pure core READY，target 仍 WAIT | `37a881a`；D1A `retry_reset_diagnostic.json` 与 status trajectory；`hedge-core.json` | 只提交本 progress 文件；不打断当前传输，完成后验收 D1A；target 就绪前不进入 D3 |
| 2026-07-28T23:25:00Z | D1A/D3 readiness | 2.5 小时 checkpoint：复核 worker list 与 10×1 秒 keepalive gate；独立审计 Eagle target marker/provider/manifest/formal entity；监控 D1A retry recovery | worker `4099543` 仍为 8×H20，八卡均值 100%；target READY，revision/73 files/159,630,041,626 bytes/46 shards/index/config/tokenizer/OID/manifest/immutable publication 全部 PASS；D1A second pass 2.876/3.608 GB 且单调 | target complete marker `af6f274a…facd`；D1A retry trajectory；keepalive PID `34059` | 只提交本 progress 文件；完成并验收 D1A 后立即调度独立 D3 executor |
