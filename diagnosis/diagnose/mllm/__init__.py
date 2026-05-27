"""视觉 oracle 强化层：cascade 中的 MLLM/重判模块。

提供三种实现：
- HeuristicMLLM: 不依赖外部 API 的多尺度 + 多 patch 重判（离线兜底）
- QwenVLOpenAI:  真实多模态大模型，走 OpenAI 兼容端点（推荐，见 qwen.md）
- DashScopeQwenVL: 真实多模态大模型，走 dashscope SDK（需 DASHSCOPE_API_KEY）

三者实现同一接口 `analyze(image_bytes, page_type) -> OracleResult`。
"""
from .base import VisualOracle, OracleResult
from .heuristic import HeuristicMLLM
from .qwen_vl_openai import QwenVLOpenAI, resolve_api_key

__all__ = [
    "VisualOracle",
    "OracleResult",
    "HeuristicMLLM",
    "QwenVLOpenAI",
    "default_mllm",
]


def default_mllm(prefer_real: bool = True) -> VisualOracle:
    """工厂：有 key 时返回真实 Qwen-VL，否则回退 HeuristicMLLM。

    通过环境变量 VT_MLLM 可强制选择：
        VT_MLLM=heuristic  → 强制启发式
        VT_MLLM=qwen       → 强制 Qwen（无 key 仍会在 analyze 时回退报错）
    """
    import os

    forced = os.environ.get("VT_MLLM", "").strip().lower()
    if forced == "heuristic":
        return HeuristicMLLM()
    if forced in ("qwen", "qwen_vl", "qwen-vl"):
        return QwenVLOpenAI()

    if prefer_real and resolve_api_key():
        qwen = QwenVLOpenAI()
        if qwen.is_available():
            return qwen
    return HeuristicMLLM()
