#!/usr/bin/env python3
"""Offline evidence audit for one completed Phase 05 DSpark run.

This script does not inspect live processes or GPUs.  It only reads artifacts
from the supplied run directory and writes a candidate acceptance decision.
Unknown log wording is reported as MISSING_EVIDENCE instead of being guessed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS = "PASS"
FAIL = "FAIL"
MISSING = "MISSING_EVIDENCE"
EXPECTED_RANKS = {0, 1, 2, 3}
EXPECTED_COMMIT = "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1"
MIN_KEEPALIVE_SAMPLES = 10
MIN_KEEPALIVE_UTILIZATION = 40.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(
    status: str,
    summary: str,
    *,
    evidence: Iterable[str] = (),
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "gate": True,
        "status": status,
        "summary": summary,
    }
    evidence_list = list(evidence)
    if evidence_list:
        item["evidence"] = evidence_list
    if details is not None:
        item["details"] = details
    return item


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层不是 object")
    return value


def command_value(command: list[str], flag: str) -> str | None:
    try:
        index = command.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return command[index + 1]


def check_resolved_config(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "resolved_config.json"
    if not path.is_file():
        return result(MISSING, "缺少 resolved_config.json")
    try:
        config = read_json_object(path)
        command = config["command"]
        environment = config["environment"]
        unset_environment = config["unset_environment"]
        if not isinstance(command, list) or not all(
            isinstance(item, str) for item in command
        ):
            raise ValueError("command 不是字符串数组")
        if not isinstance(environment, dict):
            raise ValueError("environment 不是 object")
        if not isinstance(unset_environment, list):
            raise ValueError("unset_environment 不是数组")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return result(FAIL, f"resolved_config.json 无法验证：{error}")

    errors: list[str] = []
    expected_arguments = {
        "--tp-size": "4",
        "--speculative-algorithm": "DSPARK",
        "--speculative-dspark-block-size": "5",
        "--moe-runner-backend": "flashinfer_mxfp4",
        "--speculative-moe-runner-backend": "flashinfer_mxfp4",
        "--max-running-requests": "1",
    }
    for flag, expected in expected_arguments.items():
        observed = command_value(command, flag)
        if observed != expected:
            errors.append(f"{flag}={observed!r}，预期 {expected!r}")
    for flag in (
        "--disable-cuda-graph",
        "--disable-overlap-schedule",
        "--disable-radix-cache",
    ):
        if flag not in command:
            errors.append(f"缺少 {flag}")
    if environment.get("CUDA_VISIBLE_DEVICES") != "0,1,2,3":
        errors.append("CUDA_VISIBLE_DEVICES 不是 0,1,2,3")
    if environment.get("SGLANG_RAGGED_VERIFY_MODE") != "static":
        errors.append("SGLANG_RAGGED_VERIFY_MODE 不是 static")
    if environment.get("SGLANG_DSV4_FP4_EXPERTS") != "1":
        errors.append("SGLANG_DSV4_FP4_EXPERTS 不是 1")
    if "SGLANG_DSV4_FP4_DEQUANT" in environment:
        errors.append("运行环境仍设置 SGLANG_DSV4_FP4_DEQUANT")
    if "SGLANG_DSV4_FP4_DEQUANT" not in unset_environment:
        errors.append("未显式 unset SGLANG_DSV4_FP4_DEQUANT")
    if config.get("sglang_commit") != EXPECTED_COMMIT:
        errors.append("SGLang source commit 与固定候选不一致")

    details = {
        "model_path": config.get("model_path"),
        "python": config.get("python"),
        "sglang_commit": config.get("sglang_commit"),
        "tp_size": command_value(command, "--tp-size"),
        "speculative_algorithm": command_value(
            command, "--speculative-algorithm"
        ),
        "moe_runner_backend": command_value(
            command, "--moe-runner-backend"
        ),
    }
    if errors:
        return result(
            FAIL,
            "resolved config 不符合固定的 4×H20 packed-FP4 DSpark 配置",
            evidence=errors,
            details=details,
        )
    return result(
        PASS,
        "resolved config 固定 TP=4、DSPARK、packed FP4 与 flashinfer_mxfp4",
        details=details,
    )


RANK_PATTERNS = (
    re.compile(r"\[\s*TP\s*([0-3])\s*\]", re.IGNORECASE),
    re.compile(r"\bTP[_ -]?rank\s*[:=#]?\s*([0-3])\b", re.IGNORECASE),
    re.compile(r"\btp_rank\s*[:=]\s*([0-3])\b", re.IGNORECASE),
    re.compile(r"\bTP([0-3])\b", re.IGNORECASE),
)


def ranks_in_line(line: str) -> set[int]:
    ranks: set[int] = set()
    for pattern in RANK_PATTERNS:
        ranks.update(int(match.group(1)) for match in pattern.finditer(line))
    return ranks


def snippets(
    lines: list[str], predicate: Any, *, limit: int = 8
) -> list[str]:
    found: list[str] = []
    for number, line in enumerate(lines, 1):
        if predicate(line):
            rendered = line.strip()
            if len(rendered) > 300:
                rendered = rendered[:297] + "..."
            found.append(f"L{number}: {rendered}")
            if len(found) >= limit:
                break
    return found


def check_server_log(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "server.log"
    names = (
        "server_log_dspark",
        "server_log_tp_ranks",
        "server_log_draft_architecture_per_rank",
        "server_log_moe_backend",
        "server_log_packed_fp4",
        "server_log_no_unhandled_cuda_nccl_crash",
    )
    if not path.is_file():
        return {
            name: result(MISSING, "缺少 server.log，无法核对运行时证据")
            for name in names
        }

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    checks: dict[str, dict[str, Any]] = {}

    dspark_pattern = re.compile(
        r"(?i)(?:speculative[_ -]?algorithm|speculative decoding)"
        r".{0,100}\bDSPARK\b|"
        r"\bDSPARK\b.{0,100}(?:speculative[_ -]?algorithm|enabled)"
    )
    dspark_evidence = snippets(lines, lambda line: bool(dspark_pattern.search(line)))
    checks["server_log_dspark"] = result(
        PASS if dspark_evidence else MISSING,
        (
            "server.log 记录运行时 speculative_algorithm=DSPARK"
            if dspark_evidence
            else "未从 server.log 识别出运行时 DSPARK 证据，需人工确认措辞"
        ),
        evidence=dspark_evidence,
    )

    observed_ranks: set[int] = set()
    for line in lines:
        observed_ranks.update(ranks_in_line(line))
    rank_evidence = snippets(lines, lambda line: bool(ranks_in_line(line)))
    checks["server_log_tp_ranks"] = result(
        PASS if observed_ranks == EXPECTED_RANKS else MISSING,
        (
            "server.log 覆盖 TP0–TP3"
            if observed_ranks == EXPECTED_RANKS
            else "server.log 未明确覆盖全部 TP0–TP3，需人工确认"
        ),
        evidence=rank_evidence,
        details={
            "observed_ranks": sorted(observed_ranks),
            "missing_ranks": sorted(EXPECTED_RANKS - observed_ranks),
        },
    )

    draft_ranks: set[int] = set()
    draft_lines: list[str] = []
    for number, line in enumerate(lines, 1):
        lowered = line.lower()
        is_draft_architecture = (
            "draft" in lowered
            and (
                "architect" in lowered
                or "model" in lowered
                or "dspark" in lowered
            )
        )
        if is_draft_architecture and ranks_in_line(line):
            draft_ranks.update(ranks_in_line(line))
            if len(draft_lines) < 8:
                draft_lines.append(f"L{number}: {line.strip()[:300]}")
    checks["server_log_draft_architecture_per_rank"] = result(
        PASS if draft_ranks == EXPECTED_RANKS else MISSING,
        (
            "四个 TP rank 均有 DSpark draft architecture 日志"
            if draft_ranks == EXPECTED_RANKS
            else "draft architecture 日志无法关联到全部四个 TP rank，需人工确认"
        ),
        evidence=draft_lines,
        details={
            "observed_ranks": sorted(draft_ranks),
            "missing_ranks": sorted(EXPECTED_RANKS - draft_ranks),
        },
    )

    backend_pattern = re.compile(
        r"(?i)(?:moe|runner|selected|using|backend).{0,100}"
        r"flashinfer_mxfp4|flashinfer_mxfp4.{0,100}"
        r"(?:moe|runner|selected|using|backend)"
    )
    backend_evidence = snippets(
        lines, lambda line: bool(backend_pattern.search(line))
    )
    checks["server_log_moe_backend"] = result(
        PASS if backend_evidence else MISSING,
        (
            "server.log 记录实际 MoE backend 为 flashinfer_mxfp4"
            if backend_evidence
            else "未从 server.log 识别出实际 flashinfer_mxfp4 backend"
        ),
        evidence=backend_evidence,
    )

    packed_pattern = re.compile(
        r"(?i)\bpacked\b.{0,80}\b(?:fp4|mxfp4)\b|"
        r"\b(?:fp4|mxfp4)\b.{0,80}\bpacked\b|"
        r"\bexpert(?:_dtype|\s+dtype|\s+layout)?\b.{0,40}"
        r"\b(?:fp4|mxfp4)\b|"
        r"Preparing\s+DSv4\s+MXFP4\s+experts\s+for\s+FlashInfer"
        r"\s+SM90\s+CUTLASS|"
        r"quant_method\s*=\s*Mxfp4FlashinferCutlassMoEMethod"
    )
    dequant_pattern = re.compile(
        r"(?i)SGLANG_DSV4_FP4_DEQUANT\s*[=:]\s*1|"
        r"\bdequant(?:ize|ization)?\b.{0,40}(?:enabled|true|=\s*1)"
    )
    packed_evidence = snippets(
        lines, lambda line: bool(packed_pattern.search(line))
    )
    dequant_evidence = snippets(
        lines, lambda line: bool(dequant_pattern.search(line))
    )
    if dequant_evidence:
        checks["server_log_packed_fp4"] = result(
            FAIL,
            "server.log 显示 FP4 dequant 路径已启用",
            evidence=dequant_evidence,
        )
    else:
        checks["server_log_packed_fp4"] = result(
            PASS if packed_evidence else MISSING,
            (
                "server.log 记录 packed-FP4 expert layout"
                if packed_evidence
                else "未从 server.log 识别出 packed-FP4 expert layout"
            ),
            evidence=packed_evidence,
        )

    fatal_patterns = (
        re.compile(
            r"(?i)CUDA (?:error|out of memory)|CUDA_ERROR|"
            r"device-side assert|illegal memory access|"
            r"CUDNN_STATUS_|CUBLAS_STATUS_"
        ),
        re.compile(
            r"(?i)\bNCCL\b.{0,120}(?:error|fail|abort|timeout|watchdog)|"
            r"nccl(?:UnhandledCuda|System|Internal|Remote)Error"
        ),
        re.compile(
            r"Traceback \(most recent call last\)|"
            r"\bsegmentation fault\b|\bcore dumped\b|"
            r"\bSIGSEGV\b|\bSIGABRT\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?i)\b(?:worker|rank)\b.{0,100}"
            r"(?:crashed|died|exited unexpectedly|unhandled exception)"
        ),
    )
    fatal_evidence = snippets(
        lines,
        lambda line: any(pattern.search(line) for pattern in fatal_patterns),
        limit=20,
    )
    normal_shutdown = snippets(
        lines,
        lambda line: bool(
            re.search(
                r"(?i)graceful.{0,40}shutdown|shutdown.{0,40}complete|"
                r"(?:received|handling|stopping).{0,40}"
                r"(?:SIGTERM|SIGINT|SIGQUIT)",
                line,
            )
        ),
    )
    checks["server_log_no_unhandled_cuda_nccl_crash"] = result(
        FAIL if fatal_evidence else PASS,
        (
            "发现未处理 CUDA/NCCL/worker crash 模式"
            if fatal_evidence
            else "未发现未处理 CUDA/NCCL/worker crash 模式；普通关闭信号不计为崩溃"
        ),
        evidence=fatal_evidence or normal_shutdown,
        details={"normal_shutdown_lines": normal_shutdown},
    )
    return checks


def check_startup(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "startup.json"
    if not path.is_file():
        return result(MISSING, "缺少 startup.json，无法确认服务完成启动")
    try:
        data = read_json_object(path)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return result(FAIL, f"startup.json 无法解析：{error}")
    status = data.get("status")
    details = {
        "status": status,
        "server_pid": data.get("server_pid"),
        "elapsed_seconds": data.get("elapsed_seconds"),
        "finished_at": data.get("finished_at"),
    }
    if status == "ready":
        return result(PASS, "SGLang startup waiter 记录服务 ready", details=details)
    if status in {"server_exited", "timeout"}:
        return result(
            FAIL,
            f"SGLang startup 未完成：{status}",
            details=details,
        )
    return result(
        FAIL,
        f"startup.json 状态无效或未达到 ready：{status!r}",
        details=details,
    )


def parse_timestamp(raw: str) -> datetime:
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_api_smoke(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = run_dir / "api_smoke.json"
    if not path.is_file():
        return result(MISSING, "缺少 api_smoke.json"), None
    try:
        data = read_json_object(path)
        models = data["models_response"]
        chat = data["chat_response"]
        models_data = models["body"]["data"]
        content = chat["body"]["choices"][0]["message"]["content"]
    except (
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return result(FAIL, f"api_smoke.json 结构无效：{error}"), None
    errors: list[str] = []
    if data.get("status") != "PASS":
        errors.append(f"status={data.get('status')!r}")
    if models.get("http_status") != 200 or not models_data:
        errors.append("models endpoint 未返回 HTTP 200 和非空 data")
    if chat.get("http_status") != 200:
        errors.append("chat completions endpoint 未返回 HTTP 200")
    if not isinstance(content, str) or not content.strip():
        errors.append("chat completion 内容为空")
    if errors:
        return (
            result(FAIL, "OpenAI-compatible API smoke 未通过", evidence=errors),
            data,
        )
    return (
        result(
            PASS,
            "models 与 chat completions 均成功，模型响应非空",
            details={"chat_content": content.strip()[:300]},
        ),
        data,
    )


def check_gpu_samples(
    run_dir: Path,
    api_data: dict[str, Any] | None,
    *,
    min_model_memory_mib: float,
) -> dict[str, dict[str, Any]]:
    names = ("gpu_samples_four_card_participation", "gpu_samples_request_window")
    path = run_dir / "gpu_samples.csv"
    if not path.is_file():
        return {
            name: result(MISSING, "缺少 gpu_samples.csv") for name in names
        }
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            raw_rows = list(csv.DictReader(stream))
        rows = [
            {
                "timestamp": parse_timestamp(row["timestamp_utc"]),
                "gpu_index": int(row["gpu_index"]),
                "gpu_uuid": row["gpu_uuid"].strip(),
                "utilization": float(row["utilization_gpu_percent"]),
                "memory_used": float(row["memory_used_mib"]),
            }
            for row in raw_rows
        ]
    except (KeyError, TypeError, ValueError) as error:
        failed = result(FAIL, f"gpu_samples.csv 结构无效：{error}")
        return {name: dict(failed) for name in names}
    if not rows:
        missing = result(MISSING, "gpu_samples.csv 没有样本")
        return {name: dict(missing) for name in names}

    observed = {row["gpu_index"] for row in rows}
    uuids_by_gpu = {
        index: {row["gpu_uuid"] for row in rows if row["gpu_index"] == index}
        for index in observed
    }
    per_gpu = {
        str(index): {
            "samples": sum(row["gpu_index"] == index for row in rows),
            "uuid": sorted(uuids_by_gpu[index]),
            "max_utilization_percent": max(
                row["utilization"]
                for row in rows
                if row["gpu_index"] == index
            ),
            "max_memory_used_mib": max(
                row["memory_used"]
                for row in rows
                if row["gpu_index"] == index
            ),
        }
        for index in sorted(observed)
    }
    inventory_errors: list[str] = []
    if observed != EXPECTED_RANKS:
        inventory_errors.append(
            f"GPU index={sorted(observed)}，预期 [0, 1, 2, 3]"
        )
    if any(
        len(values) != 1 or not next(iter(values), "")
        for values in uuids_by_gpu.values()
    ):
        inventory_errors.append("GPU UUID 缺失或在采样期间发生变化")
    unique_uuids = {
        next(iter(values)) for values in uuids_by_gpu.values() if values
    }
    if len(unique_uuids) != len(uuids_by_gpu):
        inventory_errors.append("GPU UUID 不唯一")
    for index in EXPECTED_RANKS & observed:
        stats = per_gpu[str(index)]
        if stats["max_memory_used_mib"] < min_model_memory_mib:
            inventory_errors.append(
                f"GPU {index} 峰值显存低于 {min_model_memory_mib:g} MiB"
            )
        if stats["max_utilization_percent"] <= 0:
            inventory_errors.append(f"GPU {index} 没有非零利用率样本")

    participation = result(
        FAIL if inventory_errors else PASS,
        (
            "gpu_samples.csv 证明四张卡均有模型显存和非零活动"
            if not inventory_errors
            else "四卡参与证据不满足门禁"
        ),
        evidence=inventory_errors,
        details={"minimum_model_memory_mib": min_model_memory_mib, "per_gpu": per_gpu},
    )

    if api_data is None:
        request_window = result(
            MISSING, "缺少有效 API 时间窗口，无法关联请求期间的 GPU 采样"
        )
    else:
        try:
            started = parse_timestamp(api_data["started_at"])
            finished = parse_timestamp(api_data["finished_at"])
            if finished < started:
                raise ValueError("finished_at 早于 started_at")
        except (KeyError, TypeError, ValueError) as error:
            request_window = result(
                MISSING, f"API 时间窗口无效，无法关联 GPU 采样：{error}"
            )
        else:
            window_rows = [
                row for row in rows if started <= row["timestamp"] <= finished
            ]
            window_stats = {
                str(index): {
                    "samples": sum(
                        row["gpu_index"] == index for row in window_rows
                    ),
                    "max_utilization_percent": max(
                        (
                            row["utilization"]
                            for row in window_rows
                            if row["gpu_index"] == index
                        ),
                        default=None,
                    ),
                }
                for index in sorted(EXPECTED_RANKS)
            }
            proven = all(
                item["samples"] > 0
                and item["max_utilization_percent"] is not None
                and item["max_utilization_percent"] > 0
                for item in window_stats.values()
            )
            request_window = result(
                PASS if proven else MISSING,
                (
                    "API 请求时间窗口内四张卡均有非零利用率样本"
                    if proven
                    else "采样未明确证明 API 请求窗口内四张卡均活动，需人工确认"
                ),
                details={
                    "api_started_at": started.isoformat(),
                    "api_finished_at": finished.isoformat(),
                    "per_gpu": window_stats,
                },
            )
    return {
        "gpu_samples_four_card_participation": participation,
        "gpu_samples_request_window": request_window,
    }


def check_gsm8k(run_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    output_path = run_dir / "gsm8k_outputs.jsonl"
    summary_path = run_dir / "summary.json"
    names = (
        "gsm8k_ten_terminal_records",
        "gsm8k_all_requests_succeeded",
        "gsm8k_summary_recomputed",
    )
    missing_files = [
        path.name for path in (output_path, summary_path) if not path.is_file()
    ]
    if missing_files:
        checks = {
            name: result(MISSING, f"缺少 {', '.join(missing_files)}")
            for name in names
        }
        return checks, {}
    try:
        records = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        saved_summary = read_json_object(summary_path)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        checks = {
            name: result(FAIL, f"GSM8K artifact 无法解析：{error}")
            for name in names
        }
        return checks, {}

    terminal_errors: list[str] = []
    indices: list[int] = []
    allowed_parse_status = {
        "parsed",
        "parse_failure",
        "not_attempted_after_request_failure",
    }
    normalized_records: list[dict[str, Any]] = []
    for row_number, raw_record in enumerate(records, 1):
        if not isinstance(raw_record, dict):
            terminal_errors.append(f"row {row_number}: JSONL 行不是 object")
            normalized_records.append({})
            continue
        record = raw_record
        normalized_records.append(record)
        try:
            index = record["sample_index"]
            attempts = record["attempts"]
            request_succeeded = record["request_succeeded"]
            parse_status = record["parse_status"]
            matched = record["matched"]
            reference_response = record["reference_response"]
            reference_answer = record["reference_answer"]
        except (KeyError, TypeError) as error:
            terminal_errors.append(f"row {row_number}: 缺少字段 {error}")
            continue
        if not isinstance(index, int):
            terminal_errors.append(f"row {row_number}: sample_index 无效")
        else:
            indices.append(index)
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= 3:
            terminal_errors.append(f"row {row_number}: attempts 数量不在 1–3")
        if not isinstance(request_succeeded, bool):
            terminal_errors.append(f"row {row_number}: request_succeeded 无效")
        if parse_status not in allowed_parse_status:
            terminal_errors.append(f"row {row_number}: parse_status 无效")
        if not isinstance(matched, bool):
            terminal_errors.append(f"row {row_number}: matched 无效")
        if not isinstance(reference_response, str) or not reference_response:
            terminal_errors.append(f"row {row_number}: 标准答案原文缺失")
        if not isinstance(reference_answer, str) or not reference_answer:
            terminal_errors.append(f"row {row_number}: 标准答案提取值缺失")
        if "extracted_answer" not in record or "extraction_rule" not in record:
            terminal_errors.append(f"row {row_number}: 模型答案提取字段缺失")
        if request_succeeded:
            if not isinstance(record.get("response"), dict):
                terminal_errors.append(f"row {row_number}: 完整模型 response 缺失")
            model_text = record.get("model_text")
            if not isinstance(model_text, str) or not model_text.strip():
                terminal_errors.append(f"row {row_number}: model_text 为空")
            final_attempt = attempts[-1] if attempts else None
            if (
                not isinstance(final_attempt, dict)
                or final_attempt.get("status") != "success"
            ):
                terminal_errors.append(f"row {row_number}: 成功请求终态不一致")
        else:
            final_attempt = attempts[-1] if attempts else None
            if (
                parse_status != "not_attempted_after_request_failure"
                or not isinstance(final_attempt, dict)
                or final_attempt.get("status") != "error"
            ):
                terminal_errors.append(f"row {row_number}: 失败请求终态不一致")

    if len(records) != 10:
        terminal_errors.append(f"记录数为 {len(records)}，预期 10")
    if sorted(indices) != list(range(10)):
        terminal_errors.append(
            f"sample_index={sorted(indices)!r}，预期 0–9 且无重复"
        )
    terminal_check = result(
        FAIL if terminal_errors else PASS,
        (
            "GSM8K 0–9 共 10 条均有完整终态字段"
            if not terminal_errors
            else "GSM8K 终态记录不完整"
        ),
        evidence=terminal_errors,
    )

    counts = {
        "total": len(records),
        "success_requests": sum(
            record.get("request_succeeded") is True
            for record in normalized_records
        ),
        "failed_requests": sum(
            record.get("request_succeeded") is False
            for record in normalized_records
        ),
        "matches": sum(
            record.get("parse_status") == "parsed"
            and record.get("matched") is True
            for record in normalized_records
        ),
        "mismatches": sum(
            record.get("parse_status") == "parsed"
            and record.get("matched") is False
            for record in normalized_records
        ),
        "parse_failures": sum(
            record.get("parse_status") == "parse_failure"
            for record in normalized_records
        ),
    }
    counts["all_terminal"] = (
        counts["success_requests"] + counts["failed_requests"] == counts["total"]
        and not terminal_errors
    )
    request_check = result(
        PASS
        if counts["total"] == 10 and counts["success_requests"] == 10
        else FAIL,
        (
            "GSM8K 10 条请求均成功"
            if counts["total"] == 10 and counts["success_requests"] == 10
            else "存在 GSM8K 最终请求失败"
        ),
        details={
            "success_requests": counts["success_requests"],
            "failed_requests": counts["failed_requests"],
        },
    )

    summary_fields = (
        "total",
        "success_requests",
        "failed_requests",
        "matches",
        "mismatches",
        "parse_failures",
        "all_terminal",
    )
    summary_differences = {
        key: {"saved": saved_summary.get(key), "recomputed": counts[key]}
        for key in summary_fields
        if saved_summary.get(key) != counts[key]
    }
    summary_check = result(
        FAIL if summary_differences else PASS,
        (
            "summary.json 与 GSM8K JSONL 重算一致"
            if not summary_differences
            else "summary.json 与 GSM8K JSONL 重算不一致"
        ),
        details={
            "recomputed": counts,
            "differences": summary_differences,
        },
    )
    observations = {
        **counts,
        "match_rate_among_parsed": (
            counts["matches"] / (counts["matches"] + counts["mismatches"])
            if counts["matches"] + counts["mismatches"]
            else None
        ),
        "accuracy_is_gate": False,
    }
    return (
        {
            "gsm8k_ten_terminal_records": terminal_check,
            "gsm8k_all_requests_succeeded": request_check,
            "gsm8k_summary_recomputed": summary_check,
        },
        observations,
    )


def check_cuda_context_cleanup(run_dir: Path) -> dict[str, Any]:
    json_path = run_dir / "cuda_contexts_after_server.json"
    text_path = run_dir / "cuda_contexts_after_server.txt"
    if json_path.is_file():
        try:
            data = read_json_object(json_path)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            return result(FAIL, f"{json_path.name} 无法解析：{error}")
        clean = data.get("healthy") is True or (
            "contexts" in data and data["contexts"] in ([], None, "none")
        )
        return result(
            PASS if clean else FAIL,
            (
                "服务清理后无 CUDA context"
                if clean
                else "服务清理后仍有 CUDA context"
            ),
            details=data,
        )
    if not text_path.is_file():
        return result(
            MISSING,
            "缺少 cuda_contexts_after_server.txt/json，无法证明服务 context 已清理",
        )
    text = text_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if "query_failed=" in text:
        return result(
            FAIL,
            "清理后 CUDA context 查询失败",
            evidence=lines[-5:],
        )
    clean = bool(lines) and "contexts=none" in lines[-1].lower()
    return result(
        PASS if clean else FAIL,
        (
            "服务清理后最终 CUDA context 采样为空"
            if clean
            else "清理后 CUDA context 最终状态不是 none"
        ),
        evidence=lines[-5:],
    )


def extract_last_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def check_keepalive_after(run_dir: Path) -> dict[str, Any]:
    json_paths = (
        run_dir / "keepalive_final.json",
        run_dir / "keepalive_after.json",
    )
    text_path = run_dir / "keepalive_after.txt"
    headline = ""
    json_path = next((path for path in json_paths if path.is_file()), None)
    if json_path is not None:
        try:
            health = read_json_object(json_path)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            return result(FAIL, f"{json_path.name} 无法解析：{error}")
    elif text_path.is_file():
        text = text_path.read_text(encoding="utf-8", errors="replace")
        headline = next(
            (
                line.strip()
                for line in reversed(text.splitlines())
                if line.strip().startswith(("HEALTHY ", "UNHEALTHY "))
            ),
            "",
        )
        health = extract_last_json_line(text)
        if health is None:
            return result(
                FAIL,
                "keepalive_after.txt 缺少结构化健康采样",
                evidence=[headline] if headline else [],
            )
    else:
        return result(
            MISSING,
            "缺少 keepalive_final.json 或 keepalive_after.txt/json",
        )

    try:
        per_gpu = health["per_gpu"]
        expected_gpus = int(health["expected_gpus"])
        sample_count = int(health["sample_count"])
        minimum = float(health["minimum_utilization"])
        underutilized = health["underutilized_gpus"]
        if not isinstance(per_gpu, dict):
            raise ValueError("per_gpu 不是 object")
        if not isinstance(underutilized, list):
            raise ValueError("underutilized_gpus 不是数组")
    except (KeyError, TypeError, ValueError) as error:
        return result(FAIL, f"keepalive_after 健康结构无效：{error}")

    errors: list[str] = []
    if headline and not headline.startswith("HEALTHY "):
        errors.append(f"状态行不是 HEALTHY：{headline}")
    if health.get("healthy") is not True:
        errors.append("healthy 不是 true")
    if expected_gpus != 4 or set(per_gpu) != {"0", "1", "2", "3"}:
        errors.append("keepalive GPU inventory 不是准确四卡")
    if sample_count < MIN_KEEPALIVE_SAMPLES:
        errors.append(
            f"keepalive 样本数 {sample_count} < {MIN_KEEPALIVE_SAMPLES}"
        )
    if minimum < MIN_KEEPALIVE_UTILIZATION:
        errors.append(
            f"keepalive 门槛 {minimum:g}% < {MIN_KEEPALIVE_UTILIZATION:g}%"
        )
    if underutilized:
        errors.append(f"underutilized_gpus={underutilized!r}")
    for index in ("0", "1", "2", "3"):
        item = per_gpu.get(index, {})
        if not isinstance(item, dict):
            errors.append(f"GPU {index} keepalive 统计结构无效")
            continue
        try:
            item_samples = int(item.get("sample_count", 0))
            item_mean = float(item.get("mean_utilization", -1))
        except (TypeError, ValueError):
            errors.append(f"GPU {index} keepalive 统计值无效")
            continue
        if item_samples < MIN_KEEPALIVE_SAMPLES:
            errors.append(f"GPU {index} keepalive 样本不足")
        if item_mean < MIN_KEEPALIVE_UTILIZATION:
            errors.append(f"GPU {index} keepalive 平均利用率不足")
    summary = (
        "四卡 keepalive 10×1 秒健康门禁通过"
        if not errors
        else "keepalive_after 未通过四卡健康门禁"
    )
    return result(
        FAIL if errors else PASS,
        summary,
        evidence=errors or ([headline] if headline else []),
        details=health,
    )


def build_acceptance(
    run_dir: Path, *, min_model_memory_mib: float = 1024.0
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {
        "resolved_config": check_resolved_config(run_dir),
    }
    checks.update(check_server_log(run_dir))
    checks["startup"] = check_startup(run_dir)
    api_check, api_data = load_api_smoke(run_dir)
    checks["api_smoke"] = api_check
    checks.update(
        check_gpu_samples(
            run_dir,
            api_data,
            min_model_memory_mib=min_model_memory_mib,
        )
    )
    gsm_checks, gsm_observations = check_gsm8k(run_dir)
    checks.update(gsm_checks)
    checks["cuda_context_cleanup"] = check_cuda_context_cleanup(run_dir)
    checks["keepalive_after"] = check_keepalive_after(run_dir)

    failed = [
        name for name, item in checks.items() if item["status"] == FAIL
    ]
    missing = [
        name for name, item in checks.items() if item["status"] == MISSING
    ]
    candidate = "MVP_PASS" if not failed and not missing else "MVP_INCOMPLETE"
    return {
        "schema_version": 1,
        "kind": "phase06_offline_acceptance_candidate",
        "generated_at": utc_now(),
        "run_dir": str(run_dir.resolve()),
        "candidate_conclusion": candidate,
        "phase06_executed": False,
        "checks": checks,
        "failed_checks": failed,
        "missing_evidence": missing,
        "observations": {"gsm8k": gsm_observations},
        "notes": [
            "这是离线候选结论，不替代 Phase 06 主 Agent 人工复核。",
            "GSM8K matches、mismatches 和 parse_failures 不参与 MVP gate。",
            "SIGTERM/SIGINT/SIGQUIT 文本本身不被当作 worker crash。",
        ],
    }


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Phase 06 离线验收报告草稿",
        "",
        "> 此报告由前置工具离线生成，`phase06_executed=false`；",
        "> 只有主 Agent 完成 Phase 06 人工交叉核对后才能发布最终 MVP 结论。",
        "",
        f"- Run：`{audit['run_dir']}`",
        f"- 候选结论：`{audit['candidate_conclusion']}`",
        f"- 生成时间：`{audit['generated_at']}`",
        "",
        "## 门禁核查",
        "",
        "| 检查项 | 状态 | 摘要 |",
        "| --- | --- | --- |",
    ]
    for name, item in audit["checks"].items():
        lines.append(
            f"| `{name}` | `{item['status']}` | "
            f"{markdown_escape(item['summary'])} |"
        )

    gsm8k = audit["observations"].get("gsm8k", {})
    lines.extend(
        [
            "",
            "## GSM8K 观察值（不作为准确率门禁）",
            "",
            f"- 请求成功/失败：{gsm8k.get('success_requests', 'unknown')}/"
            f"{gsm8k.get('failed_requests', 'unknown')}",
            f"- 匹配/不匹配/解析失败：{gsm8k.get('matches', 'unknown')}/"
            f"{gsm8k.get('mismatches', 'unknown')}/"
            f"{gsm8k.get('parse_failures', 'unknown')}",
        ]
    )
    if audit["failed_checks"]:
        lines.extend(
            [
                "",
                "## 明确失败",
                "",
                *[f"- `{name}`" for name in audit["failed_checks"]],
            ]
        )
    if audit["missing_evidence"]:
        lines.extend(
            [
                "",
                "## 待人工确认的缺失证据",
                "",
                *[f"- `{name}`" for name in audit["missing_evidence"]],
            ]
        )
    if not audit["failed_checks"] and not audit["missing_evidence"]:
        lines.extend(
            [
                "",
                "## 人工复核提醒",
                "",
                "- 所有自动门禁均通过；仍需核对日志完整性、artifact 来源及最终 handoff。",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline acceptance audit for a completed Phase 05 run"
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--min-model-memory-mib", type=float, default=1024.0)
    args = parser.parse_args()
    if not args.run_dir.is_dir():
        parser.error(f"run directory does not exist: {args.run_dir}")
    if args.min_model_memory_mib <= 0:
        parser.error("--min-model-memory-mib must be positive")

    output_json = args.output_json or args.run_dir / "acceptance.json"
    output_report = (
        args.output_report or args.run_dir / "acceptance_report.md"
    )
    audit = build_acceptance(
        args.run_dir,
        min_model_memory_mib=args.min_model_memory_mib,
    )
    output_json.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_report.write_text(render_markdown(audit), encoding="utf-8")
    print(
        f"{audit['candidate_conclusion']} "
        f"failed={len(audit['failed_checks'])} "
        f"missing={len(audit['missing_evidence'])}"
    )
    return 0 if audit["candidate_conclusion"] == "MVP_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
