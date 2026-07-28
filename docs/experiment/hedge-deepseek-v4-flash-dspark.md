# HEDGE × DeepSeek-V4-Flash-DSpark

## 快速结果

- 状态：`IN_PROGRESS`
- 记录更新时间：`2026-07-28T23:57:08Z`
- 自主窗口：`2026-07-28T20:54:41Z` → `2026-07-29T08:54:41Z`
- B0：`NOT_RUN`
- 结论/首要事项：P00–P03 均已 PASS 并 commit/push；P04 静态 tooling 已由
  主 Agent 验收并以 `210b281` commit/push。模型/server、native/B0 attempts
  均未启动；下一步是把 native live smoke 分配给新的 bounded executor。
- 正式 native run：`NOT_RUN`
- 正式 HEDGE run：`NOT_RUN`
- worker / TP / GPU 参与：`4106666` / 8 / 模型参与 `NOT_RUN`；keepalive 8/8 gate `PASS`
- model / checkpoint：固定目标
  `deepseek-ai/DeepSeek-V4-Flash-DSpark@62af8fffb2f7030cac4de2f0169f5b8d1101b646`；
  P00 checkpoint r1 PASS，canonical identity 记录 75 files / 48 shards /
  166898666759 bytes，按计划未做全量 hash
- SGLang：固定 base
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，独立 source 双侧 clean；
  env/source identity PASS
