"""歧义带评测：证明 Rule→Qwen cascade 在"模糊歧义带"上的价值。

动机（见 docs/GOAL_PROGRESS.md Round 1/2）：clean 的 14 样本要么清晰要么全黑/blur=0，
没有"轻度/中度模糊"这种规则法拿不准、MLLM 能救的样本，所以 cascade 的 cost-accuracy 价值显不出来。

本脚本从清晰截图**程序化合成**一组渐进高斯模糊样本，覆盖从清晰→中度→重度，
对比三种视觉 oracle 在"该不该判模糊"上的准确率/成本/延迟：
    - rule_only      : 规则法固定阈值（baseline）
    - cascade        : 规则自信带直接出，歧义带升级到真 Qwen-VL
    - qwen_always    : 每张都问 Qwen（最贵，accuracy 上界）

Ground truth：原图=清晰(pass)，任何施加了可感知模糊核(k>=K_FAIL)的版本=模糊(fail)。
K_FAIL 取人眼明显可感知的核大小；介于其间的核构成"歧义带"，正是 cascade 升级触发区。

运行：
    DASHSCOPE_API_KEY=sk-xxx python diagnosis/diagnose/training/evaluate_ambiguous.py
（无 key 时 cascade/qwen_always 会回退到 HeuristicMLLM，仍可对比启发式 vs 规则。）
"""
from __future__ import annotations

import os
import sys
import glob
import json
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose import triage as rule_triage  # noqa: E402
from diagnose.cascade_oracle import CascadeOracle  # noqa: E402
from diagnose.mllm import QwenVLOpenAI, HeuristicMLLM, resolve_api_key  # noqa: E402
from diagnose.mllm.base import OracleResult  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# HERE=.../diagnosis/diagnose/training → 上溯 3 层到仓库根
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SCREENSHOT_DIR = os.path.join(REPO, "auto_test", "reports", "screenshots")

# 高斯模糊核：0=原图(清晰)。k>=K_FAIL 记为 ground-truth 模糊。
BLUR_KERNELS = [0, 3, 5, 7, 9, 13, 19, 27]
K_FAIL = 5  # >=5 的核已是人眼明显可感知的模糊


def _sharpest_feed() -> str:
    """挑一张最清晰的 feed 正常截图当合成基底。"""
    best, best_score = None, -1.0
    for p in glob.glob(os.path.join(SCREENSHOT_DIR, "feed_normal_*.png")):
        img = cv2.imdecode(np.frombuffer(open(p, "rb").read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        s = float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
        if s > best_score:
            best, best_score = p, s
    return best


def _make_samples(base_path: str) -> list:
    """返回 [(name, gt_is_blur, image_bytes, blur_full), ...]。"""
    base = cv2.imdecode(np.frombuffer(open(base_path, "rb").read(), np.uint8), cv2.IMREAD_COLOR)
    samples = []
    for k in BLUR_KERNELS:
        if k == 0:
            img = base.copy()
        else:
            img = cv2.GaussianBlur(base, (k, k), 0)
        ok, buf = cv2.imencode(".png", img)
        img_bytes = buf.tobytes()
        blur_full = float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
        gt_is_blur = k >= K_FAIL
        samples.append((f"k{k:02d}", gt_is_blur, img_bytes, blur_full))
    return samples


def _rule_is_blur(img_bytes: bytes) -> bool:
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    v = rule_triage._run_visual_assertions(img, "feed")
    return bool(v.get("is_blur") or v.get("black_white"))


def main() -> int:
    base = _sharpest_feed()
    if not base:
        print("找不到 feed_normal 截图当基底")
        return 1
    print(f"合成基底: {os.path.basename(base)}")
    samples = _make_samples(base)

    has_key = bool(resolve_api_key())
    qwen = QwenVLOpenAI() if has_key else HeuristicMLLM()
    cascade = CascadeOracle()  # 默认工厂：有 key 用真 Qwen
    print(f"MLLM: {qwen.name}  (real_qwen={has_key})\n")

    rows = []
    rule_correct = casc_correct = qwen_correct = 0
    casc_ms_total = qwen_ms_total = 0.0
    n_escalated = 0
    casc_cost = qwen_cost = 0.0

    for name, gt, img_bytes, blur_full in samples:
        # rule
        rule_blur = _rule_is_blur(img_bytes)
        rule_correct += int(rule_blur == gt)

        # cascade
        t0 = time.time()
        cres = cascade.analyze(img_bytes, "feed")
        casc_ms = (time.time() - t0) * 1000.0
        casc_ms_total += casc_ms
        casc_blur = bool(cres.get("is_blur") or cres.get("black_white"))
        casc_correct += int(casc_blur == gt)
        cas_meta = cres.get("cascade", {})
        escalated = bool(cas_meta.get("escalated"))
        n_escalated += int(escalated)
        casc_cost += cas_meta.get("cost_dollars", 0.0)

        # qwen_always
        t0 = time.time()
        qres: OracleResult = qwen.analyze(img_bytes, "feed")
        qwen_ms = (time.time() - t0) * 1000.0
        qwen_ms_total += qwen_ms
        qwen_blur = bool(qres.has_blur or qres.has_blank)
        qwen_correct += int(qwen_blur == gt)
        qwen_cost += qres.cost_dollars

        rows.append({
            "name": name, "gt_blur": gt, "blur_full": round(blur_full, 1),
            "rule": rule_blur, "cascade": casc_blur, "escalated": escalated,
            "qwen": qwen_blur, "casc_ms": round(casc_ms, 1),
        })

    n = len(samples)
    print(f"{'sample':<8}{'blur_full':<11}{'gt':<6}{'rule':<7}{'cascade':<9}{'esc':<6}{'qwen':<6}")
    print("-" * 56)
    for r in rows:
        print(f"{r['name']:<8}{r['blur_full']:<11.1f}{str(r['gt_blur']):<6}{str(r['rule']):<7}"
              f"{str(r['cascade']):<9}{str(r['escalated']):<6}{str(r['qwen']):<6}")

    print()
    print(f"{'oracle':<14}{'blur_acc':<11}{'avg_ms':<10}{'esc_rate':<10}{'cost$':<10}")
    print("-" * 55)
    print(f"{'rule_only':<14}{rule_correct/n:<11.2%}{'~14':<10}{'0%':<10}{'0':<10}")
    print(f"{'cascade':<14}{casc_correct/n:<11.2%}{casc_ms_total/n:<10.1f}"
          f"{n_escalated/n:<10.2%}{round(casc_cost,5):<10}")
    print(f"{'qwen_always':<14}{qwen_correct/n:<11.2%}{qwen_ms_total/n:<10.1f}{'100%':<10}{round(qwen_cost,5):<10}")

    out = os.path.join(HERE, "reports", "ambiguous_evaluation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "base": os.path.basename(base), "real_qwen": has_key, "k_fail": K_FAIL,
            "accuracy": {
                "rule_only": rule_correct / n,
                "cascade": casc_correct / n,
                "qwen_always": qwen_correct / n,
            },
            "escalation_rate": n_escalated / n,
            "rows": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n保存: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
