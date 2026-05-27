"""训练可学习的分诊分类器。

输出：
- models/triage_tree_v1.pkl       浅决策树（深度 5，可解释）
- models/triage_forest_v1.pkl     随机森林（精度参考）
- reports/confusion_matrix_*.png  混淆矩阵
- reports/decision_tree_v1.png    决策树可视化
- reports/classification_report.txt  per-class P/R/F1
- reports/feature_importances.csv 特征重要性
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
import joblib

from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    accuracy_score,
    f1_score,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose.feature_extractor import FEATURE_NAMES, VERDICTS  # noqa: E402
from diagnose.training.mine_corpus import mine, class_counts  # noqa: E402
from diagnose.training.synthesize import synthesize_balanced  # noqa: E402


HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "models")
REPORTS_DIR = os.path.join(HERE, "reports")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


# ============ 规则法 baseline（对照组）============

def rule_based_verdict(features: list) -> str:
    """复刻 triage._decide_verdict 的纯规则版本，只看三个 pass 标记。

    feature 中 perf_pass=index 9, func_pass=index 14。
    visual pass 通过 is_black_white / is_blur 推断（无单独 visual_pass 特征）。
    """
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


# ============ 训练 ============

def train_and_eval(
    target_per_class: int = 80,
    test_size: float = 0.25,
    tree_max_depth: int = 5,
    seed: int = 42,
):
    print("\n[1/5] 挖训练样本……")
    X_mined, y_mined, meta_mined = mine()
    print(f"  mined: {len(X_mined)} 条; 分布={class_counts(y_mined)}")

    print("\n[2/5] 合成补足欠采样类……")
    X_all, y_all, meta_all = synthesize_balanced(
        X_mined, y_mined, meta_mined, target_per_class=target_per_class, seed=seed
    )
    print(f"  total: {len(X_all)} 条; 分布={class_counts(y_all)}")

    X = np.asarray(X_all, dtype=float)
    y = np.asarray(y_all)

    # 分层切分
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed
    )
    print(f"\n[3/5] 切分: train={len(X_tr)}, test={len(X_te)}")

    # ---- 决策树 ----
    print("\n[4/5] 训练浅决策树……")
    tree = DecisionTreeClassifier(
        max_depth=tree_max_depth,
        class_weight="balanced",
        random_state=seed,
    )
    tree.fit(X_tr, y_tr)
    y_pred_tree = tree.predict(X_te)
    acc_tree = accuracy_score(y_te, y_pred_tree)
    f1_tree = f1_score(y_te, y_pred_tree, average="macro")
    print(f"  Tree  accuracy={acc_tree:.4f}  macro-F1={f1_tree:.4f}")

    # ---- 随机森林 ----
    forest = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        class_weight="balanced",
        random_state=seed,
    )
    forest.fit(X_tr, y_tr)
    y_pred_forest = forest.predict(X_te)
    acc_forest = accuracy_score(y_te, y_pred_forest)
    f1_forest = f1_score(y_te, y_pred_forest, average="macro")
    print(f"  Forest accuracy={acc_forest:.4f}  macro-F1={f1_forest:.4f}")

    # ---- 规则法 baseline ----
    y_pred_rule = np.asarray([rule_based_verdict(list(x)) for x in X_te])
    acc_rule = accuracy_score(y_te, y_pred_rule)
    f1_rule = f1_score(y_te, y_pred_rule, average="macro")
    print(f"  Rule  accuracy={acc_rule:.4f}  macro-F1={f1_rule:.4f}")

    # ============ 落盘 ============

    print("\n[5/5] 落盘模型与报告……")

    # 模型 + 元信息一起 dump
    bundle = {
        "model": tree,
        "feature_names": FEATURE_NAMES,
        "classes": list(tree.classes_),
        "trained_at": datetime.now().isoformat(),
        "metrics": {
            "accuracy": acc_tree,
            "macro_f1": f1_tree,
        },
    }
    tree_path = os.path.join(MODELS_DIR, "triage_tree_v1.pkl")
    joblib.dump(bundle, tree_path)
    print(f"  模型: {tree_path}")

    forest_bundle = dict(bundle)
    forest_bundle["model"] = forest
    forest_bundle["classes"] = list(forest.classes_)
    forest_bundle["metrics"] = {"accuracy": acc_forest, "macro_f1": f1_forest}
    forest_path = os.path.join(MODELS_DIR, "triage_forest_v1.pkl")
    joblib.dump(forest_bundle, forest_path)
    print(f"  模型: {forest_path}")

    # 混淆矩阵
    _plot_confusion(y_te, y_pred_tree, "tree", os.path.join(REPORTS_DIR, "cm_tree.png"))
    _plot_confusion(y_te, y_pred_forest, "forest", os.path.join(REPORTS_DIR, "cm_forest.png"))
    _plot_confusion(y_te, y_pred_rule, "rule (baseline)", os.path.join(REPORTS_DIR, "cm_rule.png"))

    # 决策树可视化
    _plot_tree(tree, os.path.join(REPORTS_DIR, "decision_tree_v1.png"))

    # classification report 文本
    cr_path = os.path.join(REPORTS_DIR, "classification_report.txt")
    with open(cr_path, "w", encoding="utf-8") as f:
        f.write("== DecisionTree ==\n")
        f.write(classification_report(y_te, y_pred_tree, digits=4, zero_division=0))
        f.write("\n\n== RandomForest ==\n")
        f.write(classification_report(y_te, y_pred_forest, digits=4, zero_division=0))
        f.write("\n\n== Rule-based baseline ==\n")
        f.write(classification_report(y_te, y_pred_rule, digits=4, zero_division=0))
        f.write("\n\n== Summary ==\n")
        f.write(f"Tree   acc={acc_tree:.4f} macro-F1={f1_tree:.4f}\n")
        f.write(f"Forest acc={acc_forest:.4f} macro-F1={f1_forest:.4f}\n")
        f.write(f"Rule   acc={acc_rule:.4f} macro-F1={f1_rule:.4f}\n")
    print(f"  分类报告: {cr_path}")

    # 特征重要性
    imp = pd.DataFrame({
        "feature": FEATURE_NAMES,
        "tree_importance": tree.feature_importances_,
        "forest_importance": forest.feature_importances_,
    }).sort_values("forest_importance", ascending=False)
    imp_path = os.path.join(REPORTS_DIR, "feature_importances.csv")
    imp.to_csv(imp_path, index=False)
    print(f"  特征重要性: {imp_path}")

    # 一份机器友好的汇总 json
    summary = {
        "trained_at": datetime.now().isoformat(),
        "n_samples_total": len(X_all),
        "n_samples_mined": len(X_mined),
        "n_samples_train": len(X_tr),
        "n_samples_test": len(X_te),
        "class_distribution_full": class_counts(y_all),
        "metrics": {
            "tree":   {"accuracy": acc_tree,   "macro_f1": f1_tree},
            "forest": {"accuracy": acc_forest, "macro_f1": f1_forest},
            "rule":   {"accuracy": acc_rule,   "macro_f1": f1_rule},
        },
    }
    sum_path = os.path.join(REPORTS_DIR, "train_summary.json")
    with open(sum_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  训练摘要: {sum_path}")

    return summary


def _plot_confusion(y_true, y_pred, title: str, out_path: str):
    labels = list(VERDICTS)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=labels, yticklabels=labels, ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(f"Confusion Matrix - {title}")
    plt.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _plot_tree(tree: DecisionTreeClassifier, out_path: str):
    fig, ax = plt.subplots(figsize=(20, 12))
    plot_tree(
        tree,
        feature_names=FEATURE_NAMES,
        class_names=list(tree.classes_),
        filled=True,
        rounded=True,
        fontsize=8,
        ax=ax,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=80)
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train_and_eval(
        target_per_class=args.per_class,
        test_size=args.test_size,
        tree_max_depth=args.max_depth,
        seed=args.seed,
    )