- g / B / m：`NOT_CALIBRATED` / `NOT_CALIBRATED` / 固定目标 `1`
- native TPS / HEDGE TPS / delta：`NOT_RUN` / `NOT_RUN` / —
- native accepted length / HEDGE accepted length / delta：`NOT_RUN` / `NOT_RUN` / —
- native GSM match / HEDGE GSM match：`NOT_RUN` / `NOT_RUN`
- artifact root：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap`
- commits：P00 support `ebe196608893bd9972e771644ed25d019444d0f3`；P01 protocol
  `77053dd`；pure core `4d96f44065c07030ede67484a262006ec149626a`；
  integration `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`；P03 identity/progress
  `eb7b4bff850e017d708bccf27e1e1e2132bd1cd3`；config / result 尚未创建
- DeepSpec worktree / branch / accepted integration commit：
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark` /
  `exp/hedge-v4-dspark` /
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`
- latest implementation HEAD/pushed：
  `210b2815b8cdb1905a5ad57e8b565319567f8405`
- 下一步：重新只读核对 lane/keepalive 后，运行唯一的新 native P04 attempt；
  主 Agent 验收并恢复 keepalive 后才允许 B0 attempt

## 当前阶段

| Phase | 状态 | 当前证据 | 尚缺 |
| --- | --- | --- | --- |
| P00 | `PASS_COMMITTED` | canonical session 全部 checks true；support commit/push `ebe196608893bd9972e771644ed25d019444d0f3` | — |
| P01 | `PASS_COMMITTED` | handoff；13 tests PASS；dataset verify 18/18；独立 indices/hash 全 true；commit/push `77053dd` | — |
| P02 | `PASS_COMMITTED` | 历史 pinned 与新正式 venv 均 33/33；identity hashes PASS；commit/push `4d96f44065c07030ede67484a262006ec149626a`；READY marker 已发布 | — |
| P03 | `PASS_COMMITTED` | zero-context replay manifest `57328fd1…` / tree `996fbf…`、22/33/13、non-CWD 9/9 与主 Agent独立复验均 PASS；commits `3d2c6cc`、`eb7b4bf` 已 push | — |
| P04 | `IN_PROGRESS` | read-only preflight PASS；静态 tooling 20/20、contract/syntax/identity/cleanup review PASS；commit/push `210b281` | native smoke、主验收、B0 smoke |
| P05–P08 | `NOT_STARTED` | — | P04 门禁 |

## 固定实验协议

- dataset：Hugging Face `openai/gsm8k`，`main/test`，revision
  `740312add88f781978c0658806c59bc2815b9866`
- selection：DeepSpec seed `980406` 确定性 shuffle；前 32 条 calibration，随后
  不重叠的 500 条 formal；calibration 前 10 条作为 warmup
- request：无 system prompt；原 question 追加
  `Please reason step by step, and put your final answer within \boxed{}.`；
  `enable_thinking=false`、`temperature=0`、`top_p=1`、`max_tokens=512`
- execution：顺序单请求；每请求最多 3 次总尝试；保存完整响应和 token IDs
- formal timing：warmup 外，使用 `time.monotonic_ns` 从 formal #1 发出前到 #500
  达到终态后；HTTP、生成、排队、retry/backoff 均计入
- arms：native speculative baseline、calibration 上 HEDGE B=0、自动校准后的唯一
  HEDGE B>0；三个 arm 保持相同 TP=8、proposal width=5 和 decode-affecting 配置

## P01 acquisition evidence

- `artifacts/hedge-dspark/p01-protocol/gsm8k_calibration_32.jsonl`：
  32 行，SHA-256
  `28a7080565cde90b8cf1db79c88bb463861515fabe3fa7409481802104a6e47d`
- `artifacts/hedge-dspark/p01-protocol/gsm8k_formal_500.jsonl`：
  500 行，SHA-256
  `33554b90f751252ced2cfd16333d749f427c84cf025dccef4c7934144e9d5108`
- manifest 声明 calibration/formal 不重叠，dataset fingerprint
  `59ec1b7f9357c7a2`，content SHA-256
  `32f83c6becb3ba208d16bff80901547266e937b3f77c56d3ebe6a9bc3a9b41c4`
- protocol fingerprint：
  `eaa79a75fbf3bf78ed070e33b68a917172386db3b668e1be93b1fe97e0f2f152`
- handoff：`docs/plan/handoffs/hedge-dspark-p01-20260728T205900Z.md`
- 主 Agent 独立复核：13 tests PASS、dataset verifier 18/18 true、indices/hash
  复算全 true；P01 review PASS，commit/push `77053dd`。

## Attempt 时间线

| Attempt | 唯一变化 | 结果 | Evidence |
| --- | --- | --- | --- |
| `20260728T205441Z-p00-bootstrap` inventory | 建立 session 并只读盘点 lane | 8×H20 inventory PASS；当时 compute context 为空 | HDFS `worker_inventory.json` |
| keepalive attempts 01–03 | 修正 dedicated keepalive 的启动环境 | 最终 8×10×1s gate PASS；各卡均值 100%；PID 1697 | HDFS `keepalive_initial.json` |
| `20260728T205441Z-p00-bootstrap` env | 首次独立 venv/source setup | FAIL：launcher 找不到 `uv` | HDFS `environment-attempts/.../uv-sync.log` |
| `20260728T211013Z-p00-env-r1` | 显式 uv 路径后重试 | FAIL：固定 SGLang Git fetch 遇到 SSL timeout | HDFS `environment-attempts/.../uv-sync.log` |
| `20260728T211739Z-p00-env-r2` | 仅复用现有固定 uv cache | PASS：frozen sync、pip check、env/source identity 完成 | HDFS `environment_identity.json`、`sglang_base_identity.json`、`uv-sync.log` |
| checkpoint scope attempt | 首轮 checker scope | FAIL，证据保留；未改变 checkpoint | HDFS `checkpoint-attempts/...scope-failed/` |
| checkpoint r1 | 仅修复 checker scope | PASS：75 files / 48 shards / 166898666759 bytes；未全量 hash | HDFS canonical `checkpoint_identity.json` |
| CUDA link probe | guarded 创建并二次核对固定 `lib64` links | PASS：`cc` return code 0，二次 pass 均为 `verified` | HDFS `cuda_link_probe.json` |
| P00 finalizer | 汇总最终 worker/process/identity 状态 | PASS：全部 session checks true；无 model server；下一 eligible phase=P03 | HDFS `session.json` 与 P00 handoff |
| `20260728T205701Z-p02-core` | 复制并收窄纯 HEDGE core | P02 PASS；正式 venv 33/33；commit/push `4d96f44065c07030ede67484a262006ec149626a`；READY marker 已发布 | handoff 与 HDFS `hedge-core.json` |
| `20260728T220619Z-p03-cpu-build` | 单一 deep adapter 的 CPU/source integration | `IN_PROGRESS`；review guard 已修复，首轮 20/20 tests PASS；新增 fixture 总回归及 patch/identity/wheel pending | operational heartbeat 与 fixed external source dirty state |
| `20260728T224800Z-p03-locked-rebuild` | exact uv build lock 后 clean rebuild | PASS：zero-context artifact clean gate、tree/hash parity 与总回归均通过；commit/push `3d2c6cc` | final manifests/log、handoff、主 Agent replay 与 22:48 heartbeat |
| `20260728T230700Z-p04-preflight` | P04 read-only lane/keepalive preflight | PASS：exact 8×H20、无未知任务、PID 4730、8×10×1s 100%；无 server | HDFS `worker_inventory.json` |
| `20260728T230647Z-p04-native-smoke-r1` / B0 | 原计划 live attempts | `NOT_RUN`；首次 executor 被中断/重分配，未 pause keepalive、未动 GPU | 调度记录；无实验 artifact |
| P04 static tooling | 固定 native/B0 lifecycle、client、sampler、process guard 与 validator | 主 Agent验收 PASS：executor 20/20，主复验 20/20，contract/syntax/whitespace PASS；commit/push `210b281` | `artifacts/hedge-dspark/p04-tooling/tooling_test.log` |

## P04 integration smoke 当前状态

- 状态：`IN_PROGRESS`；静态 tooling `PASS_COMMITTED`；B0 `NOT_RUN`；
  模型/server 从未启动。
- 首次 read-only preflight artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T230700Z-p04-preflight/worker_inventory.json`。
  worker `4106666` 精确 8×H20、无未知任务、keepalive `4730/4730/4730`、
  8 卡 10×1 秒均 100%。
