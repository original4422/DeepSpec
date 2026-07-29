# DFlash continuation C0 handoff

## 结论

`C0 PASS；CONTINUATION_IN_PROGRESS`。新窗口冻结为
`T1=2026-07-29T07:31:39Z`、`T+9=2026-07-29T16:31:39Z`、
`T+12=2026-07-29T19:31:39Z`。原窗口的
`BEST_EFFORT_BLOCKED_IMPLEMENTATION / BEST_EFFORT_EARLY_STOP_INCOMPLETE`
结论作为 prior-window outcome 保留。

C0 没有启动模型、暂停 keepalive 或发送 signal。DeepSpec HEAD/origin 均为
`a1febb7a22920f891eb7365cf2d13415003ac91e` 且起点 clean；SGLang final
`9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`、tree
`53fc45b1b04963736254dc7ed582047313b8075a` 且 clean。target、draft、core 和
dataset identity 无漂移；HDFS 仍无 D5、D6 或 formal run。

worker `4099543` 仍是 8×H20。fresh audit 证明 port `31457` 空闲，无 owned model
或未知 CUDA context；owned keepalive PID/PGID/SID `123914`，fresh gate mtime
`2026-07-29T07:36:00.119919Z`，8×10×1 秒逐卡均值全部 100%。

## C1 resume contract

当前唯一 blocker 是 `scripts/dflash_d5_attempt.sh` 硬编码已过期的
`HARD_STOP_UTC=2026-07-29T05:55:48Z`。C1 只需把 deadline 变成显式 immutable
launcher 输入，并贯穿 contract、resolved metadata、readiness 与 API；建议使用
`2026-07-29T16:31:29Z`（T+9 前 10 秒）。frozen source、checkpoint、TP8、
block8/7、port 和 decode 参数不变。

新 native ID 预留为 `dflash-d5-native-20260729T073139Z-a01`，worker scratch 与
HDFS 均无碰撞。C1 从 fresh native calibration preflight 开始。旧
`dflash-d5-native-20260729T053735Z-a01` 只属于 prior-window preflight，不计新窗口
live attempt，也绝不复用为 calibration 结果。

每阶段最多 3 次 live attempt，从 owned keepalive pause 开始计数；C0 退出时为
`0/3`。第三次仍失败时停止，不启动第四次；恢复并 fresh 验证 keepalive，封存三次
证据，向用户汇报原因、选项与推荐方案，然后等待决策。该规则覆盖旧的自动换策略规则。

权威 JSON：
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/continuation-c0/continuation_c0.json`。
本 executor 未 add、commit 或 push，并在此停止。
