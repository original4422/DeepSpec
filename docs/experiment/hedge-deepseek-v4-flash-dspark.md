# HEDGE × DeepSeek-V4-Flash-DSpark

## 快速结果

- 状态：`IN_PROGRESS`
- 记录更新时间：`2026-07-29T02:48:50Z`
- 自主窗口：`2026-07-28T20:54:41Z` → `2026-07-29T08:54:41Z`
- B0：P04 单请求 smoke `PASS`；P05 32 条 `NOT_RUN`
- 结论/首要事项：P00–P04 已 PASS。P05 native r1 的 32 条输出、TP8、请求期八卡、
  cleanup 与 archive 均完整，但主 Agent验收发现 strict trace 混入 4 行启动
  warmup evidence，且 sampler 在定向停止边界误记 FAIL；因此 r1 明确记为
  `FAIL_TRACE_SCOPE`，其 q25 不采用。两个非 decode recovery 已 test-first 修复并
  commit/push；下一步只重跑新的 native calibration，再验收后运行 P05 B0。
- 正式 native run：`NOT_RUN`
- 正式 HEDGE run：`NOT_RUN`
- worker / TP / GPU 参与：`4106666` / 8 / P04 native+B0 `PASS`；P05 r1 live
  evidence `PASS` 但阶段为 `FAIL_TRACE_SCOPE`；keepalive 8/8 gate `PASS`
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
- artifact root：P05 failed evidence
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T020144Z-p05-native-calibration-r1`
- commits：P00 support `ebe196608893bd9972e771644ed25d019444d0f3`；P01 protocol
  `77053dd`；pure core `4d96f44065c07030ede67484a262006ec149626a`；
  integration `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`；P04 result
  `3e10b780264557e84a3cab5c1a196dc7c2a00496`；P05 tooling `ce5d672`；
  sampler recovery `6b7145d`；trace-scope recovery `eb4962f`；
  calibration config / result 尚未创建
- DeepSpec worktree / branch / accepted integration commit：
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark` /
  `exp/hedge-v4-dspark` /
  `3d2c6ccc93abfd70bc2df3f57e67f5c2f73ccedc`
- latest implementation HEAD/pushed：
  `eb4962f49a16ec88721c9fc96be5daffcc1367d1`
- 下一步：P05 重跑 32 条 scoped native calibration/trace；主验收 PASS 后才运行
  B0 并自动计算、冻结 q25

## 当前阶段

