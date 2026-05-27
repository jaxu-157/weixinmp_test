"""Driver Engine —— 把 v2 三个新模块串到现有 learned_triage 的管线。

输入（一次诊断 = 一个采集帧）：
    page:                页面标识，如 'feed' / 'counter' / 'layout'
    profile:             当前故障 profile，如 'normal' / 'slow_api'
    screenshot_path:     主截图路径（最终稳定那帧）
    pre_action_image:    交互前截图（可选，用于 WeBug R1）
    perf:                {'interaction_ms': float, 'memory_warnings': int, ...}
    business:            {'visible_value': any, 'expected_value': any, 'ui_flags': {...}}
    dom_info:            {'scrollHeight': int, 'clientHeight': int, ...}（可选）
    dom_text:            页面 OCR 或 wxml 文本（可选）

输出：
    {
        'page': ..., 'profile': ...,
        'verdict':              learned_triage 给出的五分类
        'visual', 'functional', 'performance':  原 oracle 输出
        'baseline_diff':        SSIM/pHash/像素差/是否回归
        'webug':                R1/R2/R3 信号 + 证据
        'engine':               所用 engine 名（learned_tree_v1 等）
        'evidence':             组合证据字符串列表
    }
"""
from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional, Any

import numpy as np
from PIL import Image

# 让 diagnosis/diagnose/ 在 sys.path 里
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DIAGNOSIS_DIR = os.path.join(_REPO_ROOT, "diagnosis")
if _DIAGNOSIS_DIR not in sys.path:
    sys.path.insert(0, _DIAGNOSIS_DIR)

try:
    from .baseline_compare import BaselineStore, compare_to_baseline, BaselineDiff
    from .webug_rules import evaluate_webug, WeBugSignals
except ImportError:
    # 直接以 `python driver_engine.py` 运行时 fallback
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from baseline_compare import BaselineStore, compare_to_baseline, BaselineDiff
    from webug_rules import evaluate_webug, WeBugSignals


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _img_array(path: str) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


@dataclass
class EngineResult:
    page: str
    profile: str
    verdict: str
    visual: dict
    functional: dict
    performance: dict
    baseline_diff: Optional[dict]
    webug: dict
    engine: str
    evidence: list
    explanation: str
    proba: dict
    screenshot_path: str

    def to_dict(self) -> dict:
        return asdict(self)


class DriverEngine:
    """driver 路径的端到端推理引擎。

    用法：
        eng = DriverEngine(baseline_dir='auto_test/v2_baselines',
                           use_learned=True, use_cascade=False)
        # 第一次跑 normal profile：让 engine 自动建基线
        eng.maybe_save_baseline('feed', '/path/to/feed_normal.png')
        # 之后每个 (page, profile) 跑：
        result = eng.diagnose(page='feed', profile='blur_image',
                              screenshot_path='/path/feed_blur.png',
                              perf={'interaction_ms': 300, 'memory_warnings': 0},
                              business={'visible_value': 10, 'expected_value': 10})
    """

    def __init__(
        self,
        baseline_dir: str,
        use_learned: bool = True,
        use_cascade: bool = False,
    ):
        self.baseline_store = BaselineStore(baseline_dir)
        self.use_learned = use_learned
        self.use_cascade = use_cascade

        # lazy import diagnosis 包，避免 v2_modules 单测时被拖累
        if self.use_learned:
            try:
                from diagnose.learned_triage import run_triage_learned, is_available
                if not is_available():
                    print("[driver_engine] learned 模型不存在，fallback 到 rule_triage")
                    self.use_learned = False
            except ImportError as e:
                print(f"[driver_engine] 无法导入 learned_triage: {e}, fallback 到 rule_triage")
                self.use_learned = False

    # ---------- 基线管理 ----------

    def maybe_save_baseline(self, page: str, screenshot_path: str) -> str:
        """如果该 page 还没基线，把当前截图存为基线。返回基线路径。"""
        if not self.baseline_store.has_baseline(page):
            return self.baseline_store.save_baseline(page, screenshot_path)
        return self.baseline_store.baseline_path(page)

    def force_save_baseline(self, page: str, screenshot_path: str) -> str:
        """强制覆盖该 page 的基线。"""
        return self.baseline_store.save_baseline(page, screenshot_path)

    # ---------- 核心：单次诊断 ----------

    def diagnose(
        self,
        page: str,
        profile: str,
        screenshot_path: str,
        perf: Optional[dict] = None,
        business: Optional[dict] = None,
        pre_action_image_path: Optional[str] = None,
        dom_info: Optional[dict] = None,
        dom_text: Optional[str] = None,
        diff_out_dir: Optional[str] = None,
    ) -> EngineResult:
        perf = perf or {}
        business = business or {}

        # 1) 主 verdict —— 走现有 learned_triage / rule_triage
        page_state = {
            "page": page,
            "faultProfile": profile,
            "visibleValue": business.get("visible_value"),
            "expectedValue": business.get("expected_value"),
            "uiFlags": business.get("ui_flags", {}),
        }
        perf_data = {
            "interaction_ms": perf.get("interaction_ms", 0),
            "memory_warnings": perf.get("memory_warnings", 0),
        }

        image_bytes = _read_bytes(screenshot_path)
        if self.use_learned:
            from diagnose.learned_triage import run_triage_learned
            tri = run_triage_learned(
                image_bytes,
                page_type=page,
                fault_profile=profile,
                page_state=page_state,
                perf_data=perf_data,
                use_cascade=self.use_cascade,
            )
        else:
            from diagnose.triage import run_triage
            tri = run_triage(
                image_bytes,
                page_type=page,
                fault_profile=profile,
                page_state=page_state,
                perf_data=perf_data,
            )

        # 2) 基线对比（仅在有基线时）
        baseline_diff: Optional[BaselineDiff] = self.baseline_store.diff(
            page, screenshot_path, diff_out_dir
        )

        # 3) WeBug 三规则
        cur_img = _img_array(screenshot_path)
        pre_img = _img_array(pre_action_image_path) if pre_action_image_path else None
        webug: WeBugSignals = evaluate_webug(
            pre_action_img=pre_img,
            post_action_img=cur_img if pre_img is not None else None,
            final_img=cur_img,
            interaction_ms=perf.get("interaction_ms"),
            dom_info=dom_info,
            dom_text=dom_text,
            visible_value=business.get("visible_value"),
            expected_value=business.get("expected_value"),
        )

        # 4) 合并 evidence
        evidence = []
        if baseline_diff is not None:
            if baseline_diff.is_regression:
                evidence.append(
                    f"[baseline] SSIM={baseline_diff.ssim} px_diff={baseline_diff.pixel_diff_ratio} "
                    f"→ visual regression vs baseline"
                )
            else:
                evidence.append(f"[baseline] SSIM={baseline_diff.ssim} (no regression)")
        if webug.r1_api_timeout_no_feedback:
            evidence.append(f"[webug-R1] {webug.r1_evidence}")
        if webug.r2_layout_overflow:
            evidence.append(f"[webug-R2] {webug.r2_evidence}")
        if webug.r3_async_data_mismatch:
            evidence.append(f"[webug-R3] {webug.r3_evidence}")

        engine_name = tri.get("triage_meta", {}).get("engine", "rule_v1")

        return EngineResult(
            page=page,
            profile=profile,
            verdict=tri.get("verdict", "Unknown"),
            visual=tri.get("visual", {}),
            functional=tri.get("functional", {}),
            performance=tri.get("performance", {}),
            baseline_diff=baseline_diff.to_dict() if baseline_diff else None,
            webug=webug.to_dict(),
            engine=engine_name,
            evidence=evidence,
            explanation=tri.get("explanation", ""),
            proba=tri.get("triage_meta", {}).get("proba", {}),
            screenshot_path=screenshot_path,
        )


