# DeepSeek-V4 Speculative Decoding Experiments

本上下文定义 DeepSeek-V4 speculative decoding 与 HEDGE 实验中使用的领域语言。
具体 worker、revision、参数和阶段步骤由 `AGENTS.md` 与 `docs/plan/` 规定。

## Language

**Operational keepalive**:
为避免临时 GPU worker 因低利用率被回收而运行的持续负载；它不属于模型实验，也不构成任何模型或推理链路证据。
_Avoid_: 保活实验, 模型负载

**历史 DSpark MVP**:
已经完成的四卡 DSpark 服务与十条 GSM8K smoke test，其规则只用于复现该结果。
_Avoid_: 当前实验, HEDGE 基线

**Phase executor**:
由主 Agent 分配一个有界执行阶段的 subagent；跨阶段排序、纠偏、验收与提交仍属于主 Agent。
_Avoid_: 并行总负责人

**HEDGE-on-V4**:
把 HEDGE 的风险预算接受规则及必要测试接入可运行的 DeepSeek-V4 speculative decoding 路线，而不是迁移 HEDGE 仓库的完整项目流程。
_Avoid_: 迁移 HEDGE 项目

**核心路线**:
必须完成 HEDGE 集成并取得结果的 DSpark 路线；扩展路线不能替代或稀释它。
_Avoid_: 三路线同等优先

**Best-effort 扩展路线**:
尝试把 HEDGE 接入 Eagle3 或 DFlash 的附加路线；有证据的阻碍本身可以成为最终记录。
_Avoid_: 必须成功路线

**统一 SGLang V4 栈**:
三条路线共享固定的 SGLang-derived DeepSeek-V4 target 基线，其他引擎只提供实现参考。
_Avoid_: 多引擎对比

**Native speculative baseline**:
某条路线原生 verifier 的正式对照 arm；它使用与 HEDGE arm 相同的引擎源码、请求和 proposal 设置。
_Avoid_: target-only baseline

**轻量 `B=0` 等价性核查**:
用零风险预算检查 HEDGE 接入是否复现 native 输出的低成本诊断；失败不阻断产物生成，但会降低后续结论等级。
_Avoid_: B=0 硬门禁

**HEDGE `B>0` arm**:
使用校准阶段唯一确定的正风险预算运行的正式 HEDGE arm。
_Avoid_: 手工调优 arm, 多点择优

**方法原生 proposal 宽度**:
由各 draft 方法自身定义、并在同一路线所有 arm 间保持不变的 proposal 规模。
_Avoid_: 统一 block size

**HEDGE 实验效果**:
结合接受行为、端到端输出吞吐和答案匹配描述 HEDGE 相对 native baseline 的路线内变化。
_Avoid_: HEDGE 加速结果

**Calibration cohort**:
只用于等价性核查和确定唯一 HEDGE 正预算的固定样本集合，不参与正式结果选择。
_Avoid_: tuning set

**Formal cohort**:
在参数冻结后用于 native baseline 与 HEDGE 正式对照的固定、互不重叠样本集合。
_Avoid_: calibration set

**自主执行窗口**:
用户预先授权主 Agent 在既定 lane 和范围内连续推进、换策略并提交结果的固定 timebox。
_Avoid_: 无边界自主执行

**并行 lane 所有权**:
三个会话对各自 worktree、环境、整台 8 卡 worker、进程和运行目录拥有排他管理责任。
_Avoid_: 共享工作区

**Pinned checkpoint snapshot**:
用不可变 provider revision 或等价 manifest 身份固定的模型快照。
_Avoid_: latest checkpoint

**共用 target snapshot**:
由一个会话发布、供另一个会话只读复用的同一 target 实体，draft checkpoint 不包含在其中。
_Avoid_: 重复 target 副本

**Diagnostic attempt**:
为缩小已知 blocker 范围而运行、保留完整证据且不能冒充正式成功的隔离尝试。
_Avoid_: 降级成功

**权威实验记录**:
每条路线在 `docs/experiment/` 中维护的唯一完整实验叙事，顶部提供快速结果，正文保留复现与失败证据。
_Avoid_: 进展日志, 最终结果摘要