| Phase | 状态 | 当前证据 | 尚缺 |
| --- | --- | --- | --- |
| P00 | `PASS_COMMITTED` | canonical session 全部 checks true；support commit/push `ebe196608893bd9972e771644ed25d019444d0f3` | — |
| P01 | `PASS_COMMITTED` | handoff；13 tests PASS；dataset verify 18/18；独立 indices/hash 全 true；commit/push `77053dd` | — |
| P02 | `PASS_COMMITTED` | 历史 pinned 与新正式 venv 均 33/33；identity hashes PASS；commit/push `4d96f44065c07030ede67484a262006ec149626a`；READY marker 已发布 | — |
| P03 | `PASS_COMMITTED` | zero-context replay manifest `57328fd1…` / tree `996fbf…`、22/33/13、non-CWD 9/9 与主 Agent独立复验均 PASS；commits `3d2c6cc`、`eb7b4bf` 已 push | — |
| P04 | `PASS` | native r4 `RECOVERED_PASS`；B0 r1 rc=0，API/counter/TP8/GPU/shutdown/archive 全 PASS；完整 token IDs 与 native 相同 | — |
| P05 | `IN_PROGRESS` | native r1 保留为 `FAIL_TRACE_SCOPE`；sampler/trace-scope recovery `6b7145d`、`eb4962f` 已 push；118/118 回归 PASS | scoped native r2、B0 32、q25/config freeze |
| P06–P08 | `NOT_STARTED` | — | P05 门禁 |

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
| `20260728T235900Z-p04-native-smoke-r2` | 首次实际 native launcher；无 decode 配置变化 | FAIL：pre-pause engine identity 发现 worker-local formal wheel 缺失；server/model/request 未启动；archive PASS，keepalive 从未暂停且 after PASS | HDFS attempt root；`engine_identity.json`、`shutdown.json`、`archive_manifest.json` |
| P04 persistent-wheel recovery | 仅把 formal wheel identity 从 build-local `/tmp` 改为 pinned HDFS entity | PASS：RED→GREEN、22/22、no-fallback、两次 worker engine probe 与 keepalive gate；commit/push `ddc372b` | HDFS hash-named wheel；tooling log；probe IDs `...001241Z...r3`、`...001600Z...main` |
| `20260729T001700Z-p04-native-smoke-r4` | recovery 后首个 native live attempt；decode 配置不变 | `RECOVERED_PASS`：TP8/48 shards/target+draft/API/八卡参与成立；原 live validator 因全局 cadence 硬门槛 rc=1，cleanup/contexts/keepalive 均成立 | immutable HDFS attempt；API 91 tokens；1419×8 GPU rows；archive PASS |
| P04 cadence validator recovery | 只把全局 cadence 硬失败改为诊断统计 | PASS：精确 RED→GREEN、五类反例仍 fail-closed、92/92；只读 r4 replay PASS；commit/push `37a8d37` | 原 HDFS FAIL 不修改；全局 10 个 >2.5s，请求窗口 0 个 |
| `20260729T010603Z-p04-b0-r1` | 唯一 B0 smoke；固定 wheel/TP8/width5/backend | PASS rc=0：91 token IDs 与 native 相同；25 proposals；TP8/八卡/API/shutdown/archive 全 PASS | immutable HDFS attempt；ID hash `b7288ead…8649db` |
| P05 static tooling | 固定 32 条 native-trace/B0 lifecycle、client、validator 与 reducer | PASS：executor 与主 Agent均 106/106；commit/push `ce5d672` | `artifacts/hedge-dspark/p05-tooling/tooling_test.log` |
| `20260729T020144Z-p05-native-calibration-r1` | 首个 32 条 native trace attempt | `FAIL_TRACE_SCOPE`：32/32 输出成功且 live/shutdown/archive 完整；trace 含 1 个非 cohort warmup RID 的 4 行，sampler terminal status 在停止边界为 FAIL | immutable HDFS attempt；原 488 行 trace 与 artifact 不修改 |
| P05 sampler recovery | 只修正 stop 信号打断活跃 `nvidia-smi` query 的清理语义，并把 terminal status/count 纳入 artifact gate | PASS：真实 query error 仍失败；P04/P05 gate fail-closed；118/118 总回归；commit/push `6b7145d` | 旧 r1 被新 gate 精确拒绝；P04 两个 clean 对照通过 |
| P05 trace-scope recovery | cohort 前 clear+验零，post/reducer 以 32 个 response RID 封闭 trace | PASS：旧 r1 extra RID `505959…` 被精确拒绝；全量 q25 2.083333 与 cohort-only 2.0625 的差异证明影响实质；commit/push `eb4962f` | output directory 未创建；必须重跑 native |

## P04 integration smoke 当前状态

- 状态：`PASS`；静态 tooling `PASS_COMMITTED`；native r2
  `FAIL_PRE_PAUSE_RECOVERED`；persistent-wheel recovery `PASS_COMMITTED`；
  native r4 `RECOVERED_PASS`；cadence recovery `PASS_COMMITTED`；B0 r1
  `PASS`。
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
- r2 bounded executor 只运行了该 native launcher，未重试、未运行 B0；主 Agent
  验收新的 native PASS 前仍不得启动 B0。
