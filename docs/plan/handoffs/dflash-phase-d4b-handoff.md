# DFlash Phase D4-B source freeze / D4-C readiness handoff

## 结论

`D4-B SOURCE FROZEN；READY_FOR_D4C`。canonical HEDGE core 已按原字节
注入独立 SGLang checkout，DFlash greedy verify seam 的配置、request state、
calibration trace、HEDGE acceptance 和 counters 已完成 CPU 门禁；最终 SGLang
source 已由主 Agent 固化，D4-C short live `B=0` launcher/API/counter contract
也已通过 CPU 静态门禁。尚未运行任何 D4 live attempt，因此 `B0=NOT_RUN`，
本 handoff 不宣称整个 D4 完成，也不进入 D5。

## 固定身份

- DeepSpec DFlash canonical core commit：
  `86231e536573ccc43cda732b4eca920d5ce0a28a`
- upstream pure-core commit：
  `4d96f44065c07030ede67484a262006ec149626a`
- HEDGE source commit：
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- SGLang fixed base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- D4 pre-integration SGLang HEAD：
  `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`
- D4 final SGLang commit：
  `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`
- D4 final SGLang tree：
  `53fc45b1b04963736254dc7ed582047313b8075a`
- injected core content hash：
  `2c8688110ce0fab8450df5c12b1e6d6c535f2c9f8836ef9ae02aea4ac732c348`
- integration content hash：
  `70fd4a14d1c9171d4a699ff1eb8b7bc1e9488cc6c523a612e733ab68375fb5e5`
- reproducible integration patch SHA-256：
  `1788696ec488d1844a061f4a1a37cb32af2754c0b6146094f1255f08fb226024`

最终 checkout 为 clean，且重建门禁证明从 pre-integration HEAD 注入同一 core、
以 `git apply --unidiff-zero` 应用同一 unified-zero integration patch 后得到的
tree 与 final tree 完全一致。patch artifact 自身经隔离临时 Git index 的
`git diff --cached --check` 验证无尾随空格。executor 未在 DeepSpec worktree
中 commit/push。

## 接入边界

- DFlash model block 保持 `8`，HEDGE proposal width 固定 `7`；
  `candidates[:, 0]` 是 anchor，`candidates[:, 1:]` 对齐 target logits
  positions `0:7`。
- 配置开关：
  - native：`HEDGE_ENABLED=0`，不加载 decode config；
  - calibration：`HEDGE_ENABLED=0` 加
    `SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE=1`；
  - HEDGE：`HEDGE_ENABLED=1`，并且
    `SGLANG_DFLASH_HEDGE_CONFIG_JSON` 与
    `SGLANG_DFLASH_HEDGE_CONFIG_PATH` 恰好设置一个。
- HEDGE config 使用 `B/g/m/value_scheme/block_size`，其中
  `block_size=7`；DFlash runtime block 仍为 `8`。
- target logits 已完成原生 adjustments 后才进入 adapter。native config-off
  仍走原 Triton/eager verifier；active mode 才切换到 HEDGE adapter。
- active mode 在 sampling/native 分支选择前拒绝 non-greedy，避免 sampling
  verifier 静默旁路。
- budget 与累计 relaxed mismatch 按 request-pool slot 存在 device tensor 中；
  rid/slot reorder 不改变状态。prefill 绑定，finish/abort 清零；未通知的 slot
  reuse 会先清旧状态。
- calibration 每个 request/block 在 device 上保存首个 strict-rejection
  barrier 的正 `regret/value`。proposal、strict/HEDGE accepted、
  accept-length histogram、逐位置接受、relaxed mismatch、charged regret、
  budget exhaustion 与 lifecycle counters 同样留在 device；显式
  `snapshot()` 才批量转 CPU。
- hot decision/trace 路径不含 `.item()`、`.cpu()`、`.numpy()` 或
  `.tolist()`。

## Patch artifact correction

首次 contextful patch 在第 13/34/56/71/78 行含 unified diff 的单空格
context marker；当 patch 本身作为新增 Git artifact staged 时，外层 diff 把它们
显示为 `+ ` 并触发 trailing-whitespace gate。它们不是 SGLang source 中的新增
空格行。生成器现固定使用 `--unified=0`，并要求复现时显式
`git apply --unidiff-zero`；生成后还在隔离临时 Git repository 中把 patch 当作
新增 artifact 执行 `git diff --cached --check`。没有通过字符串替换掩盖其他尾随
空格。

此次 correction 只改变 patch serialization、manifest 与派生证据；SGLang final
commit/tree、integration/core content hash 均保持不变。

