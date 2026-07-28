# HEDGE DSpark P00 handoff

- Status: `PASS`
- Attempt ID: `20260728T205441Z-p00-bootstrap`
- Started / finished: `2026-07-28T20:54:41Z` /
  `2026-07-28T21:59:00Z`
- Autonomy elapsed / deadline: `01:04:19` /
  `2026-07-29T08:54:41Z`
- Git branch / HEAD / worktree: `exp/hedge-v4-dspark` /
  `4d96f44065c07030ede67484a262006ec149626a` /
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
- Initial branch base:
  `cac6c78d88df97d395406fe831f573df3016e7f7`
- Worker / GPU lane: `4106666` /
  `g340-cd51-4b00-4622-f8b4-6e76-faf3` / exact 8×NVIDIA H20
- TP ranks / GPU participation: P00 未启动模型，TP ranks 不适用；8 张 GPU 均仅由
  登记的 operational keepalive 持续占用并通过逐卡门禁
- Authorized phase: `P00` only

## Outcome

P00 出口门禁全部通过。专用 worktree、branch、uv environment、SGLang base source、
checkpoint identity、CUDA 13 linker seam、8 卡 worker identity 和最终 operational
keepalive 都已建立并保留可审计证据。没有启动 SGLang、模型、API 或 TP 进程，也没有
进入 P01/P02/P03 的执行工作。

权威 session manifest：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap/session.json
```

其状态为 `PASS`，`AUTONOMY_START_UTC=2026-07-28T20:54:41Z`，
`AUTONOMY_DEADLINE_UTC=2026-07-29T08:54:41Z`；canonical session 于
`2026-07-28T21:58:38.374346Z` finalized。

## Changes

- 从只读 base `cac6c78...` 安全创建专用 worktree
  `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark`
  和 branch `exp/hedge-v4-dspark`；base worktree 的历史 MVP dirty files 原样保留，
  没有修改或覆盖。
- 新建 P00 inventory、checkpoint identity、environment、CUDA link、keepalive 和
  session finalizer 脚本。所有脚本仍由主 Agent 统一审查、暂存和提交；本 executor
  没有 commit 或 push。
- `docs/progress/hedge-deepseek-v4-flash-dspark.md` 与
  `docs/experiment/hedge-deepseek-v4-flash-dspark.md` 由主线程指定的 recorder
  维护；本 executor 未与 recorder 并发编辑。
- 创建独立 uv environment
  `/home/tiger/venvs/hedge-v4-dspark`，通过
  `uv sync --frozen --python 3.11` 与 `UV_LINK_MODE=copy` 构建。
- 用 `git clone --no-hardlinks` 建立独立 SGLang source
  `/home/tiger/src/hedge-v4-dspark-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`。
- 在新 venv 的 CUDA 13 root 中 guarded、幂等创建：

```text
lib64/libcudart.so -> ../lib/libcudart.so.13
lib64/libnvrtc.so  -> ../lib/libnvrtc.so.13
```

## Evidence and artifact paths

P00 artifact root：

```text
/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260728T205441Z-p00-bootstrap
```

主要 canonical artifacts：

```text
session.json
worker_inventory.json
final-state/worker_inventory.json
keepalive_initial.json
keepalive-migration/keepalive_migration.json
checkpoint_identity.json
environment_identity.json
sglang_base_identity.json
cuda_link_probe.json
uv-sync.log
uv-pip-check.log
```

checkpoint metadata-only identity：

- provider / repository：`modelscope` /
  `deepseek-ai/DeepSeek-V4-Flash-DSpark`；
- snapshot：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae`；
- HF reference revision：
  `62af8fffb2f7030cac4de2f0169f5b8d1101b646`；
- provider payload：75 files / `166898666759` bytes；
- shards：48/48，index referents 精确覆盖 48 个 shard；
- `dspark_block_size=5`、`expert_dtype=fp4`；
- `full_checkpoint_hash_performed=false`。

CUDA link probe 状态为 `PASS`，使用
`/usr/bin/cc -shared ... -lcudart -lnvrtc -o /dev/null`，`returncode=0`；
第二次 guarded pass 两个 link 都为 `verified`，且 probe 前后
keepalive CUDA context inventory 不变。没有用模型加载掩盖 linker 问题。

## Source/config identity

独立环境的已记录版本：

| 项目 | 版本 |
| --- | --- |
| Python | `3.11.2` |
| uv | `0.11.32` |
| PyTorch / CUDA | `2.11.0+cu130` / `13.0` |
| SGLang | `0.5.16` |
| sglang-kernel | `0.4.5+cu130` |
| FlashInfer | `0.6.14` |
| Triton | `3.6.0` |
| NCCL | `2.28.9` |

