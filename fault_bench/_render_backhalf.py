"""Render hand-written healthy/buggy HTML variants to PNG (back-half proof)."""
import os
from playwright.sync_api import sync_playwright

D = os.path.join(os.path.dirname(__file__), "_backhalf")
os.makedirs(D, exist_ok=True)

healthy = """<html><body style="margin:0;font-family:sans-serif">
<div style="display:flex;flex-wrap:wrap;padding:8px">
 <div style="width:48%;margin:1%;border:1px solid #ddd"><div style="height:120px;background:#4a90d9"></div><p style="margin:6px">Product A</p><b style="margin:6px;color:#e44">Y39</b></div>
 <div style="width:48%;margin:1%;border:1px solid #ddd"><div style="height:120px;background:#50b06a"></div><p style="margin:6px">Product B</p><b style="margin:6px;color:#e44">Y59</b></div>
 <div style="width:48%;margin:1%;border:1px solid #ddd"><div style="height:120px;background:#d9a04a"></div><p style="margin:6px">Product C</p><b style="margin:6px;color:#e44">Y19</b></div>
 <div style="width:48%;margin:1%;border:1px solid #ddd"><div style="height:120px;background:#9a4ad9"></div><p style="margin:6px">Product D</p><b style="margin:6px;color:#e44">Y99</b></div>
</div></body></html>"""
blank = '<html><body style="margin:0;background:#fff"></body></html>'
blur = '<html><body style="margin:0;filter:blur(6px)">' + healthy + '</body></html>'
overlap = """<html><body style="margin:0;font-family:sans-serif"><div style="position:relative">
 <div style="position:absolute;top:20px;left:10px;width:200px;height:140px;background:#4a90d9"></div>
 <div style="position:absolute;top:60px;left:40px;width:240px;height:140px;background:#e44;opacity:.85">overlapping text node</div>
</div></body></html>"""

variants = {"healthy": healthy, "blank": blank, "blur": blur, "overlap": overlap}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 375, "height": 667})
    for name, h in variants.items():
        pg.set_content(h)
        pg.wait_for_timeout(150)
        fp = os.path.join(D, name + ".png")
        pg.screenshot(path=fp)
        print("rendered", fp, os.path.getsize(fp), "bytes")
    b.close()
