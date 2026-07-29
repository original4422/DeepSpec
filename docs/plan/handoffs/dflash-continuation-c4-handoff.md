# DFlash continuation C4 handoff

## 结论

`C4 PASS；HEDGE B+ FORMAL CANONICAL PASS`。C1 calibration 冻结参数、C2
protocol `B0 PASS`、C3 native formal 与本阶段 B+ formal 已形成完整路线内结果。
C4 只运行 fresh B+ server 的固定 10 条 warmup（不计时）与唯一 500 条 formal
arm。live attempt 上限为 3；a01 首次成功后停止，最终计数 `1/3`，a02/a03
均未启动。

唯一成功 attempt：

- ID：`dflash-d6-bplus-20260729T123500Z-a01`
- HDFS：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d6-bplus-20260729T123500Z-a01`
- `.complete.json.status`：`PASS`
- manifest：46/46 PASS，SHA-256
  `bf5b77ef694e74c45fe9c064b28f5a25779946f8ad1d541ee105315a87e61492`
- repo acceptance：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/continuation-c4/continuation_c4_acceptance.json`

## 参数来源与固定身份

C1 的 32 条 native calibration 产生 4991 条正且有限的首次 strict-rejection
`regret/value`；NumPy `2.3.5` linear q25 为 `12.5`。因此 C4 在看到 formal
结果前已冻结
`B=12.5,g=12.5,m=1,value_scheme=normalized_suffix,block_size=7`，config
SHA-256 为
`ef9003cd37d475b44ed256d91036808f38bedd2e7ea40a90f26232a939fe7746`。
C2 已有 32/32 完整 output token IDs 一致的 `B0 PASS`。

- worker `4099543`，8×NVIDIA H20，TP=8，port `31457`
- SGLang base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- final source `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，tree
  `53fc45b1b04963736254dc7ed582047313b8075a`
- target revision `60d8d70770c6776ff598c94bb586a859a38244f1`
- draft revision `e44fc94ceb1e7ed45550d15e782aeadd08050483`
- dataset revision `740312add88f781978c0658806c59bc2815b9866`，seed
  `980406`，fingerprint `59ec1b7f9357c7a2`
- DFlash block `8`、proposal width `7`、单请求顺序执行

## Live、正式指标与 risk counters

server PID/PGID/SID `241075` 于 `12:40:35.295450Z` 启动，
`12:47:26.394542Z` ready。固定前 10 条 warmup 为 10/10 success、0 retry、
1959 completion tokens、8/2/0；该段不计入 formal timing。

formal timing 为 `12:51:35.526246Z` 到 `15:53:16.401180Z`：

- 500/500 terminal success、request failure 0、retry 0
- 89279 completion tokens
- timed wall `10900.874935019s`
- E2E output TPS `8.190076533507574`
- match 443、mismatch 57、parse failure 0
- proposals 82094、proposed draft tokens 574658
- accepted draft tokens 6696、strict accepted 5936、relaxed draft gain 760
- mean accepted drafts/proposal `0.08156503520354716`
- acceptance histogram `[75514,6473,98,9,0,0,0,0]`
- position 1–7 accepted drafts `[6580,107,9,0,0,0,0]`
- 含 current token的 mean acceptance length `1.0875216215557775`

formal-only counters 为 500 initialized / 500 finished、730 relaxed
mismatches、charged regret `5677.6875 <= 6250.0`、budget exhaustion 34、
slot reuse reset 0，`pass=true`。完整 lifecycle 终态 active states 与 leaks
均为 0。

TP0–7 均初始化；八卡各有 15947 个 formal samples，峰值利用率均为 99%，最低
模型显存 `92905–93145 MiB`。owned shutdown 前 CUDA/NCCL/traceback/worker
crash 均为 0。

## Native 对照与路线内 delta

C3 native 为 500/500、74802 tokens、9897.839411616s、TPS
`7.55740691369605`、484/16/0、retry 0、accepted drafts 0。B+ − native：

- completion tokens `+14477`（`+19.3538%`）
- wall time `+1003.035523403s`（`+10.1339%`）
- E2E output TPS `+0.632669619811524`（`+8.3715%`）
- mean accepted drafts/proposal `+0.08156503520354716`
- mean acceptance length（含 current）`+0.0807923275933`（`+8.0252%`）
- answer matches `-41`，match rate `-8.2` percentage points
- retries `0`

两个 arm 按协议各只有一次正式运行，没有方差或置信区间。B+ 输出 token 数和答案
分布发生变化，TPS 差必须与 token、wall、acceptance 和 match 差共同解读；
GSM8K match 不是门槛，不作跨方法绝对 TPS 排名。

## Cleanup 与交接

定向 cleanup 于 `15:54:17Z` PASS，八卡模型 context 为 `none`。fresh
keepalive PID/PGID/SID `265796`，8×10×1 秒 gate healthy，逐卡均值均为
`100.0%`。artifact 于 `15:54:35.803908Z` 原子发布，46/46 manifest 已复核。

主 Agent 下一步只需：

1. 复核 C4 acceptance、两份结果文档、progress final 与本 handoff；
2. 显式暂存上述结果小文件，按提交纪律 commit/push；
3. 完成路线最终收尾；无需更多模型 attempt。

两份 read-only progress helper 的本地修改只是运行期观察增强，不是结果复现所需
文件，保持未暂存，建议不并入结果提交。本 executor 不 add/commit/push。
