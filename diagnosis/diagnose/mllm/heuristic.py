"""HeuristicMLLM: 不依赖 API 的强化视觉重判器。

充当 cascade 中的"第二阶段"。比规则法多用了：
- 多尺度 Laplacian（金字塔降采样，挑最小值）
- 9-patch 局部模糊投票
- HSV 饱和度均值（褪色/黑白屏检出）
- Sobel 梯度峭度（亚像素模糊敏感）

这样即使没有真正的 MLLM API key，cascade 也能展示"贵 oracle 比便宜 oracle 强"的效应。
真实 MLLM 实现见 dashscope_qwen_vl.py。
"""
from __future__ import annotations

import time
from typing import Tuple

import cv2
import numpy as np

from .base import OracleResult


def _decode(image_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _multi_scale_blur(gray: np.ndarray) -> Tuple[float, list]:
    """金字塔多尺度 Laplacian 方差，取最小值（最保守）。"""
    scores = []
    cur = gray
    for _ in range(3):
        lap = cv2.Laplacian(cur, cv2.CV_64F)
        scores.append(float(lap.var()))
        if min(cur.shape) < 20:
            break
        cur = cv2.pyrDown(cur)
    return min(scores) if scores else 0.0, scores


def _patch_blur_vote(gray: np.ndarray, threshold: float = 100.0) -> Tuple[float, int]:
    """3x3 patch 分块模糊投票。返回 (平均分, 模糊 patch 数)。"""
    h, w = gray.shape[:2]
    ph, pw = h // 3, w // 3
    if ph < 8 or pw < 8:
        return 0.0, 0
    scores = []
    blur_count = 0
    for r in range(3):
        for c in range(3):
            patch = gray[r * ph:(r + 1) * ph, c * pw:(c + 1) * pw]
            if patch.size == 0:
                continue
            v = float(cv2.Laplacian(patch, cv2.CV_64F).var())
            scores.append(v)
            if v < threshold:
                blur_count += 1
    return (sum(scores) / max(len(scores), 1)), blur_count


def _saturation_mean(image: np.ndarray) -> float:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 1].mean())


def _sobel_kurtosis(gray: np.ndarray) -> float:
    """Sobel 梯度模长分布的峭度。

    清晰图 → 重尾分布（高 kurtosis）；模糊图 → 接近正态（低 kurtosis）。
    """
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy).flatten()
    if mag.size < 100:
        return 0.0
    m = mag.mean()
    s = mag.std()
    if s < 1e-6:
        return 0.0
    z = (mag - m) / s
    return float((z ** 4).mean() - 3.0)


class HeuristicMLLM:
    """启发式强化视觉 oracle。"""

    name = "heuristic_mllm_v1"
    # 估算成本：本地 CPU 一次推理 ~50ms，无外部计费
    cost_per_call_ms = 50.0
    cost_per_call_dollars = 0.0

    def analyze(self, image_bytes: bytes, page_type: str = "feed") -> OracleResult:
        t0 = time.time()
        image = _decode(image_bytes)
        if image is None:
            return OracleResult(
                source=self.name,
                reasoning="无法解码图像",
                confidence=0.0,
            )

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        ms_blur, ms_scores = _multi_scale_blur(gray)
        patch_avg, patch_blur_n = _patch_blur_vote(gray, threshold=80.0)
        sat = _saturation_mean(image)
        kurt = _sobel_kurtosis(gray)
        brightness = float(gray.mean())

        # 决策逻辑（这些阈值是基于经验设的，可在后续迭代中校准）
        is_black = brightness < 25.0
        is_white = brightness > 235.0
        is_blank = is_black or is_white or (sat < 8.0 and (brightness < 50 or brightness > 200))

        # 模糊判定：多尺度 < 50 或 半数以上 patch 模糊 或 梯度峭度过低
        is_blur = (
            ms_blur < 50.0
            or patch_blur_n >= 5
            or (kurt < 0.5 and brightness > 30 and not is_blank)
        )

        # 信心度：所有信号一致 → 高；分歧 → 低
        signals = [int(is_blur), int(is_blank), int(ms_blur < 80), int(patch_blur_n >= 4)]
        agreement = max(sum(signals), 4 - sum(signals)) / 4.0
        confidence = round(0.5 + (agreement - 0.5) * 0.9, 3)

        reasoning_parts = [
            f"ms_blur={ms_blur:.1f}",
            f"patch_avg={patch_avg:.1f}",
            f"patch_blur_n={patch_blur_n}/9",
            f"saturation={sat:.1f}",
            f"brightness={brightness:.1f}",
            f"sobel_kurt={kurt:.2f}",
        ]

        cost_ms = (time.time() - t0) * 1000.0
        return OracleResult(
            has_blur=bool(is_blur and not is_blank),
            has_blank=bool(is_blank),
            has_overlap=False,
            has_missing_image=False,
            confidence=confidence,
            reasoning="; ".join(reasoning_parts),
            cost_ms=cost_ms,
            cost_dollars=0.0,
            source=self.name,
            extra={
                "ms_blur": ms_blur,
                "ms_scores": ms_scores,
                "patch_avg": patch_avg,
                "patch_blur_n": patch_blur_n,
                "saturation": sat,
                "brightness": brightness,
                "sobel_kurtosis": kurt,
            },
        )
