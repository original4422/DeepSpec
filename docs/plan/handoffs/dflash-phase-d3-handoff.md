# DFlash Phase D3 handoff

Status: `PASS`

Accepted native smoke: `dflash-d3-native-20260729T033321Z-a05`

## 固定身份

- Worker：`4099543`，8×NVIDIA H20，TP=8。
- SGLang：base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，
  native final `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`。
- Target：`deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1`。
- Draft：`RedHatAI/DeepSeek-V4-Flash-speculator.dflash@e44fc94ceb1e7ed45550d15e782aeadd08050483`。
- Native 配置：DFLASH、block 8 / 7 draft candidates、aux
  `[3,13,23,32,42]`、`flashinfer_mxfp4`、HEDGE disabled。

## 验收结果

- TP0–TP7 均完成 target 与 `DFlashDraftModel` 加载；live log 记录
  `block_size=8` 和 fused KV `n_layers=5`。
- OpenAI-compatible chat API 返回 HTTP 200、非空内容 `4` 与 output token IDs
  `[22,1]`；一次 verify 提议 7 个 draft token。
- 八个 TP rank 映射到八个物理 GPU UUID；ready 后显存为
  `92949–93189 MiB`。API 返回后的即时采样逐卡利用率为
  `[62,67,38,30,42,53,7,62]%`。
- 请求仅 0.395 秒，短于一秒 sampler 周期，所以 CSV 没有
  `phase=request` 行；API 时间戳、同秒 lifecycle 行和即时八卡快照共同构成
  request-window 证据，未为补标签重跑请求。
- cleanup PASS、八卡 contexts clear、keepalive 恢复；主 Agent fresh readback
  PID `110847`，八卡 10×1 秒均值均为 100%。
- HDFS run：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d3-native-20260729T033321Z-a05`；
  manifest `cf92016603857ba58ee7f067c74ab0eb6e42d01777d93c40bc89cc86c9a0b558`，
  38/38 PASS。

## 恢复链

- a02 暴露 DeepSeek-V4 allowlist blocker；
- a03 证明 TP8 target/backend 后暴露 CUDA 13 JIT link layout；
- isolated FlashInfer prebuild 完成 183/183；
- a04 越过 JIT 后暴露 global checkpoint 与 local TP shard 的前置形状检查；
- source `1ac1f38` 用真实 TP loader RED/GREEN 修复；
- a05 是相对 a04 仅改变 source SHA 的未缩减复验，并通过全部 D3 门禁。

## D4 输入

DSpark pure core pointer 已 READY，commit
`4d96f44065c07030ede67484a262006ec149626a`。D4 可开始验证 pointer、cherry-pick
DeepSpec pure core，并以可复现 patch 把相同 core 注入本 lane SGLang；不得修改
pure-core 语义，且 source freeze 前必须保留 native/B0/B+ 配置切换。
