"""WeBug (ICSE'22) 三类 bug 模式的运行时映射规则。

WeBug 原论文做的是**静态分析**（扫源码找模式），我们这里做**运行时映射**：
不需要源码也能用，输入是 (截图, perf, dom_snapshot, 业务断言) 这套黑盒信号。

三条 bug 模式 → 三条规则：

  R1. PLATFORM_API_MISUSE
      原义：调用 wx API 不处理 fail 回调，导致接口失败时页面无反馈。
      运行时映射：
        在一次交互之后，interaction_ms 超 timeout 但页面没有任何视觉变化
        （current 与 pre-action 截图 SSIM > 0.999）→ 用户看不到任何反馈。
      触发字段：r1_api_timeout_no_feedback

  R2. INCOMPLETE_LAYOUT_ADAPTATION
      原义：在不同屏幕尺寸下页面溢出/截断。
      运行时映射：
        - 视觉内容紧贴或超出屏幕边缘（边缘 8 像素带的非背景像素占比异常高）
        - 或：水平 / 垂直滚动条出现（用 DOM scrollHeight > clientHeight 判断；
          无 DOM 时退化为边缘内容检测）
      触发字段：r2_layout_overflow

  R3. ASYNC_CALLBACK_DATA_MISMATCH
      原义：异步回调拿到的字段名/类型与预期不一致。
      运行时映射：
        - 业务上报的 visibleValue / expectedValue 类型或值不一致
        - 或：DOM 中存在 "undefined" / "[object Object]" 这种典型字符串
      触发字段：r3_async_data_mismatch

每条规则输出 bool 信号，可以作为 feature_extractor 的额外补丁特征。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

import numpy as np
from PIL import Image


# ---- R1: API timeout but no visual feedback ----

API_TIMEOUT_MS = 1500  # 一次 tap 超过这个时间还没有视觉反馈算异常
NO_VISUAL_CHANGE_SSIM = 0.999  # 反应：动作前后画面几乎完全一致

# ---- R2: layout overflow ----

EDGE_BAND_PX = 8
EDGE_BG_TOLERANCE = 25  # 边缘像素与背景色差 < 此值算"背景"
EDGE_CONTENT_RATIO_THRESHOLD = 0.18  # 边缘带 >18% 非背景像素 → 溢出

# ---- R3: async data mismatch ----

SUSPICIOUS_STRINGS = ("undefined", "null", "NaN", "[object Object]", "{{")


@dataclass
class WeBugSignals:
    r1_api_timeout_no_feedback: bool
    r2_layout_overflow: bool
    r3_async_data_mismatch: bool
    # 额外的解释证据
    r1_evidence: str
    r2_evidence: str
    r3_evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def any_triggered(self) -> bool:
        return self.r1_api_timeout_no_feedback or self.r2_layout_overflow or self.r3_async_data_mismatch


# -------- R1 --------

def detect_r1_api_no_feedback(
    interaction_ms: Optional[float],
    pre_action_img: Optional[np.ndarray],
    post_action_img: Optional[np.ndarray],
) -> tuple[bool, str]:
    if interaction_ms is None or interaction_ms < API_TIMEOUT_MS:
        return False, f"interaction_ms={interaction_ms} below threshold {API_TIMEOUT_MS}"
    if pre_action_img is None or post_action_img is None:
        return False, "no pre/post screenshots"
    try:
        from skimage.metrics import structural_similarity as ssim
    except ImportError:
        return False, "skimage unavailable"
    a = _to_gray(pre_action_img)
    b = _to_gray(post_action_img)
    if a.shape != b.shape:
        return False, "pre/post size mismatch"
    score = float(ssim(a, b, data_range=255))
    if score >= NO_VISUAL_CHANGE_SSIM:
        return True, f"interaction_ms={interaction_ms:.0f} but pre/post SSIM={score:.4f} (no visual response)"
    return False, f"interaction_ms={interaction_ms:.0f}, pre/post SSIM={score:.4f} (visual response present)"


# -------- R2 --------

def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        img = img[..., :3]
    return (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.uint8)


def _estimate_bg_color(img: np.ndarray) -> np.ndarray:
    """用四角 16x16 块的中位数估计背景色。"""
    h, w = img.shape[:2]
    s = 16
    corners = np.concatenate([
        img[:s, :s].reshape(-1, img.shape[2]),
        img[:s, -s:].reshape(-1, img.shape[2]),
        img[-s:, :s].reshape(-1, img.shape[2]),
        img[-s:, -s:].reshape(-1, img.shape[2]),
    ], axis=0)
    return np.median(corners, axis=0)


def detect_r2_layout_overflow(
    img: np.ndarray,
    dom_info: Optional[dict] = None,
) -> tuple[bool, str]:
    """DOM 可用时直接看 scrollHeight；否则用边缘带启发式。"""
    # 1) DOM 优先
    if dom_info:
        sh = dom_info.get("scrollHeight")
        ch = dom_info.get("clientHeight")
        sw = dom_info.get("scrollWidth")
        cw = dom_info.get("clientWidth")
        if isinstance(sh, (int, float)) and isinstance(ch, (int, float)) and ch:
            if sh > ch * 1.05:
                return True, f"dom: scrollHeight={sh}>clientHeight={ch}"
        if isinstance(sw, (int, float)) and isinstance(cw, (int, float)) and cw:
            if sw > cw * 1.05:
                return True, f"dom: scrollWidth={sw}>clientWidth={cw}"
        # DOM 给的明确无溢出，认了
        if isinstance(sh, (int, float)) and isinstance(ch, (int, float)):
            return False, f"dom: scrollHeight={sh}<=clientHeight={ch}"

    # 2) 视觉 fallback
    if img is None:
        return False, "no image"
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    if img.shape[2] == 4:
        img = img[..., :3]
    h, w = img.shape[:2]
    bg = _estimate_bg_color(img)
    bands = [
        img[:EDGE_BAND_PX, :, :],
        img[-EDGE_BAND_PX:, :, :],
        img[:, :EDGE_BAND_PX, :],
        img[:, -EDGE_BAND_PX:, :],
    ]
    total = 0
    non_bg = 0
    for b in bands:
        diff = np.abs(b.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
        non_bg += int((diff > EDGE_BG_TOLERANCE).sum())
        total += int(b.shape[0] * b.shape[1])
    ratio = non_bg / max(total, 1)
    if ratio > EDGE_CONTENT_RATIO_THRESHOLD:
        return True, f"edge non-bg ratio={ratio:.3f} > {EDGE_CONTENT_RATIO_THRESHOLD}"
    return False, f"edge non-bg ratio={ratio:.3f}"


# -------- R3 --------

def detect_r3_async_mismatch(
    visible_value=None,
    expected_value=None,
    dom_text: Optional[str] = None,
) -> tuple[bool, str]:
    """业务断言不一致 或 DOM 出现典型异步异常文本。"""
    if visible_value is not None and expected_value is not None:
        if type(visible_value) is not type(expected_value):
            return True, f"type mismatch: visible={type(visible_value).__name__} vs expected={type(expected_value).__name__}"
        if visible_value != expected_value:
            return True, f"value mismatch: visible={visible_value!r} vs expected={expected_value!r}"

    if dom_text:
        for s in SUSPICIOUS_STRINGS:
            if s in dom_text:
                return True, f"dom contains suspicious token: {s!r}"

    return False, "no mismatch detected"


# -------- 顶层入口 --------

def evaluate_webug(
    *,
    pre_action_img: Optional[np.ndarray] = None,
    post_action_img: Optional[np.ndarray] = None,
    final_img: Optional[np.ndarray] = None,
    interaction_ms: Optional[float] = None,
    dom_info: Optional[dict] = None,
    dom_text: Optional[str] = None,
    visible_value=None,
    expected_value=None,
) -> WeBugSignals:
    r1, r1_ev = detect_r1_api_no_feedback(interaction_ms, pre_action_img, post_action_img)
    r2, r2_ev = detect_r2_layout_overflow(final_img if final_img is not None else post_action_img, dom_info)
    r3, r3_ev = detect_r3_async_mismatch(visible_value, expected_value, dom_text)
    return WeBugSignals(
        r1_api_timeout_no_feedback=r1,
        r2_layout_overflow=r2,
        r3_async_data_mismatch=r3,
        r1_evidence=r1_ev,
        r2_evidence=r2_ev,
        r3_evidence=r3_ev,
    )


if __name__ == "__main__":
    print("=== self-test webug_rules ===")
    # R1: 长交互无视觉变化
    fake_img = (np.ones((240, 160, 3), dtype=np.uint8) * 220)
    sig = evaluate_webug(
        pre_action_img=fake_img,
        post_action_img=fake_img.copy(),
        interaction_ms=2300,
    )
    print(f"R1 (timeout no feedback): triggered={sig.r1_api_timeout_no_feedback}  | {sig.r1_evidence}")

    # R2 视觉 fallback: 边缘有大量非背景内容
    overflow_img = (np.ones((240, 160, 3), dtype=np.uint8) * 220)
    overflow_img[:4, :, :] = (30, 30, 30)        # 顶边贴满深色
    overflow_img[-4:, :, :] = (30, 30, 30)       # 底边贴满
    sig2 = evaluate_webug(final_img=overflow_img)
    print(f"R2 (layout overflow visual): triggered={sig2.r2_layout_overflow}  | {sig2.r2_evidence}")

    # R2 DOM 路径
    sig2b = evaluate_webug(final_img=fake_img, dom_info={"scrollHeight": 1200, "clientHeight": 600})
    print(f"R2 (overflow via dom): triggered={sig2b.r2_layout_overflow}  | {sig2b.r2_evidence}")

    # R3 业务断言
    sig3 = evaluate_webug(visible_value=7, expected_value=10)
    print(f"R3 (mismatch): triggered={sig3.r3_async_data_mismatch}  | {sig3.r3_evidence}")

    # R3 DOM 文本
    sig3b = evaluate_webug(dom_text="hello undefined world")
    print(f"R3 (dom token): triggered={sig3b.r3_async_data_mismatch}  | {sig3b.r3_evidence}")

    # all-normal
    sig0 = evaluate_webug(visible_value=10, expected_value=10, final_img=fake_img,
                           interaction_ms=200,
                           pre_action_img=fake_img, post_action_img=fake_img.copy())
    print(f"normal: any={sig0.any_triggered}")
