"""离线版 v2 driver smoke：用历史截图代替真实抓拍，跑遍 (page × profile) 矩阵。

为什么需要离线版：
    Minium 真实抓拍需要 (微信开发者工具 + minium + 编译好的小程序) 三者就位。
    教学场景下没法保证。本脚本用 auto_test/reports/screenshots/ 下的历史截图，
    完整跑一遍 v2 pipeline（learned_triage + baseline_diff + WeBug 规则），
    证明 driver_engine + v2_modules 的端到端逻辑可用。

输出：
    auto_test/reports/v2_driver/smoke_offline_<ts>.json   (矩阵原始)
    auto_test/reports/v2_driver/smoke_offline_<ts>.md     (人类可读)
    auto_test/v2_baselines/                                (基线截图)
    auto_test/reports/v2_driver/smoke_offline_<ts>/diffs/  (基线 diff 图)
"""
from __future__ import annotations

import os
import sys
import json
import glob
import io
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (HERE, AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from driver_engine import DriverEngine  # type: ignore

# Windows 控制台 utf-8 兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


SCREENSHOT_DIR = os.path.join(AUTO_TEST_DIR, "reports", "screenshots")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"smoke_offline_{TS}")
DIFF_DIR = os.path.join(OUT_DIR, "diffs")
BASELINE_DIR = os.path.join(AUTO_TEST_DIR, "v2_baselines")
JSON_OUT = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"smoke_offline_{TS}.json")
MD_OUT = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"smoke_offline_{TS}.md")


# 14 个可用矩阵单元格。stable_ms 是模拟值，模拟"实际页面"的稳定耗时。
CASES = [
    # (page, profile, expected, glob_pattern, mock_interaction_ms, business)
    ("feed",    "normal",          "Pass",            "feed_normal_*",                300,
        {"visible_value": 6, "expected_value": 6}),
    ("feed",    "blur_image",      "RenderBug",       "feed_blur_image_*",            350,
        {"visible_value": 6, "expected_value": 6}),
    ("feed",    "slow_api",        "PerformanceRisk", "feed_slow_api_*",              1400,
        {"visible_value": 6, "expected_value": 6}),
    ("feed",    "memory_pressure", "PerformanceRisk", "feed_memory_pressure_*",       450,
        {"visible_value": 6, "expected_value": 6}),
    ("feed",    "mixed_fault",     "Mixed",           "feed_mixed_fault_*",           1100,
        {"visible_value": 0, "expected_value": 6}),

    ("counter", "normal",          "Pass",            "counter_normal_*",             300,
        {"visible_value": 5, "expected_value": 5}),
    ("counter", "slow_api",        "PerformanceRisk", "counter_slow_api_*",           1400,
        {"visible_value": 5, "expected_value": 5}),
    ("counter", "stale_ui",        "FunctionalFail",  "counter_stale_ui_*",           300,
        {"visible_value": 0, "expected_value": 5}),
    ("counter", "wrong_mapping",   "FunctionalFail",  "counter_wrong_mapping_*",      300,
        {"visible_value": "undefined", "expected_value": 5}),
    ("counter", "mixed_fault",     "Mixed",           "counter_mixed_fault_*",        1200,
        {"visible_value": 0, "expected_value": 5}),

    ("layout",  "normal",          "Pass",            "layout_normal_*",              300,
        {"visible_value": 3, "expected_value": 3}),
    ("layout",  "slow_api",        "PerformanceRisk", "layout_slow_api_*",            1400,
        {"visible_value": 3, "expected_value": 3}),
    ("layout",  "layout_overlap",  "RenderBug",       "layout_layout_overlap_*",      350,
        {"visible_value": 3, "expected_value": 3, "ui_flags": {"hasOverlap": True}}),
    ("layout",  "memory_pressure", "PerformanceRisk", "layout_memory_pressure_*",     450,
        {"visible_value": 3, "expected_value": 3}),
]


