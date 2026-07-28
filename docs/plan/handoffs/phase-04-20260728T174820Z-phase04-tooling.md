# Phase 04 Handoff

- Status: PASS
- Attempt ID: `20260728T174820Z-phase04-tooling`
- Started at: `2026-07-28T17:48:20Z`
- Finished at: `2026-07-28T17:51:15Z`
- Git branch / HEAD: `exp/v4-flash-dspark` /
  `66ec629ca68b7edaf2af224478197e6ff338ad87`
- Worker: `4105641` /
  `g340-cd51-4b00-e6cb-5724-8a1b-59f0`
- Authorized phase: Phase 04
- Artifact root:
  `/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T174820Z-phase04-tooling`

## Outcome

Phase 04 已完成运行工具链与离线 smoke 准备，具备进入 Phase 05 的直接前置条件：

- 首轮 DSpark command/env 已固定并通过 resolver；
- Phase 05 原子 lifecycle 已覆盖 keepalive pause/resume、SGLang process group、
  bounded startup wait、GPU sampler、orphan watchdog、API/GSM8K smoke 和定向清理；
- `openai/gsm8k` 的 `main/test` 前 10 条已按固定 revision 保存，包含标准答案；
- mock OpenAI API 下 models、chat completion、顺序 10 条、失败重试、答案提取和汇总
  均通过；
- 没有暂停 keepalive、访问 checkpoint 权重或启动真实模型。

本阶段没有进入 Phase 05，也没有创建 Git commit。

## Resolved Phase 05 baseline

配置文件：

```text
config/dspark/deepseek_v4_flash_dspark_4xh20_mvp.json
```

核心启动参数：

```text
--tp-size 4
--speculative-algorithm DSPARK
--speculative-dspark-block-size 5
--moe-runner-backend flashinfer_mxfp4
--speculative-moe-runner-backend flashinfer_mxfp4
--context-length 4096
--max-running-requests 1
--mem-fraction-static 0.80
--disable-cuda-graph
--disable-overlap-schedule
--disable-radix-cache
```

关键环境：

```text
CUDA_VISIBLE_DEVICES=0,1,2,3
SGLANG_RAGGED_VERIFY_MODE=static
SGLANG_DSV4_FP4_EXPERTS=1
SGLANG_DSV4_FP4_DEQUANT unset
TOKENIZERS_PARALLELISM=false
```

checkpoint 自带 DSpark draft，因此没有传
`--speculative-draft-model-path`；SGLang 会将 draft path 自动解析为 target path。
`--disable-cuda-graph` 是固定 commit 中同时禁用 target 与 DSpark draft graph 的关键
开关。`SGLANG_DISABLE_DRAFT_EXTEND_CUDA_GRAPH=1` 仅作为防御性设置，不能当作
DSpark graph 已禁用的证据。

完整 resolved command：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T174820Z-phase04-tooling/resolved_command.txt
```

## Repository changes

本 executor 只新增以下 Phase 04/05 文件：

```text
config/dspark/deepseek_v4_flash_dspark_4xh20_mvp.json
eval_datasets/gsm8k_main_test_first10.jsonl
eval_datasets/gsm8k_main_test_first10.manifest.json
scripts/phase04_finalize.py
scripts/phase04_mock_openai_server.py
scripts/phase04_prepare_gsm8k.py
scripts/phase04_tooling_test.py
scripts/phase05_api_smoke.py
scripts/phase05_dspark_attempt.sh
scripts/phase05_gpu_sampler.py
scripts/phase05_gsm8k_smoke.py
scripts/phase05_resolve.py
scripts/phase05_wait_ready.py
scripts/phase05_watchdog.py
```

未 stage、未 commit，也未触碰 Phase 01、Phase 03 或 Hugging Face 并行任务文件。

## Evidence

最终 gate：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T174820Z-phase04-tooling/phase04_gate.json
SHA256 e0fd2af64645bca72cba478005e58728a6f2250c7ef32651d73d6bb5c1e297cf
```

Gate 为 `PASS`，主要结果：

- dataset revision：
  `740312add88f781978c0658806c59bc2815b9866`；
- datasets fingerprint：`0e6f671aa503666b`；
- 10 条 JSONL SHA-256：
  `fa377ee367e0c1fcd5be8e639933981d749d0b6a685740e596935652e7a5dda9`；
- mock API smoke：`PASS`；
- GSM8K：10 成功、0 失败、10 个终态；
- mock 结果：10 匹配、0 不匹配、0 解析失败；
- fixture 对每条样本首次返回 HTTP 503，10 条均在第二次请求成功，验证了“最多
  3 次总尝试”和逐次错误保存；
- `boxed`、`####`、`final answer`、最后数值的提取优先级及数值规范化均通过。

必需 artifact：

```text
resolved_config.json
resolved_command.txt
dataset_manifest.json
gsm8k_first10.jsonl
tooling_test.log
process_lifecycle_test.log
```

附加 mock 证据：

```text
mock_startup.json
mock_api_smoke.json
mock_gsm8k_outputs.jsonl
mock_summary.json
```

所有 shell 脚本通过 `bash -n`，所有新增 Python 脚本通过正式 venv 的
`py_compile`。Phase 05 lifecycle 在 keepalive pause 后、正式 server 启动前，以及
server process group 停止后、keepalive resume 前，各执行一次最长 30 秒的
CUDA-context 清空检查并保存 PID 列表。

## Attempts

1. `20260728T174603Z-phase04-tooling`：mock fixture 正常启动，但环境代理截获
   `127.0.0.1` 请求并返回 HTTP 403。fixture 按登记的 PID=PGID=SID 定向停止，无残留。
   证据位于
   `/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T174603Z-phase04-tooling`。
2. `20260728T174820Z-phase04-tooling`：唯一修改是本地 API clients 使用空
   `ProxyHandler` 绕过代理；models、chat、GSM8K、重试、解析和汇总全部 PASS。

## Process and GPU state at exit

- SGLang server：未启动；
- checkpoint / 模型权重：未访问；
- mock fixture：已按 PID=PGID=SID 定向停止，无残留；
- worker list：`4105641` 仍是当前唯一 4×NVIDIA-H20 worker；
- GPU UUID：
  - `GPU-dccbc830-5459-6b2b-84d5-a1eb5eb05252`
  - `GPU-9995c88c-bcf4-0482-60a5-fc04880a0df8`
  - `GPU-8e412234-a4de-5e4c-1414-6d3acd681896`
  - `GPU-26c888a5-df24-039f-c0c5-621163ce32cf`
- operational keepalive：PID `9277`；
- 最终 10×1 秒采样中 GPU 0–3 的 mean/min/max 均为 `100%`，
  `underutilized_gpus=[]`，每卡约 `811 MiB`。

最终 keepalive 证据：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T174820Z-phase04-tooling/keepalive_after.txt
```

## Failure or open questions

没有 Phase 04 blocker。`flashinfer_mxfp4` kernel、packed-FP4 checkpoint 实际加载、
DSpark draft architecture 和四卡 TP 只能由 Phase 05 正式 attempt 验证；这不是
Phase 04 FAIL。

## Next eligible phase

Phase 04 PASS，Phase 01–03 也已 PASS，因此具备进入 Phase 05 的条件。仍须由主
Agent 验收，并由用户明确确认后才能调度 Phase 05。
