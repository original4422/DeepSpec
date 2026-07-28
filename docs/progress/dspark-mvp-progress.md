# DeepSeek V4 Flash DSpark MVP 进展

> 最后更新：2026-07-29 01:40 CST
>
> 总体状态：进行中，Phase 04
>
> 下一次记录：不晚于 2026-07-29 02:10 CST

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 4×H20 worker | 正常 | Worker `4105641`；keepalive PID `9277`；最近 10×1 秒采样四卡均为 100% |
| Phase 01：环境 preflight | PASS | 4×H20、CUDA、拓扑、存储和源 checkpoint 基线已确认 |
| Phase 02：正式 checkpoint | PASS | ModelScope checkpoint 已发布到 DeepSpec-owned HDFS 路径 |
| Phase 03：uv/SGLang 环境 | PASS | uv 环境和 SGLang `v0.5.16` 固定 commit 已验证，PyTorch 可见 4 卡 |
| Phase 04：离线运行工具链 | 进行中 | CLI 参数审计已完成；正在实现 launcher、生命周期管理、API/GSM8K runner 和 mock 测试 |
| HF 备用 checkpoint | 复制中 | fixed revision 已完整下载到 worker NVMe，正在并行复制到 HDFS 备用路径 |

当前没有阻塞主线的问题。

## 已固定的 Phase 05 首轮配置

- 模型：DeepSpec-owned ModelScope checkpoint；
- 并行：`TP=4`，bundled DSpark draft 复用同一 TP group；
- MoE backend：target 和 draft 均为 `flashinfer_mxfp4`；
- 保持 packed FP4，禁止 FP4→FP8 dequant；
- `dspark_block_size=5`，ragged verify 使用 `static`；
- `context_length=4096`、单并发、`mem_fraction_static=0.80`；
- 禁用 CUDA Graph、overlap schedule 和 radix cache。

## 下一步

1. 完成 Phase 04 脚本、GSM8K 前 10 条数据和离线 mock 验证；
2. 主 Agent 验收并提交 Phase 04；
3. 用户确认后进入 Phase 05，执行首次 4 卡模型加载、API smoke 和 GSM8K smoke。

## 历史记录

| 时间（CST） | 进展 |
| --- | --- |
| 2026-07-29 00:29 | Phase 01 PASS；提交 `3942e9a` |
| 2026-07-29 01:13 | Phase 02 PASS；正式 ModelScope checkpoint 发布；提交 `a2b7c13` |
| 2026-07-29 01:23 | Phase 03 PASS；uv/SGLang 固定环境完成；提交 `6601eb6` |
| 2026-07-29 01:30 | 用户确认进入 Phase 04；启动离线工具链实现和 SGLang CLI 参数审计 |
| 2026-07-29 01:39 | SGLang CLI 审计完成；HF checkpoint 完整下载并开始复制到 HDFS 备用路径 |