- 首次 executor 在 preflight 后两 turn 无落盘而被主 Agent 中断/重分配；未暂停
  keepalive、未操作 GPU。该事件是调度问题，不是实验 blocker。
- `p04_tooling` 全程未登录 worker、未触碰 GPU/keepalive/model。它交付 6 个
  lifecycle/client/sampler/process/validator 脚本、20 个离线测试与测试证据。
- executor 20/20 tests PASS；主 Agent独立重跑 20/20 PASS，并复核 exact native
  no-config、B0 config bytes、formal wheel/source/checkpoint identity、
  PID/PGID/SID/start-ticks/cmdline/hostname、8-rank/8-GPU request evidence、
  cleanup-before-keepalive 与 immutable archive 门禁。staged whitespace 和
  contract JSON 均 PASS；工具 commit/push 为
  `210b2815b8cdb1905a5ad57e8b565319567f8405`。
- 直接执行非 executable shell 文件曾在本地得到一次 `Permission denied`；固定
  合同一直是 `bash <absolute-script-path>`，按该方式复验 PASS。它不是 live
  attempt、没有状态变化，也不是实验 blocker。
- 下一 bounded executor 只运行 native live smoke；主 Agent验收前不得启动 B0。

## P03 integration 当前证据

- exact `p03-build` pins：`build==1.5.0`、`setuptools==81.0.0`、
  `setuptools-rust==1.13.0`、`setuptools-scm==10.2.1`、`wheel==0.47.0`。
- identity：pyproject `2ef3e7…`，uv.lock `0524523…`，build script `5553c8…`；
  lock check 与 frozen group sync/check PASS。
- locked07 formal wheel SHA-256：
  `f2054c32025182ea8b4e57731ffa9d0150a40d5ac296f34e93c9b124181c7262`，
  14,646,094 bytes；clean replay build/uv install PASS。旧 `2f267…` wheel 为
  `PASS_SUPERSEDED`。
- 22/22 integration、33/33 pure core、13/13 protocol、非 DeepSpec CWD import、
  9/9 hashes 与 manifest cross-check PASS。executor handoff finished
  `2026-07-28T22:58:59Z`。
