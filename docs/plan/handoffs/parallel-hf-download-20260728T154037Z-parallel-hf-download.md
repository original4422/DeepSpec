# Parallel Hugging Face Checkpoint Handoff

- Status: PASS
- Acquisition attempt: `20260728T154037Z-parallel-hf-download`
- HDFS backup attempt: `20260728T173307Z-hf-hdfs-backup`
- Finished at: `2026-07-28T17:42:12Z`
- Git HEAD: `4a0166b206524878025a78defae19cf2c44c07f7`
- Worker: `4105641`
- Provider: Hugging Face
- Repository: `deepseek-ai/DeepSeek-V4-Flash-DSpark`
- Revision: `62af8fffb2f7030cac4de2f0169f5b8d1101b646`

## Outcome

官方 Hugging Face fixed revision 已下载到 worker NVMe，并按用户后续授权复制为 HDFS
备用实体副本：

```text
/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/huggingface-62af8fffb2f7030cac4de2f0169f5b8d1101b646
```

结果为 74 个 provider payload 文件、48 个权重 shard、总计
`166898666055` bytes。正式目录另有已写入并回读成功的 `.complete`。

worker NVMe 源快照仍保留：

```text
/tmp/deepspec-hf-20260728T154037Z-parallel-hf-download/snapshot
```

## Validation

按用户最新授权使用
`validation_level=operational_minimal_user_authorized`：

- requested revision 和 resolved revision 都精确等于固定 commit；
- 74 个 provider 路径集合与官方 metadata 完全一致；
- 逐文件 size 和总大小完全一致；
- 48 个 `model-*-of-00048.safetensors` 完整；
- `config.json`、`generation_config.json`、
  `model.safetensors.index.json`、`tokenizer.json` 和
  `tokenizer_config.json` 存在；
- NVMe 和 HDFS provider tree 均无 symlink；
- HDFS staging 与正式目标同父目录，验证通过后原子 rename，发布后 staging 不存在；
- `.complete` 写入正式目录并回读一致；
- 采用 4-worker userspace buffered byte copy，没有使用 symlink、hardlink、reflink
  或 provider cache 引用；
- NVMe 源快照没有删除。

本次明确没有计算 166 GB provider payload 的全量内容 hash。这是用户要求的快速最小
验证范围，不能把该结果描述为逐内容 hash 验证。

## Attempts

1. 首条直接向 HDFS FUSE `--local-dir` 下载的路径失败。Hugging Face local-dir
   metadata lock 调用 `os.ftruncate`，HDFS FUSE 返回
   `OSError: [Errno 38] Function not implemented`。该失败路径没有写入 provider
   payload；其零字节 `.cache/huggingface` 元数据留作证据，未发布。
2. 改为 worker NVMe-first，使用 uv 环境中固定的
   `huggingface-hub[hf-xet]==0.34.4`。下载 attempt 1 在
   `model-00045-of-00048.safetensors` 的 HEAD 请求处遇到
   `ProxyError/RemoteDisconnected`，73/74 文件被保留。
3. 有界续传 attempt 2 补齐最后一个 shard。completion gate 在
   74/74 和官方下载进程退出后对旧 supervisor 发出 `SIGSTOP`，阻止旧代码进入已取消
   的全量 SHA 和 HDFS copy；最小 NVMe 验证 PASS 后，旧 supervisor 与 watchdog 经
   PID、PGID 和完整命令行核对后定向清理。
4. 用户随后授权 HDFS 备用副本。4 路实体复制完成后通过快速最小验证，并原子发布到
   上述正式路径。

旧 acquisition `download_summary.json` 在 completion gate 冻结 supervisor 时仍可能
显示 `IN_PROGRESS`；它不是最终 gate。最终 NVMe 结论以
`nvme_minimal_validation.json` 和 `nvme_completion_gate.json` 为准，HDFS 结论以
`hf_hdfs_gate.json` 为准。

## Evidence

NVMe acquisition：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T154037Z-parallel-hf-download/hf_metadata.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T154037Z-parallel-hf-download/nvme_minimal_validation.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T154037Z-parallel-hf-download/progress/nvme_completion_gate.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T154037Z-parallel-hf-download/hf_cli.log
```

HDFS backup and publication：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/hf_hdfs_gate.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/copy.log
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/copy_manifest.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/source_validation.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/target_validation.json
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T173307Z-hf-hdfs-backup/keepalive_checks.json
```

HDFS gate 为 `status=PASS`、`formal_target_exists=true`、
`staging_absent=true`、`complete_marker_readback=true`、
`source_nvme_retained=true` 和 `content_hashes_computed=false`。

## Worker and process state

- HDFS copy coordinator PID/PGID `13384/13384` 已正常退出；
- acquisition supervisor PID/PGID `5126/5126` 和 watchdog
  PID/PGID `6227/6227` 已定向清理；
- 没有启动 SGLang，也没有修改 Phase 04 文件；
- keepalive 未被本 executor 暂停。复制前后两次 10×1 秒 gate 均 PASS，worker-local
  keepalive PID 为 `9277`，四张卡平均利用率均为 `100%`。

## Repository changes

本 executor 新增或修改以下未提交文件：

```text
scripts/hf_checkpoint_staging_download.py
scripts/hf_checkpoint_nvme_worker.py
scripts/hf_checkpoint_nvme_watchdog.py
scripts/hf_checkpoint_nvme_completion_gate.py
scripts/hf_checkpoint_nvme_validate.py
scripts/hf_checkpoint_nvme_download.sh
scripts/hf_checkpoint_hdfs_backup.py
scripts/hf_checkpoint_hdfs_backup.sh
docs/plan/handoffs/parallel-hf-download-20260728T154037Z-parallel-hf-download.md
```

其中 `hf_checkpoint_staging_download.py` 是失败的直接 HDFS 下载路径，未用于最终下载；
保留它仅用于解释 `ftruncate` blocker。executor 未 commit。

## Handoff

HDFS Hugging Face 正式备用路径已具备下游读取条件。当前 Phase 04 应继续使用主 Agent
已经验收的阶段输入；是否改用该备用路径由主 Agent 决定，不应在未记录的新 attempt
中静默切换 provider。NVMe 副本只能在主 Agent 明确确认不再需要后清理。
