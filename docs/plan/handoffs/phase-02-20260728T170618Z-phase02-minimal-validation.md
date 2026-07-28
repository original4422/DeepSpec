# Phase 02 Handoff

- Status: PASS
- Copy attempt: `20260728T164102Z-phase02-modelscope-copy`
- Publication attempt: `20260728T170618Z-phase02-minimal-validation`
- Finished at: `2026-07-28T17:10:03Z`
- Git HEAD: `3942e9a224a467dd05aeb7c86ba092a22580528b`
- Worker: `4105641`
- Authorized phase: Phase 02

## Outcome

ModelScope checkpoint 已复制为 DeepSpec-owned 实体目录并发布：

```text
/mnt/hdfs/pengzegang/DeepSpec/models/deepseek-ai__DeepSeek-V4-Flash-DSpark/snapshots/modelscope-bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae
```

复制结果为 75 个 provider payload 文件、48 个权重 shard、总计
`166898666759` bytes；正式目录另有 DeepSpec 写入并回读成功的 `.complete`。

## Evidence

最终 gate：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/20260728T170618Z-phase02-minimal-validation/phase02_gate.json
SHA256 9dc134d07ca4855d4e4c15cfa48713fb46e908bef2edeab7a27b7d8e213e5af0
```

独立收尾复核结果：

- gate `status=PASS`，全部登记 artifact 的 size/SHA-256 匹配；
- 正式目录含 75 个 payload 文件和 1 个 `.complete`；
- 48 个 shard 与 index 引用集合一致；
- payload 总大小为 `166898666759` bytes；
- config、tokenizer、index 存在，`dspark_block_size=5`、
  `expert_dtype=fp4`；
- 无 symlink，源目录 stat snapshot 未变；
- `.complete` SHA-256 为
  `f2d7b881d8b569728314e31c84fdf63bb330cc38feca79a5d92c8abbc857018f`。

按用户最新要求，本次使用
`validation_level=operational_minimal_user_authorized`，没有完成目标 48 个权重
文件的全量 SHA-256；Phase 01 的源 checkpoint 已做过全量 manifest 验证，目标仅验证
文件集合、逐文件大小、总大小、核心小文件 SHA-256 和实体独立性。下游模型加载若暴露
内容问题，再按实际错误处理。

## Attempts and process state

- `20260728T163300Z-phase02-modelscope-copy`：在复制前因 detached stdout
  `BrokenPipeError` 失败，0 bytes；证据保留。
- copy attempt 完成 75/75 复制后，full-hash watchdog 与已授权的短 GPU validation
  暂停 keepalive 冲突。PID/PGID `4170621` 经完整命令行核对后定向 TERM，1 秒退出；
  完整 staging 保留并由 publication attempt 接管，未重复制。
- Phase 02 当前无残留进程，未启动 SGLang，也未创建或修改正式模型环境。
- 发布前 keepalive 已恢复：worker-local PID `9277`，10×1 秒四卡均为 `100%`。

## Repository changes

本 executor 只新增：

```text
scripts/phase02_copy.py
scripts/phase02_start.sh
scripts/phase02_validate_publish.py
scripts/phase02_validate_publish.sh
docs/plan/handoffs/phase-02-20260728T170618Z-phase02-minimal-validation.md
```

未 commit，未触碰并行 Hugging Face acquisition 路径，也未进入 Phase 03。

## Next eligible phase

Phase 02 已满足用户当前的最小前置条件。只有 Phase 03 自身 PASS 且用户确认后，才具备
进入 Phase 04 的条件。
