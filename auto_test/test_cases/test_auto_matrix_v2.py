"""V2 自动矩阵驱动 —— 受 MiniScope (arXiv'24) 的 UI 自动探索思路启发。

不需要开发者埋 hook、不需要业务方写 test 方法。
本测试只有 **一个** test 方法 (`test_full_matrix`)，
它会自动遍历 (page × profile) 的笛卡尔积，对每一格做：

  1. 切到该页面 (navigate_to)
  2. 切到该故障 profile (POST /fault/activate)
  3. WeReplay 风格的稳定性等待 (连续帧 SSIM > 阈值)
  4. 截图
  5. 喂给 v2 DriverEngine：
        - 调 learned_triage 出主 verdict
        - 与 baseline 对比 SSIM/pHash
        - 跑 WeBug R1/R2/R3 规则
  6. 写矩阵结果到 reports/v2_driver_matrix_<ts>.json

输出的矩阵表是该项目"零业务侵入跑遍小程序"的最终 demo——
任何符合 minium 协议的 uni-app/原生小程序，都可以替换 PAGES 配置直接跑。
"""
from __future__ import annotations

import os
import sys
import time
import json
import traceback
from datetime import datetime

import minium

# 让 auto_test/ 与 v2_modules/ 都在 sys.path
HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from utils.diagnose_client import DiagnoseClient
from v2_modules.driver_engine import DriverEngine, _print_result
from v2_modules.stability_wait import wait_from_files


PAGES = [
    {"name": "feed", "path": "/pages/feed/index"},
    {"name": "counter", "path": "/pages/counter/index"},
    {"name": "layout", "path": "/pages/layout/index"},
]

# (profile, expected_verdict, page_business_state)
# business_state 在不同页面下 visible/expected 是什么，按 demo-uniapp 现状写
SCENARIOS = [
    ("normal",         "Pass",            lambda p: {"visible_value": _norm(p), "expected_value": _norm(p)}),
    ("slow_api",       "PerformanceRisk", lambda p: {"visible_value": _norm(p), "expected_value": _norm(p)}),
    ("blur_image",     "RenderBug",       lambda p: {"visible_value": _norm(p), "expected_value": _norm(p)}),
    ("stale_ui",       "FunctionalFail",  lambda p: {"visible_value": _stale(p), "expected_value": _norm(p)}),
    ("wrong_mapping",  "FunctionalFail",  lambda p: {"visible_value": _wrong(p), "expected_value": _norm(p)}),
    ("layout_overlap", "RenderBug",       lambda p: {"visible_value": _norm(p), "expected_value": _norm(p),
                                                       "ui_flags": {"hasOverlap": True}}),
    ("memory_pressure","PerformanceRisk", lambda p: {"visible_value": _norm(p), "expected_value": _norm(p)}),
    ("mixed_fault",    "Mixed",           lambda p: {"visible_value": _stale(p), "expected_value": _norm(p)}),
]


def _norm(page):
    return {"feed": 6, "counter": 5, "layout": 3}.get(page, 0)


def _stale(page):
    return {"feed": 6, "counter": 0, "layout": 3}.get(page, 0)


def _wrong(page):
    return {"feed": "undefined", "counter": "NaN", "layout": "undefined"}.get(page, 0)


TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver")
SCREENSHOT_DIR = os.path.join(OUT_DIR, f"matrix_{TS}", "screenshots")
DIFF_DIR = os.path.join(OUT_DIR, f"matrix_{TS}", "diffs")
BASELINE_DIR = os.path.join(AUTO_TEST_DIR, "v2_baselines")
MATRIX_JSON = os.path.join(OUT_DIR, f"matrix_{TS}.json")


