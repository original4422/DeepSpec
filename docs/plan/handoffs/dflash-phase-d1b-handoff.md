# DFlash Phase D1B handoff

结论：`D1B PASS`。正式 uv environment、固定 SGLang source 和
DFlash-on-DeepSeek-V4 contract 均已固定；CPU-only contract probe 为 `PASS`，
unittest `5/5 PASS`。本 executor 未暂停 worker `4099543` 的 keepalive、未加载大模型、
未修改 SGLang、未进入 D2，也未 stage/commit/push。

## 退出门禁

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 独立 uv env 可复现、lock identity 固定 | PASS | `dflash_d1b_environment_lock.json`；`uv pip check` 201 packages compatible |
| SGLang exact `fdebc938…` / `v0.5.16` / clean detached checkout | PASS | `dflash_d1b_source_identity.json` |
| Python/PyTorch/CUDA/NCCL/FlashInfer/Triton/sglang-kernel 已记录 | PASS | `dflash_d1b_dependency_versions.json` |
| worker metadata import 不改变 CUDA context，keepalive 前后健康 | PASS | `dflash_d1b_worker_probe.json` |
| primary config 与 partial safetensors header identity 固定 | PASS | `dflash_d1b_primary_config.json`、`dflash_d1b_safetensors_header_summary.json` |
| `4×4096→16384`、五层 concat `81920` 可运行验证 | PASS | `dflash_d1b_contract_test_output.json` |
| aux 顺序 `[3,13,23,32,42]` 可运行验证 | PASS | identifiable-tensor sentinels in contract output |
| generic `+1` / DeepSeek after-layer `no +1` 规则可运行验证 | PASS | contract output + fixed-source assertions |
| `completed.mean(dim=1)` 被拒绝 | PASS | `[2,20480]` 对 checkpoint-required `[N,81920]` 的硬失败 |
| block 8 / `candidates[:,1:]` = 7 可运行验证 | PASS | contract output + fixed-worker assertion |
| D2 production parser/hook/projection integration | WAIT（按阶段设计） | D1B 只固定 contract；未改 SGLang |
| D1A draft publish / coordination pointers | WAIT（不属于 D1B） | 由对应并行 phase/主 Agent 验收 |
| FAIL 项 | 无 | — |

Artifact 根目录：
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1b/`。

Contract 文档：
`dflash_d1b_contract.md`（对应计划中的 `dflash_contract.md` artifact）。

## D2 必须继承的 contract

1. Primary config schema：
   `transformer_layer_config`、`aux_hidden_state_layer_ids` 和 top-level
   `mask_token_id` 必须被 production parser/loader 显式接入。当前 fixed parser 直接
   读取 raw config 时只能拿到 `block_size=8`，其余关键字段缺失。
2. Aux capture 顺序严格为 `[3,13,23,32,42]`。
3. DeepSeek-V4 当前 capture seam 是执行 layer 后再捕获，因此 checkpoint IDs 原样使用，
   不加一；只有 before-layer generic seam 才映射为 `[4,14,24,33,43]`。
4. 每个 `completed` 的 mHC shape 必须从 `[N,4,4096]` 通过 `.flatten(1)` 变为
   `[N,16384]`，再按 aux 顺序 concat 成 `[N,81920]`。禁止
   `completed.mean(dim=1)`。
5. Primary `fc.weight` 是 `[4096,81920]`；当前 fixed DFlash model 的 generic
   `5×4096=20480` projection 不能加载该权重，D2 必须修复并保留 shape test。
6. Proposal 宽度固定为 block 8，其中第 0 列是 current token；HEDGE 处理的七个
   draft candidates 是 `candidates[:,1:]`。

## Operational handoff

- worker：`4099543`，8×H20。
- keepalive：继续使用 D0 supervisor PID/PGID `34059`；D1B 全程未 pause/stop。
- D1B 最终 worker probe：前后均 `HEALTHY`，8 卡各 10×1 秒 mean utilization 100%，
  compute-process inventory 不变。
- 正式 env：`/home/tiger/venvs/deepspec-hedge-dflash`。
- fixed source：`/home/tiger/src/deepspec-sglang-hedge-dflash`，
  detached HEAD `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，clean。
