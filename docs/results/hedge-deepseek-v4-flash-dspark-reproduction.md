# HEDGE × DeepSeek-V4-Flash-DSpark 复现索引

本路线已经完成，复现不需要重新启动模型。完整、可直接执行的离线步骤见
[`artifacts/hedge-dspark/p08-final/reproduction.md`](../../artifacts/hedge-dspark/p08-final/reproduction.md)。

## 固定输入

- dataset：`openai/gsm8k` `main/test`，
  revision `740312add88f781978c0658806c59bc2815b9866`
- selection：seed `980406` 确定性 shuffle；前 32 条 calibration，随后
  不重叠的 500 条 formal
- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- DeepSpec pure core / integration：
  `4d96f44065c07030ede67484a262006ec149626a` /
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36`
- formal wheel SHA-256：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`
- checkpoint HF reference：
  `deepseek-ai/DeepSeek-V4-Flash-DSpark@62af8fffb2f7030cac4de2f0169f5b8d1101b646`

## 权威结果与证据

- 人类可读结果：
  [`hedge-deepseek-v4-flash-dspark.md`](hedge-deepseek-v4-flash-dspark.md)
- 权威实验账本：
  [`docs/experiment/hedge-deepseek-v4-flash-dspark.md`](../experiment/hedge-deepseek-v4-flash-dspark.md)
- 机器可读结果：
  [`final_results.json`](../../artifacts/hedge-dspark/p08-final/final_results.json)
- 最终审计：
  [`final_audit.json`](../../artifacts/hedge-dspark/p08-final/final_audit.json)
- artifact 覆盖：
  [`artifact_manifest.json`](../../artifacts/hedge-dspark/p08-final/artifact_manifest.json)

离线复现会重验固定数据、从 P05 原始 trace 重放 B0/q25 reducer、从 P06/P07
完整 JSONL 重算两个正式 summary，并验证两个正式 run 的 identity、TP8/八卡参与、
shutdown、contexts-none、keepalive 以及各 39 项 archive manifest。所有重放输出
只写到新建的 `/tmp` 目录；HDFS 原始 artifact 保持只读。
