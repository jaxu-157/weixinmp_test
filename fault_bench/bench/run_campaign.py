"""随机/穷举源码变异大样本检出基准（H5 全自动，无需 devtools）。

目标（回应 PROJECT_REVIEW §3.4 + 用户"多次随机注入测更准检出数据并和 baseline 比较"）：
  - 用 gen_random_mutations 穷举首页可变异点（无抽样偏差），种子打乱顺序。
  - 每个变异：git clean → apply → build:h5 → headless 渲染 → 多通道诊断 → 记通道命中 → 还原。
  - 健康对照多次重渲染测假阳。
  - 报每个方法（crash-only / 整图SSIM / 分块SSIM / webug / ours）的检出率 + **bootstrap 95% CI**。
  - ours vs 各 baseline 的 Δ，给出更可信（带不确定性）的检出数据。

自包含：自己 build 健康基线 + 起静态服务器 + 跑。
用法：python fault_bench/bench/run_campaign.py [--port 8099] [--controls 3]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.dirname(FB)
for p in (REPO, FB, HERE, os.path.join(REPO, "auto_test", "v2_modules")):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 复用 H5 harness
from bench.run_bench import (XTX, SRC, sh, git_clean_src, build,
                             channels_of, predict_dim, detected)  # noqa: E402
from bench.renderer import XtxRenderer  # noqa: E402
from bench.gen_random_mutations import generate, PAGE_SPEC  # noqa: E402
from vt_diagnose import VTDiagnoser  # noqa: E402

H5_DIST = os.path.join(XTX, "dist", "build", "h5")
OUT = os.path.join(FB, "campaign_out")
SHOTS = os.path.join(OUT, "screens")
DIMS = ["visual", "functional", "performance"]


def log(*a):
    print(*a, flush=True)


def apply_unique(rel, old, new):
    fp = os.path.join(SRC, rel)
    s = open(fp, "r", encoding="utf-8").read()
    if s.count(old) != 1:
        return None, f"count={s.count(old)}"
    open(fp, "w", encoding="utf-8").write(s.replace(old, new, 1))
    return fp, None


def serve(port):
    """起静态服务器 serving H5 dist。返回 Popen。"""
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                         cwd=H5_DIST, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return p
        except Exception:
            time.sleep(0.5)
    return p


def bootstrap_ci(hits: list[int], n_boot=2000, seed=7):
    """对 0/1 命中向量做 bootstrap 95% CI（检出率）。"""
    import random as _r
    if not hits:
        return (0.0, 0.0, 0.0)
    rng = _r.Random(seed)
    n = len(hits)
    means = []
    for _ in range(n_boot):
        s = sum(hits[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    point = sum(hits) / n
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return (round(point, 3), round(lo, 3), round(hi, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--controls", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    os.makedirs(SHOTS, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    log("[setup] git clean + build 健康基线")
    git_clean_src()
    ok, secs, err = build()
    if not ok:
        log("[FATAL] baseline build failed:", err); sys.exit(1)
    log(f"  baseline build ok ({secs}s)")

    srv = serve(args.port)
    url = f"http://127.0.0.1:{args.port}"
    r = XtxRenderer(url)
    diag = VTDiagnoser(use_learned=True, use_cascade=False)

    # Page-aware：每页各渲一张 baseline（同构建，R2 教训：跨页/跨构建比会假阳）。
    muts = generate(SRC, seed=args.seed, limit=args.limit)
    pages = sorted({m.get("page", "index") for m in muts}) or ["index"]
    base_load = {}
    for pk in pages:
        spec = PAGE_SPEC[pk]
        b = r.render(spec["route"], os.path.join(SHOTS, f"baseline_{pk}.png"),
                     wait_selector=spec["wait_selector"])
        diag.set_baseline(pk, b["png"])
        base_load[pk] = b["load_ms"]
        log(f"  baseline[{pk}] content-ready={b['load_ms']:.0f}ms dom={b['dom_info']}")

    cases = []
    # 健康对照（每页各 controls 张，对比同页 baseline）
    for pk in pages:
        spec = PAGE_SPEC[pk]
        for i in range(args.controls):
            res = r.render(spec["route"], os.path.join(SHOTS, f"healthy_{pk}_{i}.png"),
                           wait_selector=spec["wait_selector"])
            d = diag.diagnose(pk, res["png"], dom_info=res["dom_info"], dom_text=res["dom_text"])
            ch = channels_of(d, res["load_ms"], base_load[pk], res["page_errors"])
            cases.append({"id": f"healthy_{pk}_{i}", "kind": "healthy", "gt_dim": "none", "page": pk,
                          "channels": ch, "raw_channels": d["channels"], "verdict": d["verdict"],
                          "detected": detected(ch), "pred_dim": predict_dim(ch)})
            log(f"  [healthy {pk} {i}] detected={detected(ch)} ch={[k for k,v in ch.items() if v]}")

    # 变异（每个按其 page 渲染对应路由，对比同页 baseline）
    log(f"\n[campaign] {len(muts)} mutations across pages={pages} (seed={args.seed})")
    for idx, m in enumerate(muts):
        # RCA 维度：layout 折叠进 visual（与 triage 三轴一致）
        gt = "visual" if m["dim"] in ("visual", "layout") else m["dim"]
        pk = m.get("page", "index")
        spec = PAGE_SPEC[pk]
        log(f"\n[{idx+1}/{len(muts)}] {m['id']} (gt={gt}, page={pk})")
        git_clean_src()
        fp, e = apply_unique(m["file"], m["old"], m["new"])
        if e:
            log("  SKIP apply:", e)
            cases.append({"id": m["id"], "kind": "fault", "gt_dim": gt, "page": pk, "error": "apply:" + e})
            continue
        try:
            bok, bsecs, berr = build()
            if not bok:
                log("  build failed:", berr[:150])
                cases.append({"id": m["id"], "kind": "fault", "gt_dim": gt, "page": pk, "error": "build_failed"})
                continue
            res = r.render(spec["route"], os.path.join(SHOTS, f"{m['id'].replace('/','_').replace(':','_')}.png"),
                           wait_selector=spec["wait_selector"])
            d = diag.diagnose(pk, res["png"], dom_info=res["dom_info"], dom_text=res["dom_text"])
            ch = channels_of(d, res["load_ms"], base_load[pk], res["page_errors"])
            rec = {"id": m["id"], "kind": "fault", "gt_dim": gt, "gt_fine": m["dim"],
                   "subtype": m["subtype"], "file": m["file"], "page": pk,
                   "verdict": d["verdict"], "channels": ch, "raw_channels": d["channels"],
                   "tile_ssim": d["channels"].get("tiled_min_ssim"),
                   "detected": detected(ch), "pred_dim": predict_dim(ch),
                   "rca_correct": predict_dim(ch) == gt}
            cases.append(rec)
            log(f"  build {bsecs}s detected={rec['detected']} pred={rec['pred_dim']} "
                f"gt={gt} {'OK' if rec['rca_correct'] else 'XX'} tile={rec['tile_ssim']}")
        finally:
            git_clean_src()

    r.close()
    try:
        srv.terminate()
    except Exception:
        pass
    git_clean_src()

    report = score(cases)
    os.makedirs(OUT, exist_ok=True)
    jp = os.path.join(OUT, f"campaign_{ts}.json")
    json.dump({"ts": ts, "seed": args.seed, "cases": cases, "report": report},
              open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    mp = os.path.join(OUT, f"campaign_{ts}.md")
    open(mp, "w", encoding="utf-8").write(render_md(cases, report, ts))
    log(f"\n[done] {jp}")
    log(f"[done] {mp}")
    log("\n=== SUMMARY ===")
    log(json.dumps(report["headline"], ensure_ascii=False, indent=2))


def score(cases):
    faults = [c for c in cases if c["kind"] == "fault" and "error" not in c]
    healthy = [c for c in cases if c["kind"] == "healthy"]
    nf, nh = len(faults), len(healthy)
    methods = {
        "crash_only": lambda c: c["channels"]["crash"],
        "verdict_only": lambda c: c["verdict"] not in ("Pass", "Unknown"),
        "ssim_whole_only": lambda c: c["raw_channels"].get("baseline_regression"),
        "ssim_tiled_only": lambda c: c["raw_channels"].get("tiled_regression"),
        "webug_only": lambda c: c["raw_channels"].get("webug_r2") or c["raw_channels"].get("webug_r3"),
        "ours_multichannel": lambda c: c["detected"],
    }
    detection = {}
    for name, fn in methods.items():
        fhits = [1 if fn(c) else 0 for c in faults]
        hhits = [1 if fn(c) else 0 for c in healthy]
        pt, lo, hi = bootstrap_ci(fhits)
        fp = round(sum(hhits) / nh, 3) if nh else 0
        detection[name] = {"recall": pt, "ci95": [lo, hi], "n_detected": sum(fhits),
                           "fp_healthy": fp}

    import collections
    conf = {g: collections.Counter() for g in DIMS}
    for c in faults:
        conf[c["gt_dim"]][c["pred_dim"]] += 1
    rca_top1 = round(sum(1 for c in faults if c["pred_dim"] == c["gt_dim"]) / nf, 3) if nf else 0
    n_det = sum(1 for c in faults if c["detected"])
    n_det_corr = sum(1 for c in faults if c["detected"] and c["pred_dim"] == c["gt_dim"])
    cond_rca = round(n_det_corr / n_det, 3) if n_det else 0

    headline = {
        "n_faults": nf, "n_healthy": nh,
        "ours_recall": detection["ours_multichannel"]["recall"],
        "ours_ci95": detection["ours_multichannel"]["ci95"],
        "ours_fp": detection["ours_multichannel"]["fp_healthy"],
        "crash_only_recall": detection["crash_only"]["recall"],
        "tiled_only_recall": detection["ssim_tiled_only"]["recall"],
        "rca_top1": rca_top1,
        "conditional_rca": f"{n_det_corr}/{n_det}={cond_rca}",
    }
    return {"headline": headline, "detection": detection, "rca_confusion": {k: dict(v) for k, v in conf.items()}}


def render_md(cases, report, ts):
    h = report["headline"]
    L = [f"# 随机/穷举源码变异 大样本检出基准 — 小兔鲜儿 H5（全自动）\n",
         f"_run {ts} · {h['n_faults']} 变异 / {h['n_healthy']} 健康对照 · bootstrap 95% CI_\n",
         "## Headline\n",
         f"- **ours 检出率 {h['ours_recall']:.0%}**  95%CI [{h['ours_ci95'][0]:.0%}, {h['ours_ci95'][1]:.0%}]  健康假阳 {h['ours_fp']:.0%}",
         f"- crash-only {h['crash_only_recall']:.0%} · 分块SSIM {h['tiled_only_recall']:.0%}",
         f"- RCA top-1 {h['rca_top1']:.0%}；检出即对 {h['conditional_rca']}\n",
         "## 各方法检出率（含 bootstrap 95% CI）\n",
         "| 方法 | 检出率 | 95% CI | 检出数 | 健康假阳 |", "|---|---|---|---|---|"]
    for name, d in report["detection"].items():
        L.append(f"| {name} | {d['recall']:.0%} | [{d['ci95'][0]:.0%}, {d['ci95'][1]:.0%}] | {d['n_detected']} | {d['fp_healthy']:.0%} |")
    L += ["", "## 逐变异\n", "| id | gt | pred | 检出 | verdict | tileSSIM |", "|---|---|---|---|---|---|"]
    for c in cases:
        if c["kind"] != "fault":
            continue
        if "error" in c:
            L.append(f"| {c['id']} | {c['gt_dim']} | — | ERR | {c['error']} | |")
            continue
        L.append(f"| {c['id']} | {c['gt_dim']} | {c['pred_dim']} | {'✅' if c['detected'] else '❌'} | {c['verdict']} | {c.get('tile_ssim')} |")
    L += ["", "> 变异穷举首页可发现站点（无抽样偏差），种子打乱顺序；CI 由 bootstrap 重采样给出。",
          "> 还原用 `git checkout -- src`（xtx 有独立 .git）。"]
    return "\n".join(L)


if __name__ == "__main__":
    main()
