"""R3 小验证：非首页能否被 renderer 渲染出非空白内容（决定能否扩样本到 category/cart/my）。

renderer 的 _handle_route 只 fixture 了首页相关 API；其它页若 API 没 fixture 可能是骨架/空白。
本脚本逐页渲染，报告 dom_text 长度 + 截图非空像素占比 + 文本快照，写 JSON 供核对。不臆断。
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

from bench.renderer import XtxRenderer  # noqa: E402

H5_DIST = os.path.join(FB, "xtx", "dist", "build", "h5")
OUT = os.path.join(FB, "campaign_out", "probe_pages")

# uni-app H5 hash 路由；首页 "" 特殊处理，其余用 pages/<x>/<x>
PAGES = [
    ("index", "", ".guess-item"),
    ("category", "pages/category/category", None),
    ("cart", "pages/cart/cart", None),
    ("my", "pages/my/my", None),
    ("hot", "pages/hot/hot", None),
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


def nonblank_ratio(png):
    try:
        import numpy as np
        from PIL import Image
        a = np.array(Image.open(png).convert("L"))
        # 非背景像素占比（背景多为白/浅灰 >= 245）
        return round(float((a < 245).mean()), 4)
    except Exception:
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    results = []
    srv = serve(args.port)
    try:
        r = XtxRenderer(f"http://127.0.0.1:{args.port}")
        for name, route, sel in PAGES:
            png = os.path.join(OUT, f"{name}.png")
            try:
                res = r.render(route, png, wait_selector=sel, settle_ms=1800)
                txt = (res.get("dom_text") or "").strip()
                results.append({
                    "page": name, "route": route,
                    "dom_text_len": len(txt),
                    "text_head": txt[:80].replace("\n", " "),
                    "nonblank_ratio": nonblank_ratio(png),
                    "page_errors": res.get("page_errors", [])[:2],
                })
            except Exception as e:
                results.append({"page": name, "route": route, "error": str(e)[:160]})
        r.close()
    finally:
        try:
            srv.terminate()
        except Exception:
            pass

    json.dump(results, open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for x in results:
        print(json.dumps(x, ensure_ascii=False))


if __name__ == "__main__":
    main()
