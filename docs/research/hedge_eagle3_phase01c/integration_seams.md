# Phase 02 implementation seams

本文只给实现 handoff，不重复研究事实。固定身份、证据、张量契约、生命周期和风险假设
以 [`eagle3_compatibility_research.md`](eagle3_compatibility_research.md) 为准；机器
可读 shape/layout 以 [`aux_state_contract.json`](aux_state_contract.json) 为准。

设计词汇遵循 `codebase-design`：**module** 隐藏实现复杂度，**interface** 是调用方和
测试共同依赖的契约，**seam** 是责任切换的位置，只有存在多个策略实现时才使用
**adapter**。

## 1. Module 与责任

| Module | Interface | 隐藏的复杂度 | 责任边界 |
| --- | --- | --- | --- |
| DeepSeek-V4 target | `set_eagle3_layers_to_capture(logical_ids)`；target forward 返回 aux list | logical→hook `+1`、fused/non-fused completed state、4-stream mean、tap 顺序 | 不知道 draft `fc`、proposal 或 acceptance |
| EAGLE3 draft | 现有 `forward_batch.spec_info.hidden_states: [N,12288]` 与 target token | 三个 `fc_norm`、12,288→4,096 `fc`、draft KV/recurrent state、32k↔target vocab mapping | 不知道 target mHC 或 risk budget |
| EAGLE worker/runner | 现有 `EagleDraftExtendInput` / `EagleDraftInput` | prefill/decode selection、FULL/LAST capture、request state 生命周期 | 不计算 mHC mean，不决定 strict/HEDGE 接受 |
| Verify | 现有 target verify + `eagle_sample` 输出 `accept_index/accept_lens` | verify tree/window 与 commit bookkeeping | 不捕获 target state，不加载 draft |

`[N,3,4096]` 是 target aux 的结构化 interface；进入现有 runner 时，按 logical
`[1,21,40]` 在最后一维拼接为 `[N,12288]`。这两者不是两个可互换的 shape：

```text
target internal: [N, 3, 4096]
       |
       | flatten/concat last dim, fixed tap order
       v
runner/draft interface: [N, 12288]
```

runner 不应看见 `[N,4,4096]` raw mHC state；target module 必须在 seam 之前隐藏并完成
stream mean。

## 2. 最小 source 改动

### 2.1 `python/sglang/srt/arg_groups/deepseek_v4_hook.py`

只做 capability guard：

- 将 `EAGLE3` 加入 DeepSeek-V4 允许集合；
- 对本 checkpoint 保持 `topk=1`；
- 不在此处推导 aux shape，不改变 proposal steps；
- 单元测试分别覆盖 `EAGLE3` 通过、未知算法仍拒绝。

这是按实际控制流必须先解除的第一层阻断。

### 2.2 `python/sglang/srt/models/deepseek_v4.py`

把 DeepSeek-V4 EAGLE3 aux capture 做成一个深 target module：

1. 新增独立 `eagle3_layers_to_capture` 状态，不能复用
   `dspark_layers_to_capture`；
2. 新增
   `set_eagle3_layers_to_capture(logical_ids: list[int])` interface：
   - 只在适用 PP rank 启用；
   - 拒绝 `None`、重复、越界或非递增 IDs；
   - 保存 logical IDs 与 hook IDs `[id + 1]`，日志同时记录两套编号；
3. 在 layer loop 中取得 logical `[1,21,40]` 的 **completed** mHC state；
   - after-layer 实现应以 `(executed_layer_id + 1) in hook_ids` 匹配；
   - fused path 先用该 layer 的 `hc_post` 形成 completed state；
4. 一个 module-internal pure helper 验证 `[N,4,4096]` BF16 并执行
   `mean(dim=1) -> [N,4096]`；
5. 按 logical 顺序积累三个 `[N,4096]`，语义上组成
   `[N,3,4096]`；
6. 沿现有 `LogitsProcessor(aux_hidden_states=list)` interface 输出，由其固定
   last-dim concat 形成 runner `[N,12288]`；
7. capture 打开时沿用现有逐 layer eager loop；不要把 TBO/graph 支持作为首轮
   native smoke 的扩展目标。

pure helper 只有一个实现，属于 target module 的 internal seam；不要为它制造
port/adapter。它应是无模型权重、无 distributed 初始化即可测试的 interface。

### 2.3 现有文件默认不改

以下固定 source 已有需要的 interface；只有真实 failing fixture 才改变：

- `model_executor/model_runner_components/spec_aux_hidden_state.py`：已从 draft
  config 解析 logical IDs；
- `model_executor/model_runner_components/attention_backend_setup.py`：已调用
  target setter；
