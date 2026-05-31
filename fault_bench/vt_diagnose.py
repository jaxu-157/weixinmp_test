"""Vision-Triage diagnosis wrapper for the source-mutation fault benchmark.

Wraps the project's DriverEngine (learned/rule triage + baseline SSIM diff +
WeBug rules) so the benchmark can feed it a (baseline.png, buggy.png) pair and
get back a clean, comparable record:

    {
      "verdict":            <5-class: Pass|RenderBug|PerformanceRisk|FunctionalFail|Mixed>,
      "pred_dimension":     <visual|performance|functional|mixed|none>,   # RCA top-1
      "channels": {
          "verdict_alarm":      bool,   # learned/rule verdict != Pass
          "baseline_regression":bool,   # SSIM vs baseline < threshold
          "baseline_ssim":      float|None,
          "webug_r1":/r2/r3":   bool,   # WeBug runtime rules
      },
      "multichannel_alarm": bool,        # OR over all channels  (== "something is wrong")
      "evidence": [...],
    }

This is framework-agnostic: it only consumes screenshots, so it works on
uni-app->H5 renders exactly as on WeChat-devtools captures.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image
try:
    from skimage.metrics import structural_similarity as _ssim
except Exception:  # pragma: no cover
    _ssim = None

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "auto_test", "v2_modules"),
          os.path.join(_REPO_ROOT, "diagnosis")):
    if p not in sys.path:
        sys.path.insert(0, p)

from driver_engine import DriverEngine  # type: ignore

# verdict -> coarse root-cause dimension (RCA top-1)
VERDICT_TO_DIM = {
    "Pass": "none",
    "RenderBug": "visual",
    "PerformanceRisk": "performance",
    "FunctionalFail": "functional",
    "Mixed": "mixed",
    "Unknown": "none",
}

BASELINE_SSIM_REGRESSION = 0.92      # whole-image SSIM (the project's existing channel)
TILE_SSIM_REGRESSION = 0.85          # per-tile SSIM: any tile below this = localized regression
TILE_ROWS, TILE_COLS = 8, 3          # regional grid for localized-change sensitivity


def tiled_min_ssim(base_png: str, cur_png: str, rows: int = TILE_ROWS, cols: int = TILE_COLS) -> float:
    """Min per-tile SSIM between two screenshots.

    Whole-image SSIM dilutes a localized regression (a broken banner is a small
    fraction of a long scroll page) so it stays above threshold. Tiling restores
    locality: a tile fully covering the changed region drops sharply. Returns the
    WORST tile SSIM (1.0 = identical everywhere).
    """
    if _ssim is None:
        return 1.0
    a = np.array(Image.open(base_png).convert("L"))
    b_img = Image.open(cur_png).convert("L")
    if b_img.size != (a.shape[1], a.shape[0]):
        b_img = b_img.resize((a.shape[1], a.shape[0]))
    b = np.array(b_img)
    H, W = a.shape
    worst = 1.0
    for i in range(rows):
        ya, yb = i * H // rows, (i + 1) * H // rows
        for j in range(cols):
            xa, xb = j * W // cols, (j + 1) * W // cols
            ta, tb = a[ya:yb, xa:xb], b[ya:yb, xa:xb]
            if ta.size == 0 or min(ta.shape) < 7:
                continue
            worst = min(worst, float(_ssim(ta, tb, data_range=255)))
    return worst


def per_tile_ssim(base_png: str, cur_png: str, rows: int = TILE_ROWS, cols: int = TILE_COLS) -> dict:
    """返回 {(i,j): ssim}，每个 tile 的 SSIM。供动态区标定与带掩码诊断复用。"""
    if _ssim is None:
        return {}
    a = np.array(Image.open(base_png).convert("L"))
    b_img = Image.open(cur_png).convert("L")
    if b_img.size != (a.shape[1], a.shape[0]):
        b_img = b_img.resize((a.shape[1], a.shape[0]))
    b = np.array(b_img)
    H, W = a.shape
    out = {}
    for i in range(rows):
        ya, yb = i * H // rows, (i + 1) * H // rows
        for j in range(cols):
            xa, xb = j * W // cols, (j + 1) * W // cols
            ta, tb = a[ya:yb, xa:xb], b[ya:yb, xa:xb]
            if ta.size == 0 or min(ta.shape) < 7:
                continue
            out[(i, j)] = float(_ssim(ta, tb, data_range=255))
    return out


def calibrate_dynamic_tiles(healthy_pngs: list, rows: int = TILE_ROWS, cols: int = TILE_COLS,
                            dyn_thresh: float = TILE_SSIM_REGRESSION) -> set:
    """用多张【同会话渲染的健康图】标定"天然抖动"的 tile（轮播/随机推荐/时间戳）。

    做法：以第一张为基准，其余健康图逐张对比；某 tile 在健康图之间就 SSIM < dyn_thresh，
    说明它即使无故障也会波动 → 标记为动态 tile，诊断时跳过（避免正常抖动假阳）。
    需 ≥2 张健康图；<2 张返回空集（退化为不掩码）。
    """
    if len(healthy_pngs) < 2:
        return set()
    base = healthy_pngs[0]
    worst_among_healthy = {}  # (i,j) -> 健康图之间该 tile 的最差 SSIM
    for h in healthy_pngs[1:]:
        for k, v in per_tile_ssim(base, h, rows, cols).items():
            worst_among_healthy[k] = min(worst_among_healthy.get(k, 1.0), v)
    return {k for k, v in worst_among_healthy.items() if v < dyn_thresh}


def tiled_min_ssim_masked(base_png: str, cur_png: str, skip: set,
                          rows: int = TILE_ROWS, cols: int = TILE_COLS) -> float:
    """跳过 skip 集合里的（动态）tile，返回剩余 tile 的最差 SSIM。"""
    tiles = per_tile_ssim(base_png, cur_png, rows, cols)
    vals = [v for k, v in tiles.items() if k not in skip]
    return min(vals) if vals else 1.0


class VTDiagnoser:
    def __init__(self, use_learned: bool = True, use_cascade: bool = False):
        self._baseline_dir = tempfile.mkdtemp(prefix="vt_bench_baseline_")
        self._baseline_png: dict[str, str] = {}
        self._dynamic_tiles: dict[str, set] = {}  # page -> 需跳过的天然抖动 tile（轮播/随机）
        self.engine = DriverEngine(
            baseline_dir=self._baseline_dir,
            use_learned=use_learned,
            use_cascade=use_cascade,
        )

    def set_baseline(self, page: str, baseline_png: str):
        baseline_png = os.path.abspath(baseline_png)
        if not os.path.exists(baseline_png):
            raise FileNotFoundError(baseline_png)
        self.engine.force_save_baseline(page, baseline_png)
        self._baseline_png[page] = baseline_png

    def calibrate_dynamic(self, page: str, healthy_pngs: list):
        """用多张同会话健康图标定该 page 的动态 tile（轮播/随机内容），诊断时自动跳过。

        healthy_pngs[0] 应为 set_baseline 用的同一基线（或同会话另一健康帧）。
        标定后，diagnose 的分块 SSIM 会忽略这些天然抖动区，降低跨渲染假阳。
        """
        pngs = [os.path.abspath(p) for p in healthy_pngs if os.path.exists(p)]
        self._dynamic_tiles[page] = calibrate_dynamic_tiles(pngs)
        return self._dynamic_tiles[page]

    def diagnose(self, page: str, buggy_png: str,
                 perf: dict | None = None, business: dict | None = None,
                 dom_info: dict | None = None, dom_text: str | None = None) -> dict:
        buggy_png = os.path.abspath(buggy_png)
        r = self.engine.diagnose(
            page=page, profile="bench",
            screenshot_path=buggy_png,
            perf=perf or {"interaction_ms": 300, "memory_warnings": 0},
            business=business or {},
            dom_info=dom_info,
            dom_text=dom_text,
            diff_out_dir=None,
        )
        bd = r.baseline_diff or {}
        ssim = bd.get("ssim")
        baseline_regression = bool(ssim is not None and ssim < BASELINE_SSIM_REGRESSION)
        wb = r.webug or {}
        webug_r1 = bool(wb.get("r1_api_timeout_no_feedback"))
        # R2 仅在 DOM 来源(scrollWidth/Height>client)时作硬报警；像素边缘 fallback 在内容丰富页
        # (满幅渐变/装饰边框)会误报，降级为低置信证据不驱动 alarm（PROJECT_REVIEW P1）。
        r2_raw = bool(wb.get("r2_layout_overflow"))
        r2_ev = str(wb.get("r2_evidence", ""))
        webug_r2 = r2_raw and r2_ev.startswith("dom")
        webug_r2_pixel_evidence = r2_raw and not r2_ev.startswith("dom")  # 仅记录，不报警
        webug_r3 = bool(wb.get("r3_async_data_mismatch"))
        # regional (tiled) SSIM — restores sensitivity to localized visual regressions.
        # 若该 page 已标定动态 tile（轮播/随机内容），跳过它们以免正常抖动假阳。
        base_png = self._baseline_png.get(page)
        dyn = self._dynamic_tiles.get(page)
        if base_png and dyn:
            tiled_min = tiled_min_ssim_masked(base_png, buggy_png, dyn)
        elif base_png:
            tiled_min = tiled_min_ssim(base_png, buggy_png)
        else:
            tiled_min = 1.0
        tiled_regression = tiled_min < TILE_SSIM_REGRESSION

        verdict_alarm = r.verdict not in ("Pass", "Unknown")
        multichannel_alarm = (verdict_alarm or baseline_regression or tiled_regression
                              or webug_r1 or webug_r2 or webug_r3)
        return {
            "verdict": r.verdict,
            "pred_dimension": VERDICT_TO_DIM.get(r.verdict, "none"),
            "channels": {
                "verdict_alarm": verdict_alarm,
                "baseline_regression": baseline_regression,
                "baseline_ssim": ssim,
                "tiled_regression": tiled_regression,
                "tiled_min_ssim": round(tiled_min, 4),
                "webug_r1": webug_r1,
                "webug_r2": webug_r2,
                "webug_r2_pixel_evidence": webug_r2_pixel_evidence,
                "webug_r3": webug_r3,
            },
            "multichannel_alarm": multichannel_alarm,
            "evidence": r.evidence,
            "explanation": r.explanation,
            "visual": r.visual,
            "performance": r.performance,
            "functional": r.functional,
        }


if __name__ == "__main__":
    # self-test on the hand-rendered HTML variants if present
    d = VTDiagnoser(use_learned=True, use_cascade=False)
    base = os.path.join(os.path.dirname(__file__), "_backhalf", "healthy.png")
    if os.path.exists(base):
        d.set_baseline("feed", base)
        for name in ("healthy", "blank", "blur", "overlap"):
            p = os.path.join(os.path.dirname(__file__), "_backhalf", name + ".png")
            if os.path.exists(p):
                r = d.diagnose("feed", p)
                print(f"{name:9s} verdict={r['verdict']:16s} dim={r['pred_dimension']:11s} "
                      f"alarm={r['multichannel_alarm']} ssim={r['channels']['baseline_ssim']}")
    else:
        print("no _backhalf screenshots; render them first")
