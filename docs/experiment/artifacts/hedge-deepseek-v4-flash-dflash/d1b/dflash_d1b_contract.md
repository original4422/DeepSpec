# DFlash-on-DeepSeek-V4 contract audit（Phase D1B）

结论：`D1B PASS`。固定 checkpoint 的 DFlash contract 已由 provider config、
safetensors header、固定 SGLang source 和 CPU-only 可运行测试交叉固定。D1B 没有加载
模型、没有暂停 keepalive、没有修改 SGLang，也没有实现 D2 production integration。

## 固定身份

| 项目 | 固定值 | 证据 |
| --- | --- | --- |
| SGLang | `v0.5.16` / `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` | `dflash_d1b_source_identity.json` |
| source checkout | `/home/tiger/src/deepspec-sglang-hedge-dflash`，detached、clean | `dflash_d1b_source_identity.json` |
| uv env | `/home/tiger/venvs/deepspec-hedge-dflash` | `dflash_d1b_environment_lock.json` |
| primary draft | `RedHatAI/DeepSeek-V4-Flash-speculator.dflash` | provider config/header |
| primary revision | `e44fc94ceb1e7ed45550d15e782aeadd08050483` | provider config/header |
| model LFS identity | size `3607596760`；SHA-256 OID `d686aef63ec7debf699b4534851c38451a3f2bc7a532e0d4f9ea0ed844d3d6ee` | `dflash_d1b_safetensors_header_summary.json` |

环境实测为 Python `3.11.2`、PyTorch `2.11.0+cu130`、CUDA compile runtime
`13.0`、CUDA toolkit `13.0.88`、NCCL runtime `2.28.9`、FlashInfer `0.6.14`、
Triton `3.6.0`、`sglang-kernel 0.4.5+cu130`。`sglang 0.5.16` 的 import path
直接落在上述固定 checkout。worker `4099543` 上以 `CUDA_VISIBLE_DEVICES=""` 做
metadata-only import；前后 CUDA compute-process inventory 完全相同，keepalive 两次
均为 8 卡逐卡 100%。

## Canonical contract

### Config 与 parser

Provider config 的 draft schema 不是当前 SGLang generic parser 原生期待的 schema：

- draft transformer 字段在 `transformer_layer_config`，不是 `text_config`；
- checkpoint 使用 `aux_hidden_state_layer_ids=[3,13,23,32,42]`，不是
  `dflash_config.target_layer_ids`；
- `mask_token_id=1` 位于 top-level；
- `block_size=8` 位于 top-level，当前 parser 能读到这一项；
- `target_hidden_size=null`，不能据此回退成 draft `hidden_size=4096`。

可执行测试证明，把原始 config 直接交给固定 SGLang
`parse_dflash_draft_config` 时，`num_hidden_layers`、`target_layer_ids` 和
`mask_token_id` 都是 `None`，且 `require_num_layers()` 报错。测试中的
`normalize_primary_config_for_contract_audit` 只用于证明所需字段映射；它没有接入
SGLang，D2 必须正式实现并测试这个 normalization。

### mHC layout 与 aux 顺序

固定 contract 是：

```text
checkpoint aux order: [3, 13, 23, 32, 42]
completed per selected target layer: [N, 4, 4096]
per-layer transform: completed.flatten(1) -> [N, 16384]
cross-layer transform: cat in checkpoint aux order -> [N, 81920]
fc.weight: [4096, 81920]
```

`16384` 不是从 nullable `target_hidden_size` 猜出的默认值。它由 config 的
`hc_mult=4` 与 `hidden_size=4096` 推导，并由 safetensors header 中
`fc.weight=[4096,81920]`、`q_proj=[16384,4096]` 和
`o_proj=[4096,16384]` 独立约束。五个 aux layer 的输入宽度必须是
`5×16384=81920`。

小测为两个 batch、五个 aux slot、四个 stream 和 4096 个 feature 构造了可识别
`int64` 编码，逐 aux/stream 边界验证：

1. 每层 `.flatten(1)` 保留 stream-major 连续顺序；
2. 五层按 `[3,13,23,32,42]` 顺序 `torch.cat(..., dim=-1)`；
3. 最终 shape 精确为 `[2,81920]`；
4. `completed.mean(dim=1)` 会变成每层 `[2,4096]`、五层仅 `[2,20480]`，
   因与 `fc.weight` 不兼容而被测试硬拒绝。

因此任何复用 DeepSeek-V4 现有 DSpark
`dspark_aux_hidden_states.append(completed.mean(dim=1))` 的 DFlash 方案都不符合
checkpoint contract。

### Layer index

Checkpoint 的 `[3,13,23,32,42]` 表示选定 target layer 的 post-layer hidden
state。固定 SGLang 的 Llama 等 generic seam 在进入 layer `i` 之前取到前一层输出，
所以它们将 checkpoint ID 映射为 `id+1`。

