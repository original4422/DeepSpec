# DFlash continuation C3 handoff

## 结论

`C3 PASS；NATIVE FORMAL CANONICAL PASS`。本阶段只完成 fresh native server 的
固定 10 条 warmup（不计时）与唯一 500 条 formal arm，没有进入 C4 或启动
HEDGE B+。live attempt 上限为 3；a01 首次成功后停止，最终计数 `1/3`，
a02/a03 均未启动。

唯一成功 attempt：

- ID：`dflash-d6-native-20260729T093000Z-a01`
- HDFS：
  `/mnt/hdfs/pengzegang/DeepSpec/hedge/dflash/runs/dflash-d6-native-20260729T093000Z-a01`
- `.complete.json.status`：`PASS`
- manifest：46/46 PASS，SHA-256
  `a1c1a1e44ec66e21cb0ab5455aa42f011768c096bea25c81cf59c34b8b26eef4`
- repo acceptance：
  `docs/experiment/artifacts/hedge-deepseek-v4-flash-dflash/continuation-c3/continuation_c3_acceptance.json`

## 固定身份与协议

- worker `4099543`，8×NVIDIA H20，TP=8，port `31457`
- SGLang base `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- final source `9a01e2df71d6de085b0b2d50ccd687ec5abc7ff1`，tree
  `53fc45b1b04963736254dc7ed582047313b8075a`
- target revision `60d8d70770c6776ff598c94bb586a859a38244f1`
- draft revision `e44fc94ceb1e7ed45550d15e782aeadd08050483`
- dataset revision `740312add88f781978c0658806c59bc2815b9866`，seed
  `980406`，fingerprint `59ec1b7f9357c7a2`
- native arm：`HEDGE_ENABLED=0`、calibration trace `0`
- DFlash block `8`、proposal width `7`、单请求顺序执行

D6 tooling 6/6 与 D5/D4-C regression 11/11 PASS；shell syntax、API
`py_compile`、embedded Python AST、contract 与 `git diff --check` 均 PASS。

## Live 与正式指标

server PID/PGID/SID `209152` 于 `09:35:21.187020Z` 启动，
`09:42:17.275524Z` ready。固定前 10 条 calibration warmup 全部成功：
10/10、0 retry、1657 completion tokens、9 match / 1 mismatch /
0 parse failure；该段不计入 formal timing。

formal timing 为 `09:45:57.629147Z` 到 `12:30:55.468558Z`：

- 500/500 terminal success、request failure 0、retry 0
- 74802 completion tokens
- timed wall `9897.839411616s`
- E2E output TPS `7.55740691369605`
- match 484、mismatch 16、parse failure 0
- proposals 74302、proposed draft tokens 520114
- accepted draft tokens 0、mean accepted drafts/proposal `0.0`
- acceptance-length histogram `[74302,0,0,0,0,0,0,0]`
- position 1–7 acceptance rate 均为 `0.0`
- 含 current token 的 mean acceptance length
  `1.0067292939624775`

独立复算确认 500 行、74802 tokens、484/16/0、0 retry 以及所有
proposal/acceptance 聚合与 sealed summary 一致。TP0–7 均初始化；八卡各有
14405 个 formal samples，峰值利用率均为 99%，最低模型显存
`92905–93145 MiB`。owned shutdown 前没有未处理 CUDA、NCCL、Python
traceback 或 worker crash。

## Cleanup 与交接门禁

定向 cleanup 于 `12:31:39Z` PASS，八卡模型 context 均已退出。fresh
keepalive PID/PGID/SID `239449`，identity time
`12:31:38.990533Z`；8×10×1 秒 gate healthy，逐卡均值为
`[50,40,40,40,46,40,40,40]%`，最低 `40.0%`。

主 Agent 下一步：

1. 只读复核 C3 acceptance、HDFS `.complete.json`、46/46 manifest、
   summary/timing/acceptance 与 fresh keepalive gate；
2. 只显式暂存 C3 相关小文件并按提交纪律 commit/push；
3. 验收通过后立即另派独立 C4 executor，使用 frozen
   `B=g=12.5,m=1,value_scheme=normalized_suffix,block_size=7` 运行
   HEDGE B+ 的相同 10 warmup + 500 formal。

本 executor 到此停止，不进入 C4，不 add/commit/push。
