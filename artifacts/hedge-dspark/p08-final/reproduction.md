# HEDGE DSpark P08 离线复现

这套复现只读取 Git 小型 artifact 与已经归档的 P05–P07 HDFS run；不需要
worker、GPU、模型服务或 checkpoint 重载。不要对 HDFS run 执行
`live`、`final`、`archive` 等可能物化或写入 artifact 的 CLI 子命令。

## 固定入口

```bash
cd /mlx_devbox/users/pengzegang/playground/github/DeepSpec-hedge-dspark

P08_PYTHON=/home/tiger/venvs/hedge-v4-dspark/bin/python
P05_NATIVE=/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T044309Z-p05-native-calibration-r4
P05_B0=/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T051340Z-p05-b0-calibration-r1
P06_RUN=/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T062241Z-p06-native-formal-r1
P07_RUN=/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/20260729T084544Z-p07-hedge-formal-r1
P08_REPLAY_ROOT="$(mktemp -d /tmp/deepspec-hedge-dspark-repro.XXXXXX)"
```

固定身份：

- SGLang base：
  `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1`
- integration / patched tree：
  `e028d2c31658a06b4f5a5ee072d7e21c79d51c36` /
  `69e80df97b815587a5b7b57665c99cd436b2ceb617dc71f31c7e44807ab82422`
- pure core / HEDGE source：
  `4d96f44065c07030ede67484a262006ec149626a` /
  `9fb903d676254ea5f5d171051fb15c54f331111c`
- formal wheel：
  `a5c14bd799117d0c491323b916a123c5c2196940dc09a5567e0a561fa8de71f9`
- checkpoint provider snapshot / HF reference：
  `bb7ac3172e1a257482d3256d7a720f20ea39ce25625f3cacc1091f59ad43bcae` /
  `62af8fffb2f7030cac4de2f0169f5b8d1101b646`
- dataset revision：
  `740312add88f781978c0658806c59bc2815b9866`

## 1. 重验固定数据

```bash
"$P08_PYTHON" scripts/hedge_dspark_protocol.py verify-dataset \
  --output-dir artifacts/hedge-dspark/p01-protocol
```

预期最后输出 `status=PASS`，18/18 checks 为 true；这一步会读取已冻结的
manifest/JSONL，不改变它们。

## 2. 重放 B0 与 q25 reducer

```bash
"$P08_PYTHON" scripts/hedge_dspark_p05_reduce.py \
  --native-outputs "$P05_NATIVE/native_calibration_outputs.jsonl" \
  --b0-outputs "$P05_B0/b0_calibration_outputs.jsonl" \
  --native-trace "$P05_NATIVE/strict_rejection_trace.jsonl" \
  --native-counters "$P05_NATIVE/hedge_counters.json" \
  --output-dir "$P08_REPLAY_ROOT/p05"

for name in \
  b0_equivalence.json \
  calibration_summary.json \
  calibration_values.jsonl \
  hedge_config.json
do
  cmp \
    "$P08_REPLAY_ROOT/p05/$name" \
    "artifacts/hedge-dspark/p05-calibration/$name"
done

sha256sum "$P08_REPLAY_ROOT"/p05/*
```

四个 `cmp` 必须静默成功。预期 `32/32` 完整 token-ID 列表相同，
484 个正且有限的首次 strict-rejection barrier 值、线性 q25=`2.0625`，
冻结 `g=B=2.0625,m=1`。

## 3. 只读重放两个正式 arm

下面调用既有 validator 的纯读取函数；不会调用会写 artifact 的
`finalize_attempt` 或 `archive_attempt`。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts:. \
  "$P08_PYTHON" - <<'PY'
import hashlib
import json
from pathlib import Path

import hedge_dspark_p04_validate as p4
import hedge_dspark_p06_validate as p6
import hedge_dspark_p07_prepare as p7_prepare
import hedge_dspark_p07_validate as p7


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


runs = {
    "P06": Path(
        "/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/"
        "20260729T062241Z-p06-native-formal-r1"
    ),
    "P07": Path(
        "/mnt/hdfs/pengzegang/DeepSpec/runs/hedge-dspark/"
        "20260729T084544Z-p07-hedge-formal-r1"
    ),
}