def _print_result(r: EngineResult):
    print(f"\n=== {r.page} | {r.profile} ===")
    print(f"  verdict = {r.verdict}   engine={r.engine}")
    print(f"  explanation: {r.explanation}")
    if r.baseline_diff:
        bd = r.baseline_diff
        print(f"  baseline_diff: ssim={bd['ssim']} px_diff={bd['pixel_diff_ratio']} "
              f"phash={bd['phash_hamming']}")
    w = r.webug
    if w.get("r1_api_timeout_no_feedback") or w.get("r2_layout_overflow") or w.get("r3_async_data_mismatch"):
        print("  webug:")
        if w["r1_api_timeout_no_feedback"]:
            print(f"    R1: {w['r1_evidence']}")
        if w["r2_layout_overflow"]:
            print(f"    R2: {w['r2_evidence']}")
        if w["r3_async_data_mismatch"]:
            print(f"    R3: {w['r3_evidence']}")
    for ev in r.evidence:
        print(f"  {ev}")


if __name__ == "__main__":
    # 自测：用历史截图跑一遍 driver_engine（不需要真小程序）
    import glob

    ss_dir = os.path.join(_REPO_ROOT, "auto_test", "reports", "screenshots")
    if not os.path.exists(ss_dir):
        print(f"no historical screenshots at {ss_dir}")
        sys.exit(0)

    eng = DriverEngine(baseline_dir=os.path.join(_REPO_ROOT, "auto_test", "v2_baselines"))

    # 选一组：feed_normal / feed_blur_image / feed_slow_api / counter_stale_ui
    candidates = {
        "feed_normal": glob.glob(os.path.join(ss_dir, "feed_normal*.png")),
        "feed_blur_image": glob.glob(os.path.join(ss_dir, "feed_blur_image*.png")),
        "feed_slow_api": glob.glob(os.path.join(ss_dir, "feed_slow_api*.png")),
        "counter_stale_ui": glob.glob(os.path.join(ss_dir, "counter_stale_ui*.png")),
        "layout_layout_overlap": glob.glob(os.path.join(ss_dir, "layout_layout_overlap*.png")),
    }

    # 先用 feed_normal 第一张建基线
    if candidates["feed_normal"]:
        baseline = candidates["feed_normal"][0]
        eng.maybe_save_baseline("feed", baseline)
        print(f"[setup] baseline for 'feed' = {baseline}")

    profile_map = {
        "feed_normal":          ("feed", "normal",          {"interaction_ms": 200, "memory_warnings": 0},
                                  {"visible_value": 10, "expected_value": 10}),
        "feed_blur_image":      ("feed", "blur_image",      {"interaction_ms": 250, "memory_warnings": 0},
                                  {"visible_value": 10, "expected_value": 10}),
        "feed_slow_api":        ("feed", "slow_api",        {"interaction_ms": 1300, "memory_warnings": 0},
                                  {"visible_value": 10, "expected_value": 10}),
        "counter_stale_ui":     ("counter", "stale_ui",     {"interaction_ms": 200, "memory_warnings": 0},
                                  {"visible_value": 0, "expected_value": 5}),
        "layout_layout_overlap":("layout", "layout_overlap",{"interaction_ms": 250, "memory_warnings": 0},
                                  {"visible_value": 3, "expected_value": 3}),
    }

    for key, paths in candidates.items():
        if not paths:
            continue
        page, profile, perf, biz = profile_map[key]
        r = eng.diagnose(page=page, profile=profile, screenshot_path=paths[0],
                         perf=perf, business=biz)
        _print_result(r)