DeepSeek-V4 当前 seam 则先执行 `layer(...)`，再在当前 `i` 上构造 `completed`。
因此未来 D2 若在这个 after-layer seam 增加 DFlash capture，必须原样使用
`[3,13,23,32,42]`，不能再加一。测试同时固定两套结果：

```text
generic before-layer seam: [4, 14, 24, 33, 43]
DeepSeek-V4 after-layer seam: [3, 13, 23, 32, 42]
```

固定 DeepSeek-V4 source 目前只有 `set_dspark_layers_to_capture`，没有
`set_dflash_layers_to_capture`；这属于 D2 明确要补的 production seam，而不是 D1B
失败。

### Block 8 / draft 7 / HEDGE 边界

Provider config 同时固定 `block_size=8` 与 `speculative_tokens=7`。SGLang DFlash
worker 把第 0 列写为 current/anchor token，draft 预测和 strict verify 都从第 1 列
开始。因此 HEDGE 的 draft-token 输入必须是：

```python
draft_candidates = candidates[:, 1:]  # [batch, 7]
```

小测使用两行带唯一 token ID 的 `[2,8]` candidates，证明 slice 恰好得到预期
`[2,7]`，且不包含第 0 列 current token。

## 固定 source 的 D2 接缝

D1B 的审计结论不是可启动实现。D2 至少需要同时满足下列三个接缝，并用本阶段测试防止
回归：

1. parser/loader：显式接入 `transformer_layer_config`、
   `aux_hidden_state_layer_ids` 和 top-level `mask_token_id`；
2. target capture：为 DeepSeek-V4 增加 after-layer DFlash hook，ID 不加一，并对
   `[N,4,4096]` 做 `.flatten(1)`，绝不 `mean(dim=1)`；
3. draft projection：当前 fixed base 的
   `num_context_features * hidden_size` 只会构造 `5×4096=20480`，必须按 primary
   header 接收 `81920`，且 checkpoint loader shape 必须精确匹配。

D1B 未修改这些文件，也未对 D2 的具体代码结构作超出 contract 所需的设计承诺。

## 可复现命令

环境创建与 fixed-source overlay：

```bash
SGLANG_BUILD_RUST_EXTS=none \
UV_PROJECT_ENVIRONMENT=/home/tiger/venvs/deepspec-hedge-dflash \
uv sync --frozen --no-install-project --link-mode copy

SGLANG_BUILD_RUST_EXTS=none \
uv pip install \
  --python /home/tiger/venvs/deepspec-hedge-dflash/bin/python \
  --no-deps --editable \
  /home/tiger/src/deepspec-sglang-hedge-dflash/python
```

CPU-only contract probe 与测试：

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

worker metadata probe（保持 keepalive）：

```bash
mlx worker login 4099543 -- bash \
  /mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dflash/scripts/dflash_d1b_environment_probe.sh \
  4099543
```

## 一手资料

- Primary checkpoint 的固定 revision
  [config.json](https://huggingface.co/RedHatAI/DeepSeek-V4-Flash-speculator.dflash/blob/e44fc94ceb1e7ed45550d15e782aeadd08050483/config.json)、
  [config.py](https://huggingface.co/RedHatAI/DeepSeek-V4-Flash-speculator.dflash/blob/e44fc94ceb1e7ed45550d15e782aeadd08050483/config.py)、
  [README](https://huggingface.co/RedHatAI/DeepSeek-V4-Flash-speculator.dflash/blob/e44fc94ceb1e7ed45550d15e782aeadd08050483/README.md)。
- DFlash paper：[arXiv:2602.06036](https://arxiv.org/abs/2602.06036)。
- vLLM Project Speculators 固定审计 commit
  `aee3cc9b4ed151ae9ec79befee851757c62b3be9` 的
  [DFlash config](https://github.com/vllm-project/speculators/blob/aee3cc9b4ed151ae9ec79befee851757c62b3be9/src/speculators/models/dflash/config.py)
  与
  [core](https://github.com/vllm-project/speculators/blob/aee3cc9b4ed151ae9ec79befee851757c62b3be9/src/speculators/models/dflash/core.py)。
- SGLang 固定 commit 的
  [DFlash parser](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/dflash_utils.py)、
  [DFlash model](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/dflash.py)、
  [DFlash worker](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/dflash_worker_v2.py)
  与
  [DeepSeek-V4 model](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/deepseek_v4.py)。

其中 `target_hidden_size=null` 时按 `hc_mult×hidden_size` 解释为 `16384` 是本阶段依据
provider README、config 与实际 weight shape 作出的受约束推断；generic Speculators
实现本身不能替代 primary DeepSeek-V4 checkpoint header。
