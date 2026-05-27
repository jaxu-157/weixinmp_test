"""Cascade Visual Oracle: 便宜规则 → 模糊时升级到 MLLM。

工作流：
    1. 跑一遍现有规则 oracle（_run_visual_assertions），拿到 blur_score / edge_density / ...
    2. 评估"是否落在模糊带"
       - blur_score 远高于阈值 且 边缘密度足够 → confident_pass，直接出
       - blur_score 远低于阈值 且 边缘密度极低 → confident_fail，直接出
       - 否则 → escalate 到 MLLM
    3. MLLM 返回结构化结果，覆盖/合并到 visual 字典
    4. 记录每次决策的成本与是否 escalate，便于绘制成本-准确率曲线
"""
from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

from . import triage as rule_triage
from .mllm import OracleResult, default_mllm
from .mllm.base import VisualOracle


# 升级阈值：blur_score（Laplacian 方差）落在 [LOW, HIGH] 之间算"模糊歧义带"，需要升级。
# v2 校准（2026-05-26）：升级判定**只看 blur_score，不再用 edge_density 当 pass 门槛**。
#   原因：edge_density 是"页面内容稠密度"的代理，不是"模糊度"的信号——文字稀疏但很清晰的页面
#   （如 counter 计数页 blur≈429 / edge≈0.023）会被旧逻辑 (blur>=400 AND edge>=0.08) 误判为歧义、
#   白白升级到 MLLM 烧钱。模糊会拉低 Laplacian 方差，所以 blur_score 本身就足以判"够清晰"。
ESCALATE_BLUR_LOW = 30.0    # ≤ 此值：规则法自信判"模糊/空白"（无需升级）
ESCALATE_BLUR_HIGH = 400.0  # ≥ 此值：规则法自信判"足够清晰"（无需升级，与 edge 无关）


def _is_confident_zone(blur_score: float, edge_density: float, is_bw: bool) -> Optional[bool]:
    """返回 True=自信 Pass, False=自信 Fail, None=落在模糊歧义带需升级到 MLLM。

    注意：edge_density 形参保留是为接口兼容，**不再参与 pass 判定**（见上方校准说明）。
    """
    if is_bw and blur_score <= ESCALATE_BLUR_LOW:
        return False  # 真正黑/白屏 + 无结构 → 自信 Fail
    if is_bw and blur_score > ESCALATE_BLUR_LOW:
        return None   # 可能稀疏页面误判为白屏 → 升级让 Qwen 判断
    if blur_score >= ESCALATE_BLUR_HIGH:
        return True   # 足够清晰，自信 Pass
    if blur_score <= ESCALATE_BLUR_LOW:
        return False  # 足够模糊/空白，自信 Fail
    return None       # 30 < blur < 400：真正的歧义带，升级到 MLLM


class CascadeOracle:
    """规则 → MLLM 级联视觉 oracle。"""

    def __init__(self, mllm: Optional[VisualOracle] = None):
        # 默认走工厂：有 Qwen key 用真实 MLLM，否则回退启发式
        self.mllm = mllm or default_mllm()

    def analyze(self, image_bytes: bytes, page_type: str = "feed") -> dict:
        """返回与 _run_visual_assertions 兼容的 dict，外加 cascade 元数据。"""
        t0 = time.time()

        # 1. 规则法
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            return {
                "pass": False,
                "black_white": False,
                "blur_score": 0.0,
                "blur_score_full": 0.0,
                "is_blur": True,
                "edge_density": 0.0,
                "ocr_text": "",
                "mean_brightness": 0.0,
                "cascade": {
                    "escalated": False,
                    "reason": "decode_failed",
                    "stage_ms": 0.0,
                    "total_ms": 0.0,
                },
            }

        rule_result = rule_triage._run_visual_assertions(image, page_type)
        rule_ms = (time.time() - t0) * 1000.0

        # 2. 判断是否升级
        confident = _is_confident_zone(
            rule_result.get("blur_score_full", 0.0),
            rule_result.get("edge_density", 0.0),
            bool(rule_result.get("black_white", False)),
        )

        if confident is not None:
            # 不升级
            total_ms = (time.time() - t0) * 1000.0
            rule_result["cascade"] = {
                "escalated": False,
                "reason": "confident_pass" if confident else "confident_fail",
                "rule_ms": rule_ms,
                "mllm_ms": 0.0,
                "total_ms": total_ms,
                "cost_dollars": 0.0,
            }
            return rule_result

        # 3. 升级到 MLLM
        mllm_result: OracleResult = self.mllm.analyze(image_bytes, page_type)

        # 4. 合并：MLLM 的判断覆盖规则法的 is_blur / black_white
        merged = dict(rule_result)
        if mllm_result.confidence >= 0.6:
            # 高置信度 MLLM 才覆盖
            merged["is_blur"] = mllm_result.has_blur
            merged["black_white"] = mllm_result.has_blank
            merged["pass"] = not (mllm_result.has_blur or mllm_result.has_blank
                                  or mllm_result.has_overlap or mllm_result.has_missing_image)
            # Qwen 说清晰 → 拉高 blur_score，防止下游 learned_triage 因低 blur 误判
            if not mllm_result.has_blur and not mllm_result.has_blank:
                merged["blur_score_full"] = max(merged.get("blur_score_full", 0), ESCALATE_BLUR_HIGH)
                merged["blur_score"] = max(merged.get("blur_score", 0), ESCALATE_BLUR_HIGH)
        # 把 MLLM 输出附加到结果上，方便 learned-triage 拿到额外特征
        merged["mllm"] = mllm_result.as_dict()

        total_ms = (time.time() - t0) * 1000.0
        merged["cascade"] = {
            "escalated": True,
            "reason": "ambiguous",
            "rule_ms": rule_ms,
            "mllm_ms": mllm_result.cost_ms,
            "total_ms": total_ms,
            "cost_dollars": mllm_result.cost_dollars,
            "mllm_source": mllm_result.source,
            "mllm_confidence": mllm_result.confidence,
        }
        return merged
