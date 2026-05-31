"""根因定位准确率基准(确定性,无 LLM)——衡量"检出后能否定位到正确源文件"。

复用上轮 campaign 的已存故障截图(免重编译);index 页渲染确定(R3 实测 tile≈1.0 跨构建),
故 fresh baseline 与 saved fault 比对有效。流程:
  1. build_class_file_index(src)  —— class→源文件
  2. 渲染 index baseline(live)+ 在 24 个 tile 中心 elementsFromPoint → tile→element 映射
  3. mutations=generate(index) → {id: file}(定位真值)
  4. 每个变异:per_tile_ssim(baseline, saved_fault) → worst tiles → 查 tile→element → localize → file
     与真值 file 比 → 命中?  仅在【检出】(worst<0.85)的变异上算定位率(没检出无从定位)。

输出 JSON:每变异 {id, gt_file, detected, worst_tile, pred_file, file_hit};汇总 detection/localization 率。
"""
from __future__ import annotations
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
for p in (os.path.dirname(FB), FB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

from bench.renderer import XtxRenderer  # noqa
from bench.gen_random_mutations import generate  # noqa
from bench.localize import (build_class_file_index, build_hash_file_index,  # noqa
                            tile_center_px, tile_box_px, localize_from_elements,
                            localize_by_datav, localize_by_bbox_area, TILE_ROWS, TILE_COLS)
from vt_diagnose import per_tile_ssim, TILE_SSIM_REGRESSION  # noqa

H5 = os.path.join(FB, "xtx", "dist", "build", "h5")
SRC = os.path.join(FB, "xtx", "src")
SCREENS = os.path.join(FB, "campaign_out", "screens")
OUT = os.path.join(FB, "campaign_out", "localize_out")
ELEMENTS_JS = r"""
(pts) => pts.map(([x,y]) => {
  const els = document.elementsFromPoint(x,y) || [];
  return els.slice(0,6).map(e => ({
    tag: e.tagName,
    cls: (e.className && e.className.baseVal!==undefined ? e.className.baseVal : e.className) || '',
    dataV: Array.from(e.attributes||[]).filter(a=>a.name.startsWith('data-v-')).map(a=>a.name),
    text: (e.textContent||'').trim().slice(0,20)
  }));
})
"""
# 采集全部带 data-v 的元素 + 其 page 坐标 rect(视口固定2200高、scroll=0,getBoundingClientRect即page坐标)
ALL_ELEMENTS_JS = r"""
() => {
  const out = [];
  for (const e of document.querySelectorAll('[class*="data-v-"], *')) {
    const dv = Array.from(e.attributes||[]).filter(a=>a.name.startsWith('data-v-')).map(a=>a.name);
    if (!dv.length) continue;
    const r = e.getBoundingClientRect();
    if (r.width<=0 || r.height<=0) continue;
    out.push({
      cls: (e.className && e.className.baseVal!==undefined ? e.className.baseVal : e.className) || '',
      dataV: dv,
      rect: {x: r.x, y: r.y, w: r.width, h: r.height}
    });
  }
  return out;
}
"""


def serve(port):
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                         cwd=H5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2); return p
        except Exception:
            time.sleep(0.5)
    return p


def sanitize(mid):  # 与 run_campaign 存图命名一致
    return mid.replace("/", "_").replace(":", "_")


def worst_tiles(base_png, fault_png, k=3):
    tiles = per_tile_ssim(base_png, fault_png)
    ranked = sorted(tiles.items(), key=lambda kv: kv[1])  # 低 SSIM 在前
    return ranked[:k], (ranked[0][1] if ranked else 1.0)


