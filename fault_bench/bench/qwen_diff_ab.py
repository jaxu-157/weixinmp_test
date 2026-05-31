"""混合池 A/B：故障 + 正确样本混在一起，按 precision/recall/FPR/F1 诚实评测，
对比 ours(多通道) / qwen_single(旧单图) / qwen_diff(新差分+可选代码)。

回应用户两点：
  1. 融合诊断应把"基线图+当前图(+代码)"一起给大模型 → analyze_diff 已实现。
  2. 测试不应全是故障 → 混入若干"正确(未变异/健康)"样本，让指标包含真实 FPR。

正确样本：已存 healthy_* + 本脚本新渲染的若干健康帧（dist 是干净健康版，免重编译）。
故障样本：复用 campaign 已渲染的 20 张故障截图。
所有截图离线可诊断；仅"补渲染正确样本"需要静态服务器(自动起)。
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import subprocess
import sys
import time
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

from vt_diagnose import VTDiagnoser            # noqa: E402
from diagnose.mllm import default_mllm          # noqa: E402

SCREENS = os.path.join(FB, "campaign_out", "screens")
H5_DIST = os.path.join(FB, "xtx", "dist", "build", "h5")
OUT = os.path.join(FB, "campaign_out")
HOME_SRC_FILES = [
    "components/XtxSwiper.vue", "components/XtxGuess.vue",
    "pages/index/components/CategoryPanel.vue", "pages/index/components/HotPanel.vue",
    "pages/index/index.vue",
]


def load_code_context():
    src = os.path.join(FB, "xtx", "src")
    parts = []
    for rel in HOME_SRC_FILES:
        fp = os.path.join(src, rel)
        if os.path.exists(fp):
            parts.append(f"// ==== {rel} ====\n" + open(fp, encoding="utf-8").read())
    return "\n\n".join(parts)


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


def prf(tp, fp, fn, tn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    acc = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
            "fpr": round(fpr, 3), "accuracy": round(acc, 3),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def fault_png(cid):
    safe = cid.replace("/", "_").replace(":", "_")
    p = os.path.join(SCREENS, safe + ".png")
    return p if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--extra-healthy", type=int, default=4)
    ap.add_argument("--with-code", action="store_true", help="差分诊断附带页面源码")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_png = os.path.join(SCREENS, "baseline.png")
    base_bytes = open(base_png, "rb").read()

    # 正确样本必须与 baseline/faults **同一构建** —— 用 campaign 自己的 healthy_*。
    # （R2 实测：fresh 重渲染的 correct_extra 与旧 disk baseline 跨构建比，SSIM~0.49 全假阳；
    #   而同构建 healthy_* FPR=0%。残留 FPR 是跨构建 baseline 不匹配的方法学问题，非轮播抖动。
    #   见 fault_bench/campaign_out/fpr_rc/。--extra-healthy 已废弃，保留参数兼容。）
    correct = sorted(glob.glob(os.path.join(SCREENS, "healthy_*.png")))

    camp = sorted(glob.glob(os.path.join(OUT, "campaign_*.json")))
    cdata = json.load(open(camp[-1], encoding="utf-8"))
    fault_cases = [c for c in cdata["cases"] if c["kind"] == "fault" and "error" not in c]

    pool = []
    for c in fault_cases:
        p = fault_png(c["id"])
        if p:
            pool.append({"id": c["id"], "label": 1, "png": p, "gt_dim": c["gt_dim"]})
    for p in correct:
        pool.append({"id": os.path.basename(p)[:-4], "label": 0, "png": p, "gt_dim": "none"})

    n_pos = sum(1 for x in pool if x["label"] == 1)
    n_neg = sum(1 for x in pool if x["label"] == 0)
    print(f"[pool] 故障(正例)={n_pos}  正确(负例)={n_neg}  共 {len(pool)}")

    diag = VTDiagnoser(use_learned=True, use_cascade=False)
    diag.set_baseline("feed", base_png)
    m = default_mllm()
    print(f"[oracle] {type(m).__name__} available={m.is_available()} with_code={args.with_code}")
    code_ctx = load_code_context() if args.with_code else None
    if code_ctx:
        print(f"[oracle] code_context {len(code_ctx)} chars")

    rows = []
    t_start = time.time()
    for i, x in enumerate(pool):
        cur = open(x["png"], "rb").read()
        d = diag.diagnose("feed", x["png"])
        ours = bool(d["multichannel_alarm"])
        rs = m.analyze(cur, page_type="feed")
        q_single = bool(rs.has_blur or rs.has_blank or rs.has_overlap or rs.has_missing_image)
        rd = m.analyze_diff(base_bytes, cur, page_type="feed", code_context=code_ctx)
        q_diff = bool(rd.extra.get("has_defect"))
        rows.append({"id": x["id"], "label": x["label"], "gt_dim": x["gt_dim"],
                     "ours": ours, "qwen_single": q_single, "qwen_diff": q_diff,
                     "qwen_diff_dim": rd.extra.get("dimension"),
                     "qwen_diff_reason": rd.reasoning[:90]})
        print(f"  [{i+1}/{len(pool)}] {('FAULT' if x['label'] else 'OK   ')} {x['id'][:32]:32s} "
              f"ours={int(ours)} q1={int(q_single)} qdiff={int(q_diff)} [{rd.extra.get('dimension')}]")

    def metrics(key):
        tp = sum(1 for r in rows if r["label"] == 1 and r[key])
        fn = sum(1 for r in rows if r["label"] == 1 and not r[key])
        fp = sum(1 for r in rows if r["label"] == 0 and r[key])
        tn = sum(1 for r in rows if r["label"] == 0 and not r[key])
        return prf(tp, fp, fn, tn)

    for r in rows:
        r["ours_plus_qwendiff"] = r["ours"] or r["qwen_diff"]
    report = {"ts": ts, "n_pos": n_pos, "n_neg": n_neg, "with_code": args.with_code,
              "elapsed_s": round(time.time() - t_start),
              "ours": metrics("ours"), "qwen_single": metrics("qwen_single"),
              "qwen_diff": metrics("qwen_diff"), "ours_plus_qwen_diff": metrics("ours_plus_qwendiff")}

    jp = os.path.join(OUT, f"qwen_diff_ab_{ts}.json")
    json.dump({"report": report, "rows": rows}, open(jp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    mp = os.path.join(OUT, f"qwen_diff_ab_{ts}.md")
    open(mp, "w", encoding="utf-8").write(render_md(report, rows))
    print("\n=== 混合池 A/B（precision/recall/FPR/F1）===")
    for k in ("ours", "qwen_single", "qwen_diff", "ours_plus_qwen_diff"):
        v = report[k]
        print(f"  {k:20s} P={v['precision']:.2f} R={v['recall']:.2f} F1={v['f1']:.2f} "
              f"FPR={v['fpr']:.2f} acc={v['accuracy']:.2f} (tp{v['tp']} fp{v['fp']} fn{v['fn']} tn{v['tn']})")
    print(f"\n[done] {jp}\n[done] {mp}")


def render_md(report, rows):
    L = [f"# 混合池 A/B：故障+正确样本 · precision/recall/FPR/F1\n",
         f"_run {report['ts']} · 正例(故障){report['n_pos']} / 负例(正确){report['n_neg']} · "
         f"差分诊断 with_code={report['with_code']}_\n",
         "## 各方法（同一混合池）\n",
         "| 方法 | Precision | Recall | F1 | FPR | Accuracy | tp/fp/fn/tn |", "|---|---|---|---|---|---|---|"]
    name = {"ours": "ours(多通道)", "qwen_single": "qwen 单图(旧)",
            "qwen_diff": "qwen 差分(新,图+基线)", "ours_plus_qwen_diff": "ours + qwen差分 融合"}
    for k in ("ours", "qwen_single", "qwen_diff", "ours_plus_qwen_diff"):
        v = report[k]
        L.append(f"| {name[k]} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} | "
                 f"{v['fpr']:.2f} | {v['accuracy']:.2f} | {v['tp']}/{v['fp']}/{v['fn']}/{v['tn']} |")
    L += ["", "## 逐样本\n", "| id | 真实 | ours | qwen单图 | qwen差分 | 差分维度 |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id'][:30]} | {'故障' if r['label'] else '正确'} | "
                 f"{'✅' if r['ours'] else '·'} | {'✅' if r['qwen_single'] else '·'} | "
                 f"{'✅' if r['qwen_diff'] else '·'} | {r.get('qwen_diff_dim','')} |")
    L += ["", "> 正例=注入故障应报警；负例=正确样本不应报警。FPR=负例被误报比例。",
          "> qwen差分=给【健康基线图+当前图(+源码)】判'相对基线是否引入缺陷'，消除单图判缺陷的占位图偏见。"]
    return "\n".join(L)


if __name__ == "__main__":
    main()
