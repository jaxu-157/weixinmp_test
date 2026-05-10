"""分诊决策模块 - 三重断言融合"""
import cv2
import numpy as np
from .blur import detect_blur
from .screen import detect_blank_screen
from .ocr import extract_text


# 阈值配置
PERF_THRESHOLD_MS = 800        # 交互延迟阈值
BLUR_THRESHOLD_FULL = 100.0    # 全屏模糊阈值
BLUR_THRESHOLD_ROI = 300.0     # ROI区域模糊阈值
BLUR_THRESHOLD_CARD = 200.0    # 卡片图片区域模糊阈值
EDGE_DENSITY_LOW = 0.05        # 边缘密度低于此值判定为模糊/异常


def run_triage(
    image_bytes: bytes,
    page_type: str = "feed",
    fault_profile: str = "normal",
    page_state: dict = None,
    perf_data: dict = None,
) -> dict:
    """
    执行完整分诊流程。
    
    Returns:
        {
            "visual": { 视觉断言结果 },
            "functional": { 功能断言结果 },
            "performance": { 性能断言结果 },
            "verdict": str,
            "explanation": str
        }
    """
    page_state = page_state or {}
    perf_data = perf_data or {}

    # 解码图像
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        return _error_result("无法解码图像")

    # ======== 视觉断言 ========
    visual_result = _run_visual_assertions(image, page_type)

    # ======== 功能断言 ========
    functional_result = _run_functional_assertions(page_state, page_type)

    # ======== 性能断言 ========
    performance_result = _run_performance_assertions(perf_data)

    # ======== 分诊决策 ========
    verdict, explanation = _decide_verdict(
        visual_result, functional_result, performance_result
    )

    return {
        "visual": visual_result,
        "functional": functional_result,
        "performance": performance_result,
        "verdict": verdict,
        "explanation": explanation,
    }


def _run_visual_assertions(image: np.ndarray, page_type: str) -> dict:
    """视觉断言：黑白屏 + 多级模糊检测 + 边缘密度 + OCR"""
    blank = detect_blank_screen(image)
    h, w = image.shape[:2]

    # 1. 全屏模糊
    blur_full = detect_blur(image, threshold=BLUR_THRESHOLD_FULL)

    # 2. ROI 模糊（跳过导航栏和tabbar）
    roi = image[int(h * 0.15):int(h * 0.85), :]
    blur_roi = detect_blur(roi, threshold=BLUR_THRESHOLD_ROI)

    # 3. 卡片图片区域模糊采样（仅 feed 页双列布局有效）
    card_blur_scores = []
    card_is_blur = False
    if page_type == "feed":
        card_regions = [
            (0.06, 0.32, 0.02, 0.48),  # 左上卡片
            (0.06, 0.32, 0.52, 0.98),  # 右上卡片
            (0.40, 0.62, 0.02, 0.48),  # 左下卡片
            (0.40, 0.62, 0.52, 0.98),  # 右下卡片
        ]
        for (y1r, y2r, x1r, x2r) in card_regions:
            y1, y2 = int(h * y1r), int(h * y2r)
            x1, x2 = int(w * x1r), int(w * x2r)
            patch = image[y1:y2, x1:x2]
            if patch.size > 0:
                card_blur_scores.append(detect_blur(patch)["score"])
        avg_card_score = sum(card_blur_scores) / max(len(card_blur_scores), 1)
        card_is_blur = avg_card_score < BLUR_THRESHOLD_CARD
    avg_card_score = sum(card_blur_scores) / max(len(card_blur_scores), 1) if card_blur_scores else blur_roi["score"]

    # 4. 边缘密度（Canny）
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray_roi, 50, 150)
    edge_density = float(np.sum(edges > 0) / edges.size)
    edge_too_low = edge_density < EDGE_DENSITY_LOW

    # 综合判定：全图模糊 或 卡片区域模糊 触发
    # 边缘密度仅对图片密集页(feed)生效，counter/layout页面天然边缘少
    is_blur = blur_full["is_blur"] or card_is_blur
    if page_type == "feed" and edge_too_low:
        is_blur = True

    ocr = extract_text(image)
    is_visual_fail = blank["is_black"] or blank["is_white"] or is_blur

    return {
        "pass": not is_visual_fail,
        "black_white": blank["is_black"] or blank["is_white"],
        "blur_score": round(avg_card_score, 2),
        "blur_score_full": blur_full["score"],
        "is_blur": is_blur,
        "edge_density": round(edge_density, 4),
        "ocr_text": ocr["full_text"][:200],
        "mean_brightness": blank["mean_brightness"],
    }


