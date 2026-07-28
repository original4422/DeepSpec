# HEDGE × DeepSeek-V4-Flash-DSpark

## 快速结果

- 状态：`IN_PROGRESS`
- 记录更新时间：`2026-07-28T21:25:22Z`（`21:24:41Z` checkpoint 后约 41 秒落盘）
- 自主窗口：`2026-07-28T20:54:41Z` → `2026-07-29T08:54:41Z`
- B0：`NOT_RUN`
- 结论/首要 blocker：P00 独立 uv 环境未完成；env-r2
  `20260728T211739Z-p00-env-r2` 正在从已有固定 uv cache copy，venv 约 6.7 GiB，
  已有实质进展，并规避 env-r1 的 SGLang Git fetch `SSL connection timeout`。
  最近 8 卡 keepalive gate 均为 100%，但这不构成模型或阶段成功。
- 正式 native run：`NOT_RUN`
- 正式 HEDGE run：`NOT_RUN`
- worker / TP / GPU 参与：`4106666` / 8 / 模型参与 `NOT_RUN`；keepalive 8/8 gate `PASS`
- model / checkpoint：固定目标
  `deepseek-ai/DeepSeek-V4-Flash-DSpark@62af8fffb2f7030cac4de2f0169f5b8d1101b646`；
  本 session 的 checkpoint identity artifact 尚未验收
- SGLang：固定 base
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；独立 source clone 有 evidence，
  environment/base identity 尚未完整产生
- g / B / m：`NOT_CALIBRATED` / `NOT_CALIBRATED` / 固定目标 `1`
- native TPS / HEDGE TPS / delta：`NOT_RUN` / `NOT_RUN` / —
- native accepted length / HEDGE accepted length / delta：`NOT_RUN` / `NOT_RUN` / —
- native GSM match / HEDGE GSM match：`NOT_RUN` / `NOT_RUN`
- artifact root：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap`
- core / integration / config / result commits：均未创建
- DeepSpec worktree / branch / HEAD：
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark` /
  `exp/hedge-v4-dspark` /
  `cac6c78d88df97d395406fe831f573df3016e7f7`
- 下一步：完成并验收 P00 env-r2；提交已通过主 Agent 独立复核的 P01 节点；在新
  HEDGE venv 重跑 P02 tests 后由主 Agent处理 pure-core commit/push/READY marker

## 当前阶段

| Phase | 状态 | 当前证据 | 尚缺 |
| --- | --- | --- | --- |
| P00 | `IN_PROGRESS` | 8×H20 inventory；最近 keepalive 8/8 gate 均为 100%，PID 1697；固定 SGLang source clone；env-r2 正在 cache copy，venv 约 6.7 GiB | venv、environment/base identity、CUDA probe、checkpoint/session 完整验收 |
| P01 | `MAIN_REVIEW_PASS_PENDING_COMMIT` | handoff；13 tests PASS；dataset verify 18/18；独立 indices/hash 复算全 true | 主 Agent commit/push |
| P02 | `MAIN_REVIEW_PARTIAL_PASS` | handoff；主 Agent pinned-torch 33/33 tests；7 source/9 target identity hashes 全匹配 | 新 HEDGE venv 复跑、commit/push、READY marker |
| P03–P08 | `NOT_STARTED` | — | 前置阶段门禁 |

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
  复算全 true；P01 review PASS，但尚未形成 commit。

## Attempt 时间线

| Attempt | 唯一变化 | 结果 | Evidence |
| --- | --- | --- | --- |
| `20260728T205441Z-p00-bootstrap` inventory | 建立 session 并只读盘点 lane | 8×H20 inventory PASS；当时 compute context 为空 | HDFS `worker_inventory.json` |
| keepalive attempts 01–03 | 修正 dedicated keepalive 的启动环境 | 最终 8×10×1s gate PASS；各卡均值 100%；PID 1697 | HDFS `keepalive_initial.json` |
| `20260728T205441Z-p00-bootstrap` env | 首次独立 venv/source setup | FAIL：launcher 找不到 `uv` | HDFS `environment-attempts/.../uv-sync.log` |
| `20260728T211013Z-p00-env-r1` | 显式 uv 路径后重试 | FAIL：固定 SGLang Git fetch 遇到 SSL timeout | HDFS `environment-attempts/.../uv-sync.log` |
| `20260728T211739Z-p00-env-r2` | 仅复用现有固定 uv cache | `RUNNING`；正在 copy，venv 约 6.7 GiB，已有实质进展 | P00 executor / main-Agent checkpoint |
| `20260728T205701Z-p02-core` | 复制并收窄纯 HEDGE core | ready for review；33 tests 在两个已有环境通过；非 P02 PASS | `docs/plan/handoffs/hedge-dspark-p02-20260728T205701Z.md` |

## HEDGE core 当前证据

- 固定 source commit：
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- canonical path：`deepspec/hedge_spec/`
- handoff 记录的现有测试：两个 CPU-mode torch 环境中各 33 tests PASS。
- 主 Agent 已独立确认 pinned-torch 33/33 tests，并核对 7 个 source 与 9 个 target
  identity hashes 全匹配。
- 尚未满足的正式门禁：新 `/home/tiger/venvs/hedge-v4-dspark` 中复跑；
  pure-core commit/push；匹配 commit/hash 的 HDFS READY marker。

## GPU、进程与 shutdown

- P00 inventory 在 `2026-07-28T20:56:10Z` 记录 worker `4106666` 的 8 张 H20，
  compute capability 9.0，每卡 97871 MiB；当时无 compute context。
- keepalive artifact 记录 supervisor PID/PGID/SID `1697`，8 张卡各 10 个样本且
  平均利用率均为 100%，状态 `PASS`。
- 尚未启动 SGLang model server，尚无 TP rank 0–7 初始化、模型显存或请求期间八卡
  参与证据。
- recorder 未做实时 worker/进程探测，因此这里只记录 artifact 状态，不把 PID 1697
  写成当前实时存活保证。

## 限制与复现状态

- P00、P01、P02 均尚未完成主 Agent 的阶段 PASS 验收。
- B0、q25 calibration、native 500 与 HEDGE B>0 500 均未运行。
- 当前没有 TPS、acceptance、GSM8K 正式结果或可比较 delta。
- 尚未发生模型 shutdown；env setup 失败属于依赖获取路径，不是 CUDA/NCCL/worker
  crash。
