"""第0步探测(先验证再建):H5 渲染后的 DOM 里到底有哪些可用于根因归因的信息?
- data-v-* scoped 属性在不在?(→ 组件级归因)
- 元素 class 能不能指认组件?(.guess-item / .caption ...)
- elementsFromPoint 在固定视口下返回什么?
- 能否从 DOM 读到 Vue 实例 / 空绑定文本节点?
只读探测,产物写 JSON,不改任何东西。
"""
from __future__ import annotations
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
for p in (os.path.dirname(FB), FB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from bench.renderer import XtxRenderer  # noqa

H5 = os.path.join(FB, "xtx", "dist", "build", "h5")
OUT = os.path.join(FB, "campaign_out", "probe_dom")


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


PROBE_JS = r"""
() => {
  const out = {};
  // 1) data-v-* 属性统计
  const all = Array.from(document.querySelectorAll('*'));
  const dataVAttrs = {};
  let withDataV = 0;
  for (const el of all) {
    for (const a of el.attributes) {
      if (a.name.startsWith('data-v-')) { dataVAttrs[a.name] = (dataVAttrs[a.name]||0)+1; withDataV++; }
    }
  }
  out.total_elements = all.length;
  out.elements_with_data_v = withDataV;
  out.distinct_data_v = Object.keys(dataVAttrs);
  // 2) 常见组件 class 是否存在
  const classes = ['guess-item','caption','category','swiper','navbar','panel','image','name','price'];
  out.class_present = {};
  for (const c of classes) out.class_present[c] = document.querySelectorAll('.'+c).length;
  // 3) elementsFromPoint 在几个采样点
  const pts = [[187, 200],[187, 600],[187, 1100],[187, 1700],[187, 2000]];
  out.points = pts.map(([x,y]) => {
    const els = document.elementsFromPoint(x, y) || [];
    return {x, y, stack: els.slice(0,4).map(e => ({
      tag: e.tagName, cls: (e.className && e.className.baseVal!==undefined ? e.className.baseVal : e.className) || '',
      dataV: Array.from(e.attributes||[]).filter(a=>a.name.startsWith('data-v-')).map(a=>a.name),
      text: (e.textContent||'').trim().slice(0,30)
    }))};
  });
  // 4) Vue 实例可达性
  out.has_vue_global = typeof window.__VUE__ !== 'undefined';
  out.has_vue_hook = typeof window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined';
  const probe = document.querySelector('.guess-item') || document.querySelector('uni-view');
  out.node_vue_expandos = probe ? Object.keys(probe).filter(k => k.startsWith('__v')) : [];
  // 5) 空/undefined 文本节点(功能故障定位用)
  const sus = [];
  for (const el of all) {
    const t = (el.childNodes.length===1 && el.firstChild && el.firstChild.nodeType===3) ? el.textContent.trim() : '';
    if (t === 'undefined' || t === 'NaN' || t === 'null') sus.push({cls: el.className||'', text:t});
  }
  out.suspicious_text_nodes = sus.slice(0,10);
  return out;
}
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    srv = serve(8099)
    try:
        r = XtxRenderer("http://127.0.0.1:8099")
        # 用内部 page：renderer 没暴露 evaluate，临时自己开一个 page 复用其 browser
        page = r.browser.new_page(viewport={"width": 375, "height": 2200}, device_scale_factor=1)
        page.route("**/*", r._handle_route)
        page.goto("http://127.0.0.1:8099/", wait_until="load", timeout=30000)
        try:
            page.wait_for_selector(".guess-item", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1600)
        res = page.evaluate(PROBE_JS)
        page.close(); r.close()
    finally:
        try: srv.terminate()
        except Exception: pass
    json.dump(res, open(os.path.join(OUT, "dom_attribution.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("[done]", os.path.join(OUT, "dom_attribution.json"))


if __name__ == "__main__":
    main()
