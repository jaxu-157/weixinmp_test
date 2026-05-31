"""Headless renderer for the xtx uni-app H5 dev server.

Intercepts the (down) itheima backend and returns local fixtures, navigates to
a page, waits for content, and writes a FIXED-size viewport screenshot (so
baseline-vs-buggy comparisons keep identical dimensions).
"""
from __future__ import annotations

import json
import os

from playwright.sync_api import sync_playwright

from .fixtures import route_table, guess_fixture

# Tall viewport so the WHOLE home page (incl. the below-the-fold 猜你喜欢 grid,
# where many mutations live) is captured in one fixed-size frame. Fixed dims keep
# baseline-vs-buggy SSIM comparable; full-page screenshot would vary in height.
VIEWPORT = {"width": 375, "height": 2200}


class XtxRenderer:
    def __init__(self, base_url: str, headless: bool = True):
        self.base_url = base_url.rstrip("/")
        self._routes = route_table()
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.console_errors: list[str] = []

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()

    def _handle_route(self, route):
        url = route.request.url
        if "itheima" in url or "/home/" in url or "/category/" in url or "/member/" in url:
            for key, builder in self._routes:
                if key in url:
                    route.fulfill(status=200, content_type="application/json",
                                  body=json.dumps(builder(), ensure_ascii=False))
                    return
            # unknown itheima endpoint -> benign empty success
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"code": "1", "msg": "ok",
                                           "result": {"items": [], "pages": 1, "counts": 0}}))
            return
        route.continue_()

    def render(self, route_path: str, out_png: str,
               wait_selector: str | None = None, settle_ms: int = 1600) -> dict:
        """Render a page and return browser-observable signals (zero app instrumentation):
        {png, dom_info:{scrollWidth,clientWidth,scrollHeight,clientHeight}, dom_text, load_ms}.
        """
        page = self.browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page_errors: list[str] = []      # uncaught JS exceptions (real crashes)
        console_errors: list[str] = []   # console.error (includes benign 404 noise)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        # 在导航前装 Long Task 采集器（PROJECT_REVIEW §3.2 真实性能信号）：
        # 主线程被同步阻塞(如组件 mounted 死循环)会产生 >50ms 的 longtask，累加到 __vt_longtask_total。
        page.add_init_script(
            "window.__vt_longtask_total=0; window.__vt_longtask_max=0;"
            "try{new PerformanceObserver(function(l){l.getEntries().forEach(function(e){"
            "window.__vt_longtask_total+=e.duration;"
            "if(e.duration>window.__vt_longtask_max)window.__vt_longtask_max=e.duration;});})"
            ".observe({type:'longtask',buffered:true});}catch(e){}"
        )
        page.route("**/*", self._handle_route)
        if route_path in ("", "/", "index"):
            url = self.base_url + "/"
        else:
            url = f"{self.base_url}/#/{route_path}"
        import time as _t
        t0 = _t.perf_counter()
        page.goto(url, wait_until="load", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=8000)
            except Exception:
                pass
        content_ready_ms = (_t.perf_counter() - t0) * 1000.0  # zero-touch time-to-content
        page.wait_for_timeout(settle_ms)
        # browser-observable signals
        try:
            dom = page.evaluate(
                """() => {
                  const de = document.documentElement, b = document.body;
                  const nav = performance.getEntriesByType('navigation')[0] || {};
                  const paints = performance.getEntriesByType('paint') || [];
                  const fcp = (paints.find(p => p.name === 'first-contentful-paint') || {}).startTime || null;
                  return {
                    scrollWidth: Math.max(de.scrollWidth, b ? b.scrollWidth : 0),
                    clientWidth: de.clientWidth,
                    scrollHeight: Math.max(de.scrollHeight, b ? b.scrollHeight : 0),
                    clientHeight: de.clientHeight,
                    text: (b ? b.innerText : '').slice(0, 4000),
                    navMs: nav.duration || null,
                    domContentLoaded: nav.domContentLoadedEventEnd || null,
                    loadEventEnd: nav.loadEventEnd || null,
                    fcp: fcp,
                    longtaskTotal: window.__vt_longtask_total || 0,
                    longtaskMax: window.__vt_longtask_max || 0,
                  };
                }"""
            )
        except Exception:
            dom = {}
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        page.screenshot(path=out_png, clip={"x": 0, "y": 0, **VIEWPORT})
        page.close()
        return {
            "png": out_png,
            "dom_info": {k: dom.get(k) for k in ("scrollWidth", "clientWidth", "scrollHeight", "clientHeight")},
            "dom_text": dom.get("text", ""),
            "load_ms": content_ready_ms,
            "nav_ms": dom.get("navMs"),
            "perf": {  # 真实运行时性能信号（PROJECT_REVIEW §3.2）
                "fcp": dom.get("fcp"),
                "dom_content_loaded": dom.get("domContentLoaded"),
                "load_event_end": dom.get("loadEventEnd"),
                "longtask_total_ms": dom.get("longtaskTotal", 0),
                "longtask_max_ms": dom.get("longtaskMax", 0),
            },
            "page_errors": list(page_errors),
            "console_errors": list(console_errors),
        }


if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
    r = XtxRenderer(base)
    out = os.path.join(os.path.dirname(__file__), "..", "_render_home.png")
    res = r.render("", out, wait_selector=".guess-item")
    print("rendered ->", os.path.abspath(out), os.path.getsize(out), "bytes")
    print("dom_info:", res["dom_info"], "load_ms:", res["load_ms"])
    print("dom_text head:", (res["dom_text"] or "")[:80].replace("\n", " "))
    if r.console_errors:
        print("console errors:", r.console_errors[:5])
    r.close()
