"""把 oracle 输出打平为可供分类器使用的特征向量。

特征向量结构（顺序固定，便于 sklearn 训练）：
    blur_score_full, blur_score_card, edge_density, mean_brightness,
    is_black_white, is_blur, ocr_text_len,
    interaction_ms, memory_warnings, perf_pass,
    func_visible_diff, func_has_overlap, func_is_blank,
    func_state_provided, func_pass,
    page_feed, page_counter, page_layout
"""
from __future__ import annotations

from typing import Dict, List, Tuple

FEATURE_NAMES: List[str] = [
    "blur_score_full",
    "blur_score_card",
    "edge_density",
    "mean_brightness",
    "is_black_white",
    "is_blur",
    "ocr_text_len",
    "interaction_ms",
    "memory_warnings",
    "perf_pass",
    "func_visible_diff",
    "func_has_overlap",
    "func_is_blank",
    "func_state_provided",
    "func_pass",
    "page_feed",
    "page_counter",
    "page_layout",
]

PAGES: Tuple[str, ...] = ("feed", "counter", "layout")
VERDICTS: Tuple[str, ...] = (
    "Pass",
    "PerformanceRisk",
    "RenderBug",
    "FunctionalFail",
    "Mixed",
)


def _to_int_bool(v) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return 1 if v else 0
    return 0


def _func_visible_diff(page_state: Dict) -> int:
    """visibleValue 与 expectedValue 不一致时返回 1，否则 0。

    类型差异（字符串 vs 数字）也算不一致。
    """
    if not page_state:
        return 0
    visible = page_state.get("visibleValue")
    expected = page_state.get("expectedValue")
    if visible is None or expected is None:
        return 0
    return 0 if visible == expected else 1


def extract_features(
    visual: Dict,
    functional: Dict,
    performance: Dict,
    page_type: str,
    page_state: Dict | None = None,
) -> List[float]:
    """把 oracle 输出 + 上下文打平成定长特征向量。

    入参容忍 None / 缺字段，缺字段以中性值填充。
    """
    visual = visual or {}
    functional = functional or {}
    performance = performance or {}
    page_state = page_state or {}

    blur_full = float(visual.get("blur_score_full", 0.0) or 0.0)
    blur_card = float(visual.get("blur_score", 0.0) or 0.0)
    edge_density = float(visual.get("edge_density", 0.0) or 0.0)
    mean_brightness = float(visual.get("mean_brightness", 0.0) or 0.0)
    is_bw = _to_int_bool(visual.get("black_white", False))
    is_blur = _to_int_bool(visual.get("is_blur", False))
    ocr_text = visual.get("ocr_text", "") or ""
    ocr_len = float(len(ocr_text))

    interaction_ms = float(performance.get("interaction_ms", 0) or 0)
    memory_warnings = float(performance.get("memory_warnings", 0) or 0)
    perf_pass = _to_int_bool(performance.get("pass", True))

    visible_diff = _func_visible_diff(page_state)
    ui_flags = page_state.get("uiFlags", {}) if page_state else {}
    has_overlap = _to_int_bool(ui_flags.get("hasOverlap", False))
    is_blank = _to_int_bool(ui_flags.get("isBlank", False))
    state_provided = 1 if page_state else 0
    func_pass = _to_int_bool(functional.get("pass", True))

    page_one_hot = [
        1.0 if page_type == "feed" else 0.0,
        1.0 if page_type == "counter" else 0.0,
        1.0 if page_type == "layout" else 0.0,
    ]

    return [
        blur_full,
        blur_card,
        edge_density,
        mean_brightness,
        float(is_bw),
        float(is_blur),
        ocr_len,
        interaction_ms,
        memory_warnings,
        float(perf_pass),
        float(visible_diff),
        float(has_overlap),
        float(is_blank),
        float(state_provided),
        float(func_pass),
        *page_one_hot,
    ]


def feature_names() -> List[str]:
    return list(FEATURE_NAMES)


def feature_groups() -> Dict[str, List[str]]:
    """按模态分组的特征，用于 ablation。"""
    return {
        "visual": [
            "blur_score_full",
            "blur_score_card",
            "edge_density",
            "mean_brightness",
            "is_black_white",
            "is_blur",
            "ocr_text_len",
        ],
        "performance": [
            "interaction_ms",
            "memory_warnings",
            "perf_pass",
        ],
        "functional": [
            "func_visible_diff",
            "func_has_overlap",
            "func_is_blank",
            "func_state_provided",
            "func_pass",
        ],
        "context": [
            "page_feed",
            "page_counter",
            "page_layout",
        ],
    }


def neutral_value_for(feature_name: str) -> float:
    """ablation 用：把某组特征置成中性值。"""
    if feature_name in ("blur_score_full", "blur_score_card"):
        return 500.0
    if feature_name == "edge_density":
        return 0.15
    if feature_name == "mean_brightness":
        return 150.0
    if feature_name == "ocr_text_len":
        return 0.0
    if feature_name == "interaction_ms":
        return 100.0
    if feature_name == "memory_warnings":
        return 0.0
    if feature_name in ("perf_pass", "func_pass"):
        return 1.0
    return 0.0
