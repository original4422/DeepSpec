# Phase R Handoff

- Phase R status: `PASS`
- Phase 05 evidence gate: `SATISFIED`（待主 Agent 验收）
- Attempt ID: `20260728T184242Z-phase05-dspark-r1`
- Started at: `2026-07-28T18:43:26Z`
- API ready at: `2026-07-28T18:55:11Z`
- GSM8K finished at: `2026-07-28T18:56:18Z`
- CUDA context cleanup verified at: `2026-07-28T18:56:27Z`
- Final keepalive gate started at: `2026-07-28T18:57:48Z`
- Git branch / HEAD at handoff: `exp/v4-flash-dspark` /
  `d21fb10d13d093e925c5e61fb61a4e1d65c173ce`
- Worker: `4105641` /
  `g340-cd51-4b00-e6cb-5724-8a1b-59f0`
- Artifact root:
  `/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T184242Z-phase05-dspark-r1`

## 结论

Phase R 的单变量 CUDA 13 link-layout 恢复成功，同一个 Phase 05 TP=4 DSpark
lifecycle 已完成服务启动、API smoke、GSM8K 前 10 条顺序推理、定向停止、CUDA
context 清理和 keepalive 恢复。

本 executor 判断本次 attempt 已具备进入 Phase 06 离线验收的条件。最终
`MVP_PASS` 结论由主 Agent 在 Phase 06 审计后给出，本 handoff 不代替最终审计。

## 唯一恢复变量

正式 CUDA root：

```text
/home/tiger/venvs/deepspec-dspark/lib/python3.11/site-packages/nvidia/cu13
```

新增且仅新增以下两个相对 symlink；没有替换、删除或升级任何库、wheel、SGLang
source、checkpoint 或运行参数：

```text
lib64/libcudart.so -> ../lib/libcudart.so.13
lib64/libnvrtc.so  -> ../lib/libnvrtc.so.13
```

可复现脚本：

```text
scripts/phase_r_fix_cuda_link_layout.sh
scripts/phase_r_prepare_cuda_link_layout.sh
scripts/phase_r_finalize_attempt.sh
```

`phase_r_fix_cuda_link_layout.sh` 只接受上述固定 CUDA root，遇到冲突文件或 symlink
会拒绝修改；重复执行成功，已验证幂等。

保存的反馈环结果：

```text
cuda_link_probe_red.txt
  returncode=1
  cannot find -lcudart
  cannot find -lnvrtc

cuda_link_probe_green.txt
  returncode=0
```

## 未改变的正式配置

baseline 文件相对 Git 无修改，SHA-256 为：

```text
443a6d105cde25d28ab9d0e89aaebb20c51aa7ede18d59ea04d7f94c09b363c6
config/dspark/deepseek_v4_flash_dspark_4xh20_mvp.json
```

本次继续使用：

- ModelScope 正式 checkpoint；
- SGLang `v0.5.16` / commit
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；
- TP=4、`speculative_algorithm='DSPARK'`、block size 5；
- target 和 draft 均为 `flashinfer_mxfp4`；
- context length 4096、单请求、`mem-fraction-static=0.80`；
- CUDA Graph、overlap schedule 和 radix cache 均禁用。

## 服务与 DSpark 证据

- TP0–TP3 均完成 distributed 初始化，NCCL P2P/IPC rings 和 trees 建立成功；
- target checkpoint 48/48 shard 完成，四个 rank 均完成
  `DeepseekV4ForCausalLM` 加载；
- 四个 rank 均明确加载 draft architecture
  `DeepseekV4ForCausalLMDSpark`，draft checkpoint 48/48 shard 完成；
- target 和 draft 均选择
  `flashinfer_mxfp4` / `Mxfp4FlashinferCutlassMoEMethod`；
- packed expert 日志进入并完成
  `Preparing DSv4 MXFP4 experts for FlashInfer SM90 CUTLASS`；
- TP0 记录
  `Initialized DSpark draft runner`，`gamma=5`；
- TP0–TP3 的 FlashInfer autotune 均完成，未再出现
  `cannot find -lcudart`、`cannot find -lnvrtc` 或 `ninja` link failure；
- `startup.json` 为 `ready`，elapsed 705.13 秒，最终 `/health` 返回 200。

## API 与 GSM8K

`api_smoke.json`：

