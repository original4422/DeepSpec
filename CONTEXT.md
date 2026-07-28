# DeepSeek-V4-Flash-DSpark MVP

本仓库当前围绕单机四卡上的 DSpark 服务与最小端到端验证开展工作。这里记录讨论中已经达成一致、且会影响后续判断的领域语言。

## Language

**需求对齐阶段（alignment phase）** — 用户与 Agent 正在逐项确认目标、成功标准和执行边界的阶段。此阶段不开始模型实验，也不把任何操作结果作为 MVP 成功证据；只有用户单独明确授权的 operational keepalive 可以运行。
_Avoid_: “准备阶段”，因为它容易把环境安装、checkpoint 操作和 GPU 实验也含混地纳入授权范围。

**Operational keepalive** — 唯一目的是避免临时 GPU worker 因低利用率被平台回收的运行负载。它不属于模型实验，不证明 DSpark、SGLang、checkpoint 或推理链路可用，也不能计入 MVP 完成条件。
_Avoid_: “保活实验”或“模型负载”，因为这些说法会混淆资源保留与正式实验。

**阶段门禁执行（stage-gated execution）** — 每个阶段由主 Agent 派出的独立 subagent 实施。阶段结束后，主 Agent 必须汇总结果、判断是否符合预期并判断能否进入下一阶段，然后等待用户确认；未获确认不得派发下一阶段。范围扩大和连续 3 次无进展后的新方向同样由用户决策。
_Avoid_: “自动连续推进”，因为阶段间转换始终需要用户确认。

**Phase executor** — 由主 Agent 为一个明确阶段派出的 subagent。它只实施被分配的阶段，负责过程日志、退出清理和 handoff；无权自行进入下一阶段或扩大范围。
_Avoid_: “并行总负责人”，因为跨阶段排序、调整和最终验收属于主 Agent。

**DeepSpec-owned checkpoint copy** — 从已验证的既有 checkpoint 创建、由 DeepSpec 存储命名空间独立持有的完整实体副本。源副本保持只读；symlink、hardlink 和 Hugging Face cache 引用不构成独立副本；目标只有在身份与完整性验证通过后才可发布为正式模型路径。
_Avoid_: “复用 checkpoint”，因为它无法区分独立复制与跨项目引用。

**Pinned checkpoint snapshot** — 来自 Hugging Face 或 ModelScope 官方 `deepseek-ai/DeepSeek-V4-Flash-DSpark` 仓库、且身份不可变地记录的 checkpoint snapshot。优先使用 provider revision；若 provider 未提供可验证 revision，则使用完整逐文件 cryptographic manifest 的 hash 作为 snapshot ID。不同 provider 的非模型 metadata 不要求逐字节相同。
_Avoid_: “latest checkpoint”，因为浮动名称不能支持复现。

**Post-smoke handoff** — 正式 smoke test 产物完整保存后，将 SGLang 服务定向停止、确认其 CUDA context 全部退出，并恢复 operational keepalive 的交接状态。MVP 完成不承诺 API 在交接后继续在线。
_Avoid_: “服务保持可用”，除非另行授权持续请求负载及其监控。

**Diagnostic attempt** — 已有正式 DSpark attempt 失败证据后，为定位故障所属层而进行的隔离运行。它可以临时使用 target-only 启动来区分基础 checkpoint/FP4 backend 与 DSpark drafter 问题，但不得用于 benchmark、A/B 或替代 DSpark 成功；连续 3 个 attempt 均无可验证进展后，Agent 必须提交证据、后续选项与建议，由用户决定是否扩大范围。
_Avoid_: “降级成功”，因为 diagnostic attempt 永远不满足 MVP 成功定义。
