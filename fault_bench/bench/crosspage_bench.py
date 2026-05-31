"""R3 跨页基准（Vision-Triage）：证明"健康基线局部对比"在多个页面布局上都成立。

设计（避开 R1/R2 两个坑）：
  - 只测"探针验证过能渲染真实内容"的页：index / cart / my（category/hot 空白已排除）。
  - **每页各自 baseline**（R2 教训：跨页/跨构建比会假阳）。同一次 build、同一会话渲染。
  - 故障只注入"已肉眼确认在当前(登出态)可见区"的站点——避免注入 logged-in 分支里
    根本不渲染的故障（那会人为压低 recall，是 R1 性能注入不可见的同类错误）。
  - 报每页：健康 FPR（健康图 vs 本页 baseline）+ 可见故障是否被检出 + tile SSIM。

可见故障（已读源码确认在登出态渲染）：
  - my:avatar_missing —— 未登录头像 <image class="avatar gray" src="..."> 置空（缺图）。
  - my:avatar_width —— .avatar { width:120rpx } 改成 12rpx（几何塌缩）。
两者都在 my 页"未登录"区，probe 已确认该区渲染（text含"未登录 点击登录账号"）。

用法：python fault_bench/bench/crosspage_bench.py --port 8099 --healthy 4
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

from bench.run_bench import XTX, SRC, git_clean_src, build, channels_of, predict_dim, detected  # noqa: E402
from bench.renderer import XtxRenderer  # noqa: E402
from vt_diagnose import VTDiagnoser  # noqa: E402

H5_DIST = os.path.join(XTX, "dist", "build", "h5")
OUT = os.path.join(FB, "campaign_out", "crosspage")

# 探针验证可渲染真实内容的页：(page_key, route, wait_selector)
PAGES = [
    ("index", "", ".guess-item"),
    ("cart", "pages/cart/cart", ".guess-item"),   # 登出态：空购物车引导 + 猜你喜欢
    ("my", "pages/my/my", ".guess-item"),         # 登出态：未登录头 + 我的订单 + 猜你喜欢
]

# 仅注入"已读源码确认登出态(未登录)可见"的故障；marker 均单行 count==1（已校验）。
VISIBLE_FAULTS = [
    # 未登录头像 <image class="avatar gray" src="https://yjy-...">：破坏 src → 缺图（露出 #eee 圆底）
    {"id": "my:avatar_missing", "page": "my", "dim": "visual", "subtype": "missing_image",
     "file": "pages/my/my.vue",
     "old": 'src="https://yjy-xiaotuxian-dev', "new": 'srcX="https://yjy-xiaotuxian-dev'},
    # .avatar { width:120rpx } → 12rpx：头像几何塌缩（visual/layout）
    {"id": "my:avatar_width", "page": "my", "dim": "visual", "subtype": "geometry_collapse",
     "file": "pages/my/my.vue",
     "old": "width: 120rpx", "new": "width: 12rpx"},
    # 我的订单标题色 #1e1e1e → 接近背景的浅色：低对比度（visual，已知是系统短板，测它）
    {"id": "my:title_lowcontrast", "page": "my", "dim": "visual", "subtype": "low_contrast",
     "file": "pages/my/my.vue",
     "old": "color: #1e1e1e", "new": "color: #f6f6f6"},
    # 猜你喜欢卡片缺图（XtxGuess 在 index/cart/my 都渲染）—— 大面积视觉回归，
    # 在 MY 路由上注入，验证检测器在非首页路由能端到端抓到真故障（与首页同类、面积大）。
    {"id": "my:guess_img_missing", "page": "my", "dim": "visual", "subtype": "missing_image",
     "file": "components/XtxGuess.vue",
     "old": ':src="item.picture"', "new": ':src="\'\'"'},
    # 同一缺图故障在 CART 路由上注入，进一步证明跨页（cart 布局）也能抓。
    {"id": "cart:guess_img_missing", "page": "cart", "dim": "visual", "subtype": "missing_image",
     "file": "components/XtxGuess.vue",
     "old": ':src="item.picture"', "new": ':src="\'\'"'},
]


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


def apply_unique(rel, old, new):
    fp = os.path.join(SRC, rel)
    s = open(fp, "r", encoding="utf-8").read()
    if s.count(old) != 1:
        return None, f"count={s.count(old)}"
    open(fp, "w", encoding="utf-8").write(s.replace(old, new, 1))
    return fp, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--healthy", type=int, default=4)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    git_clean_src()
    ok, secs, err = build()
    if not ok:
        print("[FATAL] baseline build:", err[:200]); sys.exit(1)
    print(f"[setup] baseline build {secs}s")

    srv = serve(args.port)
    url = f"http://127.0.0.1:{args.port}"
    result = {"ts": ts, "pages": {}, "faults": []}
    try:
        r = XtxRenderer(url)
        diag = VTDiagnoser(use_learned=True, use_cascade=False)
        base_load = {}
        # 每页 baseline + 健康 FPR
        for key, route, sel in PAGES:
            b = r.render(route, os.path.join(OUT, f"{key}_baseline.png"), wait_selector=sel)
            diag.set_baseline(key, b["png"])
            base_load[key] = b["load_ms"]
            fps, rows = 0, []
            for i in range(args.healthy):
                h = r.render(route, os.path.join(OUT, f"{key}_healthy_{i}.png"), wait_selector=sel)
                d = diag.diagnose(key, h["png"], dom_info=h["dom_info"], dom_text=h["dom_text"])
                ch = channels_of(d, h["load_ms"], base_load[key], h["page_errors"])
                al = detected(ch)
                fps += 1 if al else 0
                rows.append({"i": i, "alarm": al, "tile": d["channels"].get("tiled_min_ssim"),
                             "channels": [k for k, v in ch.items() if v]})
            result["pages"][key] = {"n_healthy": args.healthy, "fp": fps,
                                    "fpr": round(fps / max(args.healthy, 1), 3), "rows": rows}
            print(f"[{key}] healthy FPR={fps}/{args.healthy} base_load={base_load[key]:.0f}ms")
        r.close()

        # 可见故障注入（每个：clean→apply→build→render 本页→诊断 vs 本页 baseline→还原）
        for f in VISIBLE_FAULTS:
            git_clean_src()
            fp, e = apply_unique(f["file"], f["old"], f["new"])
            if e:
                result["faults"].append({**{k: f[k] for k in ("id", "page", "dim")}, "error": "apply:" + e})
                print(f"[fault {f['id']}] SKIP apply {e}")
                continue
            try:
                bok, bsecs, berr = build()
                if not bok:
                    result["faults"].append({**{k: f[k] for k in ("id", "page", "dim")}, "error": "build"})
                    print(f"[fault {f['id']}] build FAIL")
                    continue
                srv2 = serve(args.port)  # 重启 serve 指向新（故障）dist
                rr = XtxRenderer(url)
                route = dict((p[0], p[1]) for p in PAGES)[f["page"]]
                sel = dict((p[0], p[2]) for p in PAGES)[f["page"]]
                fimg = rr.render(route, os.path.join(OUT, f"fault_{f['id'].replace(':','_')}.png"),
                                 wait_selector=sel)
                rr.close()
                try:
                    srv2.terminate()
                except Exception:
                    pass
                # 对比【页循环里渲染的干净 baseline】（仍在 diag 中，path={page}_baseline.png）。
                # 这正是 run_campaign 的正确模式：clean-build baseline vs faulted-build render。
                # （此前 bug：用故障 build 重渲一张当 baseline → baseline==fault==tile1.0 恒漏。）
                d = diag.diagnose(f["page"], fimg["png"], dom_info=fimg["dom_info"], dom_text=fimg["dom_text"])
                ch = channels_of(d, fimg["load_ms"], base_load[f["page"]], fimg["page_errors"])
                result["faults"].append({
                    "id": f["id"], "page": f["page"], "dim": f["dim"],
                    "detected": detected(ch), "pred_dim": predict_dim(ch),
                    "tile": d["channels"].get("tiled_min_ssim"),
                    "channels": [k for k, v in ch.items() if v]})
                print(f"[fault {f['id']}] detected={detected(ch)} pred={predict_dim(ch)} "
                      f"tile={d['channels'].get('tiled_min_ssim')}")
            finally:
                git_clean_src()
    finally:
        try:
            srv.terminate()
        except Exception:
            pass
        git_clean_src()

    total_fp = sum(p["fp"] for p in result["pages"].values())
    total_h = sum(p["n_healthy"] for p in result["pages"].values())
    result["summary"] = {
        "pages_tested": list(result["pages"].keys()),
        "crosspage_healthy_fpr": f"{total_fp}/{total_h}",
        "visible_faults_detected": f"{sum(1 for x in result['faults'] if x.get('detected'))}/{len(result['faults'])}",
    }
    jp = os.path.join(OUT, f"crosspage_{ts}.json")
    json.dump(result, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("\n=== SUMMARY ===")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"[done] {jp}")


if __name__ == "__main__":
    main()
