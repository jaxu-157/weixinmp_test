"""分诊决策模块 - 三重断言融合"""
import cv2
import numpy as np
from .blur import detect_blur
from .screen import detect_blank_screen
from .ocr import extract_text


# 阈值配置
PERF_THRESHOLD_MS = 800  # 交互延迟阈值
BLUR_THRESHOLD = 100.0   # 模糊分数阈值


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
    """视觉断言：黑白屏 + 模糊 + OCR"""
    blank = detect_blank_screen(image)
    blur = detect_blur(image)
    ocr = extract_text(image)

    is_visual_fail = blank["is_black"] or blank["is_white"] or blur["is_blur"]

    return {
        "pass": not is_visual_fail,
        "black_white": blank["is_black"] or blank["is_white"],
        "blur_score": blur["score"],
        "is_blur": blur["is_blur"],
        "ocr_text": ocr["full_text"][:200],
        "mean_brightness": blank["mean_brightness"],
    }


def _run_functional_assertions(page_state: dict, page_type: str) -> dict:
    """功能断言：检查可见值与期望值是否一致"""
    if not page_state:
        return {"pass": True, "reason": "no_state_provided"}

    visible = page_state.get("visibleValue")
    expected = page_state.get("expectedValue")

    if visible is None or expected is None:
        return {"pass": True, "reason": "values_not_applicable"}

    if visible != expected:
        return {
            "pass": False,
            "reason": f"visible={visible}, expected={expected}",
        }

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
