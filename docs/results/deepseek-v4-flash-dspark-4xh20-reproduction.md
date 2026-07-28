# DeepSeek-V4-Flash-DSpark 4×H20 MVP 复现

## 固定输入

```text
REPO_ROOT=/mlx_devbox/users/pengzegang/playground/github/DeepSpec
FORMAL_VENV=/home/tiger/venvs/deepspec-dspark
MODEL_PATH=/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae
SGLANG_COMMIT=fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
```

环境由 `pyproject.toml` 与 `uv.lock` 固定。需要重建时：

```bash
export UV_PROJECT_ENVIRONMENT=/home/tiger/venvs/deepspec-dspark
uv sync --frozen --python 3.11
uv pip check --python /home/tiger/venvs/deepspec-dspark/bin/python
```

## 执行

每次先重新查询准确的 4×H20 worker：

```bash
cd /mlx_devbox/users/pengzegang/playground/github/DeepSpec
mlx worker list
```

在选中的 worker 上补齐 FlashInfer JIT 所需的 CUDA 13 `lib64` link layout，并验证
秒级 link probe：

```bash
mlx worker login <worker-id> -- bash \
  /mlx_devbox/users/pengzegang/playground/github/DeepSpec/scripts/phase_r_fix_cuda_link_layout.sh
mlx worker login <worker-id> -- bash \
  /mlx_devbox/users/pengzegang/playground/github/DeepSpec/scripts/phase05_cuda_link_probe.sh current
```

为新运行生成唯一 UTC attempt ID，然后执行原子 lifecycle：

```bash
ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-phase05-dspark-repro"
mlx worker login <worker-id> -- bash \
  /mlx_devbox/users/pengzegang/playground/github/DeepSpec/scripts/phase05_dspark_attempt.sh \
  <worker-id> "${ATTEMPT_ID}"
```

该脚本会依次完成 keepalive pause、TP=4 DSpark 启动、API smoke、GSM8K 前 10 条、
服务定向停止、CUDA context 清理和 keepalive 恢复。不要与正式模型运行并发执行
keepalive。

运行完成后执行离线候选审计：

```bash
/home/tiger/venvs/deepspec-dspark/bin/python \
  scripts/phase06_accept.py \
  "/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}" \
  --output-json \
  "/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}/phase06_candidate_audit.json" \
  --output-report \
  "/mnt/hdfs/pengzegang/DeepSpec/runs/${ATTEMPT_ID}/phase06_candidate_report.md"
```

候选输出必须为 `MVP_PASS failed=0 missing=0`，随后按 Phase 06 计划核对
source/checkpoint identity、正常 shutdown 与最终 keepalive 状态，再发布正式
`final_audit.json`。