```text
status=PASS
GET /v1/models -> 200
POST /v1/chat/completions -> 200
response content -> "4"
```

`summary.json`：

```json
{
  "all_terminal": true,
  "failed_requests": 0,
  "matches": 10,
  "mismatches": 0,
  "parse_failures": 0,
  "success_requests": 10,
  "total": 10
}
```

`gsm8k_outputs.jsonl` 含固定前 10 条的题目、标准答案、完整 API response、模型文本、
提取答案、提取规则、解析状态、匹配状态和逐次请求状态。10 条均在第一次请求成功。
匹配数量仅作观察，不改变基础设施 gate。

## 四卡参与

`gpu_samples.csv` 每卡 703 个样本。全程峰值显存：

| GPU | Peak memory |
| --- | ---: |
| 0 | 79691 MiB |
| 1 | 80015 MiB |
| 2 | 80015 MiB |
| 3 | 79535 MiB |

API/GSM8K 请求窗口内每卡各有 59 个样本：

| GPU | Mean utilization | Max utilization | Memory range |
| --- | ---: | ---: | ---: |
| 0 | 43.17% | 99% | 79643–79691 MiB |
| 1 | 63.07% | 97% | 79969–80015 MiB |
| 2 | 56.46% | 100% | 79969–80015 MiB |
| 3 | 41.81% | 97% | 79489–79535 MiB |

四个 rank 无提前退出或静默降级。

## Shutdown 与 keepalive

最后一条 GSM8K 请求在 `2026-07-28T18:56:18Z` 返回 200 后，lifecycle 才向已登记
server process group 发送 `SIGTERM`。日志中的：

```text
SIGTERM received. ... Draining requests and shutting down...
```

属于预期 post-smoke shutdown。shell 随后打印 server PID `Killed`，是 lifecycle
有界停止 process group 的结果；它发生在 API/GSM8K 全部成功之后，不是 OOM、
worker crash 或外部未知强杀。

`cuda_contexts_after_server.txt` 记录：

```text
2026-07-28T18:56:27Z attempt=1 contexts=none
```

Operational keepalive 已恢复为 PID `29335`。Phase R finalizer 另行追加完整的
10×1 秒 gate；GPU0–3 的 mean/min/max 均为 100%，每卡约 811 MiB。

## Artifact

HDFS 已封存：

```text
resolved_config.json
resolved_command.txt
server.log
gpu_samples.csv
startup.json
api_smoke.json
gsm8k_outputs.jsonl
summary.json
lifecycle.log
cuda_contexts_after_pause.txt
cuda_contexts_after_server.txt
keepalive_before.txt
keepalive_after.txt
cuda_link_probe_red.txt
cuda_link_layout_fix.txt
cuda_link_probe_green.txt
server.pid
sampler.pid
watchdog.pid
watchdog.log
```

关键 SHA-256：

```text
6e1d5d109ab001d0eaa27344b452316613e177c2496c30fae019c33d43a31113  resolved_config.json
86e9077f74c1e5b5d4295ae0eca9cd8064f09f3faa261bad7479d51e87aa7eeb  server.log
bb55e6747960ce7985493643366e5a9127bf5250fa101358ebb7b5bd3fd6f06d  gpu_samples.csv
b2f341f0dc5b4cb18238b45626757eff19b94011f54bb99c7b56f920d30ffbd3  api_smoke.json
7a31e5027b15ec95efce25cf4a5b45ecb667b6ae451885528ad66e2f50c559c3  gsm8k_outputs.jsonl
d735d198dcd8daeeca523d4398d84aa9161e61fa5b01a0aac4572a709e958feb  summary.json
71519683a558ccb52cf3ccdaa41a3fa32572be94f90ca07fdc2d1e9da7348bde  startup.json
df26d0c163f3a1cac714822ca221de62d27682d7e8d61340ffe6cb45079fe92c  keepalive_after.txt
b4eeeed51742d3c010c6573b2e90e1950cb7998ce8435d9602fb3b732d157450  cuda_link_probe_red.txt
1e8091ec96f703569d3f2eb4fc865196eec909bd5112ecc341a367706332e304  cuda_link_probe_green.txt
```

## 下一阶段

可以进入 Phase 06，但本 executor 不自行执行。主 Agent 应先验收本 handoff，再等待
用户明确确认后调度 Phase 06 离线验收。
