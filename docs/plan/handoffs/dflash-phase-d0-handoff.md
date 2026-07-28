# DFlash Phase D0 handoff

结论：`D0 PASS`。独立 lane 已固定，worker `4099543` 的 8×H20 身份、拓扑、容量和
空闲状态已只读核验；未发现 legacy GPU task，也未向任何既有/未知进程发送 signal。
本 lane 8 卡 sustained keepalive 正在运行并通过逐卡门禁。

## 退出门禁

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 从固定 commit 建立独立 branch/worktree | PASS | `lane_identity.json`；HEAD `cac6c78d88df97d395406fe831f573df3016e7f7` |
| T0、T+9h、T+12h 可机器读取 | PASS | `timebox.json` |
| worker identity 为 4099543 / 8×H20 | PASS | `preflight.json` |
| GPU UUID/型号/拓扑/容量/端口 | PASS | `preflight.json` |
| legacy tasks 只读识别、自然退出策略、无 signal | PASS | `legacy_process_inventory.json`；两次观察均为空 |
| lane 专用 keepalive PID/PGID/命令/UUID | PASS | `keepalive_identity.json`；PID/PGID `34059` |
| 10×1 秒每卡平均利用率 ≥40% | PASS | `keepalive_gpu_samples.csv`；八卡均 100% |
| Eagle target pointer | WAIT | canonical `eagle_target_pointer.json` 尚不存在 |
| DSpark pure-core pointer | WAIT | canonical `dspark_pure_core_pointer.json` 尚不存在 |
| progress/session/canonical experiment 基线 | PASS | progress、experiment、`session_manifest.json` |

Artifact 根目录：
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d0/`。

## Operational handoff

- keepalive supervisor：PID/PGID/SID `34059`。
- state：`/tmp/deepspec-hedge-dflash/keepalive`。
- control：`scripts/dflash_keepalive.sh`，固定要求 worker ID `4099543` 与准确 8×H20。
- status：先运行 `mlx worker list`，再从本 worktree 根目录运行
  `mlx worker login 4099543 -- bash /mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_d0_keepalive_status.sh`。
- 未来模型 phase 必须在 fresh inventory 后调用 control 的 `pause`，并核对 context
  清空；本 D0 executor 未暂停或停止 keepalive。
- operational runtime 是 `/tmp` 中 uv 创建的 lane-local venv，使用 system
  site-package PyTorch 2.7.1/CUDA 12.6，仅用于 keepalive。正式 DFlash 环境仍须 D1B 在
  `/home/tiger/venvs/deepspec-hedge-dflash` 建立并锁定，不能把 operational runtime
  当作正式环境证据。

## Attempts 与限制

1. 首个 runtime probe 因 `torch` import/CUDA count 超过 15 秒超时而有界退出；改用
   metadata-only probe，再用独立 120 秒 runtime gate，证明 8 CUDA devices 可见。
2. 首个 keepalive start 在创建 GPU load 前因 mawk 不允许变量名 `index` 而失败；只将
   该变量改名为 `gpu_index` 后成功。
3. 后续 status 身份刷新曾因嵌入 Python 缺少 `import os` 失败，但 keepalive 未退出；
   单行修复后 status/gate 再次 PASS。
4. `nvidia-smi` 的 host PID namespace 与容器 PID namespace 不同；定向控制以已登记的
   container PID/PGID、完整 argv 和 process group 为准，GPU UUID 另行固定。

未决 blocker：Eagle target 与 DSpark pure-core coordination pointers 为 `WAIT`；
formal uv/source/dataset/draft 工作属于 D1+，D0 未越界执行。

本 executor 未 stage、commit 或 push，且未进入 D1。
