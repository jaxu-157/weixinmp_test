"""为欠采样类合成额外训练样本。

策略：
1. 以现有 mined 样本为锚点，对数值特征加高斯噪声，得到"近邻样本"
2. 对于完全没锚点的 (page, profile) 组合，按 EXPECT_MATRIX 的语义构造原型样本
"""
from __future__ import annotations

import os
import sys
import random
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose.feature_extractor import FEATURE_NAMES, VERDICTS, extract_features  # noqa: E402


# 数值特征的扰动比例（相对于自身值的 sigma）
NUMERIC_NOISE = {
    "blur_score_full": 0.25,
    "blur_score_card": 0.25,
    "edge_density": 0.30,
    "mean_brightness": 0.15,
    "ocr_text_len": 0.20,
    "interaction_ms": 0.20,
}

# 布尔/计数特征以一定概率翻转或扰动 1 个单位
BOOL_FLIP_PROB = 0.0  # 默认不翻转，保留 ground-truth 语义


def _add_noise(feats: List[float], rng: random.Random) -> List[float]:
    out = list(feats)
    for i, name in enumerate(FEATURE_NAMES):
        if name in NUMERIC_NOISE:
            sigma_ratio = NUMERIC_NOISE[name]
            base = out[i]
            # 用 max(base, 1.0) 避免接近 0 时 sigma 退化为 0
            sigma = max(abs(base), 1.0) * sigma_ratio
            out[i] = max(0.0, base + rng.gauss(0.0, sigma))
        elif name == "memory_warnings":
            # 计数轻微扰动
            if rng.random() < 0.05 and out[i] > 0:
                out[i] = max(0, out[i] + rng.choice([-1, 1]))
    return out


# ============ 原型样本：给完全没锚点的组合用 ============

# 把 EXPECT_MATRIX 中的每个 (page, profile) 对应到一个典型特征向量
# 这些值与 auto_test_runner._collect_perf_data 和实际 oracle 输出保持一致
def _build_prototype(page: str, profile: str, verdict: str) -> List[float]:
    """构造一个该 (page, profile) → verdict 的典型样本特征。"""

    # 视觉默认值（normal 状态）
    visual = {
        "blur_score_full": 500.0,
        "blur_score": 300.0,
        "edge_density": 0.12,
        "mean_brightness": 170.0,
        "black_white": False,
        "is_blur": False,
        "ocr_text": "",
    }
    performance = {
        "pass": True,
        "interaction_ms": 100,
        "memory_warnings": 0,
    }
    functional = {"pass": True}

    page_state = {}

    if profile == "blur_image":
        visual["is_blur"] = True
        visual["blur_score"] = 40.0
        visual["blur_score_full"] = 60.0
        visual["edge_density"] = 0.03
    if profile == "slow_api":
        performance["pass"] = False
        performance["interaction_ms"] = 900
    if profile == "memory_pressure":
        performance["pass"] = False
        performance["memory_warnings"] = 1
    if profile == "stale_ui":
        functional["pass"] = False
        page_state = {"visibleValue": 0, "expectedValue": 1}
    if profile == "wrong_mapping":
        functional["pass"] = False
        page_state = {"visibleValue": "undefined", "expectedValue": 1}
    if profile == "layout_overlap":
        functional["pass"] = False
        page_state = {"uiFlags": {"hasOverlap": True}}
    if profile == "mixed_fault":
        performance["pass"] = False
        performance["interaction_ms"] = 900
        if page == "feed":
            visual["is_blur"] = True
            visual["blur_score"] = 50.0
            visual["edge_density"] = 0.04
        elif page == "counter":
            functional["pass"] = False
            page_state = {"visibleValue": 0, "expectedValue": 1}

    return extract_features(visual, functional, performance, page, page_state)


# 期望矩阵的展开形式：(page, profile, verdict)
EXPECTED_TRIPLES = [
    ("feed", "normal", "Pass"),
    ("feed", "slow_api", "PerformanceRisk"),
    ("feed", "blur_image", "RenderBug"),
    ("feed", "memory_pressure", "PerformanceRisk"),
    ("feed", "mixed_fault", "Mixed"),
    ("counter", "normal", "Pass"),
    ("counter", "slow_api", "PerformanceRisk"),
    ("counter", "stale_ui", "FunctionalFail"),
    ("counter", "wrong_mapping", "FunctionalFail"),
    ("counter", "mixed_fault", "Mixed"),
    ("layout", "normal", "Pass"),
    ("layout", "slow_api", "PerformanceRisk"),
    ("layout", "layout_overlap", "FunctionalFail"),
    ("layout", "memory_pressure", "PerformanceRisk"),
]


def synthesize_balanced(
    mined_X: List[List[float]],
    mined_y: List[str],
    mined_meta: List[dict],
    target_per_class: int = 60,
    seed: int = 42,
) -> Tuple[List[List[float]], List[str], List[dict]]:
    """把每个 verdict 类补齐到 target_per_class 条。

    优先用 mined 样本加噪扩增；mined 不够时用原型 + 加噪兜底。
    """
    rng = random.Random(seed)

    # 按 verdict 分桶
    buckets: dict = {v: [] for v in VERDICTS}
    bucket_meta: dict = {v: [] for v in VERDICTS}
    for x, y_, m in zip(mined_X, mined_y, mined_meta):
        buckets[y_].append(x)
        bucket_meta[y_].append(m)

    # 同时按 verdict 收集对应的原型
    proto_by_verdict: dict = {v: [] for v in VERDICTS}
    for page, profile, verdict in EXPECTED_TRIPLES:
        proto_by_verdict[verdict].append(_build_prototype(page, profile, verdict))

    out_X: List[List[float]] = list(mined_X)
    out_y: List[str] = list(mined_y)
    out_meta: List[dict] = list(mined_meta)

    for verdict in VERDICTS:
        existing = len(buckets[verdict])
        need = max(0, target_per_class - existing)
        if need <= 0:
            continue

        anchors = buckets[verdict] + proto_by_verdict[verdict]
        if not anchors:
            continue

        for i in range(need):
            anchor = rng.choice(anchors)
            noisy = _add_noise(anchor, rng)
            out_X.append(noisy)
            out_y.append(verdict)
            out_meta.append({
                "page": "synthetic",
                "profile": "synthetic",
                "source": "synthesize.py",
                "anchor_kind": "mined" if anchor in buckets[verdict] else "prototype",
            })

    return out_X, out_y, out_meta


if __name__ == "__main__":
    from diagnose.training.mine_corpus import mine, class_counts

    X, y, meta = mine()
    print(f"mined: {len(X)} 样本, 类别 = {class_counts(y)}")

    X2, y2, meta2 = synthesize_balanced(X, y, meta, target_per_class=80)
    print(f"after synthesize: {len(X2)} 样本, 类别 = {class_counts(y2)}")
