"""Cascade 视觉 oracle 评测：rule-only vs cascade vs heuristic-always。

度量：
- 视觉子断言的 pass/fail 准确率
- 端到端分诊准确率（接 learned-tree 后）
- 平均延迟（ms）
- 升级率（cascade 中走到 MLLM 的比例）
- 估算成本（美元）
"""
from __future__ import annotations

import os
import sys
import json
import glob
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose import triage as rule_triage  # noqa: E402
from diagnose.learned_triage import run_triage_learned, is_available  # noqa: E402
from diagnose.cascade_oracle import CascadeOracle  # noqa: E402
from diagnose.mllm import HeuristicMLLM  # noqa: E402
from diagnose.training.smoke_test import (  # noqa: E402
    EXPECT,
    _infer_context,
    _build_page_state,
    _build_perf,
)


HERE = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "auto_test", "reports", "screenshots",
)


def _select_latest_one_per_combo() -> list:
    pngs = sorted(glob.glob(os.path.join(SCREENSHOT_DIR, "*.png")))
    latest: dict = {}
    for p in pngs:
        page, profile = _infer_context(p)
        key = (page, profile)
        if key in EXPECT and (key not in latest or p > latest[key]):
            latest[key] = p
    return [
        (page, profile, EXPECT[(page, profile)], path)
        for (page, profile), path in sorted(latest.items())
    ]


def _eval_oracle(name: str, oracle_fn, samples: list) -> dict:
    """oracle_fn(image_bytes, page) -> visual_dict (与 _run_visual_assertions 兼容)。"""
    correct_visual = 0
    correct_verdict = 0
    total_ms = 0.0
    total_dollars = 0.0
    n_escalated = 0
    rows = []

    for page, profile, expected, path in samples:
        with open(path, "rb") as f:
            img = f.read()
        page_state = _build_page_state(page, profile)
        perf_data = _build_perf(profile)

        t0 = time.time()
        visual = oracle_fn(img, page)
        oracle_ms = (time.time() - t0) * 1000.0

        # 视觉子准确率：normal 应当 pass=True，异常应当 pass=False
        visual_pass = visual.get("pass", True)
        # 这些 profile 在视觉维度上应当为"异常"
        visual_fail_profiles = {"blur_image", "mixed_fault"}
        visual_should_fail = profile in visual_fail_profiles
        visual_ok = (not visual_pass) == visual_should_fail
        if visual_ok:
            correct_visual += 1

        # 升级率（仅 cascade 有这个字段）
        cas = visual.get("cascade", {})
        if cas.get("escalated"):
            n_escalated += 1
        total_dollars += cas.get("cost_dollars", 0.0)
        total_ms += oracle_ms

        # 把 visual 灌进 learned_triage 流程（同接口）
        from diagnose.feature_extractor import extract_features  # 延迟导入避免顶层循环
        functional = rule_triage._run_functional_assertions(page_state, page)
        performance = rule_triage._run_performance_assertions({
            "interactionMs": perf_data["interactionMs"],
            "memoryWarningCount": perf_data["memoryWarningCount"],
        })

        # 用模型预测 verdict
        from diagnose.learned_triage import _predict_verdict  # noqa: E402
        verdict, _ = _predict_verdict(visual, functional, performance, page, page_state)
        if verdict == expected:
            correct_verdict += 1

        rows.append({
            "page": page,
            "profile": profile,
            "expected": expected,
            "verdict": verdict,
            "visual_pass": visual_pass,
            "escalated": cas.get("escalated", False),
            "oracle_ms": round(oracle_ms, 2),
        })

    n = len(samples)
    return {
        "name": name,
        "n": n,
        "visual_accuracy": correct_visual / n,
        "verdict_accuracy": correct_verdict / n,
        "avg_oracle_ms": total_ms / n,
        "total_cost_dollars": round(total_dollars, 6),
        "escalation_rate": n_escalated / n,
        "rows": rows,
    }


def main():
    if not is_available():
        print("先训练模型: python diagnosis/diagnose/training/train.py")
        return 1

    samples = _select_latest_one_per_combo()
    print(f"样本数: {len(samples)}")

    # 三种 oracle
    import cv2
    import numpy as np

    def rule_only(img_bytes: bytes, page: str) -> dict:
        nparr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return rule_triage._run_visual_assertions(image, page)

    cascade = CascadeOracle()

    def cascade_fn(img_bytes: bytes, page: str) -> dict:
        return cascade.analyze(img_bytes, page)

    heuristic = HeuristicMLLM()

    def heuristic_always(img_bytes: bytes, page: str) -> dict:
        # 全用 heuristic，但要把字段转成与 _run_visual_assertions 同 schema
        r = heuristic.analyze(img_bytes, page)
        return {
            "pass": not (r.has_blur or r.has_blank),
            "black_white": r.has_blank,
            "blur_score": r.extra.get("ms_blur", 0.0),
            "blur_score_full": r.extra.get("ms_blur", 0.0),
            "is_blur": r.has_blur,
            "edge_density": 0.0,
            "ocr_text": "",
            "mean_brightness": r.extra.get("brightness", 0.0),
            "cascade": {
                "escalated": True,
                "reason": "heuristic_always",
                "rule_ms": 0.0,
                "mllm_ms": r.cost_ms,
                "total_ms": r.cost_ms,
                "cost_dollars": r.cost_dollars,
                "mllm_source": r.source,
                "mllm_confidence": r.confidence,
            },
        }

    results = [
        _eval_oracle("rule_only", rule_only, samples),
        _eval_oracle("cascade", cascade_fn, samples),
        _eval_oracle("heuristic_always", heuristic_always, samples),
    ]

    # 打印汇总
    print()
    print(f"{'oracle':<20}{'visual_acc':<12}{'verdict_acc':<13}{'avg_ms':<10}{'esc_rate':<10}")
    print("-" * 70)
    for r in results:
        print(f"{r['name']:<20}{r['visual_accuracy']:<12.2%}{r['verdict_accuracy']:<13.2%}"
              f"{r['avg_oracle_ms']:<10.2f}{r['escalation_rate']:<10.2%}")

    # 保存
    out_path = os.path.join(HERE, "reports", "cascade_evaluation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2, ensure_ascii=False)
    print(f"\n保存: {out_path}")

    # 画 cost-accuracy 散点
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    for r in results:
        ax.scatter(r["avg_oracle_ms"], r["verdict_accuracy"] * 100, s=120, label=r["name"])
        ax.annotate(r["name"], (r["avg_oracle_ms"], r["verdict_accuracy"] * 100),
                    xytext=(5, 5), textcoords="offset points")
    ax.set_xlabel("avg oracle latency (ms)")
    ax.set_ylabel("verdict accuracy (%)")
    ax.set_title("Cost-Accuracy Pareto (Visual Oracle Variants)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    png_path = os.path.join(HERE, "reports", "cascade_pareto.png")
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    print(f"保存: {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
