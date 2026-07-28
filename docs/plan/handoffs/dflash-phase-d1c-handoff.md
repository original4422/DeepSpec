# DFlash Phase D1C handoff

结论：`D1C PASS`。固定 GSM8K 数据、32 条 calibration、其前 10 条 warmup、后续
500 条 formal、prompt/request 协议、顺序请求 harness、artifact schema 与 bounded
mock 测试均已完成。没有调用真实模型或改变 GPU 状态；worker `4099543` 的既有
keepalive 保持 PID `34059`，结束时 8 卡 10×1 秒均值仍为 100%。

主验收指出的单点协议偏差已修正：正式请求不启用 `logprobs`，output token IDs
严格只读 `choices[0].meta_info.output_token_ids`，无 fallback。

## 数据身份

- 数据：`openai/gsm8k` / `main` / `test` /
  `740312add88f781978c0658806c59bc2815b9866`。
- HF fingerprint：`59ec1b7f9357c7a2`；1319 条有序原始内容
  SHA-256：`32f83c6becb3ba208d16bff80901547266e937b3f77c56d3ebe6a9bc3a9b41c4`。
- selection authority：DSpark 已发布并 push 的
  `origin/exp/hedge-v4-dspark@77053dd3ea84bb1c8dde7971f5f12759c1375e1f`。
  共享 manifest SHA-256 为
  `34db2fc76099b2725f51dfd6ceeb1410802ad54c9008b2ab3cc1b8927f02be90`；
  DFlash 保存的副本与其 byte-identical。
- DFlash 独立 HF acquisition 复算后，revision、row count、内容 hash、HF
  fingerprint、seed、32/500 counts、全部 indices 和无重叠均与共享 manifest 一致，
  因而正式复用共享 indices/fingerprint。
- shuffle indices SHA-256：
  `04e54897dab635651e7cbc9e140a5f0473fe72b272b0e355301e08dc8a701f69`。
- 生成环境是独立 `/tmp/deepspec-hedge-dflash/dflash_d1c_venv`，未修改 D1B venv；
  Python 3.11.2、datasets 4.8.5、huggingface_hub 0.36.2、pyarrow 25.0.0、
  fsspec 2026.2.0。

权威 D1C artifact 根目录：
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1c/`。

主要文件：

- `dflash_d1c_dataset_identity.json`
- `dflash_d1c_dataset_manifest.json`
- `dflash_d1c_dspark_shared_dataset_manifest.json`
- `dflash_d1c_calibration_indices.json`
- `dflash_d1c_formal_indices.json`
- `dflash_d1c_gsm8k_calibration_32.jsonl`
- `dflash_d1c_gsm8k_warmup_10.jsonl`
- `dflash_d1c_gsm8k_formal_500.jsonl`
- `dflash_d1c_prompt_manifest.json`
- `dflash_d1c_artifact_schema.json`

## Harness contract 与测试

实现：`scripts/dflash_d1c_harness.py`；测试：
`tests/dflash_d1c_harness_test.py`。

请求严格为单条 user message：原始 question、换行、精确后缀
`Please reason step by step, and put your final answer within \boxed{}.`；无 system；
`enable_thinking=false`、temperature 0、top_p 1、max_tokens 512。未请求
`logprobs`，避免给正式 TPS 引入计划外开销。`return_meta_info=true` 提供 canonical
`choices[0].meta_info.output_token_ids`；为满足 DFlash 计划保存 tokenized input，
额外保留观察性的 `return_prompt_token_ids=true`，它不参与解码决策。

每条终态记录保存 request payload、prompt token IDs、完整 response、output token IDs、
usage、每次 attempt、总 latency、retry、终态和答案解析。解析优先级固定为最后一个
boxed、最后一个 `####`、显式 final answer、最后一个数值。正式 summary 的 wall time
从首个请求 dispatch 前到第 500 条达到终态，包含失败、retry 与 backoff；
E2E TPS 为 completion tokens 总数除以该 wall time。output token IDs 只允许读取
`choices[0].meta_info.output_token_ids` 并要求其长度等于
`usage.completion_tokens`；不存在 logprob 或重编码 fallback。

最终 bounded test：

```text
/tmp/deepspec-hedge-dflash/dflash_d1c_venv/bin/python \
  tests/dflash_d1c_harness_test.py
Ran 13 tests in 2.929s — OK
```

测试覆盖 32/500 split 与 warmup、精确 payload、四级解析、成功、HTTP 失败有界重试、
重试耗尽失败终态、parse failure，以及 500 个 mock 请求的最大并发 1、首尾计时边界和
1000 completion-token 汇总。最终 artifact audit 复核 9 个 manifest 登记文件 hash，
结果 `PASS`。

## 退出门禁

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 固定 repo/config/split/revision 与 provider resolution | PASS | `dflash_d1c_dataset_identity.json` |
| published DSpark manifest 精确验证并复用 | PASS | shared manifest 副本、DFlash dataset manifest |
| 32 calibration / 500 formal 无重叠 | PASS | indices JSON、dataset manifest、artifact audit |
| 原始 index/question/answer/标准答案完整 | PASS | 两份 cohort JSONL |
| 前 10 calibration warmup 固定 | PASS | `dflash_d1c_gsm8k_warmup_10.jsonl` |
| prompt 与 generation 参数精确 | PASS | prompt manifest、payload test |
| 顺序请求、完整证据、retry 与终态 | PASS | harness、mock tests、artifact schema |
| 500 wall-time 边界与 E2E token 计数 | PASS | 500-request mock test |
| 不依赖旧 prompt-only GSM8K 文件 | PASS | pinned HF acquisition identity |
| keepalive 保持且无 GPU/model 操作 | PASS | 结束 status：PID 34059，8 卡均值 100% |
| 未修改 canonical progress/experiment、未 stage/commit/push | PASS | phase executor scope |

D1C 无 blocker，可交由主 Agent 验收；本 executor 不进入 D2+。
