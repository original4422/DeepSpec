# DFlash Phase D1A handoff

结论：`D1A PASS`。首选 DFlash draft checkpoint 已按固定 Hugging Face revision
完成 provider identity、config、safetensors header/shape、NVMe 实体和 HDFS 独立实体
核查，并通过同父目录原子 rename 发布正式目录、`.complete` 与 lane pointer。
fallback 未启用；本 executor 全程未暂停或停止 worker `4099543` 的 keepalive、未启动
模型、未进入 D1B/D1C/D2，也未 stage/commit/push。

## 退出门禁

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| provider repo/revision 精确解析 | PASS | `provider_metadata.json`：requested/resolved revision 均为 `e44fc94…` |
| provider OID、文件集合和总大小固定 | PASS | 6 files / `3,607,606,957` bytes；manifest SHA-256 `86b023…` |
| 唯一 worker NVMe staging 完整 | PASS | 6/6 regular files，size/file set 精确，无 symlink |
| config contract 自洽 | PASS | architecture、DFlash、block 8/7 candidates、aux IDs、mHC width、5 layers、vocab、sliding attention 全部通过 |
| safetensors header 与 shape 自洽 | PASS | 62 tensors、5 layers、payload offset 连续、shape/dtype byte span 精确 |
| HDFS 是独立实体且二次校验通过 | PASS | 6/6 文件均与 NVMe 不同 device/inode；size、small-file hash、header 一致，无 symlink |
| HDFS 原子发布完成 | PASS | 正式目录、`.complete`、pointer 均存在；同父 staging 在 rename 后不存在 |
| keepalive 连续且最终 gate 通过 | PASS | PID/PGID/SID `34059`；8 卡各 10×1 秒 mean utilization `100%` |
| 模型与 fallback 边界 | PASS | 未启动任何模型；primary 成功，fallback 未启用 |
| repo/HDFS/NVMe 证据镜像一致 | PASS | `evidence_audit.json`：`evidence_mirrors_match=true` |
| signed download URL 已清除 | PASS | repo evidence 扫描无 `cas-bridge`、`X-Amz` 或 `Signature` 命中 |
| FAIL 项 | 无 | — |

## 固定 checkpoint identity

| 项目 | 固定值 |
| --- | --- |
| Provider | Hugging Face |
| Repo | `RedHatAI/DeepSeek-V4-Flash-speculator.dflash` |
| Revision | `e44fc94ceb1e7ed45550d15e782aeadd08050483` |
| Provider file count | `6` |
| Provider total bytes | `3,607,606,957` |
| Provider manifest SHA-256 | `86b023ba9be98bb8e5e003424b660da9bcf8cd085e7a33bb93942ce60a8cca02` |
| Weight bytes | `3,607,596,760` |
| Weight LFS SHA-256/OID | `d686aef63ec7debf699b4534851c38451a3f2bc7a532e0d4f9ea0ed844d3d6ee` |
| Weight git blob pointer ID | `7ad962eaf656325bfa91f1c4ad5d5a6857bbccab` |
| `config.json` SHA-256 | `2271198e97a0f443f6c530e5a1fc8c85ccc8f5b914293f08a3301551870522a5` |
| Safetensors header length | `6,608` bytes |
| Safetensors header SHA-256 | `a920047d53810be3c990ba1a8765fcbbee2bedc8821853990d26042a1f14ef35` |
| Safetensors tensors / parameters | `62` / `1,803,763,712` |

Config contract 固定为：

- `architectures=["DFlashDraftModel"]`，algorithm `dflash`；
- `block_size=8`，实际 draft proposal candidates 为 `7`；
- `aux_hidden_state_layer_ids=[3,13,23,32,42]`；
- `hc_mult=4`，hidden size `4096`，目标 feature width `16384`；
- draft layers 为 `[0,1,2,3,4]`；
- draft vocab `32000`，target vocab `129280`；
- 五层均为 `sliding_attention`，window `2048`。

Safetensors header 证明层集合为 `[0,1,2,3,4]`，全部 data offset 连续覆盖 payload，
每个 tensor 的 dtype/shape 与 byte span 一致；`4096`、`16384`、`32000` 关键维度
均存在并通过检查。

## 发布路径与不可变 marker

