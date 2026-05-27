"""DashScope Qwen-VL 适配器：真实 MLLM 视觉重判。

需要：
    pip install dashscope
    export DASHSCOPE_API_KEY=sk-xxx

设计：把图像 + 一段提示一起发给 qwen-vl-plus，要求它输出 JSON。
如果环境没装 dashscope 或没有 API key，调用方应回退到 HeuristicMLLM。
"""
from __future__ import annotations

import base64
import json
import os
import time
import re
from typing import Optional

from .base import OracleResult


SYSTEM_PROMPT = """你是一个小程序界面视觉异常检测器。给定一张小程序截图，请判断它是否存在以下视觉异常：
1. has_blur: 整张图或大量区域明显模糊
2. has_blank: 整屏黑屏或白屏
3. has_overlap: 文字或卡片明显错位/重叠
4. has_missing_image: 大量图片占位符或图片加载失败

请只输出一个 JSON 对象，格式如下，不要任何额外文字：
{"has_blur": false, "has_blank": false, "has_overlap": false, "has_missing_image": false, "confidence": 0.9, "reasoning": "简短说明"}
"""


def _try_parse_json(text: str) -> Optional[dict]:
    # 把可能的 ```json ... ``` 包裹去掉
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class DashScopeQwenVL:
    """Qwen-VL-Plus / qwen2-vl 适配器。"""

    name = "qwen_vl_plus"
    # 估价（截至 2026 上半年公开价目）：~¥0.008 每张图
    cost_per_call_dollars = 0.0011

    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-vl-plus"):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import dashscope  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, image_bytes: bytes, page_type: str = "feed") -> OracleResult:
        if not self.is_available():
            return OracleResult(
                source=self.name,
                reasoning="DashScope 不可用（缺 API key 或未安装 dashscope）",
                confidence=0.0,
            )

        import dashscope
        from dashscope import MultiModalConversation

        dashscope.api_key = self.api_key
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        t0 = time.time()
        try:
            resp = MultiModalConversation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": [{"text": SYSTEM_PROMPT}]},
                    {"role": "user", "content": [
                        {"image": data_uri},
                        {"text": f"页面类型：{page_type}。请输出 JSON。"},
                    ]},
                ],
            )
        except Exception as e:
            return OracleResult(
                source=self.name,
                reasoning=f"调用失败: {e}",
                confidence=0.0,
                cost_ms=(time.time() - t0) * 1000.0,
            )

        cost_ms = (time.time() - t0) * 1000.0
        text = ""
        try:
            text = resp["output"]["choices"][0]["message"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return OracleResult(
                source=self.name,
                reasoning=f"返回格式异常: {resp}",
                confidence=0.0,
                cost_ms=cost_ms,
            )

        parsed = _try_parse_json(text)
        if not parsed:
            return OracleResult(
                source=self.name,
                reasoning=f"无法解析 JSON: {text[:200]}",
                confidence=0.0,
                cost_ms=cost_ms,
            )

        return OracleResult(
            has_blur=bool(parsed.get("has_blur", False)),
            has_blank=bool(parsed.get("has_blank", False)),
            has_overlap=bool(parsed.get("has_overlap", False)),
            has_missing_image=bool(parsed.get("has_missing_image", False)),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=str(parsed.get("reasoning", "")),
            cost_ms=cost_ms,
            cost_dollars=self.cost_per_call_dollars,
            source=self.name,
            extra={"raw": text[:500]},
        )