- source upstream identity：`https://github.com/sgl-project/sglang.git`。
- D2 在任何模型 attempt 前仍须重新 `mlx worker list`，并按 D0 operational handoff
  紧邻地 pause keepalive、证明 CUDA context 清空；D1B 的 metadata probe 不替代该门禁。

## Environment identity

| 组件 | 实测 |
| --- | --- |
| Python | `3.11.2` |
| PyTorch | `2.11.0+cu130` |
| PyTorch compiled CUDA | `13.0` |
| nvcc | `13.0.88` |
| NCCL runtime/package | `2.28.9` |
| FlashInfer | `0.6.14` |
| Triton | `3.6.0` |
| sglang-kernel | distribution `0.4.5+cu130` / module `0.4.5` |
| SGLang | `0.5.16`，editable import 指向 fixed checkout |
| uv | `0.11.32` |

`pyproject.toml` SHA-256：
`b5f96c3c709cb93a8d2b24ec965260f473fbcb494f124a8368462c9bba98759d`。
`uv.lock` SHA-256：
`cdb50b27e332bc6da1bef8ce39c7f46196f5c041738a395bc13d8f95dd2cddd7`。

## Tests

运行：

```bash
CUDA_VISIBLE_DEVICES='' \
CUDA_HOME=/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13 \
PYTHONNOUSERSITE=1 \
/home/tiger/venvs/deepspec-hedge-dflash/bin/python \
  scripts/dflash_d1b_contract_probe.py \
  --output docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1b/dflash_d1b_contract_test_output.json

CUDA_VISIBLE_DEVICES='' \
CUDA_HOME=/home/tiger/venvs/deepspec-hedge-dflash/lib/python3.11/site-packages/nvidia/cu13 \
PYTHONNOUSERSITE=1 \
/home/tiger/venvs/deepspec-hedge-dflash/bin/python \
  -m unittest -v tests/dflash_d1b_contract_test.py
```

结果：

```text
Ran 5 tests
OK
```

CPU-only 运行出现的 “Triton is not supported on current platform” 与量化 backend
warning 是因为开发机没有暴露 CUDA；测试没有执行 CUDA operation，所有 contract
assertion 均通过。

## Attempts 与单变量归因

1. 首次 `uv sync --frozen` 在构建 SGLang editable wheel 时因缺少 Rust compiler
   失败。固定 source 的 `setup.py` 明确支持 `SGLANG_BUILD_RUST_EXTS=none`；只加入
   该 build selector 后 sync 成功，没有更换依赖或 source。
2. 首次 worker environment probe 完成 import 与 keepalive 检查后，在读取
   `uv --version` 时因非交互 `PATH` 不含 `~/.local/bin` 失败。keepalive 随即复核仍为
   八卡 100%；只把 uv 固定为 `/home/tiger/.local/bin/uv` 后重跑 PASS。
3. 首次 contract static assertion 对 `candidates[:,1:]` 的 regex 多转义了一层；只修正
   test regex 后，contract probe 与 5 个 unittest 全部通过。被测 SGLang source 和
   contract 未变化。

这三项均有明确 blocker 迁移，没有进行多变量试错。

## D1B 文件边界

D1B 新增内容均使用 `dflash_d1b_*` 前缀，除计划指定的本 handoff 文件外：

- `scripts/dflash_d1b_environment_probe.py`
- `scripts/dflash_d1b_environment_probe.sh`
- `scripts/dflash_d1b_contract_probe.py`
- `tests/dflash_d1b_contract_test.py`
- `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d1b/`
- `docs/plan/handoffs/dflash-phase-d1b-handoff.md`

其他 D1A/D1C untracked/committed 文件未触碰。主 Agent 可仅显式暂存上述 D1B 文件。