- 正式目录：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft/RedHatAI--DeepSeek-V4-Flash-speculator.dflash/e44fc94ceb1e7ed45550d15e782aeadd08050483`
- `.complete`：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft/RedHatAI--DeepSeek-V4-Flash-speculator.dflash/e44fc94ceb1e7ed45550d15e782aeadd08050483/.complete`
- lane pointer：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/draft_pointer.json`
- `.complete` SHA-256：
  `f26d58995a8f9ff3e387fb6e940e13521bc4ad82455bd51f548faa610e94338b`
- pointer SHA-256：
  `d2b439945df143bff0873705b7f1aac37bf35e47b098eaaf3e1a6a408c2e1add`

发布前 HDFS staging 与 NVMe 是独立实体；6 个 payload 文件的集合和总大小完全一致。
`.complete` 在唯一同父 HDFS staging 内写入并读回后，目录原子 rename 到正式路径；
rename 后 staging 不存在。后续 phase 只有在主 Agent 验收 D1A 后才可只读消费
`draft_pointer.json`；本 handoff 不代表 D2 或任何模型阶段已经开始。

## Attempt 与下载重试归因

- Attempt：`dflash-d1a-primary-20260728T213507Z`
- 开始：`2026-07-28T21:35:37Z`
- weight transfer 开始：`2026-07-28T21:35:49Z`
- weight transfer 完成：`2026-07-28T23:39:12Z`
- NVMe 校验完成：`2026-07-28T23:39:14Z`
- 原子发布完成：`2026-07-28T23:39:21Z`
- 最终 evidence audit：`2026-07-28T23:41:03Z`

第一次长传输在 partial 文件约 `3.40 GB` 时发生同一 curl 进程内 reset，随后从较小尺寸
重新增长。只读 `/proc`、inode 和 byte trajectory 证明 curl PID `36076` 未变、
partial inode `154404175` 未变，而累计写入字节显著大于当前文件长度；命令同时使用
`--retry 8 --retry-all-errors --continue-at -`。根因 fingerprint 固定为：

```text
curl-internal-retry-restarts-from-invocation-offset-zero
```

没有向进程发送 signal，也没有切换 checkpoint。相同 curl 的后续 pass 自然完成并达到
provider 精确字节数。为失败后的最小恢复预先准备了“每次由外层重启 curl、重新计算
resume offset”的 bounded resume 脚本，但未执行。完整 byte trajectory 和只读诊断分别
保存在 `retry_monitor.jsonl`、`reset_observation.json` 和
`retry_reset_diagnostic.json`；本次 reset 没有被当成 checkpoint-specific failure，
因此 fallback 始终关闭。

## Evidence

Attempt 的权威小型证据镜像：

- worker NVMe：
  `/tmp/deepspec-hedge-dflash/d1a/attempts/dflash-d1a-primary-20260728T213507Z`
- HDFS：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/evidence/d1a/dflash-d1a-primary-20260728T213507Z`
- repo：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1a/dflash-d1a-primary-20260728T213507Z`

`evidence_manifest.json` 覆盖 19 个 evidence 文件，manifest SHA-256：
`569e254cd449dbe3f5de438f0ef5296fa4ce31a58be0fb3b79b41c0f70e2e2c5`。
`evidence_audit.json` 的最终状态为 `PASS`，且三份 evidence mirror 一致。

按计划和 `AGENTS.md` 的最小核查纪律，未在 NVMe 和 HDFS 各完整重读 3.6 GB weight
计算第二份 SHA-256；没有出现传输损坏证据。当前身份由 provider LFS SHA-256/OID、
exact revision、精确文件集合/大小、有效且自洽的 safetensors header、small-file hash、
独立实体复制和发布后二次检查共同固定。真实模型加载仍是后续 phase 的可用性核查，
不属于 D1A。

## Operational handoff

- worker：`4099543`，hostname
  `g340-cd51-4b00-4d69-9088-7ae6-6253`，8×NVIDIA H20。
- keepalive supervisor PID/PGID/SID：`34059`。
- D1A 全程未 pause/stop keepalive，未启动模型。
- 最终 fresh gate：GPU `0..7` 各 10 个 1 秒样本，mean utilization 均为 `100%`
  （最低要求 `40%`）。
- downstream executor 在任何 worker 操作前仍须重新运行 `mlx worker list`；任何模型
  attempt 必须按 D0 handoff 紧邻地定向暂停 keepalive 并确认全部 CUDA context 退出。
  D1A 不授权提前执行该切换。

## D1A 文件边界

D1A 新增内容使用 `dflash_d1a_*` 前缀，除计划指定的 artifact 与本 handoff 外：

- `scripts/dflash_d1a_acquire_publish.py`
- `scripts/dflash_d1a_run.sh`
- `scripts/dflash_d1a_status.sh`
- `scripts/dflash_d1a_partial_header_probe.py`
- `scripts/dflash_d1a_partial_header_probe.sh`
- `scripts/dflash_d1a_retry_diagnostic.py`
- `scripts/dflash_d1a_retry_diagnostic.sh`
- `scripts/dflash_d1a_retry_status.py`
- `scripts/dflash_d1a_retry_status.sh`
- `scripts/dflash_d1a_resume_publish.py`
- `scripts/dflash_d1a_resume_publish.sh`
- `scripts/dflash_d1a_sanitize_events.py`
- `scripts/dflash_d1a_sanitize_events.sh`
- `scripts/dflash_d1a_finalize_evidence.py`
- `scripts/dflash_d1a_finalize_evidence.sh`
- `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1a/`
- `docs/plan/handoffs/dflash-phase-d1a-handoff.md`

其中 `dflash_d1a_resume_publish.*` 仅为 reset 后的有界恢复预案，本次没有调用。其他
phase 文件未触碰；主 Agent 可只显式暂存上述 D1A 文件。