## CPU 验证

统一证据：

- 首轮 semantic CPU evidence（历史、pre-correction）：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4_cpu_validation.json`
  与 `.log`
- correction 后权威 final evidence：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4_final_source_validation.json`
  与 `.log`

结果：

- canonical pure core：33/33 PASS；
- DFlash HEDGE integration：9/9 PASS；
- D4-C launcher/API/counter tooling：3/3 PASS；
- D4 source-capture tooling：1/1 PASS；
- DFlash primary regression：10/10 PASS；
- DFlash overlap regression：6 PASS，1 个 CUDA-only test skip；
- injected core byte/hash check：PASS；
- unified-zero integration patch artifact `git diff --cached --check`：PASS；
- integration patch temporary-index `git apply --unidiff-zero`：PASS；
- source syntax 与 `git diff --check`：PASS。

integration tests 覆盖 native config-off、`B=0` strict accept/bonus、正 barrier
trace、跨 block budget、并发 request reorder、finish、abort、真实 slot reuse、
accept-length/per-position/relaxed/risk counters、non-greedy fail-closed 和
hot-path host-sync guard。

最终 post-commit validation 还固定了 final SHA/tree、pure-core 两侧 SHA、
integration/core content hash，并复核 integration patch + injected core 与最终
tree 完全相同。

## D4-C short live `B=0` contract

- launcher：`scripts/dflash_d4_b0_attempt.sh`
- API/counter auditor：`scripts/dflash_d4_b0_api.py`
- worker/port：`4099543` / `31457`
- source：final SGLang
  `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`
- TP / DFlash model block / proposal width：`8 / 8 / 7`
- HEDGE：`HEDGE_ENABLED=1`，
  `SGLANG_DFLASH_HEDGE_CALIBRATION_TRACE=0`，
  `B=0, g=1000000, m=1, value_scheme=normalized_suffix, block_size=7`
- request：与 sealed D3 a05 相同的非思考 `2+2` short smoke；输出 token IDs
  必须精确等于 `[22, 1]`
- lifecycle/counter gate：`/get_server_info` 必须返回 enabled HEDGE、至少一个
  proposal、`draft_tokens_verifiable=proposals*7`、strict accepted 等于 HEDGE
  accepted、零 relaxed mismatch/charged regret、request 已初始化并终结、零 active
  state/leak
- sampler：D4 launcher 通过 `bash "$0" _sample ...` 自调用；静态测试禁止引用
  D3 attempt sampler
- seal：只有 ready、API、token-ID、HEDGE counters、定向 cleanup、CUDA context
  clear 和 keepalive resume 全部 PASS，最终 summary 才能为 PASS

contract action 与 tooling tests 均为 CPU-only；未 login worker、未暂停 keepalive、
未启动 server。

## 可复现文件

- core 注入脚本：
  `scripts/dflash_d4_inject_core.py`
- source/patch 封存脚本：
  `scripts/dflash_d4_capture_source.py`
- CPU 验证脚本：
  `scripts/dflash_d4_validate.py`
- D4-C short live launcher：
  `scripts/dflash_d4_b0_attempt.sh`
- D4-C API/counter auditor：
  `scripts/dflash_d4_b0_api.py`
- integration tests：
  `tests/hedge_dflash_integration/test_dflash_hedge_integration.py`
- D4-C tooling tests：
  `tests/hedge_dflash_integration/test_dflash_d4c_tooling.py`
- core 注入 manifest：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4_core_injection.json`
- source manifest：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4_source_manifest.json`
- integration patch：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/d4/dflash_d4_sglang_integration.patch`

重建顺序：

1. checkout SGLang `1ac1f38205adf08db53cd7cbb2a56c5bccdc62c5`；
2. 运行 `scripts/dflash_d4_inject_core.py`；
3. 以 `git apply --unidiff-zero dflash_d4_sglang_integration.patch` 应用 patch；
4. 运行 `scripts/dflash_d4_validate.py`。

## 主 Agent 下一门禁

1. 只读审查最终 DeepSpec diff、final validation、native disabled path、D4-C
   launcher process ownership 与 lifecycle/counter gate；
2. 显式暂存、commit 并 push 本阶段的小型 DeepSpec 文件；
3. 主 Agent 明确授权 D4-C 后，才使用 worker `4099543` 运行 short live `B=0`
   smoke；attempt 前后执行 lane keepalive 的定向暂停、context-clear、恢复与逐卡
   gate；
4. D4-C 未验收前不进入 D5。