def main():
    os.makedirs(OUT, exist_ok=True)
    class_idx = build_class_file_index(SRC)
    hash_idx = build_hash_file_index(SRC, os.path.join(H5, "assets"))

    srv = serve(8099)
    try:
        r = XtxRenderer("http://127.0.0.1:8099")
        base = r.render("", os.path.join(OUT, "baseline_index.png"), wait_selector=".guess-item")
        # 在 24 个 tile 中心做 elementsFromPoint(用内部 browser 开一个 page)
        page = r.browser.new_page(viewport={"width": 375, "height": 2200}, device_scale_factor=1)
        page.route("**/*", r._handle_route)
        page.goto("http://127.0.0.1:8099/", wait_until="load", timeout=30000)
        try: page.wait_for_selector(".guess-item", timeout=8000)
        except Exception: pass
        page.wait_for_timeout(1600)
        pts = [tile_center_px(i, j) for i in range(TILE_ROWS) for j in range(TILE_COLS)]
        stacks = page.evaluate(ELEMENTS_JS, pts)
        all_elements = page.evaluate(ALL_ELEMENTS_JS)  # bbox 面积排序用
        page.close(); r.close()
    finally:
        try: srv.terminate()
        except Exception: pass

    # tile (i,j) → 元素栈
    tile_elems = {}
    idx = 0
    for i in range(TILE_ROWS):
        for j in range(TILE_COLS):
            tile_elems[(i, j)] = stacks[idx]; idx += 1

    base_png = os.path.join(OUT, "baseline_index.png")
    muts = [m for m in generate(SRC, seed=42, pages=["index"])]

    def _hit(pf, gt):
        return bool(pf and (pf == gt or os.path.basename(pf) == os.path.basename(gt)))

    rows = []
    for m in muts:
        sp = os.path.join(SCREENS, sanitize(m["id"]) + ".png")
        if not os.path.exists(sp):
            rows.append({"id": m["id"], "gt_file": m["file"], "error": "no_screenshot"}); continue
        wt, worst = worst_tiles(base_png, sp, k=3)
        detected = worst < TILE_SSIM_REGRESSION
        worst_ij = wt[0][0] if wt else None
        gt = m["file"]
        pred_pt = {"file": None}   # 路线A:单点 hash(旧)
        pred_bb = {"file": None}   # 路线B:bbox 面积排序(新)
        if detected and worst_ij is not None:
            pred_pt = localize_by_datav(tile_elems.get(worst_ij, []), hash_idx)
            if not pred_pt.get("file"):
                pred_pt = localize_from_elements(tile_elems.get(worst_ij, []), class_idx)
            worst_boxes = [tile_box_px(i, j) for (i, j), s in wt if s < TILE_SSIM_REGRESSION]
            if not worst_boxes:
                worst_boxes = [tile_box_px(*worst_ij)]
            pred_bb = localize_by_bbox_area(all_elements, worst_boxes, hash_idx)
        rows.append({"id": m["id"], "dim": m["dim"], "gt_file": gt, "detected": detected,
                     "worst_tile": list(worst_ij) if worst_ij else None, "worst_ssim": round(worst, 4),
                     "pred_pt": pred_pt.get("file"), "hit_pt": _hit(pred_pt.get("file"), gt),
                     "pred_bbox": pred_bb.get("file"), "hit_bbox": _hit(pred_bb.get("file"), gt),
                     "bbox_inter": pred_bb.get("inter_area")})

    det = [r_ for r_ in rows if "error" not in r_ and r_["detected"]]
    n_det = len(det)
    n_pt = sum(1 for r_ in det if r_["hit_pt"])
    n_bb = sum(1 for r_ in det if r_["hit_bbox"])
    n_union = sum(1 for r_ in det if r_["hit_pt"] or r_["hit_bbox"])
    summary = {
        "n_mutations": len([r_ for r_ in rows if "error" not in r_]),
        "n_detected": n_det,
        "file_acc_singlepoint": f"{n_pt}/{n_det}=" + (f"{n_pt/n_det:.3f}" if n_det else "NA"),
        "file_acc_bbox_area": f"{n_bb}/{n_det}=" + (f"{n_bb/n_det:.3f}" if n_det else "NA"),
        "file_acc_union": f"{n_union}/{n_det}=" + (f"{n_union/n_det:.3f}" if n_det else "NA"),
    }
    json.dump({"summary": summary, "rows": rows},
              open(os.path.join(OUT, "localization_v2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("[done]", os.path.join(OUT, "localization_v2.json"))


if __name__ == "__main__":
    main()
