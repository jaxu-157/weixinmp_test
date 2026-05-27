"""在 Vision-Triage Fault Benchmark 上评测任意分诊 oracle。

可评测的 oracle：
- rule         规则法 truth table（baseline）
- learned      决策树
- forest       随机森林
- cascade      规则 → MLLM 级联
- all          上面三个一起跑，输出对比表

用法：
    python diagnosis/benchmark/evaluate.py --bench diagnosis/benchmark/vt_bench_v1.json --oracle all
"""
from __future__ import annotations

import os
import sys
import json
import argparse
from typing import List, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

_THIS = os.path.dirname(os.path.abspath(__file__))
_DIAGNOSIS_DIR = os.path.dirname(_THIS)
if _DIAGNOSIS_DIR not in sys.path:
    sys.path.insert(0, _DIAGNOSIS_DIR)

from diagnose.feature_extractor import FEATURE_NAMES, VERDICTS  # noqa: E402
import joblib  # noqa: E402


REPORTS_DIR = os.path.join(_THIS, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def load_bench(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ Oracle 1: 规则法 ============

def _rule_predict(features: List[float]) -> str:
    idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
    perf_pass = features[idx["perf_pass"]] >= 0.5
    func_pass = features[idx["func_pass"]] >= 0.5
    visual_fail = (features[idx["is_black_white"]] >= 0.5) or (features[idx["is_blur"]] >= 0.5)
    visual_pass = not visual_fail
    if func_pass and perf_pass and visual_pass:
        return "Pass"
    if func_pass and not perf_pass and visual_pass:
        return "PerformanceRisk"
    if func_pass and perf_pass and not visual_pass:
        return "RenderBug"
    if not func_pass and perf_pass and visual_pass:
        return "FunctionalFail"
    return "Mixed"


# ============ Oracle 2/3: 模型 ============

def _load_model(path: str):
    return joblib.load(path)


def _model_predict(model_bundle: dict, X: np.ndarray) -> List[str]:
    return model_bundle["model"].predict(X).tolist()


# ============ Main eval ============

def evaluate_oracle(
    name: str, y_pred: List[str], y_true: List[str], samples: List[dict]
) -> dict:
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro")

    cls_report = classification_report(
        y_true, y_pred, labels=list(VERDICTS), digits=4,
        output_dict=True, zero_division=0,
    )

    # 边界样本上的准确率
    borderline_idx = [i for i, s in enumerate(samples) if s["metadata"]["is_borderline"]]
    bord_acc = float("nan")
    if borderline_idx:
        b_true = [y_true[i] for i in borderline_idx]
        b_pred = [y_pred[i] for i in borderline_idx]
        bord_acc = accuracy_score(b_true, b_pred)

    return {
        "name": name,
        "accuracy": acc,
        "macro_f1": macro_f1,
        "borderline_accuracy": bord_acc,
        "per_class": {
            cls: {
                "precision": cls_report[cls]["precision"],
                "recall": cls_report[cls]["recall"],
                "f1": cls_report[cls]["f1-score"],
            }
            for cls in VERDICTS if cls in cls_report
        },
    }


def _plot_cm(y_true, y_pred, name: str, out_path: str):
    labels = list(VERDICTS)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=labels, yticklabels=labels, ax=ax)
    ax.set_title(f"Confusion Matrix - {name}")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    plt.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", type=str,
                        default=os.path.join(_THIS, "vt_bench_v1.json"))
    parser.add_argument("--oracle", type=str, default="all",
                        choices=["rule", "learned", "forest", "all"])
    args = parser.parse_args()

    bench = load_bench(args.bench)
    samples = bench["samples"]
    X = np.array([s["features"] for s in samples], dtype=float)
    y_true = [s["expected_verdict"] for s in samples]

    print(f"Benchmark: {args.bench}")
    print(f"Samples: {len(samples)}")
    print(f"Schema: features={len(bench['schema']['feature_names'])}, verdicts={bench['schema']['verdicts']}")

    results = []

    if args.oracle in ("rule", "all"):
        y_pred = [_rule_predict(list(x)) for x in X]
        r = evaluate_oracle("rule", y_pred, y_true, samples)
        results.append(r)
        _plot_cm(y_true, y_pred, "rule", os.path.join(REPORTS_DIR, "bench_cm_rule.png"))

    if args.oracle in ("learned", "all"):
        bundle = _load_model(os.path.join(_DIAGNOSIS_DIR, "diagnose", "training",
                                          "models", "triage_tree_v1.pkl"))
        y_pred = _model_predict(bundle, X)
        r = evaluate_oracle("learned_tree", y_pred, y_true, samples)
        results.append(r)
        _plot_cm(y_true, y_pred, "learned_tree", os.path.join(REPORTS_DIR, "bench_cm_tree.png"))

    if args.oracle in ("forest", "all"):
        bundle = _load_model(os.path.join(_DIAGNOSIS_DIR, "diagnose", "training",
                                          "models", "triage_forest_v1.pkl"))
        y_pred = _model_predict(bundle, X)
        r = evaluate_oracle("learned_forest", y_pred, y_true, samples)
        results.append(r)
        _plot_cm(y_true, y_pred, "learned_forest", os.path.join(REPORTS_DIR, "bench_cm_forest.png"))

    # 打印
    print()
    print(f"{'oracle':<18}{'acc':<10}{'macro_f1':<12}{'borderline_acc':<16}")
    print("-" * 60)
    for r in results:
        print(f"{r['name']:<18}{r['accuracy']:<10.4f}{r['macro_f1']:<12.4f}{r['borderline_accuracy']:<16.4f}")

    # 保存
    out_path = os.path.join(REPORTS_DIR, "benchmark_eval.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "bench_path": args.bench,
            "n_samples": len(samples),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n保存: {out_path}")

    # 综合对比图
    if len(results) > 1:
        fig, ax = plt.subplots(figsize=(8, 5))
        names = [r["name"] for r in results]
        x = np.arange(len(names))
        width = 0.25
        ax.bar(x - width, [r["accuracy"] for r in results], width, label="accuracy")
        ax.bar(x, [r["macro_f1"] for r in results], width, label="macro-F1")
        ax.bar(x + width, [r["borderline_accuracy"] for r in results], width, label="borderline-acc")
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("score")
        ax.set_title(f"Oracle Comparison on VT-Bench v1 ({len(samples)} samples)")
        ax.legend()
        plt.tight_layout()
        bar_path = os.path.join(REPORTS_DIR, "benchmark_comparison.png")
        fig.savefig(bar_path, dpi=140)
        plt.close(fig)
        print(f"保存: {bar_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
