# DeepSeek V4 Flash DSpark MVP 进展

> 最后更新：2026-07-29 02:50 CST
>
> 总体状态：Phase R 恢复 attempt 正在加载，原 linker blocker 已修复
>
> 下一步：完成 packed MXFP4 JIT，等待 API ready 后顺序执行 smoke
>
> 阻塞：无新 blocker；正式 JIT 路径验证中
>
> 下一次记录：不晚于 2026-07-29 03:20 CST

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 4×H20 worker | 正式加载中 | Worker `4105641`；keepalive 已按 lifecycle 暂停；TP0–TP3 context 均存在 |
| Phase 01：环境 preflight | PASS | 4×H20、CUDA、拓扑、存储和源 checkpoint 基线已确认 |
| Phase 02：正式 checkpoint | PASS | ModelScope checkpoint 已发布到 DeepSpec-owned HDFS 路径 |
| Phase 03：uv/SGLang 环境 | PASS | uv 环境和 SGLang `v0.5.16` 固定 commit 已验证，PyTorch 可见 4 卡 |
| Phase 04：离线运行工具链 | PASS | attempt `20260728T174820Z-phase04-tooling` 门禁通过；提交 `230c1bd` 已推送 |
| Phase 05 attempt 01 | 启动失败 | JIT link blocker 已定位；失败证据与 reproducer 提交 `bc64012` |
| Phase R：CUDA link 恢复 | 进行中 | attempt `20260728T184242Z-phase05-dspark-r1`；target 和 draft 均完成 48/48 shards |
| Phase 06 验收工具 | 已准备 | 离线验收器及 fixture 已通过；提交 `c018d13`，尚未执行最终验收 |
| HF 备用 checkpoint | PASS | fixed revision 已发布为独立 HDFS 实体副本；提交 `66ec629` 已推送 |

Phase R 仅在 CUDA 13 `lib64` 下补充 `libcudart.so` 和 `libnvrtc.so` 相对 symlink；
RED→fix→GREEN probe 通过且修复幂等。恢复 attempt 保持原模型配置，当前四个 rank
均已加载 target 和 `DeepseekV4ForCausalLMDSpark` draft architecture，四卡显存约
43.9–44.1 GiB，正在准备 packed MXFP4/JIT；尚未出现 linker、OOM 或 NCCL error。

## 已固定的 Phase 05 首轮配置

- 模型：DeepSpec-owned ModelScope checkpoint；
- 并行：`TP=4`，bundled DSpark draft 复用同一 TP group；
- MoE backend：target 和 draft 均为 `flashinfer_mxfp4`；
- 保持 packed FP4，禁止 FP4→FP8 dequant；
- `dspark_block_size=5`，ragged verify 使用 `static`；
- `context_length=4096`、单并发、`mem_fraction_static=0.80`；
- 禁用 CUDA Graph、overlap schedule 和 radix cache。

## 下一步

1. 确认 packed MXFP4 JIT 正式完成并等待服务 ready；
2. 执行 OpenAI-compatible API smoke；
3. 顺序完成 GSM8K test split 前 10 条并生成汇总，随后执行最终验收。

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
| 2026-07-29 02:34 | Phase 05 失败证据与 linker reproducer 提交 `bc64012`；离线验收工具提交 `c018d13` |
| 2026-07-29 02:42 | Phase R linker layout 单变量修复通过 RED→GREEN 与幂等 probe |
| 2026-07-29 02:50 | 恢复 attempt target/draft 48/48 shards 完成；四个 rank 均加载 DSpark draft architecture |
