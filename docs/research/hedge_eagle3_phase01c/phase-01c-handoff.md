# Phase 01C handoff

> 状态：PASS（等待主 Agent 验收）
>
> 完成时间：2026-07-29T05:32:38+08:00
>
> 执行范围：只读兼容性研究、最小适配设计、CPU synthetic contract
>
> GPU/模型服务：未使用、未启动

## 结论

固定 SGLang 已有 EAGLE3 draft architecture/loader、runner lifecycle 和 strict verify
主体；DeepSeek-V4 的最小 native 缺口集中在：

1. `deepseek_v4_hook.py` 首先拒绝 `EAGLE3`；
2. 放开后 target 缺少 `set_eagle3_layers_to_capture`；
3. setter 之后仍须实现独立的 logical `[1,21,40]` → hook `[2,22,41]`、
   completed mHC 4-stream mean，以及 structured `[N,3,4096]` →
   runner `[N,12288]` interface。

详细证据只在 canonical research 中维护：
[`eagle3_compatibility_research.md`](eagle3_compatibility_research.md)。

## 退出门禁

| Phase 01C gate | 状态 | 证据 |
| --- | --- | --- |
| 完整读取固定 model card/config | PASS | canonical research §1–2 的 pinned URL/字段 |
| 阅读固定 SGLang target/draft/runner/verify seam | PASS | canonical research §3–6 的固定 SHA 源码引用 |
| 从公开一手实现提取 contract，未运行其他 engine | PASS | 固定模型卡、SGLang；vLLM 仅只读 interface 交叉核对 |
| 输出 shape/layers/dtype/TP ownership/lifecycle | PASS | canonical research §3–5；TP 明确标为 C 级待 live |
| synthetic `+1` / 4-stream mean / `3×4096` | PASS | 3 个 CPU tests 全部通过 |
| target/draft/runner/verify 四层分离 | PASS | `integration_seams.md` §1 |
| 最小文件改动和 offline test seam | PASS | `integration_seams.md` §2–3 |
| 3–5 个可证伪 native 风险 | PASS | canonical research §8，共 5 个 |
| 最小 native smoke 信号 | PASS | canonical research §9 |
| 未复制其他 engine scheduler | PASS | 仅生成研究 Markdown、JSON、纯 helper/test |

## Artifact

权威交付：

- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/docs/research/hedge_eagle3_phase01c/eagle3_compatibility_research.md`
- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/docs/research/hedge_eagle3_phase01c/aux_state_contract.json`
- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/docs/research/hedge_eagle3_phase01c/integration_seams.md`
- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/docs/research/hedge_eagle3_phase01c/phase-01c-handoff.md`

最小可执行 reference：

- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/deepspec/hedge_eagle3_phase01c/aux_contract.py`
- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/deepspec/hedge_eagle3_phase01c/__init__.py`
- `/mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-v4-eagle3/tests/test_hedge_eagle3_phase01c_aux_contract.py`

没有修改 01B SGLang source，没有修改主实验/进展文档，没有 commit/push。

## 命令与结果

固定 source identity：

```text
git -C /home/tiger/src/deepspec-sglang-fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1 rev-parse HEAD
=> fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1

git -C /tmp/hedge-eagle3-phase01c-vllm.tEF8ZD rev-parse HEAD
=> 0b3ba88f165976e77ca5e6a7a3f5bba4562b80af
```

固定 provider 文件通过 `curl -fsSL <pinned raw URL>` 读取；draft binary 通过
HTTP HEAD/Range + Python stdlib `pickletools` 解析 ZIP metadata 与两个小 mapping
storage，结果记录在 canonical research §2.3。

合成测试：

```text
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests \
  -p 'test_hedge_eagle3_phase01c_aux_contract.py' -v

Ran 3 tests
OK
```

最终复跑环境为 Python 3.11.2 / PyTorch 2.7.1 CPU；CUDA unavailable 且未使用。

最终静态审计：

```text
python -m json.tool docs/research/hedge_eagle3_phase01c/aux_state_contract.json
git diff --check
rg -n '[[:blank:]]+$' deepspec/hedge_eagle3_phase01c \
  tests/test_hedge_eagle3_phase01c_aux_contract.py \
  docs/research/hedge_eagle3_phase01c

=> 全部 PASS，无 JSON/whitespace 错误
```

本阶段测试生成的三个 `.pyc` 和两个 `__pycache__` 目录已按完整绝对路径定向删除；
最终复跑设置 `PYTHONDONTWRITEBYTECODE=1`，审计确认没有残留 cache。

## Phase 02 前置与顺序

Phase 01C 已具备进入 native 适配的研究门禁，但 Phase 02 仍须由主 Agent 同时确认：

- worker `4099544` 原任务自然结束；
- 8 卡项目 keepalive 已建立并通过门禁；
- Phase 01A target/draft 实体发布完成；
- Phase 01B uv/source/launcher 离线门禁完成。

实现顺序应保持单变量：

1. source-side aux/guard tests；
2. 放开 `EAGLE3` guard；
3. 加独立 target setter/capture；
4. loader fixture；
5. runner lifecycle fixture；
6. TP=8 native smoke；
7. native 成功后才做 HEDGE adapter。

## 仍待 live 验证

- TP=8 每 rank aux 是否为完整 replicated BF16 tensor；
- fused mHC 路径下 capture 的准确运行行为；
- 最终 Phase 01A snapshot 的 19-entry 全量加载；
- prefill/decode padding 与 request-state lifecycle；
- protocol 3-token proposal、内部 width 4 和 strict verify trace；
- rank 0–7、GPU memory/utilization 与无 CUDA/NCCL crash。

这些不确定性没有被写成 Phase 01C 成功事实，也不阻止把研究和离线 contract 交给
Phase 02。
