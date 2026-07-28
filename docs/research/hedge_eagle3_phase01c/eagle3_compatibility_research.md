# DeepSeek-V4-Flash EAGLE3.1 × SGLang v0.5.16 兼容性研究

> Phase：01C（只读研究、最小适配设计与无 GPU 合成契约）
>
> 状态：PASS；native/full-model 兼容性尚未在 TP=8 上验证
>
> 研究日期：2026-07-29

本文是 Phase 01C 研究事实的唯一权威记录。实现边界见
[`integration_seams.md`](integration_seams.md)，阶段交接见
[`phase-01c-handoff.md`](phase-01c-handoff.md)，可机读契约见
[`aux_state_contract.json`](aux_state_contract.json)。

## 1. 范围、方法与证据等级

本阶段完整读取固定 draft model card/config、固定 target config、固定 SGLang
EAGLE3/DeepSeek-V4/model-runner/verify 源码，并把固定 draft checkpoint 的 PyTorch ZIP
metadata 做了只读解析。没有运行 vLLM、SGLang 服务、模型或 GPU，也没有复制其他引擎
scheduler。

证据等级：

- **A — 固定一手 artifact**：固定 revision 的模型卡、config 或 checkpoint bytes
  直接给出的事实；
- **B — 固定源码**：固定 commit 的控制流、接口或 tensor 操作直接给出的事实；
- **C — 待运行验证**：由 A/B 推出的集成预期，必须在 Phase 02 TP=8 live attempt
  中证伪或确认。

固定身份：