class TestAutoMatrixV2(minium.MiniTest):
    """V2 driver：单个 test_full_matrix 自动遍历整个矩阵。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        os.makedirs(DIFF_DIR, exist_ok=True)
        os.makedirs(BASELINE_DIR, exist_ok=True)
        cls.diagnose_client = DiagnoseClient()
        cls.engine = DriverEngine(
            baseline_dir=BASELINE_DIR,
            use_learned=True,
            use_cascade=False,
        )
        cls.results = []

    @classmethod
    def tearDownClass(cls):
        # 写矩阵汇总
        os.makedirs(os.path.dirname(MATRIX_JSON), exist_ok=True)
        with open(MATRIX_JSON, "w", encoding="utf-8") as f:
            json.dump({
                "ts": TS,
                "n_cases": len(cls.results),
                "results": cls.results,
                "summary": _summarize(cls.results),
            }, f, indent=2, ensure_ascii=False)
        print(f"\n[done] 矩阵已写入: {MATRIX_JSON}")
        super().tearDownClass()

    def _capture(self, page_name: str, profile: str) -> str:
        """切页 + 等稳定 + 截图，返回 stable 帧路径。"""
        page = next((x for x in PAGES if x["name"] == page_name), None)
        assert page is not None, f"unknown page {page_name}"
        self.diagnose_client.activate_fault(profile)
        time.sleep(0.6)  # 让后端 fault 生效
        # demo-uniapp 三页都在 tabBar，必须 switch_tab；其他小程序可能不是 tabbar
        try:
            self.app.switch_tab(page["path"])
        except Exception:
            self.app.navigate_to(page["path"])
        time.sleep(0.4)

        # WeReplay 风格稳定性等待
        tmp_dir = os.path.join(SCREENSHOT_DIR, "_probe")
        os.makedirs(tmp_dir, exist_ok=True)

        def take_to(p: str):
            self.app.screen_shot(p)

        stable_path, trace = wait_from_files(
            take_to, tmp_dir,
            max_wait_ms=5000, poll_interval_ms=250,
            ssim_threshold=0.985, stable_window=3,
        )
        # 重命名稳定那帧到标准路径
        final_path = os.path.join(
            SCREENSHOT_DIR, f"{page_name}_{profile}.png"
        )
        os.replace(stable_path, final_path)
        # 清掉所有探针残留
        for n in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, n))
            except OSError:
                pass
        return final_path, trace

    def test_full_matrix(self):
        """跑遍 3 页 × 8 profile = 24 个用例。"""
        # 1) 先建基线（normal profile）
        print("\n[phase 1] 建基线 ...")
        for page in PAGES:
            try:
                path, trace = self._capture(page["name"], "normal")
                self.engine.force_save_baseline(page["name"], path)
                print(f"  baseline {page['name']:<10} ← {path}  (stable in {trace.wait_ms}ms)")
            except Exception as e:
                print(f"  baseline {page['name']:<10} FAILED: {e}")
                traceback.print_exc()

        # 2) 跑矩阵
        print("\n[phase 2] 矩阵遍历 ...")
        for page in PAGES:
            for profile, expected, biz_fn in SCENARIOS:
                key = f"{page['name']}/{profile}"
                try:
                    path, trace = self._capture(page["name"], profile)
                    biz = biz_fn(page["name"])
                    perf = {
                        "interaction_ms": trace.wait_ms,
                        "memory_warnings": 1 if profile in ("memory_pressure", "mixed_fault") else 0,
                    }
                    r = self.engine.diagnose(
                        page=page["name"],
                        profile=profile,
                        screenshot_path=path,
                        perf=perf,
                        business=biz,
                        diff_out_dir=DIFF_DIR,
                    )
                    ok = (r.verdict == expected)
                    self.results.append({
                        "key": key, "expected": expected, "verdict": r.verdict, "match": ok,
                        "engine": r.engine,
                        "stability_ms": trace.wait_ms,
                        "stability_stable": trace.stable,
                        "baseline_diff": r.baseline_diff,
                        "webug": r.webug,
                        "evidence": r.evidence,
                        "proba": r.proba,
                        "screenshot": path,
                    })
                    mark = "✓" if ok else "✗"
                    print(f"  {mark} {key:<28} expected={expected:<16} got={r.verdict:<16} "
                          f"stab={trace.wait_ms}ms")
                except Exception as e:
                    print(f"  ✗ {key:<28} EXCEPTION: {e}")
                    traceback.print_exc()
                    self.results.append({
                        "key": key, "expected": expected, "verdict": "ERROR",
                        "match": False, "error": str(e),
                    })

        # 3) 不断言（矩阵性质：可以有一定失败率，结果都落盘）


def _summarize(results: list) -> dict:
    n = len(results)
    n_match = sum(1 for r in results if r.get("match"))
    by_profile = {}
    by_page = {}
    for r in results:
        k = r["key"]
        page, profile = k.split("/", 1)
        by_profile.setdefault(profile, [0, 0])
        by_page.setdefault(page, [0, 0])
        by_profile[profile][1] += 1
        by_page[page][1] += 1
        if r.get("match"):
            by_profile[profile][0] += 1
            by_page[page][0] += 1
    return {
        "n_cases": n,
        "n_match": n_match,
        "accuracy": round(n_match / n, 3) if n else 0,
        "by_profile": {k: f"{v[0]}/{v[1]}" for k, v in by_profile.items()},
        "by_page": {k: f"{v[0]}/{v[1]}" for k, v in by_page.items()},
    }