for phase, root in runs.items():
    resolved = load(root / "resolved_config.json")
    dataset = resolved["dataset"]
    if phase == "P06":
        client = p6.validate_client_artifacts(
            scratch=root,
            expected_warmup_indices=dataset["warmup_indices"],
            expected_formal_indices=dataset["formal_indices"],
        )
    else:
        client = p7.validate_client_artifacts(
            scratch=root,
            expected_warmup_indices=dataset["warmup_indices"],
            expected_formal_indices=dataset["formal_indices"],
        )
        assert p7_prepare.validate_runtime_identity_parity(
            engine=load(root / "engine_identity.json"),
            checkpoint=load(root / "checkpoint_identity.json"),
        ) == resolved["p06_runtime_identity_parity"]

    gpu = p6.validate_formal_gpu_window(
        root / "gpu_samples.csv",
        expected_uuids=[row["uuid"] for row in resolved["gpu_inventory"]],
        formal_start=client["formal_start_monotonic_ns"],
        formal_end=client["formal_end_monotonic_ns"],
    )
    identity = p4._validate_identity_artifacts(
        engine=load(root / "engine_identity.json"),
        checkpoint=load(root / "checkpoint_identity.json"),
        decode_config_fingerprint=resolved["decode_config_fingerprint"],
    )
    server = p4._validate_server_log(root / "server.log")
    sampler = p4.validate_gpu_sampler_status(
        root / "gpu_sampler_status.json",
        root / "gpu_samples.csv",
    )
    lifecycle = p6.validate_lifecycle_events(
        p4._load_lifecycle_events(root / "lifecycle_events.jsonl"),
        require_archive=True,
    )

    shutdown = load(root / "shutdown.json")
    assert shutdown["status"] == "PASS"
    assert all(shutdown["checks"].values())
    assert "contexts=none" in (
        root / "cuda_contexts_after.txt"
    ).read_text(encoding="utf-8")
    p4._validate_keepalive(
        load(root / "keepalive_before.json"), "keepalive_before"
    )
    p4._validate_keepalive(
        load(root / "keepalive_after.json"), "keepalive_after"
    )

    manifest = load(root / "archive_manifest.json")
    assert manifest["status"] == "PASS"
    assert len(manifest["files"]) == 39
    assert all(
        (root / record["path"]).stat().st_size == record["bytes"]
        and digest(root / record["path"]) == record["sha256"]
        for record in manifest["files"]
    )
    print(
        phase,
        client["completion_tokens"],
        client["end_to_end_output_tps"],
        len(gpu["participation"]),
        identity["status"],
        server["status"],
        sampler["status"],
        lifecycle["status"],
        "39/39",
    )
PY
```

预期：

```text
P06 74594 31.76484698125425 8 PASS PASS PASS PASS 39/39
P07 75819 33.493242595936465 8 PASS PASS PASS PASS 39/39
```

## 4. 核对 P08 JSON 与总 manifest

```bash
"$P08_PYTHON" -m json.tool \
  artifacts/hedge-dspark/p08-final/final_results.json >/dev/null
"$P08_PYTHON" -m json.tool \
  artifacts/hedge-dspark/p08-final/final_audit.json >/dev/null
"$P08_PYTHON" -m json.tool \
  artifacts/hedge-dspark/p08-final/artifact_manifest.json >/dev/null

PYTHONDONTWRITEBYTECODE=1 "$P08_PYTHON" - <<'PY'
import hashlib
import json
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


manifest_path = Path(
    "artifacts/hedge-dspark/p08-final/artifact_manifest.json"
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["status"] == "PASS"
assert manifest["self_excluded"] is True
for record in manifest["direct_records"]:
    path = Path(record["path"])
    assert path.stat().st_size == record["bytes"]
    assert digest(path) == record["sha256"]
for nested in manifest["nested_archive_manifests"]:
    root = Path(nested["root"])
    source = root / "archive_manifest.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    assert len(value["files"]) == nested["record_count"]
    assert digest(source) == nested["sha256"]
    for record in value["files"]:
        path = root / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert digest(path) == record["sha256"]
print("P08 manifest PASS")
PY
```

`artifact_manifest.json` 刻意不记录自身哈希，避免自引用；它直接覆盖 P08
输出及关键输入，并通过六个嵌套 archive manifest 覆盖 P04–P07 canonical
run，其中 P06/P07 各 39 个文件。
