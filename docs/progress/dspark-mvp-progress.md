# DeepSeek V4 Flash DSpark MVP 进展

> 最后更新：2026-07-29 01:54 CST
>
> 总体状态：Phase 04 PASS，等待用户确认进入 Phase 05
>
> 下一步：用户确认后执行首次 4×H20 正式 DSpark attempt
>
> 阻塞：无技术 blocker；按阶段治理要求等待用户确认
>
> 下一次记录：不晚于 2026-07-29 02:24 CST

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 4×H20 worker | 正常 | Worker `4105641`；keepalive PID `9277`；最近 10×1 秒采样四卡均为 100% |
| Phase 01：环境 preflight | PASS | 4×H20、CUDA、拓扑、存储和源 checkpoint 基线已确认 |
| Phase 02：正式 checkpoint | PASS | ModelScope checkpoint 已发布到 DeepSpec-owned HDFS 路径 |
| Phase 03：uv/SGLang 环境 | PASS | uv 环境和 SGLang `v0.5.16` 固定 commit 已验证，PyTorch 可见 4 卡 |
| Phase 04：离线运行工具链 | PASS | attempt `20260728T174820Z-phase04-tooling` 门禁通过；提交 `230c1bd` 已推送 |
| HF 备用 checkpoint | PASS | fixed revision 已发布为独立 HDFS 实体副本；提交 `66ec629` 已推送 |

Phase 04 离线验证覆盖固定 GSM8K 前 10 条、API mock、顺序 GSM8K mock、
解析与重试测试和进程生命周期；10 条均到达成功终态。尚未启动真实模型。

## 已固定的 Phase 05 首轮配置

- 模型：DeepSpec-owned ModelScope checkpoint；
- 并行：`TP=4`，bundled DSpark draft 复用同一 TP group；
- MoE backend：target 和 draft 均为 `flashinfer_mxfp4`；
- 保持 packed FP4，禁止 FP4→FP8 dequant；
- `dspark_block_size=5`，ragged verify 使用 `static`；
- `context_length=4096`、单并发、`mem_fraction_static=0.80`；
- 禁用 CUDA Graph、overlap schedule 和 radix cache。

## 下一步

1. 等待用户明确确认进入 Phase 05；
2. 紧邻正式启动暂停 keepalive，并确认全部 keepalive CUDA context 已退出；
3. 执行首次 4 卡模型加载、API smoke 和 GSM8K smoke；失败时保留完整 attempt 证据。

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
