"""视觉 oracle 抽象接口。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Protocol


@dataclass
class OracleResult:
    """统一的视觉判定结构化输出。

    设计原则：所有字段都可作为 learned-triage 的额外特征，便于消融。
    """
    has_blur: bool = False
    has_blank: bool = False
    has_overlap: bool = False
    has_missing_image: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    cost_ms: float = 0.0
    cost_dollars: float = 0.0
    source: str = "unknown"  # 哪一个 oracle 出的结果，便于追溯
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class VisualOracle(Protocol):
    """视觉 oracle 协议。"""

    name: str

    def analyze(self, image_bytes: bytes, page_type: str = "feed") -> OracleResult:
        ...