- native r2 artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T235900Z-p04-native-smoke-r2`。
  `checkpoint_identity` 与 8×H20 inventory PASS；`engine_identity` 仅有
  `formal_wheel_exists`、`formal_wheel_size` 和
  `formal_wheel_actual_sha256` 三项 false。其余 fixed distribution、
  installed 9-file content、RECORD、source/base/tree/core/integration ancestry、
  CUDA 13 toolchain 与 compat checks 全 true。
- manifest 的 build provenance 路径是
  `/tmp/deepspec-hedge-dspark-p03-build.locked07/wheel/sglang-0.5.16-cp311-cp311-linux_x86_64.whl`。
  该实体仍在开发机存在，14,646,094 bytes，SHA-256
  `f2054c32025182ea8b4e57731ffa9d0150a40d5ac296f34e93c9b124181c7262`；
  worker 的独立 NVMe `/tmp` 中不存在。因此根因是 storage-domain identity，
  不是 wheel 内容、安装漂移、checkpoint、CUDA 或 GPU blocker。
- r2 在 `keepalive_pause` 前退出。`server.log`、API、counter、GPU samples 是显式
  `MISSING` placeholder；没有 server/sampler process group 或 signal。
  `archive_manifest.status=PASS`；shutdown overall FAIL 只反映 main rc=1 与进程
  从未启动。keepalive 从未暂停，after gate 为 PID/PGID/SID
  `4730/4730/4730`、8 卡各 10 样本 100%。
- recovery 只改变 formal wheel 的存储身份。P03 build path 保留为 provenance；
  新 persistent entity：
  `/mnt/hdfs/pengzegang/DeepSpec/artifacts/hedge-dspark/formal-wheel-f2054c32025182ea8b4e57731ffa9d0150a40d5ac296f34e93c9b124181c7262/sglang-0.5.16-cp311-cp311-linux_x86_64.whl`。
  source、staging、final 均为 14,646,094 bytes / SHA-256
  `f2054c32025182ea8b4e57731ffa9d0150a40d5ac296f34e93c9b124181c7262`；
  hash-named staging 经 no-clobber directory rename 发布后已不存在，source 保留。
- 最小 regression 在修复前 1 test FAIL，修复后同一命令 PASS；另有
  valid build + corrupt persistent fixture，确认绝不 fallback。完整 22/22 tests、
  shell/JSON/compile/import/contract/diff/debug gates 与主 Agent独立 22/22 均 PASS。
- executor probe `20260729T001241Z-p04-engine-probe-r3` 与主 Agent probe
  `20260729T001600Z-p04-engine-probe-main` 均在 worker `4106666` 得到
  `engine status=PASS`、`false_checks=[]`、`build_path_exists=false`，并实际读取
  persistent size/hash；两次均未 pause/model，keepalive 8×10 全 100%。
  recovery commit/push：
  `ddc372b5118595d15bfc217e7c3529c0bf86c852`。
- native r4 immutable artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T001700Z-p04-native-smoke-r4`。
  服务冷启动 1726.254 秒后 ready；TP0–TP7 均完成 NCCL、target 与
  `DeepseekV4ForCausalLMDSpark` draft 加载，target/draft 都是
  `flashinfer_mxfp4`。单次固定请求首次 HTTP 成功，10.353 秒、91 completion
  tokens、`\boxed{5}` 且匹配；native speculative metadata 为 70/105 accepted
  drafts、21 verifies。
- r4 `gpu_samples.csv` 有 1419 个连续 ordinal、11352 行，每组精确 8 个固定
  UUID 且 monotonic timestamp 严格递增。请求窗口有 9 组；八卡最大利用率
  85%–99%，模型显存约 79.6–80.1 GiB。全局只有冷 JIT/cleanup 的 10 个间隔
  略超旧 2.5 秒上限，最大 2.687626856 秒；请求窗口最大 1.199117809 秒。
- 原 `live_validation.json`、`shutdown.json` 的 FAIL/rc=1 保持不可变；唯一错误
  是旧 cadence gate。server PID 7941 与 sampler PID 7950 按登记 identity
  定向停止，cleanup rc=0、contexts none、无外部 signal；keepalive 恢复为
  `21792/21792/21792`，8×10 全卡 100%，archive PASS。因此主 Agent依据原始
  证据和修复后只读 replay 把 native r4 记为 `RECOVERED_PASS`，而不是改写原
  attempt 为 PASS。
