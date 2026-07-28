# DeepSeek V4 Flash DSpark MVP 进展

> 最后更新：2026-07-29 02:23 CST
>
> 总体状态：Phase 05 attempt 01 启动失败，blocker 已定位
>
> 下一步：修复 CUDA JIT linker 搜索路径后，以新 attempt 完整重试
>
> 阻塞：FlashInfer JIT link 找不到 `-lcudart` 和 `-lnvrtc`
>
> 下一次记录：不晚于 2026-07-29 02:52 CST

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 4×H20 worker | 保活正常 | Worker `4105641`；模型 CUDA context 已全部退出；keepalive PID `23339`，10×1 秒四卡均为 100% |
| Phase 01：环境 preflight | PASS | 4×H20、CUDA、拓扑、存储和源 checkpoint 基线已确认 |
| Phase 02：正式 checkpoint | PASS | ModelScope checkpoint 已发布到 DeepSpec-owned HDFS 路径 |
| Phase 03：uv/SGLang 环境 | PASS | uv 环境和 SGLang `v0.5.16` 固定 commit 已验证，PyTorch 可见 4 卡 |
| Phase 04：离线运行工具链 | PASS | attempt `20260728T174820Z-phase04-tooling` 门禁通过；提交 `230c1bd` 已推送 |
| Phase 05：端到端 smoke | 启动失败 | attempt `20260728T175852Z-phase05-dspark-01`；MXFP4 JIT link blocker 已定位 |
| HF 备用 checkpoint | PASS | fixed revision 已发布为独立 HDFS 实体副本；提交 `66ec629` 已推送 |

本次日志已确认 `speculative_algorithm='DSPARK'`、bundled draft、`TP=4`，
以及 target/draft 的 `flashinfer_mxfp4` 配置。四个 TP rank 和 NCCL 初始化成功，
target 48/48 shards 完成，四卡峰值显存约 41.4–41.6 GiB。随后 FlashInfer
`fused_moe_90` 首次 JIT 在最终链接时因 `/usr/bin/ld` 找不到 `-lcudart` 和
`-lnvrtc` 退出；不是 OOM，也没有进入 API 或 GSM8K。

## 已固定的 Phase 05 首轮配置

- 模型：DeepSpec-owned ModelScope checkpoint；
- 并行：`TP=4`，bundled DSpark draft 复用同一 TP group；
- MoE backend：target 和 draft 均为 `flashinfer_mxfp4`；
- 保持 packed FP4，禁止 FP4→FP8 dequant；
- `dspark_block_size=5`，ragged verify 使用 `static`；
- `context_length=4096`、单并发、`mem_fraction_static=0.80`；
- 禁用 CUDA Graph、overlap schedule 和 radix cache。

## 下一步

1. 核对 CUDA 13.0 runtime/JIT library 搜索路径，针对 linker blocker 做单变量最小修复；
2. 使用新 attempt 重跑完整 Phase 05，保留本次失败 artifacts 供前后对比；
3. 服务 ready 后继续 OpenAI-compatible API 和 GSM8K 前 10 条顺序 smoke。

## 历史记录

| 时间（CST） | 进展 |
| --- | --- |
| 2026-07-29 00:29 | Phase 01 PASS；提交 `3942e9a` |
| 2026-07-29 01:13 | Phase 02 PASS；正式 ModelScope checkpoint 发布；提交 `a2b7c13` |
| 2026-07-29 01:23 | Phase 03 PASS；uv/SGLang 固定环境完成；提交 `6601eb6` |
| 2026-07-29 01:30 | 用户确认进入 Phase 04；启动离线工具链实现和 SGLang CLI 参数审计 |
| 2026-07-29 01:39 | SGLang CLI 审计完成；HF checkpoint 完整下载并开始复制到 HDFS 备用路径 |
| 2026-07-29 01:42 | HF fixed revision HDFS 备用副本发布门禁 PASS；提交 `66ec629` |
| 2026-07-29 01:51 | Phase 04 离线工具链门禁 PASS；提交 `230c1bd`；具备进入 Phase 05 条件 |
| 2026-07-29 01:59 | Phase 05 preflight PASS；启动正式 attempt `20260728T175852Z-phase05-dspark-01` |
| 2026-07-29 02:20 | TP0–TP3、NCCL 和四卡 context 已就绪；target 48/48 shards 完成，MXFP4 首次 JIT 收尾中 |
| 2026-07-29 02:21 | JIT 最终链接缺少 CUDA runtime/NVRTC libraries，服务退出；CUDA context 已清退并恢复 keepalive |
