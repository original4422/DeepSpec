# DeepSeek-V4-Flash-DSpark 4×H20 MVP 结果

- 最终结论：`MVP_PASS`
- 正式 run：`20260728T184242Z-phase05-dspark-r1`
- Worker：`4105641` / `g340-cd51-4b00-e6cb-5724-8a1b-59f0`
- 完整证据：
  `/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T184242Z-phase05-dspark-r1`

## 跑通结果

单机 4×NVIDIA H20-96G 已使用 SGLang 成功运行
`deepseek-ai/DeepSeek-V4-Flash-DSpark`：

- uv 正式环境：`/home/tiger/venvs/deepspec-dspark`；
- SGLang `v0.5.16`，source commit
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；
- ModelScope 官方 snapshot identity
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`；
- TP=4，`speculative_algorithm='DSPARK'`，DSpark block size 5；
- target 与 draft 均使用 `flashinfer_mxfp4`，保留 packed FP4 experts；
- TP0–TP3 均加载 target 和 `DeepseekV4ForCausalLMDSpark` draft；
- target 和 draft 各完成 48/48 checkpoint shard 加载；
- 服务启动完成，OpenAI-compatible models/chat API 均返回 HTTP 200，chat 内容非空；
- 请求窗口内四张卡均有活动，峰值显存约 79.5–80.0 GiB；
- GSM8K `main/test` 固定前 10 条全部顺序完成并保存。

## GSM8K 观察结果

| 项目 | 数量 |
| --- | ---: |
| 总样本 | 10 |
| 请求成功 / 失败 | 10 / 0 |
| 匹配 / 不匹配 | 10 / 0 |
| 解析失败 | 0 |

匹配率只作输出合理性观察，不是本次 MVP gate。

## 退出状态

最后一条 GSM8K 请求返回 HTTP 200 后，lifecycle 才向登记的 server process group
发送 `SIGTERM`。随后出现的 detokenizer `-15`、`SIGQUIT` 和 shell `Killed` 是该
定向停止流程的传播结果，不是运行期间的未知 worker crash。停止后
`cuda_contexts_after_server.txt` 记录 `contexts=none`。

Phase 06 最终复查时，worker 仍是准确的 4×H20；SGLang 已停止，无 SGLang
进程。Operational keepalive PID/PGID 为 `29335`，最终 10×1 秒采样中四卡
mean/min/max 均为 100%。

## 最终产物

正式 run 中包含：

```text
final_audit.json
final_report.md
reproduction.md
keepalive_final.json
phase06_candidate_audit.json
phase06_candidate_report.md
phase06_live_state.txt
```

自动候选审计 16/16 项 `PASS`，`failed_checks=[]`、
`missing_evidence=[]`；Phase 06 人工交叉核对后发布的
`final_audit.json` 才是最终结论。

复现步骤见
[`deepseek-v4-flash-dspark-4xh20-reproduction.md`](deepseek-v4-flash-dspark-4xh20-reproduction.md)。