SGLang target source 的 worker-side `sglang_base_identity.json` 与主线程可见路径
复核均证明：

```text
HEAD=fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1
status --porcelain=(empty)
origin=https://github.com/sgl-project/sglang.git
```

HEDGE source worktree 的当前 HEAD 是
`eb3948117a8be505da64904ad718dc4efd97a5b1`，并有既存 untracked 文档/assets；
固定 commit `9fb903d676254ea5f5d171051fb15c54f331111c` 的 commit object 存在。
P00 只记录该事实，没有修改 HEDGE worktree；P02 必须从固定 commit object 读取
tracked core/tests，不能从浮动 worktree HEAD 取语义。

## Process, CUDA context and keepalive state

首次只读 inventory 证明 worker `4106666` 为准确 8×H20 且
`compute_contexts=[]`，没有未知 SGLang、torchrun 或 GPU task；平台 Jupyter
gateway 保持原样，未被触碰。

bootstrap keepalive 最初使用历史验证 venv 的只读 Python。独立 venv 完成后，迁移
严格按以下顺序完成：

1. 用旧 Python identity 精确核对并定向停止 supervisor
   PID/PGID/SID `1697/1697/1697`；
2. `contexts_after_old_pause=none`；
3. 立即用 `/home/tiger/venvs/hedge-v4-dspark/bin/python` 启动新 supervisor；
4. 最终 PID/PGID/SID 为 `4730/4730/4730`；
5. 10×1 秒 GPU0–7 的 mean/min/max 全部为 100%，每卡 10 个样本；
6. final inventory 恰有 8 个 keepalive-sized CUDA contexts，每张卡一个、
   约 806 MiB；没有 SGLang/model server 进程。

P00 退出时 operational keepalive 持续运行，不应停止。后续模型 attempt 必须由其
唯一 owner 在紧邻启动前用同一精确 identity 暂停并确认 contexts none。

## First root cause / progress since prior attempt

保留了全部失败/恢复证据：

1. keepalive attempt 01：wrapper 的 awk 局部名与 builtin 冲突，未创建进程；
   日志 `keepalive_start_attempt01_failed.txt`。单变量改名后 blocker 迁移。
2. keepalive attempt 02：CUDA 13 PyTorch 在 driver 535 上缺少已验证
   forward-compat prefix，未留下 context；日志
   `keepalive_start_attempt02_cuda_compat_failed.txt`。固定 compat + runtime lib
   后第三次启动通过。
3. environment bootstrap：收窄的 `PATH` 漏掉
   `/home/tiger/.local/bin/uv`，uv 未执行；封存在
   `environment-attempts/20260728T205441Z-p00-bootstrap/`。
4. environment r1：下载有实质进展，最终 pinned SGLang Git fetch 遇到
   `SSL connection timeout`；封存在
   `environment-attempts/20260728T211013Z-p00-env-r1/`。单变量复用历史 9.7 GiB
   uv cache（含精确 `fdebc938...` checkout），r2 完成。
5. checkpoint checker attempt 01：首版误把 provider payload 75 files 当成
   top-level 文件数，并误把 logical tensor bytes 等同于含 safetensors header 的
   shard file bytes；失败 JSON 保存在
   `checkpoint-attempts/20260728T214959Z-checkpoint-scope-failed/`。只修递归 scope
   与 total-size 语义后 r1 PASS，canonical 原子发布。
6. session checker attempt 01：主 Agent 在 P00 运行期间正常提交 P01/P02 节点，
   branch HEAD 从初始 `cac6c78...` 前进到其后代 `4d96f44...`；首版 exact-head
   assertion 因并发提交而失败，证据保存在
   `session-attempts/session01-concurrent-main-commit-failed.json`。改为核对初始
   commit 是当前 HEAD 祖先后 canonical `session.json` PASS。

以上失败均缩小了范围或迁移了 blocker，没有覆盖失败证据、改变 SGLang/model identity
或启动模型。

## Main-Agent acceptance recommendation

建议：`PASS`。

主 Agent 应直接复核：

- `session.json` 的全部 checks 为 true；
- canonical checkpoint identity 为 `PASS`；
- CUDA link probe 为 `PASS`；
- new-runtime keepalive migration 和最终 10×1 秒 gate 为 `PASS`；
- final inventory 无 model server；
- base worktree dirty paths 仍与 P00 开始时一致；
- 本 handoff 和 P00 scripts 未被 executor commit/push。

## Next eligible phase

P01/P02 已由主 Agent 在 P00 长任务期间并发完成。主 Agent 验收 P00 后，下一 eligible
phase 是 P03。P00 executor 到此停止，不自行进入下一阶段。
