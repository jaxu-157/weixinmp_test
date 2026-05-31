"""Probe: render healthy home, diagnose with and without DOM signals.
Confirms the WeBug-R2 false-positive on real content-rich pages is fixed when
the (H5-only) DOM scrollWidth/scrollHeight signal is supplied.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from fault_bench.bench.renderer import XtxRenderer
from fault_bench.vt_diagnose import VTDiagnoser

BASE = os.environ.get("XTX_URL", "http://127.0.0.1:8099")
OUT = os.path.join(os.path.dirname(__file__), "..", "_probe_home.png")

r = XtxRenderer(BASE)
res = r.render("", OUT, wait_selector=".guess-item")
r.close()
print("dom_info:", res["dom_info"], "load_ms:", round(res["load_ms"] or 0, 1))

d = VTDiagnoser(use_learned=True, use_cascade=False)
d.set_baseline("feed", res["png"])
no_dom = d.diagnose("feed", res["png"])
with_dom = d.diagnose("feed", res["png"], dom_info=res["dom_info"], dom_text=res["dom_text"])
print("WITHOUT dom -> alarm=%s channels=%s" % (no_dom["multichannel_alarm"], no_dom["channels"]))
print("WITH    dom -> alarm=%s channels=%s" % (with_dom["multichannel_alarm"], with_dom["channels"]))
