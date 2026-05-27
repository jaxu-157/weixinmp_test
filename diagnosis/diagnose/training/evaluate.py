"""模态消融实验：依次去掉 visual / performance / functional 三类特征，
观察分诊准确率退化情况。

把每组特征替换为"中性值"而不是删除，这样模型输入维度不变、可以复用同一个模型。
"""
from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose.feature_extractor import (  # noqa: E402
    FEATURE_NAMES,
    VERDICTS,
    feature_groups,
    neutral_value_for,
)
from diagnose.training.mine_corpus import mine, class_counts  # noqa: E402
from diagnose.training.synthesize import synthesize_balanced  # noqa: E402


HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(HERE, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _mask_modality(X: np.ndarray, modality: str) -> np.ndarray:
    """把指定模态的所有特征列置为中性值。"""
    groups = feature_groups()
    if modality not in groups:
        return X
    masked = X.copy()
    name2idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
    for name in groups[modality]:
        idx = name2idx[name]
        masked[:, idx] = neutral_value_for(name)
    return masked


def run_ablation(
    target_per_class: int = 80,
    test_size: float = 0.25,
    tree_max_depth: int = 5,
    seed: int = 42,
):
    X_m, y_m, meta_m = mine()
    X_all, y_all, _ = synthesize_balanced(X_m, y_m, meta_m, target_per_class=target_per_class, seed=seed)
    X = np.asarray(X_all, dtype=float)
    y = np.asarray(y_all)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed
    )

    # 用完整特征训练一次，作为消融的基线
    tree = DecisionTreeClassifier(
        max_depth=tree_max_depth, class_weight="balanced", random_state=seed
    )
    tree.fit(X_tr, y_tr)

    def eval_on(X_test_masked: np.ndarray) -> dict:
        y_pred = tree.predict(X_test_masked)
        return {
            "accuracy": accuracy_score(y_te, y_pred),
            "macro_f1": f1_score(y_te, y_pred, average="macro"),
            "per_class": classification_report(
                y_te, y_pred, output_dict=True, zero_division=0
            ),
            "y_pred": y_pred.tolist(),
        }

    results = {
        "all_features": eval_on(X_te),
        "drop_visual": eval_on(_mask_modality(X_te, "visual")),
        "drop_performance": eval_on(_mask_modality(X_te, "performance")),
        "drop_functional": eval_on(_mask_modality(X_te, "functional")),
    }

    # 也尝试只保留单一模态
    def keep_only(modality: str) -> np.ndarray:
        X_only = X_te.copy()
        for other in ("visual", "performance", "functional"):
            if other != modality:
                X_only = _mask_modality(X_only, other)
        return X_only

    results["only_visual"] = eval_on(keep_only("visual"))
    results["only_performance"] = eval_on(keep_only("performance"))
    results["only_functional"] = eval_on(keep_only("functional"))

    # ============ 输出 ============

    # 主表
    summary_rows = []
    for cond, r in results.items():
        summary_rows.append({
            "condition": cond,
            "accuracy": round(r["accuracy"], 4),
            "macro_f1": round(r["macro_f1"], 4),
        })
        for cls in VERDICTS:
            per = r["per_class"].get(cls, {})
            summary_rows[-1][f"f1_{cls}"] = round(per.get("f1-score", 0.0), 4)

    df = pd.DataFrame(summary_rows)
    csv_path = os.path.join(REPORTS_DIR, "ablation_table.csv")
    df.to_csv(csv_path, index=False)
    print(df.to_string(index=False))
    print(f"\n保存: {csv_path}")

    # 柱状图（accuracy & macro_f1）
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(summary_rows))
    width = 0.35
    ax.bar(x - width / 2, [r["accuracy"] for r in summary_rows], width, label="accuracy")
    ax.bar(x + width / 2, [r["macro_f1"] for r in summary_rows], width, label="macro-F1")
    ax.set_xticks(x)
    ax.set_xticklabels([r["condition"] for r in summary_rows], rotation=30, ha="right")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("score")
    ax.set_title("Modality Ablation (DecisionTree, depth=5)")
    ax.legend()
    plt.tight_layout()
    png_path = os.path.join(REPORTS_DIR, "ablation_bar.png")
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    print(f"保存: {png_path}")

    # 落 JSON
    json_path = os.path.join(REPORTS_DIR, "ablation_results.json")
    serializable = {}
    for k, v in results.items():
        serializable[k] = {
            "accuracy": v["accuracy"],
            "macro_f1": v["macro_f1"],
            "per_class_f1": {
                cls: v["per_class"].get(cls, {}).get("f1-score", 0.0)
                for cls in VERDICTS
            },
        }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "trained_at": datetime.now().isoformat(),
            "results": serializable,
        }, f, indent=2, ensure_ascii=False)
    print(f"保存: {json_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_ablation(target_per_class=args.per_class, seed=args.seed)
