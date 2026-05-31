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

# 差分+代码融合诊断的 system prompt：给"健康基线图 + 当前图（+ 可选页面源码）"，
# 判"当前相对基线是否引入了缺陷"。差分消除"占位纹理图被误判为缺图"的偏见
# （基线图同样含占位图，模型据此知道占位图本身是正常的）。
DIFF_SYSTEM_PROMPT = """你是一个小程序 UI 回归审查员。会给你两张同一页面的截图：
第一张是【健康基线】（已知正确），第二张是【当前版本】（待审查），可能还附上该页的源码。

你的任务：判断【当前版本】相对【健康基线】是否**引入了缺陷**。只对比差异，不要把基线里本就存在的
样式（如占位图、网格纹理、留白）当成缺陷——它们在基线里就有，是正常的。

关注这些缺陷维度（相对基线新出现的才算）：
- has_missing_image: 基线里有内容的图片区域，当前变成空白/缺失
- has_invisible_text: 基线里可见的文字，当前看不见（颜色与背景接近、对比度过低）
- has_overflow_or_overlap: 当前出现元素溢出屏幕/相互重叠/错位（基线没有）
- has_wrong_data: 当前渲染出 undefined/NaN/空绑定/异常文本（基线是正常数据）
- has_blank: 当前整屏黑/白屏（基线正常）

请只输出一个 JSON，不要额外文字：
{"has_defect": true/false, "dimension": "visual|functional|none",
 "has_missing_image": false, "has_invisible_text": false, "has_overflow_or_overlap": false,
 "has_wrong_data": false, "has_blank": false, "confidence": 0.9, "reasoning": "相对基线的具体差异"}
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

    def analyze_diff(self, baseline_bytes: bytes, current_bytes: bytes,
                     page_type: str = "feed", code_context: Optional[str] = None) -> OracleResult:
        """差分+代码融合诊断：给【健康基线图 + 当前图 + 可选源码】，判当前相对基线是否引入缺陷。

        相比 analyze（单图判缺陷），差分对比能消除"占位纹理图被误判为缺图"的系统偏见，
        因为基线图同样含占位图——模型据此知道占位图是正常的。
        code_context 是【当前页面源码】（CI 中本就可得），不含"注入了什么"的答案，不构成作弊。

        返回的 OracleResult 复用现有字段：
          has_missing_image / has_blur(=invisible_text 借位) / has_overlap(=overflow/overlap) /
          has_blank；额外把结构化结果塞进 extra（has_defect/dimension/has_wrong_data）。
        """
        if not self.is_available():
            return OracleResult(source=self.name, reasoning="Qwen-VL 不可用", confidence=0.0)

        def _uri(b):
            return f"data:image/png;base64,{base64.b64encode(b).decode('ascii')}"

        user_content = [
            {"type": "text", "text": "【健康基线】（已知正确）："},
            {"type": "image_url", "image_url": {"url": _uri(baseline_bytes)}},
            {"type": "text", "text": "【当前版本】（待审查）："},
            {"type": "image_url", "image_url": {"url": _uri(current_bytes)}},
        ]
        if code_context:
            user_content.append({"type": "text",
                                 "text": f"当前页面源码（供参考，判断渲染是否符合代码意图）：\n{code_context[:4000]}"})
        user_content.append({"type": "text", "text": f"页面类型：{page_type}。只输出 JSON。"})

        t0 = time.time()
        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": DIFF_SYSTEM_PROMPT},
                          {"role": "user", "content": user_content}],
                max_tokens=500, temperature=0.0,
            )
        except Exception as e:  # noqa: BLE001
            return OracleResult(source=self.name, reasoning=f"调用失败: {e}",
                                confidence=0.0, cost_ms=(time.time() - t0) * 1000.0)
        cost_ms = (time.time() - t0) * 1000.0
        try:
            text = resp.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            return OracleResult(source=self.name, reasoning=f"返回格式异常: {resp}",
                                confidence=0.0, cost_ms=cost_ms)
        parsed = _try_parse_json(text)
        if not parsed:
            return OracleResult(source=self.name, reasoning=f"无法解析: {str(text)[:200]}",
                                confidence=0.0, cost_ms=cost_ms)

        return OracleResult(
            has_blur=bool(parsed.get("has_invisible_text", False)),       # 借位表达"不可见文字"
            has_blank=bool(parsed.get("has_blank", False)),
            has_overlap=bool(parsed.get("has_overflow_or_overlap", False)),
            has_missing_image=bool(parsed.get("has_missing_image", False)),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=str(parsed.get("reasoning", "")),
            cost_ms=cost_ms, cost_dollars=self.cost_per_call_dollars,
            source=f"{self.name}:{self.model}:diff",
            extra={"has_defect": bool(parsed.get("has_defect", False)),
                   "dimension": parsed.get("dimension", "none"),
                   "has_wrong_data": bool(parsed.get("has_wrong_data", False)),
                   "raw": str(text)[:500]},
        )
