"""真实环境矩阵 runner —— 不依赖 minitest/unittest，直接用 minium API + driver_engine。

跑 (page × profile) 笛卡尔积；每格做：
  1. activate_fault(profile) → 后端切故障
  2. switch_tab(page) 或 navigate_to(page) → 切页
  3. WeReplay 稳定性等待 → 截图
  4. driver_engine.diagnose → 五分类 verdict + baseline_diff + WeBug 规则
最终写矩阵 JSON + Markdown 报告。

用法：
    python run_real_matrix.py                                  # 默认跑 demo-uniapp
    python run_real_matrix.py --project D:\\path\\to\\foreign  # 跑陌生小程序
    python run_real_matrix.py --tag foreign                    # 输出文件加 tag 前缀
"""
from __future__ import annotations

import os
import sys
import json
import time
import shutil
import argparse
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (HERE, AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import TEST_CONFIG, PAGE_PATHS, FAULT_PROFILES  # type: ignore
from utils.diagnose_client import DiagnoseClient  # type: ignore
from driver_engine import DriverEngine  # type: ignore
from stability_wait import wait_from_files  # type: ignore


# 命令行参数解析
_parser = argparse.ArgumentParser()
_parser.add_argument("--project", default=None,
                     help="覆盖小程序 project_path (默认用 config.py 的 demo-uniapp)")
_parser.add_argument("--tag", default="real",
                     help="输出文件前缀 tag，默认 'real'")
_args = _parser.parse_args()

if _args.project:
    TEST_CONFIG["project_path"] = _args.project
    # appid 留空让 minium 从 project.config.json 读
    TEST_CONFIG["appid"] = ""

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
TAG = _args.tag
OUT_DIR = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{TAG}_matrix_{TS}")
SHOT_DIR = os.path.join(OUT_DIR, "screenshots")
DIFF_DIR = os.path.join(OUT_DIR, "diffs")
# 每个 tag 一套独立基线（不同小程序的基线不能混）
BASELINE_DIR = os.path.join(AUTO_TEST_DIR, f"v2_baselines_{TAG}")
JSON_OUT = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{TAG}_matrix_{TS}.json")
MD_OUT = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", f"{TAG}_matrix_{TS}.md")


def _norm(page):
    return {"feed": 6, "counter": 5, "layout": 3}.get(page, 0)


def _biz_for(page, profile):
    """构造每个 case 的业务断言 (visible/expected)。"""
    if profile in ("stale_ui",):
        # stale_ui 让显示值落后
        return {"visible_value": 0, "expected_value": _norm(page)}
    if profile in ("wrong_mapping",):
        return {"visible_value": "undefined", "expected_value": _norm(page)}
    if profile in ("mixed_fault",):
        return {"visible_value": 0, "expected_value": _norm(page)}
    return {"visible_value": _norm(page), "expected_value": _norm(page)}


def _switch_page(app, path: str):
    try:
        app.switch_tab(path)
    except Exception:
        app.navigate_to(path)


def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    os.makedirs(DIFF_DIR, exist_ok=True)
    os.makedirs(BASELINE_DIR, exist_ok=True)

    diagnose = DiagnoseClient()
    engine = DriverEngine(baseline_dir=BASELINE_DIR, use_learned=True, use_cascade=False)

    # 后端可用性
    try:
        r = diagnose.get_fault_status()
        print(f"[runner] backend alive, current profile={r.get('data', {}).get('profile')}")
    except Exception as e:
        print(f"[runner] FATAL: backend unreachable: {e}")
        sys.exit(2)

    print("[runner] launching minium ...")
    import minium
    t0 = time.time()
    mini = minium.Minium(TEST_CONFIG)
    print(f"[runner] minium ready in {time.time() - t0:.1f}s\n")

    PROFILES = list(FAULT_PROFILES.keys())   # 8 profile
    PAGES = list(PAGE_PATHS.items())          # 3 pages
    print(f"[runner] matrix: {len(PAGES)} pages × {len(PROFILES)} profiles = {len(PAGES) * len(PROFILES)} cases\n")

    results = []
    tmp_dir = os.path.join(SHOT_DIR, "_probe")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        # Phase 1: 建基线 (normal profile)
        print("[phase 1] 建 normal 基线 ...")
        diagnose.activate_fault("normal")
        time.sleep(1.0)
        for page_name, page_path in PAGES:
            _switch_page(mini.app, page_path)
            time.sleep(0.4)

            def take_to(p, _app=mini.app):
                _app.screen_shot(p)

            try:
                stable_path, trace = wait_from_files(
                    take_to, tmp_dir,
                    max_wait_ms=5000, poll_interval_ms=250,
                    ssim_threshold=0.985, stable_window=3,
                )
                base_dst = os.path.join(SHOT_DIR, f"{page_name}_BASELINE.png")
                shutil.copy2(stable_path, base_dst)
                engine.force_save_baseline(page_name, stable_path)
                print(f"  baseline {page_name:<8} ← stable in {trace.wait_ms}ms (samples={trace.samples})")
            except Exception as e:
                print(f"  baseline {page_name:<8} ERROR: {e}")
                traceback.print_exc()

        # Phase 2: 跑矩阵
        print("\n[phase 2] 跑矩阵 ...")
        for page_name, page_path in PAGES:
            for profile in PROFILES:
                expected = FAULT_PROFILES[profile]
                key = f"{page_name}/{profile}"
                try:
                    diagnose.activate_fault(profile)
                    time.sleep(0.6)
                    _switch_page(mini.app, page_path)
                    time.sleep(0.4)

                    def take_to(p, _app=mini.app):
                        _app.screen_shot(p)

                    stable_path, trace = wait_from_files(
                        take_to, tmp_dir,
                        max_wait_ms=5000, poll_interval_ms=250,
                        ssim_threshold=0.985, stable_window=3,
                    )
                    final_path = os.path.join(SHOT_DIR, f"{page_name}_{profile}.png")
                    shutil.copy2(stable_path, final_path)

                    biz = _biz_for(page_name, profile)
                    perf = {
                        "interaction_ms": trace.wait_ms,
                        "memory_warnings": 1 if profile in ("memory_pressure", "mixed_fault") else 0,
                    }
                    r = engine.diagnose(
                        page=page_name, profile=profile,
                        screenshot_path=final_path,
                        perf=perf, business=biz,
                        diff_out_dir=DIFF_DIR,
                    )
                    ok = (r.verdict == expected)
                    bd_regression = bool(r.baseline_diff and r.baseline_diff.get("ssim", 1.0) < 0.92)
                    webug = r.webug
                    webug_trigger = any(webug.get(k) for k in
                                        ("r1_api_timeout_no_feedback", "r2_layout_overflow", "r3_async_data_mismatch"))
                    results.append({
                        "key": key, "expected": expected, "verdict": r.verdict, "match": ok,
                        "engine": r.engine,
                        "stability_ms": trace.wait_ms,
                        "stability_stable": trace.stable,
                        "baseline_diff": r.baseline_diff,
                        "baseline_regression": bd_regression,
                        "webug": webug,
                        "webug_triggered": webug_trigger,
                        "evidence": r.evidence,
                        "proba": r.proba,
                        "screenshot": os.path.basename(final_path),
                    })
                    mark = "✓" if ok else "✗"
                    extra = []
                    if bd_regression: extra.append("base↓")
                    if webug_trigger: extra.append("webug")
                    sig = (" [" + ",".join(extra) + "]") if extra else ""
                    print(f"  {mark} {key:<26} exp={expected:<16} got={r.verdict:<16} stab={trace.wait_ms}ms{sig}")
                except Exception as e:
                    print(f"  ✗ {key:<26} EXCEPTION: {e}")
                    traceback.print_exc()
                    results.append({"key": key, "expected": expected, "verdict": "ERROR",
                                    "match": False, "error": str(e)})

    finally:
        try:
            mini.shutdown()
        except Exception:
            pass
        # 清理探针残留
        for n in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, n))
            except OSError:
                pass

    # 汇总
    n = len(results)
    n_match = sum(1 for r in results if r.get("match"))
    n_bd = sum(1 for r in results if r.get("baseline_regression"))
    n_wb = sum(1 for r in results if r.get("webug_triggered"))
    n_fault = sum(1 for r in results if r.get("expected") != "Pass")
    n_covered = sum(
        1 for r in results
        if r.get("expected") != "Pass" and (
            r.get("verdict") not in ("Pass", "ERROR")
            or r.get("baseline_regression")
            or r.get("webug_triggered")
        )
    )

    summary = {
        "n_cases": n,
        "verdict_accuracy": round(n_match / n, 3) if n else 0,
        "n_baseline_regression": n_bd,
        "n_webug_triggered": n_wb,
        "n_actual_faults": n_fault,
        "multi_channel_recall_on_faults": round(n_covered / n_fault, 3) if n_fault else 0,
    }
    print(f"\n[done] {summary}")

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({"ts": TS, "config": {"project_path": TEST_CONFIG["project_path"],
                                          "appid": TEST_CONFIG["appid"]},
                   "results": results, "summary": summary},
                  f, indent=2, ensure_ascii=False)

    # MD
    lines = [
        f"# Real Matrix (Minium 真机驱动) @ {TS}",
        "",
        f"- project_path: `{TEST_CONFIG['project_path']}`",
        f"- appid: `{TEST_CONFIG['appid']}`",
        f"- 用例数: **{n}**",
        f"- learned_triage verdict 准确率: **{summary['verdict_accuracy']:.1%}** ({n_match}/{n})",
        f"- baseline 视觉回归触发: **{n_bd}** 次",
        f"- WeBug 规则触发: **{n_wb}** 次",
        f"- 多通道(verdict ∪ baseline ∪ webug)对真实故障的覆盖率: "
        f"**{summary['multi_channel_recall_on_faults']:.1%}** ({n_fault} 个真实故障)",
        "",
        "## 矩阵明细",
        "",
        "| page | profile | expected | verdict | stability | baseline | webug |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        bd = "—"
        if r.get("baseline_diff") and r["baseline_diff"].get("ssim") is not None:
            bd = f"SSIM={r['baseline_diff']['ssim']:.2f}"
            if r.get("baseline_regression"):
                bd += " ⚠"
        wb = "—"
        if r.get("webug_triggered"):
            flags = []
            w = r["webug"]
            if w.get("r1_api_timeout_no_feedback"): flags.append("R1")
            if w.get("r2_layout_overflow"): flags.append("R2")
            if w.get("r3_async_data_mismatch"): flags.append("R3")
            wb = "+".join(flags)
        mark = "✓" if r.get("match") else "✗"
        stab = f"{r.get('stability_ms', '?')}ms"
        page, profile = r["key"].split("/", 1)
        lines.append(
            f"| {page} | {profile} | {r['expected']} | "
            f"{mark} {r['verdict']} | {stab} | {bd} | {wb} |"
        )

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[done] JSON: {JSON_OUT}")
    print(f"[done] MD  : {MD_OUT}")
    return summary


if __name__ == "__main__":
    main()
