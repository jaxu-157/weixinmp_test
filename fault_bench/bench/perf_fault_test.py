"""聚焦测试：H5 性能通道能否检出"主线程阻塞"性能故障（PROJECT_REVIEW §3.2）。

注入 onMounted 同步死循环 1.4s → 重编译 → 渲染 → 看新增的 longtask/FCP 信号能否抓到。
对比健康基线，验证性能通道有效 + 健康不假阳。可逆（git checkout -- src）。
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.dirname(FB)
for p in (REPO, FB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bench.renderer import XtxRenderer  # noqa: E402

XTX = os.path.join(FB, "xtx")
SRC = os.path.join(XTX, "src")
# 注入页面入口 onLoad（关键路径）——实测可被墙钟检出；子组件 onMounted 会被框架调度吸收，漏检。
GUESS = os.path.join(SRC, "pages", "index", "index.vue")
OUT = os.path.join(FB, "campaign_out", "perf_test")
OLD = "onLoad(async () => {"
NEW = "onLoad(async () => {\n  { const __t = Date.now(); while (Date.now() - __t < 1400) {} }"

# 性能阈值：longtask_max 超 800ms（主线程被单个任务占住）→ 性能故障
LONGTASK_THRESHOLD_MS = 800.0


def sh(cmd, cwd, timeout=260):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def build():
    t0 = time.perf_counter()
    rc, log = sh("npm run build:h5", cwd=XTX)
    return (rc == 0 and "Build complete" in log), round(time.perf_counter() - t0, 1), log[-300:]


def serve(port):
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                         cwd=os.path.join(XTX, "dist", "build", "h5"),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return p
        except Exception:
            time.sleep(0.5)
    return p


def perf_channel(load_ms, perf, base_load_ms, base_perf):
    """性能通道判定（多信号取或）：
      - 墙钟 time-to-content（goto→内容可见）相对基线显著升高（主信号，headless 可靠）
      - longtask_max 绝对超阈值（辅助；实测 headless Long Tasks API 常返回 0，仅作加分）
      - FCP 相对基线显著升高（辅助）
    """
    lt = (perf or {}).get("longtask_max_ms", 0) or 0
    fcp = (perf or {}).get("fcp") or 0
    base_fcp = (base_perf or {}).get("fcp") or 0
    by_wall = bool(base_load_ms and load_ms and (load_ms - base_load_ms) > LONGTASK_THRESHOLD_MS)
    by_longtask = lt > LONGTASK_THRESHOLD_MS
    by_fcp = bool(base_fcp and fcp and (fcp - base_fcp) > LONGTASK_THRESHOLD_MS)
    return {"hit": by_wall or by_longtask or by_fcp,
            "load_ms": round(load_ms or 0), "base_load_ms": round(base_load_ms or 0),
            "longtask_max_ms": lt, "fcp": fcp,
            "by_wall": by_wall, "by_longtask": by_longtask, "by_fcp": by_fcp}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    # 1) 干净基线
    sh("git checkout -- src", cwd=XTX)
    ok, secs, err = build()
    if not ok:
        print("[FATAL] baseline build:", err); sys.exit(1)
    print(f"[setup] baseline build {secs}s")
    srv = serve(args.port)
    try:
        r = XtxRenderer(f"http://127.0.0.1:{args.port}")
        base = r.render("", os.path.join(OUT, "baseline.png"), wait_selector=".guess-item")
        # 健康对照再渲染一次测假阳
        h = r.render("", os.path.join(OUT, "healthy.png"), wait_selector=".guess-item")
        r.close()
    finally:
        try:
            srv.terminate()
        except Exception:
            pass
    base_perf = base["perf"]
    print(f"[baseline] perf={base_perf}")
    hc = perf_channel(h["load_ms"], h["perf"], base["load_ms"], base_perf)
    print(f"[healthy ] perf_channel_hit={hc['hit']} longtask_max={hc['longtask_max_ms']} fcp={hc['fcp']}")

    # 2) 注入性能故障
    src = open(GUESS, encoding="utf-8").read()
    assert src.count(OLD) == 1, f"marker count={src.count(OLD)}"
    open(GUESS, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    try:
        ok, secs, err = build()
        if not ok:
            print("[FATAL] fault build:", err); return
        print(f"[fault] build {secs}s (injected onLoad blocking 1.4s)")
        srv = serve(args.port)
        try:
            r = XtxRenderer(f"http://127.0.0.1:{args.port}")
            f = r.render("", os.path.join(OUT, "blocking_loop.png"), wait_selector=".guess-item")
            r.close()
        finally:
            try:
                srv.terminate()
            except Exception:
                pass
        fc = perf_channel(f["load_ms"], f["perf"], base["load_ms"], base_perf)
        print(f"[fault   ] perf={f['perf']}")
        print(f"[fault   ] perf_channel_hit={fc['hit']} longtask_max={fc['longtask_max_ms']} "
              f"fcp={fc['fcp']} by_longtask={fc['by_longtask']} by_fcp={fc['by_fcp']}")
    finally:
        open(GUESS, "w", encoding="utf-8").write(src)  # 还原
        print("[restore] XtxGuess.vue 已还原")

    result = {"baseline_perf": base_perf, "healthy_channel": hc, "fault_channel": fc,
              "VERDICT": {"fault_detected": fc["hit"], "healthy_false_positive": hc["hit"]}}
    json.dump(result, open(os.path.join(OUT, "perf_fault_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n=== 性能通道验证结论 ===")
    print(f"  性能故障(阻塞1.4s)被检出: {fc['hit']}  (应 True)")
    print(f"  健康页假阳: {hc['hit']}  (应 False)")


if __name__ == "__main__":
    main()
