# DFlash Phase D7 最终审计 handoff

## 结论

`D7 AUDIT PASS；EXPERIMENT INCOMPLETE`。证据身份、D4-C sealed run、D5 零 GPU
副作用、最终 operational cleanup 和 CPU 回归均可审计；实验完成标签应使用计划允许的
`BEST_EFFORT_BLOCKED_IMPLEMENTATION`，并以
`BEST_EFFORT_EARLY_STOP_INCOMPLETE` 描述具体 outcome。

这不是 HEDGE 正式结果：32 条 native calibration、正 ratio、q25、参数冻结和 protocol
`B0` 均未运行；native/B+ 两个 500 条正式 arm 均未运行。因此 `B0=NOT_RUN`、
`formal result=NONE`，没有 canonical 或 exploratory 指标。

## D5 证据纠正

D7 对 worker scratch 的逐文件 mtime/hash 复核发现，D5 blocker artifact 中的
`BLOCKED_BEFORE_PASS` 和“两份 CUDA-view 文件”不是最终 worker 实况：

- `preflight.json` 在 `2026-07-29T05:40:13.212797Z` 已记录 `PASS`；
- 最终 scratch 有 14 个 preflight-only 小文件，mtime 范围为
  `05:37:40.512723Z`–`05:40:13.581845Z`；
- 原 mlx PTY wrapper 仍未向 orchestrator 返回可恢复的 rc/stdout；
- `requests.jsonl` 为 0 bytes / 0 rows，`hedge_counters.status=NOT_RUN`；
- 没有 `keepalive_pause.txt`、server/sampler/startup/smoke artifact，没有 D5 HDFS
  run，端口 `31457` 空闲。

因此准确状态是 `PREFLIGHT_PASS_NOT_SURFACED_TO_ORCHESTRATOR`。原
`dflash_d5_preflight_blocker.json` 标为 `SUPERSEDED_IN_PART_BY_D7_AUDIT`；其
zero-GPU、NOT_RUN 和 early-stop 结论仍有效。不得把 preflight metadata 解释为
calibration。

## 最终身份与 artifact

- DeepSpec branch 起点：`exp/hedge-v4-dflash`，
  HEAD/origin 均为 `af6e4a6cd10eabaf9580a58e7f3a722d6f659ecd`，ahead/behind
  `0/0`；D7 写文件前 worktree clean。
- SGLang：base
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，final
  `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，tree
  `53fc45b1b04963736254dc7ed582047313b8075a`，parent
  `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`，clean。
- D4 integration patch：SHA-256
  `1788696ec488d1844a061f4a1a37cb32af2754c0b6146094f1255f08fb226024`，
  34,457 bytes / 873 lines；prior reconstruction 与 final tree 一致。
- HEDGE core：upstream `4d96f44065c07030ede67484a262006ec149626a`，
  DFlash canonical `86231e536573ccc43cda732b4eca920d5ce0a28a`；五文件逐文件
  hash 与 injection `--check` PASS。inject CLI 与 capture 的两个 aggregate hash
  使用不同序列化算法，不构成 identity 冲突。
- target：
  `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`，
  73 files / 159,630,041,626 bytes / 46 shards，marker 与 manifest hash PASS。
- draft：
  `RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483`，
  6 files / 3,607,606,957 bytes，pointer 与 `.complete` hash PASS；未用 fallback。
- dataset：
  `openai/gsm8k@740312add88f781978c0658806c59bc2815b9866`，
  seed `980406`，32/500 无重叠，fingerprint `59ec1b7f9357c7a2`，
  content SHA-256 `32f83c6b…b41c4`。
- D4-C：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d4-b0-20260729T045317Z-a01`，
  实际 marker 名为 `.complete.json`，marker 外另有 39 条 manifest records，
  39/39 PASS，manifest SHA-256 `eae4f4b…43d6`。
- HDFS runs 仅有 D3 a02–a05 与 D4-C a01；没有 D5/D6/formal run。

权威 D7 artifact：

- `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/final_audit.json`
- `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/artifact_manifest.sha256`
- `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d7/reproduction_commands.txt`
- `scripts/dflash_d7_remote_audit.sh`

manifest 三条记录全部 PASS；manifest 自身 SHA-256 为
`4e5348e622244b3f9b14b47ee48bc5e0b725586f6ecc50bf92bc72fce1f1c50e`。

## 最终 worker 状态

worker `4099543` 仍是准确的 8×NVIDIA H20。D7 fresh gate 中 owned keepalive
PID/PGID/SID 均为 `123914`，argv、hostname、CVD 和八张 UUID 全匹配；8×10×1 秒
均值全部 100%，无 pause marker。`31457` 空闲，无 owned model process；八卡只见
每 UUID 一个约 804 MiB 的 keepalive context。D7 没有发送 signal 或启动模型。

## CPU 门禁

- canonical core：33/33 PASS；
- DFlash HEDGE integration：9/9 PASS；
- D4-C tooling：3/3 PASS；
- D4 source capture tooling：1/1 PASS；
- D5 tooling：4/4 PASS；
- DFlash primary：10/10 PASS；
- overlap：6 PASS / 1 CUDA-only skip；
- core injection、bash/Python syntax、JSON parse、repo/SGLang diff check：PASS。

合计 67 个 test case：66 PASS、1 CUDA-only skip、0 FAIL。

## 交还主 Agent

本 executor 未 stage、commit 或 push。主 Agent需：

1. 复核 D7 JSON、manifest、canonical experiment 和本 handoff；
2. 保留 progress 文件由主 Agent独立维护，避免混入 D7 executor diff；
3. 只显式暂存 DFlash D7 小文件，按 `$git-commit-message` 流程生成最终提交；
4. commit/push `exp/hedge-v4-dflash`，并再次确认 keepalive healthy；
5. 不进入 D6，不把 D4-C short smoke 写成 protocol B0 或正式结果。
