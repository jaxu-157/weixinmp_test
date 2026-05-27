"""Qwen-VL 适配器（OpenAI 兼容端点）。

相比 dashscope_qwen_vl.py（用 dashscope SDK + DASHSCOPE_API_KEY），本适配器走
DashScope 的 **OpenAI 兼容模式**（见仓库根 qwen.md）：

    base_url = https://dashscope.aliyuncs.com/compatible-mode/v1
    pip install openai           # 已装 2.11.0
    图像：base64 data-uri 走 image_url

优先用本适配器，因为 openai SDK 更稳、依赖更少。key 解析顺序：
    1. 构造参数 api_key
    2. 环境变量 DASHSCOPE_API_KEY
    3. 仓库根 qwen.md 首行 `api-key：sk-xxx`（方便自主循环零配置启动）

没装 openai 或拿不到 key 时 is_available() 返回 False，调用方应回退到 HeuristicMLLM。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Optional

from .base import OracleResult


BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

SYSTEM_PROMPT = """你是一个小程序界面视觉异常检测器。给定一张小程序截图，请判断它是否存在以下视觉异常：
1. has_blur: 整张图或大量区域明显模糊
2. has_blank: 整屏黑屏或白屏
3. has_overlap: 文字或卡片明显错位/重叠
4. has_missing_image: 大量图片占位符或图片加载失败

请只输出一个 JSON 对象，格式如下，不要任何额外文字：
{"has_blur": false, "has_blank": false, "has_overlap": false, "has_missing_image": false, "confidence": 0.9, "reasoning": "简短说明"}
"""


def _repo_root() -> str:
    # diagnosis/diagnose/mllm/qwen_vl_openai.py → 上溯 4 层到仓库根
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))


def _key_from_qwen_md() -> Optional[str]:
    """从仓库根 qwen.md 首行 `api-key：sk-xxx` 解析 key。"""
    path = os.path.join(_repo_root(), "qwen.md")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return None
    m = re.search(r"(sk-[A-Za-z0-9]{16,})", head)
    return m.group(1) if m else None


def resolve_api_key(explicit: Optional[str] = None) -> str:
    return (
        explicit
        or os.environ.get("DASHSCOPE_API_KEY", "")
        or _key_from_qwen_md()
        or ""
    )


def _try_parse_json(text: str) -> Optional[dict]:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class QwenVLOpenAI:
    """Qwen-VL 适配器（OpenAI 兼容端点）。"""

    name = "qwen_vl_openai"
    # 估价（DashScope qwen-vl-plus 公开价目量级）：~¥0.008/张
    cost_per_call_dollars = 0.0011

    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-vl-plus"):
        self.api_key = resolve_api_key(api_key)
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=BASE_URL)
        return self._client

    def analyze(self, image_bytes: bytes, page_type: str = "feed") -> OracleResult:
        if not self.is_available():
            return OracleResult(
                source=self.name,
                reasoning="Qwen-VL 不可用（缺 API key 或未安装 openai）",
                confidence=0.0,
            )

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        t0 = time.time()
        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": f"页面类型：{page_type}。请只输出 JSON。"},
                    ]},
                ],
                max_tokens=400,
                temperature=0.0,
            )
        except Exception as e:  # noqa: BLE001 - 网络/鉴权失败都回退
            return OracleResult(
                source=self.name,
                reasoning=f"调用失败: {e}",
                confidence=0.0,
                cost_ms=(time.time() - t0) * 1000.0,
            )

        cost_ms = (time.time() - t0) * 1000.0
        try:
            text = resp.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
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
                reasoning=f"无法解析 JSON: {str(text)[:200]}",
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
            source=f"{self.name}:{self.model}",
            extra={"raw": str(text)[:500]},
        )