| 对象 | 固定身份 | 只读来源 |
| --- | --- | --- |
| target | `deepseek-ai/DeepSeek-V4-Flash@60d8d70770c6776ff598c94bb586a859a38244f1` | [config](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/60d8d70770c6776ff598c94bb586a859a38244f1/config.json#L1-L64) |
| draft | `SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1@4c68aa4689d59cb1064f20abec7708174ee4613d` | [model card](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/README.md#L15-L41)、[config](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/config.json#L1-L45)、[serving guide](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/SERVING.md#L1-L68) |
| 正式 engine source | SGLang `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`（`v0.5.16`） | [GitHub tree](https://github.com/sgl-project/sglang/tree/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1) |
| 其他引擎参考 | vLLM `0b3ba88f165976e77ca5e6a7a3f5bba4562b80af`（`v0.22.0`） | [GitHub tree](https://github.com/vllm-project/vllm/tree/0b3ba88f165976e77ca5e6a7a3f5bba4562b80af) |

本地只读源码核对：

- SGLang：
  `/home/tiger/src/deepspec-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，
  `HEAD=fdebc938...`，detached 且 clean；
- vLLM 稀疏只读 checkout：
  `/tmp/hedge-eagle3-phase01c-vllm.tEF8ZD`，
  `HEAD=0b3ba88f...`。它仅用于核对公开接口，不是正式 engine。

## 2. 固定模型与 checkpoint 事实

### 2.1 Target

Target config 直接固定了：

- architecture `DeepseekV4ForCausalLM`；
- `num_hidden_layers=43`、`hidden_size=4096`、`hc_mult=4`；
- `torch_dtype=bfloat16`、target `vocab_size=129280`；
- routed experts 为 `expert_dtype=fp4`。

其中本阶段 aux 契约直接依赖 `hc_mult=4` 与 `hidden_size=4096`。[证据 A：
target config 第 9–15 行](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/60d8d70770c6776ff598c94bb586a859a38244f1/config.json#L9-L15)

### 2.2 Draft config

固定 draft config 直接固定了：

- architecture `LlamaForCausalLMEagle3`，一层 Llama draft body；
- logical aux layer IDs `[1,21,40]`，`use_aux_hidden_state=true`；
- `dtype=bfloat16`、`target_hidden_size=4096`、draft hidden size `4096`；
- `num_aux_hidden_states=3`、`fc_norm=true`、`norm_output=true`；
- target vocab `129280`、draft vocab `32000`。

[证据 A：draft config](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/config.json#L1-L45)

模型作者还明确给出 logical taps `[1,21,40]`、capture indices `[2,22,41]`、4 个
hyper-connection copies 上取 mean，以及协议侧 3 个 speculative tokens。[证据 A：
architecture 表](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/README.md#L29-L39)、
[启动示例](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/README.md#L99-L124)

### 2.3 Draft checkpoint tensor inventory

对固定 revision 的
[`pytorch_model.bin`](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/resolve/4c68aa4689d59cb1064f20abec7708174ee4613d/pytorch_model.bin)
执行 HTTP HEAD 与 ZIP central-directory/data range 只读解析；没有下载完整 checkpoint。
Provider 返回对象大小 `1,858,526,016` bytes，linked ETag
`91953b33d978fa4530f65967d17b980cad2f50b997512b42d051c4da52414d41`。
`data.pkl` 中共有 19 个 state entries：

| 名称 | dtype | shape |
| --- | --- | --- |
| `t2d` | bool | `[129280]` |
| `d2t` | int64 | `[32000]` |
| `embed_tokens.weight` | BF16 | `[129280,4096]` |
| `midlayer.self_attn.q_proj.weight` | BF16 | `[4096,8192]` |
| `midlayer.self_attn.k_proj.weight` | BF16 | `[1024,8192]` |
| `midlayer.self_attn.v_proj.weight` | BF16 | `[1024,8192]` |
| `midlayer.self_attn.o_proj.weight` | BF16 | `[4096,4096]` |
| `midlayer.mlp.gate_proj.weight` | BF16 | `[12288,4096]` |
| `midlayer.mlp.up_proj.weight` | BF16 | `[12288,4096]` |
| `midlayer.mlp.down_proj.weight` | BF16 | `[4096,12288]` |
| `midlayer.hidden_norm.weight` | BF16 | `[4096]` |
| `midlayer.input_layernorm.weight` | BF16 | `[4096]` |
| `midlayer.post_attention_layernorm.weight` | BF16 | `[4096]` |
| `fc.weight` | BF16 | `[4096,12288]` |
| `fc_norm.0.weight` | BF16 | `[4096]` |
| `fc_norm.1.weight` | BF16 | `[4096]` |
| `fc_norm.2.weight` | BF16 | `[4096]` |
| `norm.weight` | BF16 | `[4096]` |
| `lm_head.weight` | BF16 | `[32000,4096]` |

对两个小 mapping storage 的 range 解析还得到：

- `t2d` 恰有 32,000 个 `true`；
- SGLang loader 所用公式是
  `target_id = draft_id + d2t[draft_id]`；
- 32,000 个映射 target IDs 全部唯一，范围 `[3,128825]`；
- 映射结果集合与 `t2d=true` 的 target index 集合完全相等。

这证明 checkpoint 的 32k hot-vocab mapping 自洽，但不替代 Phase 01A 的完整 provider
identity、manifest、实体发布与 Phase 02 的真实权重加载。[证据 A]

固定 SGLang 已有对应 loader：把 `midlayer` 重写到 `layers.0`，把 q/k/v 和
gate/up 装入 stacked parameters，按上述公式构造 `hot_token_id`，忽略冗余 `t2d`。
[证据 B：SGLang draft loader](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/llama_eagle3.py#L297-L353)

## 3. Aux state 的精确契约

### 3.1 Layer ID 与 `+1` hook

语义必须区分两套编号：

1. checkpoint/config 的 `[1,21,40]` 是 **output-of-layer logical IDs**；
2. runner/model hook 的 `[2,22,41]` 表示“第 `k` 层入口携带第 `k-1` 层的完成输出”。

固定 SGLang 的普通 Llama EAGLE3 setter 也明确执行 `val + 1`，并解释第 `i` 层接收
第 `i-1` 层输出。[证据 B：
`llama.py`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/llama.py#L808-L820)

DeepSeek-V4 当前只有 DSpark capture。其 eager loop 是“先执行 layer `i`，再以
`i in dspark_layers_to_capture` 判断并保存完成状态”。因此 Phase 02 **不能**把
`[2,22,41]` 直接塞进现有 DSpark after-layer 条件；那会得到 logical
`[2,22,41]` 的输出而产生 off-by-one。EAGLE3 必须有独立状态和以下任一等价实现：

- after-layer：执行完 `i` 后，以 `(i + 1) in eagle3_hook_ids` 判断；或
- before-layer：进入 hook `k` 前捕获已经完成的 `k-1` 输出。

无论采用哪一种，接口对外仍记录 hook `[2,22,41]`，实际值必须对应 logical
`[1,21,40]` 的完成输出。[证据 B：
DeepSeek-V4 forward loop](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/deepseek_v4.py#L2315-L2347)]

### 3.2 mHC reduction 与 layout

每个被选层在 `hc_head` 前的 completed mHC tensor 是：

```text
[num_tokens, hc_mult=4, hidden_size=4096] BF16
```

每层只在 stream 维做 arithmetic mean：

```text
[N,4,4096] --mean(dim=1)--> [N,4096]
```

然后严格按 logical `[1,21,40]` 排序：

```text
结构化契约: [N,3,4096]
runner 契约: [N,12288] = concat(layer1, layer21, layer40, dim=-1)
```

禁止直接 flatten 4 streams、选单一 stream、打乱 tap 顺序或复用 DSpark capture
layout。固定 SGLang 的 `LogitsProcessor` 已会把 aux list 在最后一维拼接，所以 target
模块交给它的最自然形式是三个 `[N,4096]` tensor。[证据 B：
DeepSeek-V4 现有 4-stream mean](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/deepseek_v4.py#L2337-L2344)、
[`LogitsProcessor`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/layers/logits_processor.py#L630-L681)]

Draft 端将 12,288 维输入切成三个 4,096 维 chunk，分别经过 checkpoint 的三个
`fc_norm`，再由 `[4096,12288]` 的 `fc.weight` 投影回 4,096 维。draft recurrent
hidden state 仍是 `[N,4096]`，不能与 target aux input width 混淆。[证据 A/B：
draft checkpoint inventory；SGLang
`llama_eagle3.py`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/llama_eagle3.py#L143-L243)；
input-width helper](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/eagle_utils.py#L434-L482)

### 3.3 dtype、device 与 TP ownership

固定 config 与 checkpoint 都要求 BF16 aux/draft hidden。CPU 合成测试已经证明 BF16
输入在 `mean(dim=1)` 后保持 BF16，并得到精确的 `[N,3,4096]` /
`[N,12288]` layout。

TP ownership 只能给出 **C 级预期**：

- 固定 SGLang 的普通 TP vocabulary embedding 会 all-reduce 得到各 TP rank 的完整
  hidden embedding；
- draft `fc` 是每 rank 的普通 `torch.nn.Linear`，因此需要每 rank 本地完整
  `[N,12288]`；
- 由此预期 target aux 在每个 TP rank 本地保持 replicated，不需要 hidden-state
  gather。

[证据 B：
`VocabParallelEmbedding.forward`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/layers/vocab_parallel_embedding.py#L562-L575)、
draft `fc`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/llama_eagle3.py#L143-L173)

源码没有为 DeepSeek-V4 EAGLE3 TP=8 给出直接证明。Phase 02 必须在 rank 0–7 断言：

- local raw `[N,4,4096]`、structured `[N,3,4096]`、runner `[N,12288]`；
- BF16 且位于各 rank 的 local CUDA device；
- 没有为 aux 新增 gather/cross-rank concat；
- 小型 checksum 在记录的 BF16 容差内一致。

不能用隐式 gather 掩盖 local shape 错误。

## 4. Prefill/decode 生命周期

固定 SGLang 已有 EAGLE worker 生命周期，可复用而不复制 scheduler：

1. **Prefill target**：target 使用 `CaptureHiddenMode.FULL`，输出所有需要位置的
   12,288-wide aux；
2. **Prefill draft-extend**：target token + aux 放入 `EagleDraftExtendInput`，draft
   使用 `CaptureHiddenMode.LAST` 留下每个 request 的 recurrent seed；
3. **Draft decode**：top-k=1 时连续执行三步 draft chain；
4. **Target verify**：对内部 verify window 使用 target
   `CaptureHiddenMode.FULL`，同时产生 target logits 与下一轮 aux；
5. **Decode draft-extend**：用 `accept_lens` 选择每 request 最后接受位置，把该位置
   的 target token/aux 和 draft recurrent state推进到下一轮。

[证据 B：
prefill draft extend](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/eagle_worker_v2.py#L742-L854)、
decode draft extend](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/eagle_worker_v2.py#L869-L1018)、
target verify capture](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/eagle_utils.py#L485-L566)

Request/batch lifecycle 属于 runner；target 只负责产生 aux，draft 只负责消费 target
token/aux 并推进自己的 hidden/KV，verify 只负责严格接受、`accept_index` 和
`accept_lens`。

## 5. Proposal width：协议 3 与内部 4

本路线 proposal width 固定为 **3 个 draft/speculative tokens**，对应：

```text
speculative_num_steps = 3
speculative_eagle_topk = 1
```

SGLang top-k=1 内部强制：

```text
speculative_num_draft_tokens = speculative_num_steps + 1 = 4
```

内部宽度 4 是 verify tree/window 的 row width，包含 root/bonus/target slot 加三个
draft positions；它不是“4-token proposal”。文档、resolved config 和 trace 都必须
分别标注这两个语义。[证据 A：
模型作者示例的 3 tokens](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/README.md#L99-L124)；
证据 B：
SGLang 参数 hook](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/arg_groups/speculative_hook.py#L624-L632)、
worker invariant](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/speculative/eagle_worker_v2.py#L254-L286)

## 6. 固定 SGLang 的已有能力与实际缺口

### 6.1 已有且可复用

- model registry 会扫描 `EntryClass`；`LlamaForCausalLMEagle3` 已以
  `EntryClass` 注册。[证据 B：
  registry](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/registry.py#L94-L131)、
  draft entry](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/llama_eagle3.py#L246-L359)
- draft loader、3×RMSNorm、12,288→4,096 projection、32k hot-vocab mapping 已存在；
- model runner 已能从 draft config 解析 aux logical IDs；
- `LogitsProcessor` 已能拼接 aux list；
- worker 已有 target embedding share、draft prefill/decode、target verify 和 accept
  bookkeeping；
- DeepSeek-V4 已有 `get_embed_and_head`，可供 draft runner 分享 target embedding。

### 6.2 启动阻断的确定顺序

固定 source 的实际阻断不是一个抽象的“不支持”，而是按控制流有序：

1. **首个阻断：server args guard。** DeepSeek-V4 post-process 只允许 `EAGLE` 和
   `DSPARK`；传 `EAGLE3` 会在模型构造前 assertion。
   [证据 B：
   `deepseek_v4_hook.py`](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/arg_groups/deepseek_v4_hook.py#L55-L63)
2. **第二个阻断：capture setter 缺失。** 放开 guard 后，attention backend setup
   会无条件调用 `model.set_eagle3_layers_to_capture(...)`；固定
   `DeepseekV4ForCausalLM` 只有 `set_dspark_layers_to_capture`，所以会在 attention
   backend 初始化前 `AttributeError`。
   [证据 B：
   setup](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/model_executor/model_runner_components/attention_backend_setup.py#L39-L65)、
   V4 DSpark-only setter](https://github.com/sgl-project/sglang/blob/fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1/python/sglang/srt/models/deepseek_v4.py#L2449-L2457)
3. **第三层缺口：V4 EAGLE3 capture semantics。** 即使补 setter，仍须实现独立的
   layer-hook mapping、completed mHC 4-stream mean、aux list 输出和 TP runtime
   assertions，不能把 DSpark setter 改名。

模型作者也明确说明本 release 没有 SGLang 支持，其 serving guide 表明另一个 engine
同样需要 DeepSeek-V4 target aux-capture overlay。[证据 A：
limitations](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/README.md#L128-L137)、
[serving gap](https://huggingface.co/SyzygyResearch/DeepSeek-V4-Flash-EAGLE3.1/blob/4c68aa4689d59cb1064f20abec7708174ee4613d/SERVING.md#L1-L16)

### 6.3 其他引擎参考的边界

固定 vLLM v0.22.0 的公开 `llama_eagle3.py` 佐证了三个独立 4,096 RMSNorm、
12,288→4,096 replicated projection，以及将 32k draft logits scatter 回 target
vocab 的契约。[证据 B：
aux projection](https://github.com/vllm-project/vllm/blob/0b3ba88f165976e77ca5e6a7a3f5bba4562b80af/vllm/model_executor/models/llama_eagle3.py#L178-L219)、
[mapping/combine](https://github.com/vllm-project/vllm/blob/0b3ba88f165976e77ca5e6a7a3f5bba4562b80af/vllm/model_executor/models/llama_eagle3.py#L336-L464)

但 stock vLLM 的 DeepSeek-V4 也没有作者所需的专属 target overlay；模型作者链接的
overlay 仓库在研究时不可公开读取。因此本文不把 overlay 内部实现当作证据，也不复制
其 scheduler/engine。正式结果仍只能来自固定 SGLang。

## 7. 合成契约测试

实现：

- `deepspec/hedge_eagle3_phase01c/aux_contract.py`
- `tests/test_hedge_eagle3_phase01c_aux_contract.py`

测试给三个 logical tap 和四个 mHC streams 注入可区分 BF16 值，并用逆序 mapping
输入，证明输出顺序不依赖容器插入顺序。断言：

- logical `[1,21,40]` 对应 hook `[2,22,41]`；
- 四流 `0,2,4,6` 的 mean contribution 为 `3`；
- structured shape 精确为 `[2,3,4096]`；
- runner flattened shape 精确为 `[2,12288]`，三个 chunk 顺序正确；
- dtype 仍为 BF16；
- 缺 hook 和错误 stream count 会 fail closed。

命令：

```bash
python -m unittest discover -s tests \
  -p 'test_hedge_eagle3_phase01c_aux_contract.py' -v
```

结果：3 tests，全部 PASS；最终以 `PYTHONDONTWRITEBYTECODE=1` 在
Python 3.11.2 / PyTorch 2.7.1 CPU 环境复跑，`OK`。CUDA 不可用且未使用。

该测试证明纯 tensor/layout 契约，不声称已证明真实 target layer 数值或 TP ownership；
后两项仍由 Phase 02 runtime assertions 验证。

## 8. 四层责任与可证伪风险假设

四层责任：

| 层 | 唯一责任 | 不应承担 |
| --- | --- | --- |
| target | 捕获 logical target outputs，完成 4-stream mean，输出有序 aux | draft projection、accept 决策、risk budget |
| draft | 载入 checkpoint/mapping，以 target token + 12,288 aux 生成三步 chain | target capture、严格验证 |
| runner | 维护 prefill/decode/request lifecycle 与 tensor 传递 | 改写 aux 数学或 acceptance |
| verify | target logits 上的严格接受、`accept_index`、`accept_lens` | target/draft 权重或 capture |

Phase 02 native bring-up 的 5 个可证伪假设：

1. **Guard 假设**：唯一最早启动错误是 DeepSeek-V4 guard 拒绝 `EAGLE3`。最小放开
   后 resolved config 能继续到 model/attention setup 即证实；出现更早错误则证伪。
2. **Capture 假设**：补独立 setter 与上述 completed-state mapping 后，每 rank 可稳定
   产生 `[N,4,4096] → [N,3,4096] → [N,12288]` BF16。任一 rank shape/dtype/device、
   hook 值或 checksum 不符即证伪。
3. **Loader 假设**：固定 SGLang 已有 loader 足以完整加载 19-entry checkpoint，并
   构造 32,000 个唯一 hot token IDs。missing/unexpected tensor、mapping OOB 或
   architecture mismatch 即证伪。
4. **Lifecycle/width 假设**：现有 worker 能在 prefill FULL/draft LAST 与 verify
   FULL/draft-extend 间传递 12,288 aux，并产生协议 3-token chain（内部 width 4）。
   prefill 成功而 decode shape/lifecycle 失败，或 trace 显示协议 proposal 非 3，即证伪。
5. **Strict verify 假设**：现有 strict greedy verify 能在 target-vocab IDs 上返回合法
   `accept_index/accept_lens` 并推进至少 3 个顺序请求。OOB、错误 bonus/commit length
   或请求无法终态即证伪。

HEDGE 不属于这些 native 假设；只有 native 成功后，Phase 03 才在 strict rejection
barrier 接入 HEDGE adapter。

## 9. 最小 native smoke 信号与未决项

Phase 02 至少保存以下信号：

- resolved config：`algorithm=EAGLE3`、`num_steps=3`、`topk=1`、内部
  `num_draft_tokens=4`，并注明二者语义；
- 启动日志：target architecture、draft `LlamaForCausalLMEagle3`、rank 0–7；
- draft loader：19-entry 对应参数无意外 missing/unexpected，32k mapping 无 OOB；
- 每 rank aux hook/logical IDs、raw/structured/flattened shape、BF16、local device；
- 至少一条 prefill FULL→draft LAST 与 verify FULL→draft extend trace；
- 至少 3 条顺序请求达到终态，trace 同时显示 draft proposal 与 target strict verify；
- `accept_index`、`accept_lens`、protocol draft count=3；
- 八卡模型显存/请求期利用率，无未处理 CUDA/NCCL/rank crash。

未决项均明确标为 C 级，不应在 Phase 01C 写成已证实：

- TP=8 上 DeepSeek-V4 layer output 是否逐 rank 数值一致；
- V4 fused mHC 路径下最小 capture 实现的准确位置与额外 eager/TBO 限制；
- fixed checkpoint 在最终 01A 实体路径上的真实全量加载；
- prefill/decode 的真实 batch padding、graph-disabled shape；
- native strict verify 的 token parity 与接受 trace；
- 模型作者 overlay 的内部 DeepSeek-V4 实现（公开来源不可得且正式路径不依赖它）。

结论：固定 SGLang 已具备 draft architecture/loader、runner 和 strict verify 主体，
缺口集中在 **DeepSeek-V4 EAGLE3 guard + 独立 target aux capture**。Phase 02 应按
guard → setter/interface → exact capture/layout → loader → lifecycle/verify 的顺序做
最小单变量 bring-up。