def _run_functional_assertions(page_state: dict, page_type: str) -> dict:
    """功能断言：检查可见值一致性 + UI标记异常"""
    if not page_state:
        return {"pass": True, "reason": "no_state_provided"}

    reasons = []

    # 检查值一致性
    visible = page_state.get("visibleValue")
    expected = page_state.get("expectedValue")
    if visible is not None and expected is not None and visible != expected:
        reasons.append(f"visible={visible}, expected={expected}")

    # 检查UI标记（布局重叠、空白等）
    ui_flags = page_state.get("uiFlags", {})
    if ui_flags.get("hasOverlap"):
        reasons.append("layout_overlap_detected")
    if ui_flags.get("isBlank"):
        reasons.append("page_is_blank")

    if reasons:
        return {"pass": False, "reason": "; ".join(reasons)}

    return {"pass": True, "reason": ""}


def _run_performance_assertions(perf_data: dict) -> dict:
    """性能断言：检查交互延迟和内存告警"""
    if not perf_data:
        return {"pass": True, "reason": "no_perf_data"}

    interaction_ms = perf_data.get("interactionMs", 0)
    memory_warnings = perf_data.get("memoryWarningCount", 0)

    reasons = []
    if interaction_ms > PERF_THRESHOLD_MS:
        reasons.append(f"interaction_latency={interaction_ms}ms")
    if memory_warnings > 0:
        reasons.append(f"memory_warnings={memory_warnings}")

    is_pass = len(reasons) == 0

    return {
        "pass": is_pass,
        "reason": "; ".join(reasons) if reasons else "",
        "interaction_ms": interaction_ms,
        "memory_warnings": memory_warnings,
    }


def _decide_verdict(visual: dict, functional: dict, performance: dict) -> tuple:
    """
    分诊决策矩阵：
    | Afunc | Aperf | Avisual | Verdict |
    |-------|-------|---------|---------|
    | Pass  | Pass  | Pass    | Pass    |
    | Pass  | Fail  | Pass    | PerformanceRisk |
    | Pass  | Pass  | Fail    | RenderBug |
    | Fail  | Pass  | Pass    | FunctionalFail |
    | Fail  | Fail  | *       | Mixed |
    | Pass  | Fail  | Fail    | Mixed |
    | Fail  | Pass  | Fail    | Mixed |
    """
    f_pass = functional.get("pass", True)
    p_pass = performance.get("pass", True)
    v_pass = visual.get("pass", True)

    if f_pass and p_pass and v_pass:
        return "Pass", "所有断言通过"

    if f_pass and not p_pass and v_pass:
        return "PerformanceRisk", f"功能正确但性能不达标: {performance.get('reason', '')}"

    if f_pass and p_pass and not v_pass:
        reason_parts = []
        if visual.get("black_white"):
            reason_parts.append("检测到黑/白屏")
        if visual.get("is_blur"):
            reason_parts.append(f"图像模糊(score={visual.get('blur_score')})")
        return "RenderBug", f"视觉异常: {'; '.join(reason_parts)}"

    if not f_pass and p_pass and v_pass:
        return "FunctionalFail", f"功能断言失败: {functional.get('reason', '')}"

    # 多重故障 -> Mixed
    reasons = []
    if not f_pass:
        reasons.append(f"功能: {functional.get('reason', '')}")
    if not p_pass:
        reasons.append(f"性能: {performance.get('reason', '')}")
    if not v_pass:
        reasons.append("视觉异常")
    return "Mixed", f"混合故障: {'; '.join(reasons)}"


def _error_result(msg: str) -> dict:
    return {
        "visual": {"pass": False, "error": msg},
        "functional": {"pass": False, "error": msg},
        "performance": {"pass": False, "error": msg},
        "verdict": "Unknown",
        "explanation": msg,
    }
