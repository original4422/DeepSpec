# DFlash Phase D2 handoff

结论：`D2 PASS`。固定 SGLang `v0.5.16` base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` 上的最小 native
DeepSeek-V4 + DFlash 接入已经完成；真实 primary JSON、partial safetensors header、
production model registry/loader、DeepSeek-V4 mHC capture、draft-vocab candidate
映射及 OpenAI output token IDs 均有 CPU/meta 可运行证据。最终测试为
`186 PASS / 1 CUDA-only SKIP`；`compileall`、HEAD-to-working-tree 全量
whitespace audit、新文件全文 audit 和完整 patch reverse-apply/error-all check
均通过。

本 phase 没有启动 GPU 或大模型，没有暂停/停止 worker `4099543` 的 keepalive，
没有引入 HEDGE，没有触碰 D1A acquisition 进程或文件，没有进入 D3，也没有
stage/commit/push。

## 退出门禁

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| native commit 唯一 parent 为固定 base，source worktree clean | PASS | `dflash_d2_source_identity.json`、main acceptance |
| 真实 primary JSON 不依赖 remote code 即解析为 `DFlashConfig` | PASS | production test + weight mapping report |
| architecture `DFlashDraftModel` 由 production registry 解析 | PASS | `dflash_d2_weight_mapping_report.json` |
| aux 顺序 `[3,13,23,32,42]` 且 DeepSeek-V4 不做 `+1` | PASS | `dflash_d2_shape_trace.json` |
| 每层 `[N,4,4096].flatten(1) -> [N,16384]`，五层 concat 为 `81920` | PASS | production tensor test + shape trace |
| `fc.weight [4096,81920]` 与 production state 精确匹配 | PASS | real-header meta load probe |
| draft vocab header/state：embed、lm_head、`t2d`、`d2t` | PASS | real-header meta load probe |
| Q/K/V header 可堆叠到 fused QKV，O projection 精确匹配 | PASS | weight mapping report |
| block 8 = current token + 七个已映射 target-vocab draft tokens | PASS | production worker helper test + shape trace |
| OpenAI `choices[0].meta_info.output_token_ids` 与 completion count 一致 | PASS | full `test_serving_chat.py` 82/82 |
| existing DFlash CPU regressions | PASS | 6 PASS；1 个 CUDA kernel test 按预期 skip |
| changed production/test source 中无 HEDGE 接入 | PASS | case-insensitive changed-file scan 0 hits |
| 新文件 EOF/whitespace 全文审计 | PASS | 两个新文件分别执行 `git diff --no-index --check /dev/null`，输出为空 |
| source patch 内容与 native commit 一致 | PASS | commit `7245c3d607a1…` 相对唯一 fixed-base parent |
| patch artifact 自身无 trailing whitespace | PASS | added-file `git diff --no-index --check` 输出为空 |
| source patch 完整且可逆校验 | PASS | fixed base apply + native commit reverse apply，均 `--whitespace=error-all` |
| TP=8 real checkpoint load / API smoke | WAIT（D3） | D2 明确禁止启动大模型 |
| D1A draft / shared target completion marker | WAIT（由主 Agent 验收） | D2 未读写 acquisition staging |
| FAIL 项 | 无 | — |

Artifact 根目录：
`docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d2/`。

## Production integration

SGLang checkout：
`/home/tiger/src/deepspec-sglang-hedge-dflash`。主 Agent 已将验收后的九个 source
files 提交为 `7245c3d607a1eadc26582bb78ebd603a70c22fa7`，其唯一 parent 是固定 base
`fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`；当前 source worktree clean。本
executor 没有 commit/push。

1. `python/sglang/srt/configs/dflash.py`
   - 新增本地 `DFlashConfig`，把 primary
     `transformer_layer_config` 规范化为 typed nested/text config；
   - 保留并校验 aux layer IDs、block size、draft/target vocab、mask token、
     sliding-window 和 target feature width。
2. `python/sglang/srt/utils/hf_transformers/config.py`
   - 在 `AutoConfig` 前识别缺少 top-level `model_type` 的 Speculators
     DFlash JSON；
   - 不启用 checkpoint remote code。
3. `python/sglang/srt/speculative/dflash_utils.py`
   - parser 接入 `transformer_layer_config`、
     `aux_hidden_state_layer_ids` 与 top-level `mask_token_id`。
4. `python/sglang/srt/models/deepseek_v4.py`
   - 增加 DFlash 专用 after-layer capture hook；
   - layer IDs 原样使用；
   - 将 mHC streams 按 stream-major 内存顺序 `.flatten(1)`，DSpark 原有
     `mean(dim=1)` 路径保持不变，并禁止两种 capture 同时启用。
5. `python/sglang/srt/models/dflash.py`
   - 使用 nested transformer config 构造 draft layers；
   - projection 输入改为
     `5 × (hc_mult 4 × hidden 4096) = 81920`；
   - 接入 checkpoint 自带 target-vocab embedding、32000 draft-vocab head、
     `t2d`/`d2t` buffers；
   - loader 对每个 direct weight/buffer 做精确 shape gate，并保留 Q/K/V 和
     gate/up stacked loader。
6. `python/sglang/srt/speculative/dflash_worker_v2.py`
   - primary checkpoint 使用自身 embedding/head；
   - greedy draft IDs 经 `d2t` 转到 target token space 后才写入 verify
     candidates；
   - 第 0 列保持 current token，`[:,1:]` 恰为七个 candidates。
7. `python/sglang/srt/entrypoints/openai/serving_chat.py`
   - 非流式 `return_meta_info` 响应复制并返回 `output_token_ids`；
   - ID 数量与 `completion_tokens` 不一致时 fail closed；
   - 不原地修改 engine 返回的 `meta_info`。

Production-facing tests：

- `test/registered/unit/spec/test_dflash_deepseek_v4_primary.py`
- `test/registered/unit/entrypoints/openai/test_serving_chat.py`

## Checkpoint 与 tensor 证据

证据绑定 primary draft：

- repo：`RedHatAI/DeepSeek-V4-Flash-speculator.dflash`
- revision：`e44fc94ceb1e7ed45550d15e782aeadd08050483`
- safetensors header SHA-256：
  `a920047d53810be3c990ba1a8765fcbbee2bedc8821853990d26042a1f14ef35`
- header tensors：62

真实 header 到 production TP=1 meta state 的关键映射：

| Checkpoint | Shape | Production state | 结果 |
| --- | --- | --- | --- |
| `fc.weight` | `[4096,81920]` | `fc.weight` | exact |
| `embed_tokens.weight` | `[129280,4096]` | same | exact |
| `lm_head.weight` | `[32000,4096]` | same | exact |
| `t2d` | `[129280] BOOL` | buffer `t2d` | exact |
| `d2t` | `[32000] I64` | buffer `d2t` | exact |
| Q/K/V | `[16384/256/256,4096]` | fused QKV `[16896,4096]` | stacked exact |
| O projection | `[4096,16384]` | same | exact |

Meta probe 实际调用 production `DFlashDraftModel.load_weights`，不是只比较手写
shape。完整明细见 `dflash_d2_weight_mapping_report.json`。

mHC trace 使用可识别 sentinel，证明每个 `[2,4,4096]` tensor 的四个 stream 依次
展开为 `[2,16384]`；五个 aux layer 以 config 顺序拼接后为 `[2,81920]`。
candidate trace 证明两个 block 都是 `[current, mapped draft × 7]`。详见
`dflash_d2_shape_trace.json`。

## Tests

最终 evidence collector 以
`CUDA_VISIBLE_DEVICES=999`、固定 formal Python/CUDA_HOME、
`PYTHONNOUSERSITE=1` 逐文件执行：

| Suite | 结果 |
| --- | --- |
| primary production contract | 6/6 PASS |
| existing DFlash overlap/host-sync | 6 PASS / 1 CUDA-only SKIP |
| full OpenAI serving chat | 82/82 PASS |
| model config parser registry | 3/3 PASS |
| model config | 1/1 PASS |
| speculative registry | 28/28 PASS |
| HF transformers utilities | 60/60 PASS |
| 合计 | 186 PASS / 1 SKIP |

同时通过：

```text
python -m compileall -q <9 changed Python files>
git diff --check HEAD -- <9 changed Python files>
git diff --no-index --check /dev/null python/sglang/srt/configs/dflash.py
git diff --no-index --check /dev/null test/registered/unit/spec/test_dflash_deepseek_v4_primary.py
git diff --no-index --check /dev/null dflash_d2_sglang.patch
git -C <fixed-base-worktree> apply --check --whitespace=error-all dflash_d2_sglang.patch
git -C <native-commit-worktree> apply --check --reverse --whitespace=error-all dflash_d2_sglang.patch
sha256sum -c dflash_d2_artifact_manifest.sha256
```

主线程首次把九个 D2 source files 显式加入 index 后，
`git diff --cached --check` 补充发现
`python/sglang/srt/configs/dflash.py:96: new blank line at EOF`。本 executor 只删除
该多余空白行并保留单个终止换行，没有改 production 逻辑。原来的 unstaged
`git diff --check` 确实没有覆盖当时 untracked 的新文件；最终门禁因此改为
HEAD-to-working-tree 全量检查、对每个新文件的 `--no-index --check`，以及完整 patch
的 `--whitespace=error-all`。三者均 PASS，并已写入 test summary/log/source identity。
按任务边界本 executor 当时未更新 index；主 Agent 随后重新 stage 修正版、通过
cached check，并形成上述 native integration commit。

主 Agent 随后的 DeepSpec staged audit 又发现一个纯证据载体问题：普通 unified diff
用单个空格表示合法的空白 context line；当 `dflash_d2_sglang.patch` 自身作为新增文件
提交时，这些行会被外层 `git diff --cached --check` 视作 trailing whitespace。
Production source 和 commit 未变化。最终 patch 从
`7245c3d607a1eadc26582bb78ebd603a70c22fa7` 重新导出，并只把“恰好一个 context
prefix 空格”的空白 context line 规范化为空行；Git 接受这种等价编码。直接使用
`--unified=0` 的 probe 未作为最终格式，因为它需要 `--unidiff-zero`，且
`--whitespace=error-all` 会把零上下文 hunk 边界处合法的新增空行判断为
blank-at-EOF。

最终 patch SHA-256 为
`1cb80d832a751952e6a1430ce94e0331f39b44fa2dc94167478e15e5120599cf`。
它作为 added file 的 whitespace check 输出为空；在 fixed base 上 forward apply、
在 native commit 上 reverse apply 均以 `--whitespace=error-all` PASS；base 实际
apply 后的 tree 为 `ed4dd52d628036ba83718d6c2a895b6581770660`，与 native commit
tree 精确一致。该补修没有重跑 186 tests，因为 production tree/commit 未改变；详情
已写入 source identity 和 test summary。

首次 broader suite 的组合命令误用了
`python -m unittest test.registered...`，产生四个
`ModuleNotFoundError: No module named 'test.registered'`。这次尝试没有导入或执行
产品代码，分类为 orchestration-only command-path error；同四个文件随后逐文件运行
并分别 `3/3 + 1/1 + 28/28 + 60/60 PASS`。该 fingerprint 和替代命令已记录在
`dflash_d2_test_summary.json`。

CPU-only warnings（Triton unsupported、AWQ/GGUF device support、可选 vLLM
module 缺失、临时 config 无 generation config）均未执行对应 GPU/可选路径，不是
测试失败。

## TDD attempts 与单变量归因

1. Primary config 没有 top-level `model_type`，原 `AutoConfig` 无法解析；只加入
   DFlash schema adapter/parser 后 production ModelConfig 通过。
2. DeepSeek-V4 只有 DSpark capture，并会 `mean(dim=1)`；只加入独立 DFlash
   after-layer flatten seam 后 `[N,81920]` contract 通过。
3. 原 DFlash projection 假设每个 aux feature 宽 4096，不能加载
   `[4096,81920]`；只改为显式 target feature width 后通过。
4. 原 worker 只借用 target vocab，没有加载/映射 primary draft vocab；只接入
   checkpoint embed/head 与 `d2t` candidate mapping 后 block8/7 测试通过。
5. OpenAI `meta_info` 缺少 output token IDs；只在 non-stream response builder
   增加 copy/count gate 后 full serving suite 通过。

测试 fixture 的 CPU dtype、runtime parallel context 和缺少 vLLM RoPE op 分别通过
float fixture、runtime override 与 meta-only dummy RoPE 隔离；这些是测试环境限制，
没有改变 production tensor contract。

## D3 handoff 与限制

D2 只证明 config、loader、capture、candidate 和 API schema 的 CPU/meta contract。
D3 仍必须在主 Agent 确认 draft/target `.complete`、旧任务自然退出和 lane gate 后：

1. 紧邻地暂停项目 keepalive，并证明八卡 CUDA context 全部退出；
2. TP=8 真实加载 primary checkpoint，核对 8 rank、实际显存与 QKV shard load；
3. 核对五层 mHC aux 的 live shape、draft-vocab `d2t` 映射与 block8；
4. 发一个短 OpenAI request，验证非空响应及
   `len(output_token_ids) == completion_tokens`；
5. 定向清理自有 PGID，恢复 keepalive 并重过逐卡 gate。

Primary embed/head 当前在每个 TP rank 上复制；这保证每个 rank 具有完整
draft-vocab logits，CUDA graph sampler 在 TP>1 因无 shard metadata 会选择已有 eager
fallback。D3 需要验证实际显存与正确性；这不是 D2 的性能结论，也没有 TPS 门槛。

HEDGE 必须等 D4 复用 DSpark 发布的 pure-core commit；D2 source scan 明确为零
HEDGE 接入，不能据此声称 `B=0` 或 `B>0` 已实现。

## Artifact 清单

- `dflash_d2_sglang.patch`
- `dflash_d2_source_diff_stat.txt`
- `dflash_d2_source_identity.json`
- `dflash_d2_test_log.txt`
- `dflash_d2_test_summary.json`
- `dflash_d2_weight_mapping_report.json`
- `dflash_d2_shape_trace.json`
- `dflash_d2_reproduction_commands.txt`
- `dflash_d2_artifact_manifest.sha256`

复现/重新封存脚本：
`scripts/dflash_d2_collect_evidence.py`。