- 最终 patch SHA-256 `8e8cc840...`，格式为 full-index/binary/zero-context；
  applicator 显式使用 `--unidiff-zero`。主 Agent 在独立 worktree
  `/tmp/deepspec-p03-main-verify.hok7bb` 重放后得到相同 manifest
  `57328fd1...`、tree `996fbfd6...`，并重跑 22/33/13 全部 PASS。
- 真实 staged `git diff --check` PASS；integration commit/push
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`。P03 已验收完成。

## HEDGE core 当前证据

- 固定 source commit：
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- canonical path：`deepspec/hedge_spec/`
- handoff 记录的现有测试：两个 CPU-mode torch 环境中各 33 tests PASS。
- 主 Agent 已独立确认 pinned-torch 33/33 tests，并核对 7 个 source 与 9 个 target
  identity hashes 全匹配。
- 新 `/home/tiger/venvs/hedge-v4-dspark` 中 33/33 tests 已 PASS。
- pure-core commit/push：
  `4d96f44065c07030ede67484a262006ec149626a`（parent `77053dd`）。
- matching READY marker：
  `/mnt/hdfs/pengzegang/DeepSpec/coordination/hedge-v4/hedge-core.json`，
  SHA-256
  `c9c09cd23655e395d3f3b85cbc7e1740194f9e4e174938cb5f54594afe31b80c`。
- P02 阶段门禁已满足并由主 Agent验收 PASS。

## GPU、进程与 shutdown

- P00 inventory 在 `2026-07-28T20:56:10Z` 记录 worker `4106666` 的 8 张 H20，
  compute capability 9.0，每卡 97871 MiB；当时无 compute context。
- `keepalive-migration/keepalive_migration.json` 记录：旧 runtime supervisor
  `1697/1697/1697` 精确停止且 CUDA contexts 为 none；新 HEDGE venv supervisor
  `4730/4730/4730` 启动，最终 8 张卡 10×1 秒门禁 `PASS`。
- P00 final inventory 记录八张卡各有且仅有登记 keepalive context，没有
  SGLang/model server；canonical `session.json` 全部 checks 为 true。
- `22:06:19Z` operational heartbeat 的 worker-list SHA-256 为
  `bda700d189777343cbf7183fecb0b72884b418bd19365f96c99be7ee99516e8e`，
  keepalive JSON SHA-256 为
  `ef2f0f0417f714adbe63eb6726781fbe2b934cf08e527e8a57a34df1878ed87e`；
  worker `4106666` 仍为精确 8×H20，PID/PGID/SID `4730/4730/4730`，
  8 卡 10×1 秒均为 100%。
- 主 Agent 于 `22:26:35Z–22:27:14Z` 再次只读复核 `mlx worker list` 与
  remote keepalive status：worker `4106666` 仍精确 8×H20；PID/PGID/SID
  `4730/4730/4730`；8 卡 10×1 秒 mean/min/max 均为 100%，各占 815 MiB；
  无模型 server。该 keepalive 是 operational load，不计作正式实验负载或结果。
- P04 preflight 与主 Agent `23:06Z` 复核均确认 worker `4106666` 精确 8×H20、
  PID/PGID/SID `4730/4730/4730`、8 卡 10×1 秒均 100%、无 server。首次漏传
  worker-id 被脚本 fail-closed 拒绝且无状态变化；随后正确 status PASS。
- `22:48Z` operational heartbeat 位于
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap/operational-heartbeats/20260728T224800Z-p03-locked-rebuild/`；
  worker `4106666` 精确 8×H20，PID/PGID/SID `4730/4730/4730`，
  8 卡 10×1 秒均 100%，无模型 server。该 keepalive 仅是 operational load。
- 尚未启动 SGLang model server，尚无 TP rank 0–7 初始化、模型显存或请求期间八卡
  参与证据。

## 限制与复现状态

- P00–P03 已完成主 Agent PASS 验收并 commit/push；P04 静态 tooling 已完成，
  live GPU smoke 尚未启动。
- B0、q25 calibration、native 500 与 HEDGE B>0 500 均未运行。
- 当前没有 TPS、acceptance、GSM8K 正式结果或可比较 delta。
- 尚未发生模型 shutdown；env setup 失败属于依赖获取路径，不是 CUDA/NCCL/worker
  crash。