- `layers/logits_processor.py`：已将三个 aux tensor concat 为 12,288；
- `models/llama_eagle3.py`：已有 architecture、loader、`fc_norm/fc` 和 mapping；
- `speculative/eagle_worker_v2.py` / `eagle_utils.py`：已有 runner lifecycle 与
  12,288 input-width 推导；
- `speculative/eagle_worker_common.py`：已有 strict verify bookkeeping。

避免为了“统一”而把 DSpark/DFlash/EAGLE3 capture 合并成宽泛抽象；三者 tensor
语义不同，当前没有能减少复杂度的统一 interface。

## 3. Interface 作为离线测试面

建议在 SGLang source 新增
`test/registered/unit/models/test_deepseek_v4_eagle3_aux.py`，至少覆盖：

| Test surface | 输入 | 断言 |
| --- | --- | --- |
| setter | logical `[1,21,40]` | hook `[2,22,41]`，独立于 DSpark state |
| hook selection | 每层唯一 sentinel | 只选择 logical 1/21/40 的 completed output，无 off-by-one |
| raw reduction | BF16 `[2,4,4096]`，四 stream 可区分 | `mean(dim=1)` 数值、shape、dtype |
| ordering | 逆序容器/触发顺序 | structured `[2,3,4096]` 仍按 1/21/40 |
| runner boundary | 三个 `[2,4096]` | `LogitsProcessor` interface 为 `[2,12288]`，chunk 顺序精确 |
| validation | 缺 tap、重复/越界 ID、3 streams、错误 hidden width | fail closed，错误包含实际/期望 shape |
| guard | `EAGLE3` / 未知算法 | 前者通过，后者拒绝 |

DeepSpec 已提供独立 CPU reference：

```text
deepspec/hedge_eagle3_phase01c/aux_contract.py
tests/test_hedge_eagle3_phase01c_aux_contract.py
```

Phase 02 应先让 source-side test 与这个 reference contract 一致，再启动 full model。
不要让 test import 当前工作目录的偶然 module 来替代 SGLang source-side implementation。

## 4. TP=8 runtime interface

静态源码只给出 TP ownership 的间接证据。native smoke 在 target→runner seam 上临时记录
或断言：

```text
rank
logical_ids
hook_ids
raw_shape / structured_shape / runner_shape
dtype
device
small_checksum
```

期望每 rank 本地完整：

```text
[N,4,4096] -> [N,3,4096] -> [N,12288], BF16
```

不得新增 aux all-gather。若 checksum 不一致，先保存 rank、layer、token 的第一个最小
反例，不能用 gather 使测试表面通过。运行时诊断应有开关或仅首请求输出，避免污染正式
arm 和 TPS。

## 5. Runner 与 proposal seam

runner interface 保持现有 EAGLE worker：

- `speculative_num_steps=3`、`topk=1` 表示协议生成 3 个 draft tokens；
- 内部 `speculative_num_draft_tokens=4` 是 verify window width；
- prefill target 为 FULL，draft extend 为 LAST；
- decode target verify 为 FULL，draft extend 按 `accept_lens` 选择最后接受位置。

source-side fixture 应构造小 batch，检查 target aux `[N,12288]` 能穿过
`EagleDraftExtendInput` 到 draft，而不需要 target 模型权重。live trace 再证明三个
proposal positions 都执行、target verify 执行、请求达到终态。

## 6. Strict verify / HEDGE adapter seam

Phase 02 只保留原生 strict verify。Phase 03 才在“target logits 已产生、strict greedy
barrier 正要判定当前 draft candidate”处增加薄 HEDGE adapter：

```text
strict verify inputs
  target logits + draft candidate + request identity
             |
             v
HEDGE adapter (disabled or enabled policy)
             |
             v
existing accept_index / accept_lens / commit lifecycle
```

这里存在 native strict 与 HEDGE 两种策略，adapter 才有意义。adapter 只能转换现有
verify 数据与 pure HEDGE core 的输入/输出；per-request `B` 属于 request lifecycle，
不能放进 target/draft module。disabled/B=0 路径必须沿 native bookkeeping，并以
fixture 证明无状态泄漏和相同输出。Phase 01C 不实现此 adapter。

## 7. 单变量 bring-up 顺序

1. 运行现有 DeepSpec CPU contract；
2. 为固定 SGLang 添加 source-side aux/guard tests，使其先失败；
3. 只放开 DeepSeek-V4 `EAGLE3` guard；
4. 只实现 target setter + exact aux capture；
5. 运行 draft config/19-entry loader fixture；
6. 运行 runner lifecycle fixture，核对协议 3 / 内部 4；
7. 具备 Phase 02 operational 前置条件后，运行 TP=8 native smoke；
8. native 成功后才进入 HEDGE adapter。

每一步的失败应移动 blocker 或缩小范围；不得同时改 guard、loader、runner 和 verify
来得到不可归因的启动结果。
