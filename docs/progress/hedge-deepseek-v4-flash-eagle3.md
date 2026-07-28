# HEDGE on DeepSeek-V4-Flash Eagle3 进展

> 当前状态：`PHASE_01_PARALLEL`
>
> 自主窗口：`2026-07-28T20:56:27Z` 至 `2026-07-29T08:56:27Z`；
> 9 小时实现门槛为 `2026-07-29T05:56:27Z`。

| 时间（UTC） | elapsed | 9h 剩余 | 12h 剩余 | Phase / executor | Worker / keepalive | 里程碑或 blocker | Artifact / 下一步 |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| 2026-07-28T20:56:27Z | 0m | 9h | 12h | Phase 00 / `eagle3_phase00` | 重新核对中；不得启动 workload | 建立实际 T0 和独立 worktree | 创建 Phase 00 inventory |
| 2026-07-28T21:04:31Z | 8m04s | 8h51m56s | 11h51m56s | Phase 00 / `eagle3_phase00` | worker `4099544` 准确 8×H20；0 compute PID；0 keepalive；keepalive 未启动 | Phase 00 inventory、namespace、schema 和脚本完成；无 blocker；未发 signal | `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T205627Z-phase-00-bootstrap-01`；等待主 Agent 验收后派发 Phase 01A–01C |
| 2026-07-28T21:11:10Z | 14m43s | 8h45m17s | 11h45m17s | Phase 00 验收 / Phase 01A/01B/01C 派发 | 两次 inventory 均为 8×H20、0 context；keepalive 尚待 01B 建立 | 必需 artifact、owner schema、路径隔离、静态/负向门禁和无 signal 证据通过；bootstrap commit `9369479acb6cbd88ae98a6e04446c6d50134feae` 已 push | 并行推进 acquisition、独立环境/runner 和 Eagle3 aux contract，优先建立 8 卡 keepalive |
| 2026-07-28T21:26:30Z | 30m03s | 8h29m57s | 11h29m57s | Phase 01A/01B/01C | 21:22Z inventory：8×H20、0 context、0 keepalive；01B 正在独立 uv env 安装 `torch==2.11.0` CUDA 13.0 wheel | 01A pinned acquisition 工具已落地但按门禁未下载；01C 已确认 SGLang `EAGLE3` guard 与缺失 V4 capture 为顺序 blocker，并证据化 checkpoint mapping/aux taps；DSpark pure-core marker 仍 pending | 安装观察 `/mnt/hdfs/pengzegang/DeepSpec/hedge-v4/eagle3/runs/20260728T212300Z-phase-01b-install-observation-01`；完成 uv 后立即建立 8 卡 keepalive，01A 再独立复核并启动下载；01C 落地 contract test |
| 2026-07-28T21:56:30Z | 1h00m03s | 7h59m57s | 10h59m57s | Phase 01A/01B；Phase 01C 已验收 | 21:50Z 复核 worker 仍为准确 8×H20、0 context、0 keepalive；01B 正在 NVMe 下载锁定 torch wheel | Phase 01C contract commit `a8d913e8f200f02519a446ea77fcb235f2c76681` 已 push；attempt 03 的 30,990-byte verbose log 证明 uv 在线 resolution 实际在推进，撤销先前 false `STALL` 推理；锁中 cp311/x86_64/cu130 wheel URL、SHA-256 和 0-context identity 已 PASS；target、draft、HEDGE core marker 均 pending | 纠偏证据 `.../20260728T214600Z-phase-01b-bootstrap-index-url-03/progress_gate_correction.json`；direct artifact `.../20260728T215100Z-phase-01b-direct-torch-04/`；完成 wheel SHA-256 与 uv local install/import gate，随后建立 8 卡 keepalive 并放行 01A acquisition |
| 2026-07-28T22:26:30Z | 1h30m03s | 7h29m57s | 10h29m57s | Phase 01A/01B；Phase 01C 已验收 | worker `4099544` 仍为准确 8×H20；22:25Z 第三次 ELF closure 为 0 context；keepalive 尚未启动 | 531,045,934-byte torch wheel 已匹配 lock SHA-256 并由 uv 本地安装；真实 blocker 依次从 `typing_extensions` 迁移至 CUDA ELF 依赖，锁定 provider 安装后完整 closure 已收敛为 `missing=[]`；一次 shared uv cache 路径缺陷已证据化且未清理；target、draft、HEDGE core marker 均 pending | 主 artifact `.../20260728T215100Z-phase-01b-direct-torch-04/`；重跑相同 torch import，若 PASS 则立即执行 8 卡 keepalive 10×1 秒门禁并放行 01A，随后继续固定 source/data/runner |
| 2026-07-28T22:56:40Z | 2h00m13s | 6h59m47s | 9h59m47s | Phase 01A/01B；Phase 01C 已验收 | keepalive attempt 06 active：owner `277607`，8×10 样本逐卡 mean=100%，精确 UUID/owner/env/device-user gate PASS；下载与 uv sync 前复核均健康 | attempt 05 失败已单变量归因为错误 compat prefix，前后 0 context；切到固定私有 CUDA 13 compat 后 PASS。01A target 已完成 83,377,044,730 bytes/48 files，另有 9,115,041,681 partial bytes/8 files，error=null；01B 固定 SGLang wheel 已 build，Rust 1.90 与 protoc 35.0 blocker 已清除，attempt 09 等待 uv 最终事务；pure-core marker `4d96f44065c07030ede67484a262006ec149626a` 已审计 READY | keepalive `.../20260728T223600Z-phase-01b-keepalive-06/`；acquisition `.../20260728T211500Z-phase-01a-acquisition-01/`；env sync `.../20260728T224800Z-phase-01b-full-env-protoc-09/`；继续 target/draft publish、editable source import/link-layout 和 data/runner fixtures |
| 2026-07-28T23:26:36Z | 2h30m09s | 6h29m51s | 9h29m51s | Phase 01A/01B/01C 全部验收 | keepalive owner `277607` 仍 active；Phase 01B 最终 8×10 样本逐卡 mean=100%；acquisition/fixture process 均已退出 | target 73 files/159,630,041,626 bytes 与 draft 7 files/1,858,538,499 bytes 已作为独立 HDFS entities 发布，Phase 01A commit `bb6ae8a92eac8c7d5a130b247835a01c70fe891b` 已 push；完整 uv/source/link-layout、固定 32+500 split、mock 10+500、q25/B0/cleanup 与 4 tests PASS；一次 final artifact 零字节 hash 竞争已修正为 fsync+hash+atomic sealing 并由主 Agent重算 | 01A `.../20260728T211500Z-phase-01a-acquisition-01/`；01B `.../20260728T232000Z-phase-01b-final-17/`，artifact manifest SHA `068c24fd510120db849e44540eaf9a8e4f88675ad5e170c0509300b8beb0e332`；提交 Phase 01B 工具链后派发 Phase 02 target diagnostic/native smoke |

