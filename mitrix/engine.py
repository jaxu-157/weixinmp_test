"""多标签诊断引擎 —— 声明式信号签名匹配。

核心理念：
  不手写检测器，而是为每个原子故障定义"信号签名"（signal signature）。
  签名 = 在断言空间 {visual, functional, performance} 中期望匹配的模式。
  新增故障 = 新增一条签名，无需写代码。

与原始 triage 的区别：
  - 原始 triage: 单一判决 (Pass/PerformanceRisk/RenderBug/FunctionalFail/Mixed)
  - mitrix engine: 多标签检测，基于声明式签名独立判定
"""
import re
from typing import Optional, Any, Callable

# ============================================================
# 阈值常量
# ============================================================
PERF_THRESHOLD_MS = 800
BLUR_SCORE_THRESHOLD = 200.0
BLUR_EDGE_LOW = 0.05

ATOMIC_FAULTS = [
    "blur_image",
    "slow_api",
    "stale_ui",
    "wrong_mapping",
    "layout_overlap",
    "memory_pressure",
]

# ============================================================
# 声明式信号签名 (Signal Signatures)
# ============================================================
#
# 每条签名 = (适用页面列表, 规则列表, 匹配策略)
#
# 规则格式:
#   ("source.field", operator, operand, confidence)
#
# operator:
#   "gt" / "lt" / "eq" / "neq"     — 数值/布尔比较
#   "contains"                      — 字符串包含
#   "regex"                         — 正则匹配
#   "eval"                          — 自定义函数 (仅复杂场景)
#
# match_policy:
#   "any"   — 任一规则命中即判定检出
#   "all"   — 全部规则命中才判定检出 (用于组合信号)
#
# ============================================================

SIGNATURES: dict[str, tuple[list[str], list[tuple], str]] = {
    "blur_image": (
        ["feed"],
        [
            ("visual.is_blur",    "eq", True,        0.90),
            ("visual.blur_score", "lt", 200.0,       0.70),
            ("visual.edge_density","lt", BLUR_EDGE_LOW, 0.60),
        ],
        "any",
    ),
    "slow_api": (
        ["feed", "counter", "layout"],
        [
            ("performance.interaction_ms", "gt", PERF_THRESHOLD_MS, 0.70),
        ],
        "any",
    ),
    "stale_ui": (
        ["counter"],
        [
            # 特征：visible 是数值（说明字段存在），但与 expected 不同
            # 示例 reason: "visible=0, expected=1"
            ("functional.reason", "regex",
             r"visible=(\d+(?:\.\d+)?),\s*expected=(\d+(?:\.\d+)?)",
             0.85),
        ],
        "any",
    ),
    "wrong_mapping": (
        ["counter"],
        [
            # 特征：visible=undefined（字段完全不存在/被改名）
            # 示例 reason: "visible=undefined, expected=1"
            ("functional.reason", "contains", "visible=undefined", 0.85),
        ],
        "any",
    ),
    "layout_overlap": (
        ["layout"],
        [
            ("functional.reason", "contains", "layout_overlap", 0.90),
        ],
        "any",
    ),
    "memory_pressure": (
        ["feed", "layout"],
        [
            ("performance.memory_warnings", "gt", 0, 0.75),
        ],
        "any",
    ),
}


# ============================================================
# 签名匹配引擎
# ============================================================

def _get_field(data: dict, path: str) -> Any:
    """按点分路径取值，如 'visual.blur_score' → data['visual']['blur_score']"""
    keys = path.split(".")
    val = data
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val


def _eval_rule(value: Any, op: str, operand: Any) -> bool:
    """执行单条规则匹配。"""
    if value is None:
        return False

    if op == "eq":
        return value == operand
    if op == "neq":
        return value != operand
    if op == "gt":
        return isinstance(value, (int, float)) and value > operand
    if op == "lt":
        return isinstance(value, (int, float)) and value < operand
    if op == "contains":
        return isinstance(value, str) and operand in value
    if op == "regex":
        return isinstance(value, str) and bool(re.search(operand, value))

    return False


def _match_signature(signature: tuple, assertion_space: dict) -> tuple:
    """将一条签名与断言空间匹配。

    Returns:
        (detected: bool, confidence: float, evidence: str)
    """
    pages, rules, policy = signature

    matched = []
    for rule in rules:
        field_path, op, operand, confidence = rule
        actual = _get_field(assertion_space, field_path)
        hit = _eval_rule(actual, op, operand)
        if hit:
            matched.append((field_path, confidence, actual))
        else:
            matched.append((field_path, 0.0, actual))

    if policy == "any":
        hits = [m for m in matched if m[1] > 0]
        if not hits:
            return False, 0.05, _format_evidence(matched)
        best = max(hits, key=lambda m: m[1])
        return True, best[1], _format_evidence(matched)

    elif policy == "all":
        if all(m[1] > 0 for m in matched):
            avg_conf = sum(m[1] for m in matched) / len(matched)
            return True, avg_conf, _format_evidence(matched)
        return False, 0.05, _format_evidence(matched)

    return False, 0.0, "unknown_policy"


def _format_evidence(matched: list) -> str:
    parts = []
    for field, conf, actual in matched:
        marker = "+" if conf > 0 else "-"
        val_str = str(actual)[:40] if actual is not None else "None"
        parts.append(f"{marker}{field}={val_str}")
    return "; ".join(parts)


# ============================================================
# 公共 API
# ============================================================

def detect_all(triage_result: dict, page_type: str = "feed") -> dict:
    """对所有原子故障进行独立检测，返回多标签向量。"""
    visual = triage_result.get("visual", {})
    functional = triage_result.get("functional", {})
    performance = triage_result.get("performance", {})

    assertion_space = {
        "visual": visual,
        "functional": functional,
        "performance": performance,
    }

    detected = {}
    confidence = {}
    evidence = {}

    for fault in ATOMIC_FAULTS:
        sig_pages, _, _ = SIGNATURES[fault]

        if page_type not in sig_pages:
            detected[fault] = 0
            confidence[fault] = 0.0
            evidence[fault] = f"not_applicable_on_{page_type}"
            continue

        det, conf, ev = _match_signature(SIGNATURES[fault], assertion_space)
        detected[fault] = 1 if det else 0
        confidence[fault] = round(conf, 3)
        evidence[fault] = ev

    return {
        "detected": detected,
        "confidence": confidence,
        "evidence": evidence,
    }


# ============================================================
# 评估工具
# ============================================================

def compute_metrics(results: list[dict]) -> dict:
    """根据所有测试用例结果，计算每个故障的 precision, recall, F1。"""
    stats = {f: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for f in ATOMIC_FAULTS}

    for case in results:
        oracle = case.get("oracle", {})
        detected = case.get("detected", {})
        for f in ATOMIC_FAULTS:
            expected = oracle.get(f, False)
            actual = detected.get(f, 0) == 1

            if expected and actual:
                stats[f]["tp"] += 1
            elif expected and not actual:
                stats[f]["fn"] += 1
            elif not expected and actual:
                stats[f]["fp"] += 1
            else:
                stats[f]["tn"] += 1

    metrics = {}
    for f in ATOMIC_FAULTS:
        s = stats[f]
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[f] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": s["tn"],
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }

    return metrics
