"""Source-mutation fault-injection + RCA benchmark on a REAL open-source uni-app.

Pipeline per case (zero app instrumentation — only browser-observable signals):
  apply source mutation -> `npm run build:h5` -> serve(static) -> headless render
  -> capture {screenshot, DOM scroll metrics, DOM text, time-to-content, JS errors}
  -> Vision-Triage multi-channel diagnose -> score detection + RCA dimension -> revert.

Outputs JSON + Markdown report under fault_bench/bench_out/.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(FB, ".."))
for p in (REPO, FB):
    if p not in sys.path:
        sys.path.insert(0, p)

from fault_bench.bench.renderer import XtxRenderer
from fault_bench.bench.mutations import MUTATIONS, coarse_dim
from fault_bench.vt_diagnose import VTDiagnoser

XTX = os.path.join(FB, "xtx")
SRC = os.path.join(XTX, "src")
OUT = os.path.join(FB, "bench_out")
SCREENS = os.path.join(OUT, "screens")

PERF_RATIO = 1.5
PERF_ABS_MS = 600.0
DIMS = ["visual", "functional", "performance"]


def sh(cmd, cwd, timeout=260):
    env = dict(os.environ)
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True,
                       timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def git_clean_src():
    sh("git checkout -- src", cwd=XTX)


def build():
    t0 = time.perf_counter()
    rc, log = sh("npm run build:h5", cwd=XTX)
    ok = rc == 0 and "Build complete" in log
    return ok, round(time.perf_counter() - t0, 1), log[-400:] if not ok else ""


def apply_mutation(m):
    fp = os.path.join(SRC, m["file"])
    with open(fp, "r", encoding="utf-8") as f:
        orig = f.read()
    n = orig.count(m["old"])
    if n != 1:
        return None, f"expected 1 occurrence of marker, found {n}"
    with open(fp, "w", encoding="utf-8") as f:
        f.write(orig.replace(m["old"], m["new"]))
    return (fp, orig), None


def revert(state):
    fp, orig = state
    with open(fp, "w", encoding="utf-8") as f:
        f.write(orig)


def channels_of(diag, load_ms, base_load_ms, page_errors):
    verdict = diag["verdict"]
    ch = diag["channels"]
    visual = (verdict == "RenderBug") or ch["baseline_regression"] or ch.get("tiled_regression", False)
    layout = ch["webug_r2"]
    functional = ch["webug_r3"] or (verdict == "FunctionalFail")
    perf = (base_load_ms and load_ms is not None
            and load_ms > base_load_ms * PERF_RATIO
            and (load_ms - base_load_ms) > PERF_ABS_MS)
    crash = bool(page_errors) or bool(diag["visual"].get("black_white"))
    return {"visual": bool(visual), "layout": bool(layout),
            "functional": bool(functional), "performance": bool(perf), "crash": crash}


def predict_dim(ch):
    if ch["performance"]:
        return "performance"
    if ch["functional"]:
        return "functional"
    if ch["visual"] or ch["layout"]:
        return "visual"
    return "none"


def detected(ch):
    return ch["visual"] or ch["layout"] or ch["functional"] or ch["performance"]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8099")
    ap.add_argument("--controls", type=int, default=3, help="healthy re-renders for FP")
    args = ap.parse_args()

    os.makedirs(SCREENS, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("[setup] git clean src + build healthy baseline")
    git_clean_src()
    ok, secs, err = build()
    if not ok:
        print("[FATAL] baseline build failed:", err)
        sys.exit(1)
    print(f"  baseline build ok ({secs}s)")

    r = XtxRenderer(args.url)
    diag = VTDiagnoser(use_learned=True, use_cascade=False)

    base = r.render("", os.path.join(SCREENS, "baseline.png"), wait_selector=".guess-item")
    diag.set_baseline("feed", base["png"])
    base_load = base["load_ms"]
    print(f"  baseline content-ready={base_load:.0f}ms dom={base['dom_info']} "
          f"page_errors={len(base['page_errors'])}")

    cases = []

    # healthy controls (false-positive measurement on the SAME real page, no mutation)
    for i in range(args.controls):
        res = r.render("", os.path.join(SCREENS, f"healthy_{i}.png"), wait_selector=".guess-item")
        d = diag.diagnose("feed", res["png"], dom_info=res["dom_info"], dom_text=res["dom_text"])
        ch = channels_of(d, res["load_ms"], base_load, res["page_errors"])
        cases.append({"id": f"healthy_{i}", "kind": "healthy", "gt_dim": "none",
                      "verdict": d["verdict"], "channels": ch, "raw_channels": d["channels"],
                      "load_ms": round(res["load_ms"], 0), "detected": detected(ch),
                      "pred_dim": predict_dim(ch), "page_errors": len(res["page_errors"])})
        print(f"  [healthy {i}] detected={detected(ch)} pred={predict_dim(ch)} ch={ch}")

    # mutations
    for m in MUTATIONS:
        print(f"\n[mutation] {m['id']} (gt={m['dim']})")
        state, e = apply_mutation(m)
        if e:
            print("  SKIP apply:", e)
            cases.append({"id": m["id"], "kind": "fault", "gt_dim": coarse_dim(m["dim"]),
                          "gt_fine": m["dim"], "error": "apply:" + e})
            continue
        try:
            ok, secs, berr = build()
            if not ok:
                print("  build failed:", berr[:200])
                cases.append({"id": m["id"], "kind": "fault", "gt_dim": coarse_dim(m["dim"]),
                              "gt_fine": m["dim"], "error": "build_failed"})
                continue
            res = r.render("", os.path.join(SCREENS, f"{m['id']}.png"), wait_selector=".guess-item")
            d = diag.diagnose("feed", res["png"], dom_info=res["dom_info"], dom_text=res["dom_text"])
            ch = channels_of(d, res["load_ms"], base_load, res["page_errors"])
            rec = {"id": m["id"], "kind": "fault", "gt_dim": coarse_dim(m["dim"]),
                   "gt_fine": m["dim"], "subtype": m["subtype"], "note": m["note"],
                   "verdict": d["verdict"], "channels": ch, "raw_channels": d["channels"],
                   "baseline_ssim": d["channels"]["baseline_ssim"],
                   "load_ms": round(res["load_ms"], 0),
                   "dom_overflow": (res["dom_info"].get("scrollWidth", 0) or 0)
                                   > (res["dom_info"].get("clientWidth", 1) or 1) * 1.05,
                   "page_errors": len(res["page_errors"]),
                   "detected": detected(ch), "pred_dim": predict_dim(ch),
                   "rca_correct": predict_dim(ch) == coarse_dim(m["dim"])}
            cases.append(rec)
            print(f"  build {secs}s | detected={rec['detected']} pred={rec['pred_dim']} "
                  f"gt={rec['gt_dim']} verdict={d['verdict']} ssim={rec['baseline_ssim']} "
                  f"load={rec['load_ms']:.0f}ms ch={ch}")
        finally:
            revert(state)

    r.close()
    git_clean_src()

    report = score(cases, base_load, ts)
    jpath = os.path.join(OUT, f"bench_report_{ts}.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump({"ts": ts, "baseline_load_ms": base_load, "cases": cases,
                   "report": report}, f, indent=2, ensure_ascii=False)
    mpath = os.path.join(OUT, f"bench_report_{ts}.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(render_md(cases, report, base_load, ts))
    print("\n[done] JSON:", jpath)
    print("[done] MD  :", mpath)
    print("\n=== SUMMARY ===")
    print(json.dumps(report["headline"], ensure_ascii=False, indent=2))


def score(cases, base_load, ts):
    faults = [c for c in cases if c["kind"] == "fault" and "error" not in c]
    healthy = [c for c in cases if c["kind"] == "healthy"]
    n_fault, n_healthy = len(faults), len(healthy)

    # detection methods (the "conventional" baselines vs ours)
    methods = {
        "crash_only": lambda c: c["channels"]["crash"],
        "verdict_only": lambda c: c["verdict"] not in ("Pass", "Unknown"),
        "ssim_whole_only": lambda c: c["raw_channels"]["baseline_regression"],
        "ssim_tiled_only": lambda c: c["raw_channels"].get("tiled_regression", False),
        "webug_only": lambda c: c["raw_channels"]["webug_r2"] or c["raw_channels"]["webug_r3"],
        "ours_multichannel": lambda c: c["detected"],
    }
    detection = {}
    for name, fn in methods.items():
        rec = sum(1 for c in faults if fn(c)) / n_fault if n_fault else 0
        fp = sum(1 for c in healthy if fn(c)) / n_healthy if n_healthy else 0
        detection[name] = {"recall_on_faults": round(rec, 3),
                           "false_positive_rate_healthy": round(fp, 3),
                           "n_detected": sum(1 for c in faults if fn(c))}

    # RCA dimension confusion + per-class P/R/F1 (only over detected faults; ours)
    confusion = {g: {p: 0 for p in DIMS + ["none"]} for g in DIMS}
    for c in faults:
        confusion[c["gt_dim"]][c["pred_dim"]] += 1
    per_class = {}
    macro = []
    for dim in DIMS:
        tp = confusion[dim][dim]
        fp = sum(confusion[g][dim] for g in DIMS if g != dim)
        fn = sum(confusion[dim][p] for p in DIMS + ["none"] if p != dim)
        p, r, f = prf(tp, fp, fn)
        per_class[dim] = {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}
        macro.append(f)
    rca_top1 = round(sum(1 for c in faults if c["pred_dim"] == c["gt_dim"]) / n_fault, 3) if n_fault else 0
    macro_f1 = round(sum(macro) / len(macro), 3) if macro else 0

    # RCA naive baselines
    import collections
    gt_counts = collections.Counter(c["gt_dim"] for c in faults)
    majority = gt_counts.most_common(1)[0][0] if gt_counts else "visual"
    rca_majority = round(gt_counts[majority] / n_fault, 3) if n_fault else 0
    rca_random = round(1 / len(DIMS), 3)

    headline = {
        "n_faults": n_fault, "n_healthy_controls": n_healthy,
        "ours_detection_recall": detection["ours_multichannel"]["recall_on_faults"],
        "ours_false_positive_rate": detection["ours_multichannel"]["false_positive_rate_healthy"],
        "crash_only_recall": detection["crash_only"]["recall_on_faults"],
        "rca_top1_ours": rca_top1, "rca_top1_majority": rca_majority,
        "rca_top1_random": rca_random, "rca_macro_f1": macro_f1,
    }
    return {"headline": headline, "detection": detection, "rca_per_class": per_class,
            "rca_confusion": confusion, "rca_top1": rca_top1, "rca_macro_f1": macro_f1,
            "rca_baselines": {"majority": rca_majority, "random": rca_random}}


def render_md(cases, report, base_load, ts):
    h = report["headline"]
    L = []
    L.append(f"# Source-Mutation Fault-Injection & RCA Benchmark — 小兔鲜儿 (real open-source uni-app)\n")
    L.append(f"_run {ts} · baseline content-ready {base_load:.0f}ms · zero app instrumentation "
             f"(screenshot + DOM + timing only)_\n")
    L.append("## Headline\n")
    L.append(f"- Faults injected: **{h['n_faults']}**, healthy controls: **{h['n_healthy_controls']}**")
    L.append(f"- **Vision-Triage detection recall: {h['ours_detection_recall']:.0%}**, "
             f"false-positive on healthy: {h['ours_false_positive_rate']:.0%}")
    L.append(f"- Crash-only (conventional) recall: **{h['crash_only_recall']:.0%}** "
             f"→ visual/layout/data faults are invisible to crash testing")
    L.append(f"- **RCA top-1 dimension accuracy: {h['rca_top1_ours']:.0%}** "
             f"(majority-class {h['rca_top1_majority']:.0%}, random {h['rca_top1_random']:.0%}), "
             f"macro-F1 {h['rca_macro_f1']:.2f}\n")

    L.append("## Detection: ours vs conventional baselines\n")
    L.append("| method | recall on faults | false-pos on healthy |")
    L.append("|---|---|---|")
    for name, d in report["detection"].items():
        L.append(f"| {name} | {d['recall_on_faults']:.0%} | {d['false_positive_rate_healthy']:.0%} |")
    L.append("")

    L.append("## RCA per-dimension (Vision-Triage)\n")
    L.append("| dimension | P | R | F1 | tp | fp | fn |")
    L.append("|---|---|---|---|---|---|---|")
    for dim, m in report["rca_per_class"].items():
        L.append(f"| {dim} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} "
                 f"| {m['tp']} | {m['fp']} | {m['fn']} |")
    L.append("")

    L.append("## Per-case detail\n")
    L.append("| case | gt | pred | detected | verdict | SSIM | overflow | load ms | note |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c in cases:
        if "error" in c:
            L.append(f"| {c['id']} | {c.get('gt_dim','-')} | — | ERROR | {c['error']} |  |  |  |  |")
            continue
        ssim = c.get("baseline_ssim")
        L.append(f"| {c['id']} | {c['gt_dim']} | {c['pred_dim']} | "
                 f"{'✅' if c['detected'] else '❌'} | {c['verdict']} | "
                 f"{ssim if ssim is not None else '-'} | {c.get('dom_overflow','-')} | "
                 f"{c.get('load_ms','-')} | {c.get('note','')} |")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