## 当前依赖

- Target marker：complete；固定 revision 的 73-file entity、46 index referents、
  manifest 和 159,630,041,626 bytes 已由主 Agent独立验收，共享 marker 最后发布。
- Draft snapshot：complete；固定 revision 的 7-file entity、单权重、manifest 和
  1,858,538,499 bytes 已由主 Agent独立验收。
- DSpark pure HEDGE core marker：READY；主 Agent 已核对 commit
  `4d96f44065c07030ede67484a262006ec149626a` 的 parent、10 个文件 hash、33 tests 与
  远端祖先关系；Phase 03 前不 cherry-pick。
- SGLang source/uv env：Phase 01B PASS；独立 source clean HEAD 为固定
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`，editable import、201-package
  `uv pip check`、CUDA 13 link-layout 和关键版本均已验证。GSM8K split、runner、
  q25/B0/report/cleanup fixtures 与 4 unit tests PASS。
- Operational keepalive：attempt 06 active；准确 8 卡、10×1 秒逐卡 mean=100%，
  owner `PID/PGID/SID=277607/277607/277607`，精确 UUID、8 个 owned descendants、
  CUDA visibility 和私有 compat/lane library precedence 已通过主 Agent 审计。

## Phase 00 操作边界

- 未发送 signal，未终止或修改任何既有进程；
- 未启动 keepalive、GPU probe、模型服务或其他 GPU workload；
- 未下载 checkpoint、未创建正式 uv 环境、未建立正式 SGLang source；
- 未进入 Phase 01，未 commit/push。