def _find(pattern: str) -> str | None:
    paths = sorted(glob.glob(os.path.join(SCREENSHOT_DIR, pattern + ".png")))
    return paths[-1] if paths else None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DIFF_DIR, exist_ok=True)

    eng = DriverEngine(
        baseline_dir=BASELINE_DIR,
        use_learned=True,
        use_cascade=False,
    )

    # 1) 用 normal 截图建基线
    print("[phase 1] 建基线（每个 page 用其 normal 截图）")
    for page in ("feed", "counter", "layout"):
        base_path = _find(f"{page}_normal_normal_*")
        if base_path is None:
            print(f"  WARN: 找不到 {page} 的 normal 截图，跳过基线")
            continue
        saved = eng.force_save_baseline(page, base_path)
        print(f"  baseline {page:<8} ← {os.path.basename(saved)}")

    # 2) 跑矩阵
    print("\n[phase 2] 跑矩阵 (14 cases)")
    results = []
    for page, profile, expected, pattern, interaction_ms, biz in CASES:
        path = _find(pattern)
        if path is None:
            print(f"  ✗ {page}/{profile:<16} NO SCREENSHOT")
            results.append({
                "page": page, "profile": profile, "expected": expected,
                "verdict": "MISSING", "match": False, "screenshot": None,
            })
            continue
        perf = {
            "interaction_ms": interaction_ms,
            "memory_warnings": 1 if profile in ("memory_pressure", "mixed_fault") else 0,
        }
        r = eng.diagnose(
            page=page, profile=profile,
            screenshot_path=path,
            perf=perf, business=biz,
            diff_out_dir=DIFF_DIR,
        )
        ok = (r.verdict == expected)
        # baseline_diff 单独的"视觉回归"评估（独立于 learned verdict）
        bd_regression = bool(r.baseline_diff and r.baseline_diff.get("ssim", 1.0) < 0.92)
        # WeBug 规则单独触发
        webug_trigger = (
            r.webug.get("r1_api_timeout_no_feedback")
            or r.webug.get("r2_layout_overflow")
            or r.webug.get("r3_async_data_mismatch")
        )
        results.append({
            "page": page, "profile": profile, "expected": expected,
            "verdict": r.verdict, "match": ok,
            "engine": r.engine,
            "baseline_regression": bd_regression,
            "baseline_ssim": r.baseline_diff.get("ssim") if r.baseline_diff else None,
            "baseline_phash_hamming": r.baseline_diff.get("phash_hamming") if r.baseline_diff else None,
            "webug_triggered": webug_trigger,
            "webug": r.webug,
            "evidence": r.evidence,
            "proba": r.proba,
            "screenshot": os.path.basename(path),
        })
        mark = "✓" if ok else "✗"
        extra_signals = []
        if bd_regression:
            extra_signals.append("baseline↓")
        if webug_trigger:
            extra_signals.append("webug")
        sig_str = (" [" + ", ".join(extra_signals) + "]") if extra_signals else ""
        print(f"  {mark} {page}/{profile:<16} exp={expected:<16} got={r.verdict:<16}{sig_str}")

    # 3) 汇总
    n = len(results)
    n_match = sum(1 for r in results if r.get("match"))
    n_bd = sum(1 for r in results if r.get("baseline_regression"))
    n_wb = sum(1 for r in results if r.get("webug_triggered"))

    # 多通道 OR 一致性：verdict ≠ Pass OR baseline_regression OR webug_triggered 视为"被发现"
    n_any_alarm = sum(
        1 for r in results
        if (r.get("verdict") not in ("Pass", "MISSING")) or r.get("baseline_regression") or r.get("webug_triggered")
    )
    n_actual_alarm = sum(1 for r in results if r.get("expected") != "Pass")
    coverage = (sum(
        1 for r in results
        if r.get("expected") != "Pass" and (
            r.get("verdict") not in ("Pass", "MISSING")
            or r.get("baseline_regression")
            or r.get("webug_triggered")
        )
    ) / n_actual_alarm) if n_actual_alarm else 0

    summary = {
        "n_cases": n,
        "verdict_accuracy": round(n_match / n, 3) if n else 0,
        "n_baseline_regression": n_bd,
        "n_webug_triggered": n_wb,
        "multi_channel_recall_on_faults": round(coverage, 3),
        "n_actual_faults": n_actual_alarm,
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({"ts": TS, "results": results, "summary": summary},
                  f, indent=2, ensure_ascii=False)
    print(f"\n[done] JSON: {JSON_OUT}")

    # MD 报告
    lines = [
        f"# V2 Driver Smoke (offline) @ {TS}",
        "",
        f"- 用例数: **{n}**",
        f"- learned_triage verdict 准确率: **{summary['verdict_accuracy']:.1%}** ({n_match}/{n})",
        f"- baseline 视觉回归触发: **{n_bd}** 次",
        f"- WeBug 规则触发: **{n_wb}** 次",
        f"- 多通道(verdict ∪ baseline ∪ webug)对真实故障的覆盖率: "
        f"**{summary['multi_channel_recall_on_faults']:.1%}** ({n_actual_alarm} 个真实故障)",
        "",
        "## 矩阵明细",
        "",
        "| page | profile | expected | verdict | baseline | webug |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        bd = "—"
        if r.get("baseline_ssim") is not None:
            bd = f"SSIM={r['baseline_ssim']:.2f}"
            if r.get("baseline_regression"):
                bd += " ⚠"
        wb = "—"
        if r.get("webug_triggered"):
            flags = []
            if r["webug"].get("r1_api_timeout_no_feedback"):
                flags.append("R1")
            if r["webug"].get("r2_layout_overflow"):
                flags.append("R2")
            if r["webug"].get("r3_async_data_mismatch"):
                flags.append("R3")
            wb = "+".join(flags)
        mark = "✓" if r.get("match") else "✗"
        lines.append(
            f"| {r['page']} | {r['profile']} | {r['expected']} | "
            f"{mark} {r['verdict']} | {bd} | {wb} |"
        )

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[done] MD : {MD_OUT}")

    return summary


if __name__ == "__main__":
    s = main()
    print("\nSummary:", json.dumps(s, ensure_ascii=False))
