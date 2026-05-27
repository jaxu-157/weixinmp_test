"""从历史 auto_test_report_*.json 中挖出 (features, verdict) 训练样本。

每份历史报告里每条 `results[i]` 都有：
- `diagnose_result.data.visual / functional / performance`：真实测量值
- `page` / `profile` / `expected`：上下文与 ground-truth verdict

这是最干净的训练源——所有特征都是真实跑出来的。
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import List, Tuple

# 允许作为脚本直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose.feature_extractor import extract_features, FEATURE_NAMES, VERDICTS  # noqa: E402


DEFAULT_REPORT_GLOBS = [
    os.path.join("auto_test", "reports", "auto_test_report_*.json"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "..", "auto_test", "reports", "auto_test_report_*.json"),
]


def _iter_report_files(globs: List[str]) -> List[str]:
    files = []
    for g in globs:
        files.extend(glob.glob(g))
    return sorted(set(os.path.abspath(f) for f in files))


def _rebuild_page_state(page: str, profile: str) -> dict:
    """复刻 auto_test_runner._build_page_state，让特征生成与运行时一致。"""
    if page == "counter":
        if profile == "stale_ui":
            return {"visibleValue": 0, "expectedValue": 1}
        if profile == "wrong_mapping":
            return {"visibleValue": "undefined", "expectedValue": 1}
        if profile == "mixed_fault":
            return {"visibleValue": 0, "expectedValue": 1}
        return {"visibleValue": 1, "expectedValue": 1}
    if page == "layout" and profile == "layout_overlap":
        return {"uiFlags": {"hasOverlap": True}}
    if page == "feed" and profile == "mixed_fault":
        return {"visibleValue": 0, "expectedValue": 1}
    return {}


def mine(globs: List[str] | None = None) -> Tuple[List[List[float]], List[str], List[dict]]:
    """挖出 (X, y, meta) 三元组。

    meta 里保留每条样本的 page/profile/source_file，方便溯源。
    """
    globs = globs or DEFAULT_REPORT_GLOBS
    files = _iter_report_files(globs)

    X: List[List[float]] = []
    y: List[str] = []
    meta: List[dict] = []

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                report = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue

        for r in report.get("results", []):
            diag = r.get("diagnose_result")
            if not diag or diag.get("code") != 0:
                continue
            data = diag.get("data", {})
            visual = data.get("visual", {})
            functional = data.get("functional", {})
            performance = data.get("performance", {})
            page = r.get("page", "feed")
            profile = r.get("profile", "normal")
            expected = r.get("expected")

            if expected not in VERDICTS:
                continue

            page_state = _rebuild_page_state(page, profile)
            feats = extract_features(visual, functional, performance, page, page_state)

            X.append(feats)
            y.append(expected)
            meta.append({
                "page": page,
                "profile": profile,
                "source": os.path.basename(f),
                "timestamp": r.get("timestamp"),
            })

    return X, y, meta


def class_counts(y: List[str]) -> dict:
    counts = {v: 0 for v in VERDICTS}
    for v in y:
        counts[v] = counts.get(v, 0) + 1
    return counts


if __name__ == "__main__":
    X, y, meta = mine()
    print(f"挖出样本数: {len(X)}")
    print(f"特征维度: {len(FEATURE_NAMES)} ({len(X[0]) if X else 0} 实测)")
    print(f"类别分布: {class_counts(y)}")
    if meta:
        files_used = sorted({m['source'] for m in meta})
        print(f"涉及报告文件: {len(files_used)} 份")
        for f in files_used[-5:]:
            print(f"  - {f}")
