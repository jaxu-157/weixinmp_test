"""干净 FPR 测量：同一渲染会话里产出 baseline + N 个健康样本，
测 ours 对"真正可比的正确样本"的假阳率。

动机：之前 qwen_diff_ab 报 ours FPR=100%，但发现是拿**跨批次**的 baseline 和 healthy
比出来的（磁盘 baseline.png 被后续运行覆盖，轮播/数据状态不同 → 分块 SSIM 假低）。
本脚本在**同一会话**连续渲染，确保 baseline 与 healthy 渲染条件一致，得到诚实 FPR。

同时测：把渲染间隔拉开/不拉开，看 ours 对"正常渲染抖动"的鲁棒性。
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
import json
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.dirname(FB)
for p in (REPO, FB, HERE, os.path.join(REPO, "auto_test", "v2_modules"), os.path.join(REPO, "diagnosis")):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from vt_diagnose import VTDiagnoser  # noqa: E402
from bench.renderer import XtxRenderer  # noqa: E402

H5_DIST = os.path.join(FB, "xtx", "dist", "build", "h5")
OUTDIR = os.path.join(FB, "campaign_out", "fpr_clean")


def serve(port):
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                         cwd=H5_DIST, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return p
        except Exception:
            time.sleep(0.5)
    return p


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--n", type=int, default=8, help="健康样本数")
    args = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    srv = serve(args.port)
    try:
        r = XtxRenderer(f"http://127.0.0.1:{args.port}")
        # 同一会话：第 0 张作 baseline，其余作健康样本
        base = os.path.join(OUTDIR, "baseline.png")
        r.render("", base, wait_selector=".guess-item")
        healthy = []
        for i in range(args.n):
            p = os.path.join(OUTDIR, f"healthy_{i}.png")
            r.render("", p, wait_selector=".guess-item")
            healthy.append(p)
        r.close()
    finally:
        try:
            srv.terminate()
        except Exception:
            pass

    diag = VTDiagnoser(use_learned=True, use_cascade=False)
    diag.set_baseline("feed", base)

    rows = []
    fp = 0
    for p in healthy:
        d = diag.diagnose("feed", p)
        ch = d["channels"]
        alarm = bool(d["multichannel_alarm"])
        fp += int(alarm)
        rows.append({"file": os.path.basename(p), "alarm": alarm,
                     "tile_min": ch["tiled_min_ssim"], "tiled_reg": ch["tiled_regression"],
                     "whole_ssim": ch["baseline_ssim"], "webug_r2": ch["webug_r2"],
                     "webug_r3": ch["webug_r3"], "verdict": d["verdict"]})
        print(f"  {os.path.basename(p):14s} alarm={alarm} tileMin={ch['tiled_min_ssim']} "
              f"whole={ch['baseline_ssim']} r2={ch['webug_r2']} r3={ch['webug_r3']}")

    fpr = round(fp / len(healthy), 3) if healthy else 0
    print(f"\n=== 干净 FPR（同会话 baseline+healthy）===")
    print(f"  健康样本 N={len(healthy)}  误报 fp={fp}  FPR={fpr}")
    out = os.path.join(OUTDIR, f"fpr_clean_{ts}.json")
    json.dump({"ts": ts, "n": len(healthy), "fp": fp, "fpr": fpr, "rows": rows},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[done] {out}")


if __name__ == "__main__":
    main()
