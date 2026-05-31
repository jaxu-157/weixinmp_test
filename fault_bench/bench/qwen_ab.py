"""Qwen-VL 视觉融合 A/B：在已保存的 campaign 截图上跑真实 Qwen，
计算 ours vs ours+Qwen vs Qwen-only 的检出率（含 bootstrap CI），
诚实回答"加上 Qwen 视觉融合能不能提升检出 / 救回漏检"。

复用 campaign 已渲染截图（无需重建），每张调一次 DashScope qwen-vl-plus。
截图会发到阿里云（用户已授权）。
"""
from __future__ import annotations
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.dirname(FB)
for p in (REPO, os.path.join(REPO, "diagnosis")):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from diagnose.mllm import default_mllm  # noqa: E402

SCREENS = os.path.join(FB, "campaign_out", "screens")


def bootstrap_ci(hits, n_boot=2000, seed=7):
    import random as _r
    if not hits:
        return (0.0, 0.0, 0.0)
    rng = _r.Random(seed)
    n = len(hits)
    means = sorted(sum(hits[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return (round(sum(hits) / n, 3), round(means[int(0.025 * n_boot)], 3), round(means[int(0.975 * n_boot)], 3))


def shot_for(case_id, kind):
    if kind == "healthy":
        p = os.path.join(SCREENS, case_id + ".png")  # healthy_0..
        return p if os.path.exists(p) else None
    safe = case_id.replace("/", "_").replace(":", "_")
    p = os.path.join(SCREENS, safe + ".png")
    return p if os.path.exists(p) else None


def main():
    camp = sorted(glob.glob(os.path.join(FB, "campaign_out", "campaign_*.json")))
    if not camp:
        print("no campaign json"); sys.exit(1)
    data = json.load(open(camp[-1], encoding="utf-8"))
    print(f"[qwen-ab] base campaign: {os.path.basename(camp[-1])}")

    m = default_mllm()
    print(f"[qwen-ab] oracle={type(m).__name__} available={m.is_available()}")
    if not m.is_available():
        print("[FATAL] Qwen not available"); sys.exit(1)

    cases = data["cases"]
    enriched = []
    total_ms = 0.0
    n_call = 0
    for c in cases:
        if c["kind"] == "fault" and "error" in c:
            continue
        sp = shot_for(c["id"], c["kind"])
        q = {"available": False}
        if sp:
            b = open(sp, "rb").read()
            t = time.time()
            r = m.analyze(b, page_type="feed")
            ms = (time.time() - t) * 1000
            total_ms += ms
            n_call += 1
            q = {"available": True,
                 "blur": r.has_blur, "blank": r.has_blank, "overlap": r.has_overlap,
                 "missing_image": r.has_missing_image, "conf": r.confidence, "ms": round(ms),
                 "anomaly": bool(r.has_blur or r.has_blank or r.has_overlap or r.has_missing_image)}
        # 现有 ours（截图规则/SSIM/webug 多通道，不含 qwen）
        ours = bool(c.get("detected"))
        qwen_hit = bool(q.get("anomaly"))
        enriched.append({"id": c["id"], "kind": c["kind"], "gt_dim": c.get("gt_dim"),
                         "subtype": c.get("subtype"), "tile_ssim": c.get("tile_ssim"),
                         "ours": ours, "qwen": qwen_hit, "ours_plus_qwen": ours or qwen_hit,
                         "qwen_raw": q})
        tag = "fault" if c["kind"] == "fault" else "healthy"
        print(f"  [{tag}] {c['id'][:34]:34s} ours={int(ours)} qwen={int(qwen_hit)} "
              f"(blur={q.get('blur')},miss={q.get('missing_image')},overlap={q.get('overlap')}) tile={c.get('tile_ssim')}")

    faults = [e for e in enriched if e["kind"] == "fault"]
    healthy = [e for e in enriched if e["kind"] == "healthy"]
    nf, nh = len(faults), len(healthy)

    def rates(key):
        fr = bootstrap_ci([1 if e[key] else 0 for e in faults])
        fp = round(sum(1 for e in healthy if e[key]) / nh, 3) if nh else 0
        return {"recall": fr[0], "ci95": [fr[1], fr[2]], "fp": fp,
                "n_det": sum(1 for e in faults if e[key])}

    report = {
        "base_campaign": os.path.basename(camp[-1]),
        "n_faults": nf, "n_healthy": nh,
        "qwen_calls": n_call, "qwen_avg_ms": round(total_ms / max(n_call, 1)),
        "ours_only": rates("ours"),
        "qwen_only": rates("qwen"),
        "ours_plus_qwen": rates("ours_plus_qwen"),
    }
    # Qwen 边际贡献：ours 漏但 qwen 中的故障
    rescued = [e["id"] for e in faults if (not e["ours"]) and e["qwen"]]
    report["qwen_rescued"] = rescued
    report["qwen_false_alarm_on_healthy"] = [e["id"] for e in healthy if e["qwen"]]

    ts = data["ts"]
    out = os.path.join(FB, "campaign_out", f"qwen_ab_{ts}.json")
    json.dump({"report": report, "cases": enriched}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n=== QWEN A/B SUMMARY ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[done] {out}")


if __name__ == "__main__":
    main()