- cadence recovery 精确 fixture 在修复前复现同一错误，修复后转绿；缺 ordinal、
  缺 GPU row、非单调 timestamp、请求无 sample、请求未 bracket 五类反例仍
  fail-closed。executor 与主 Agent各自复验 33+13+22+24=92/92 tests PASS；
  只改变 repo validator/tests，不改变 SGLang wheel 或任何 decode 配置。
  commit/push：
  `37a8d37470660cca34a5d14efe2e84553fa6ec38`。
- B0 r1 immutable artifact：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T010603Z-p04-b0-r1`。
  startup 1091.204 秒后 ready；launcher rc=0。固定 config bytes 为
  `{"B":0,"g":1e30,"m":5,"value_scheme":"normalized_suffix","block_size":5}`，
  HEDGE mode enabled；25 proposals、`verify_num_draft_tokens=6`、125 verifiable
  drafts、strict/HEDGE accepted 75/75、relaxed mismatch/regret/state leak 均 0。
- B0 API 首次成功，3.306 秒、91 completion tokens/IDs、`\boxed{5}` 且匹配；
  主 Agent逐项比较 native r4 与 B0 token IDs 为 true，canonical JSON SHA-256
  都是 `b7288ead4694ee70156e7d90c5fd63118b4f46e1347d7f263ddc1472ed8649db`。
  该单请求相等只验收 P04 smoke，不替代 P05 的 32 条 B0 核查。
- B0 live validation：TP/target/draft ranks 都是 0–7，两次 48/48 marker，
  crash markers 为空；请求期每个 UUID 有 3 个 sample，显存
  79,573–80,053 MiB、最大利用率 82%–99%。最终 CSV 935 个连续 ordinal、
  7480 行，每组精确 8 卡，严格单调且无 >2.5 秒 cadence outlier。
- server PID 23064、sampler PID 23071 仅在登记 identity 校验后受控 SIGTERM；
  main/cleanup rc=0、contexts none、无外部 signal。keepalive 恢复为
  `32894/32894/32894`，attempt 内与 executor 独立复核均为 8×10 全卡 100%；
  API/counters/live/artifact/shutdown/archive 全 PASS，33 files 完整封存。

## P05 calibration 当前状态

- 状态：`IN_PROGRESS`。首个 native-trace attempt
  `20260729T020144Z-p05-native-calibration-r1` 保留为
  `FAIL_TRACE_SCOPE`；它不是可用于冻结参数的 calibration PASS，P05 B0 尚未运行。
- r1 固定身份与模型主链路成立：DeepSpec 运行前 HEAD `ce5d672`、SGLang base
  `fdebc938…`、formal wheel `f2054c…`、worker `4106666`、TP=8、DSpark width=5、
  target/draft `flashinfer_mxfp4`。TP/target/draft ranks 均为 0–7，两次 48/48
  load marker，server crash markers 为空。
- 32 条固定 calibration 全部首次成功，0 failure / 0 retry，共 5183 completion
  tokens；输出 SHA-256
  `de4cfd8fbd5d0f9ba7f0e15772c8ccb4cb46f1683234faf558d4aec754f2987f`。
  主 Agent逐条复算原始 dataset index/order/question/user content、无 system、
  `enable_thinking=false`、`temperature=0`、`top_p=1`、`max_tokens=512` 与完整
  token IDs，32/32 均匹配冻结协议。
- 请求窗口每个固定 GPU UUID 都有 149 个 sample，显存
  79,573–80,053 MiB，最大利用率 96%–99%；完整 CSV 为 1066 个连续 ordinal、
  8528 行，每组精确 8 UUID。server/sampler 只按登记 identity 定向停止，
  contexts none；keepalive 恢复为 `44844/44844/44844`，attempt 内及主 Agent
  `02:35Z` 独立复核均为 8×10 全卡 100%。
- r1 的首个根因是 trace scope。sealed trace 有 488 行/33 个 RID；其中 32 个
  output response RID 对应 484 行，额外启动 warmup RID
  `505959725a104b34a193d3f481be36ac` 对应 4 行。全量线性 q25 为
  `2.083333333333333`，严格 cohort-only q25 为 `2.0625`，所以污染会实质改变
  参数，不能用文档解释或静默过滤后宣称成功。
- 第二个独立问题位于清理边界：live validation 在 `02:23:30Z` 已 PASS，server
  于 `02:23:34Z` 定向停止，CSV 到 `02:23:40Z` 仍完整；同一时刻 sampler PGID
  收到 SIGTERM，活跃 `nvidia-smi` child 被打断，旧 sampler 把该 stop race 写成
  `gpu_sampler_status.status=FAIL`。旧 artifact validator 漏验该 terminal status。
- sampler recovery `6b7145d` 只在 query exception 后复查 stop condition；仍在
  active 状态的真实 `nvidia-smi` error 原样失败。同时 P04/P05 required artifacts
  与 finalizer 新增 `status=stopped` 及 `sample_count==CSV ordinal count` 门禁。
  旧 r1 被精确拒绝，P04 native/B0 clean archive 分别以 1419/935 对照通过。
- trace-scope recovery `eb4962f` 在 formal client CLI 的第一个 cohort 请求前 POST
  `/set_internal_state`，固定 payload
  `{"server_args":{"dspark_clear_info_records":1}}`，要求 DP=1 返回 `[true]`；
  随后 GET `/server_info` 验全部 HEDGE counters、request state 与 trace 归零。
  post snapshot 和 formal reducer CLI 再分别以 32 个唯一 raw response ID
  fail-closed 限定 trace；某请求没有正 barrier 被允许，任何 extra RID 被拒绝。
- executor 与主 Agent分别完成全部相关 fresh-process 回归；最终主复验为
  P05 21/21、P04 29/29、protocol+core 46/46、integration 22/22，合计
  118/118 PASS，另有 shell、in-memory compile 与 diff checks PASS。两个修复
  均不改变 SGLang wheel、checkpoint 或 decode 配置。
- 下一步只允许基于 HEAD `eb4962f49a16ec88721c9fc96be5daffcc1367d1`
  动态创建新的 native-trace attempt；主 Agent独立验收 scoped trace 与 clean
  sampler terminal status 后，才可启动 P05 B0。

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
- native r4 已提供 TP rank 0–7 初始化/target+draft 加载、八卡约 79.6–80.1 GiB
  模型显存和请求期间逐 UUID 活动证据；日志没有 CUDA/NCCL/worker crash。
- native r2 在 engine identity preflight 退出；keepalive 未暂停、没有新增 CUDA
  context，结束后 8×10×1 秒门禁仍 PASS。
- 两次 recovery read-only probe 同样未暂停 keepalive；worker `4106666` 保持在线，
  PID/PGID/SID `4730/4730/4730` 且八卡门禁 PASS。
- native r4 cleanup 后 dedicated keepalive 更新为 PID/PGID/SID
  `21792/21792/21792`；attempt 内与主 Agent随后远端独立核查均为 8×10 全卡
  mean/min/max 100%。
- B0 r1 结束后 contexts none，dedicated keepalive 更新为
  `32894/32894/32894`，8×10 全卡 mean/min/max 100%；worker 保持在线。

## 限制与复现状态

- P00–P03 已完成主 Agent PASS 验收并 commit/push；P04 native r4 已由原始证据
  与修复后只读 validator replay 记为 `RECOVERED_PASS`，原 FAIL artifact 未修改。
- B0 单请求 smoke 已 PASS；P05 native r1 已运行但因 trace scope 失败，不计作
  calibration PASS；32 条 P05 B0、native 500 与 HEDGE B>0 500 尚未运行。
- 当前没有 TPS、acceptance、GSM8K 正式结果或可比较 delta。
- native r4 已完成定向 shutdown、contexts none 和 keepalive 恢复；其 rc=1 是
  validator 工具误报，不是 CUDA/NCCL/worker crash。
- P05 native r1 的 32 条 output/live GPU evidence 可复核，但 q25 不可采用；
  sampler/trace recovery 已提交，必须由新的 scoped native attempt 重新采集。
