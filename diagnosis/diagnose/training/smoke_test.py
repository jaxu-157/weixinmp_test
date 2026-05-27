"""端到端烟雾测试：用历史截图跑一遍 rule vs learned，输出对比矩阵。

不需要前端/小程序运行，只需要本地的诊断模块。
"""
from __future__ import annotations

import os
import sys
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from diagnose.triage import run_triage  # noqa: E402
from diagnose.learned_triage import run_triage_learned, is_available  # noqa: E402


SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "auto_test", "reports", "screenshots",
)


def _infer_context(filename: str) -> tuple[str, str]:
    """从截图文件名推断 (page, profile)。

    文件名形如：counter_mixed_fault_mixed_fault_20260511_024809.png
    格式是 page_<doublename>_<profile>_<ts>.png
    """
    base = os.path.basename(filename).rsplit(".", 1)[0]
    parts = base.split("_")
    if not parts:
        return "feed", "normal"
    page = parts[0]
    # 时间戳在末尾两段（YYYYMMDD_HHMMSS），前面是 profile
    profile_parts = parts[1:-2]
    # profile_parts 里前后是重复的 (page_<name>_<name>)，取后半段
    n = len(profile_parts)
    if n >= 2:
        # 后半段就是 profile
        profile = "_".join(profile_parts[n // 2:])
    else:
        profile = profile_parts[0] if profile_parts else "normal"
    return page, profile


EXPECT = {
    ("feed", "normal"): "Pass",
    ("feed", "slow_api"): "PerformanceRisk",
    ("feed", "blur_image"): "RenderBug",
    ("feed", "memory_pressure"): "PerformanceRisk",
    ("feed", "mixed_fault"): "Mixed",
    ("counter", "normal"): "Pass",
    ("counter", "slow_api"): "PerformanceRisk",
    ("counter", "stale_ui"): "FunctionalFail",
    ("counter", "wrong_mapping"): "FunctionalFail",
    ("counter", "mixed_fault"): "Mixed",
    ("layout", "normal"): "Pass",
    ("layout", "slow_api"): "PerformanceRisk",
    ("layout", "layout_overlap"): "FunctionalFail",
    ("layout", "memory_pressure"): "PerformanceRisk",
}


def _build_page_state(page: str, profile: str) -> dict:
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


def _build_perf(profile: str) -> dict:
    perf = {"interactionMs": 100, "memoryWarningCount": 0}
    if profile in ("slow_api", "mixed_fault"):
        perf["interactionMs"] = 900
    if profile in ("memory_pressure", "mixed_fault"):
        perf["memoryWarningCount"] = 1
    return perf


def main():
    if not is_available():
        print("❌ learned 模型未训练，请先 python diagnosis/diagnose/training/train.py")
        return 1

    pngs = sorted(glob.glob(os.path.join(SCREENSHOT_DIR, "*.png")))
    if not pngs:
        print(f"❌ 没有找到截图: {SCREENSHOT_DIR}")
        return 1

    # 每种 (page, profile) 只取最新一张
    latest: dict = {}
    for p in pngs:
        page, profile = _infer_context(p)
        key = (page, profile)
        if key in EXPECT and (key not in latest or p > latest[key]):
            latest[key] = p

    rows = []
    rule_correct = 0
    learned_correct = 0
    n = 0
    for (page, profile), path in sorted(latest.items()):
        expected = EXPECT[(page, profile)]
        with open(path, "rb") as f:
            img_bytes = f.read()
        page_state = _build_page_state(page, profile)
        perf_data = _build_perf(profile)

        r_rule = run_triage(img_bytes, page_type=page, fault_profile=profile,
                            page_state=page_state, perf_data=perf_data)
        r_learn = run_triage_learned(img_bytes, page_type=page, fault_profile=profile,
                                     page_state=page_state, perf_data=perf_data)
        v_rule = r_rule.get("verdict")
        v_learn = r_learn.get("verdict")
        n += 1
        if v_rule == expected:
            rule_correct += 1
        if v_learn == expected:
            learned_correct += 1
        rows.append({
            "page": page,
            "profile": profile,
            "expected": expected,
            "rule": v_rule,
            "learned": v_learn,
            "rule_ok": v_rule == expected,
            "learned_ok": v_learn == expected,
            "screenshot": os.path.basename(path),
        })

    # 打印表
    print(f"\n{'page':<8}{'profile':<18}{'expected':<18}{'rule':<18}{'learned':<18}{'rule?':<6}{'learned?':<8}")
    print("-" * 100)
    for r in rows:
        print(f"{r['page']:<8}{r['profile']:<18}{r['expected']:<18}{r['rule']:<18}{r['learned']:<18}"
              f"{'OK' if r['rule_ok'] else 'X':<6}{'OK' if r['learned_ok'] else 'X':<8}")

    print(f"\n规则法准确率: {rule_correct}/{n} = {rule_correct/n:.2%}")
    print(f"模型法准确率: {learned_correct}/{n} = {learned_correct/n:.2%}")

    # 落 JSON
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "reports", "smoke_test.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "n": n,
            "rule_accuracy": rule_correct / n,
            "learned_accuracy": learned_correct / n,
            "rows": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n保存: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
