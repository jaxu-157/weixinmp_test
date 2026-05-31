"""minium 字段名运行时恢复 → 源码行 的端到端闭环验证（离线，无真机）。

真机路径上 `devtools_probe.collect_data` 读 page.data 后,新增的逐字段扫描
(_scan_suspicious_fields)会返回坏字段路径(如 guessList[0].price)。本测试用
合成 page.data(模拟 minium 在真机会读到的结构)驱动等价扫描逻辑,再把坏字段
末段喂给 localize.resolve_field_line,验证能定位到正确 .vue 源码行。

注:真机 page.data 由 minium connect 提供(需开发者工具),此处用合成数据离线验证
"扫描→字段→行"这一确定性链路;真机只是把合成 data 换成真实 page.data。
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.abspath(os.path.join(HERE, ".."))
for p in (os.path.dirname(FB), FB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bench.localize import build_field_line_index, resolve_field_line  # noqa

SRC = os.path.join(FB, "xtx", "src")
OUT = os.path.join(FB, "campaign_out", "localize_out")
# 与 devtools_probe.collect_data 内嵌 _scan_suspicious_fields 一致的坏值集
BADSTR = {"undefined", "null", "NaN", "[object Object]", "{{", "}}"}


def scan_suspicious_fields(node, prefix=""):
    bad = []
    if isinstance(node, dict):
        for k, v in node.items():
            bad += scan_suspicious_fields(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += scan_suspicious_fields(v, f"{prefix}[{i}]")
    else:
        val = node
        if (val is None or val == "" or (isinstance(val, float) and val != val)
                or (isinstance(val, str) and val.strip() in BADSTR)) and prefix:
            bad.append({"path": prefix, "value": "" if val == "" else str(val)})
    return bad


# 合成 page.data:模拟真机会读到的结构;每条对应一个组件的一个坏字段。
CASES = [
    ("components/XtxGuess.vue",
     {"guessList": [{"id": 1, "name": "面巾纸", "picture": "x.png", "price": "undefined"}]},
     "item.price"),
    ("components/XtxGuess.vue",
     {"guessList": [{"id": 1, "name": "", "picture": "x.png", "price": 19}]},
     "item.name"),
    ("pages/index/components/HotPanel.vue",
     {"list": [{"id": 1, "title": "新鲜", "alt": "NaN", "pictures": ["a.png"]}]},
     "item.alt"),
    ("pages/index/components/CategoryPanel.vue",
     {"categoryList": [{"id": 1, "name": None, "icon": "i.png"}]},
     "item.name"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    idx = build_field_line_index(SRC)
    rows = []
    for comp, data, expect_field in CASES:
        bad = scan_suspicious_fields(data)
        ok_scan = len(bad) >= 1
        tail = bad[0]["path"].split(".")[-1] if bad else None
        field = "item." + tail if tail else ""
        r = resolve_field_line(idx, comp, field)
        line_ok = bool(r.get("lines"))
        field_matches = (field == expect_field)
        rows.append({"component": comp, "scanned_path": bad[0]["path"] if bad else None,
                     "bad_value": bad[0]["value"] if bad else None,
                     "resolved_field": field, "expected_field": expect_field,
                     "field_match": field_matches, "src_lines": r.get("lines"),
                     "closed_loop_ok": ok_scan and line_ok and field_matches})
    n = len(rows)
    n_ok = sum(1 for r in rows if r["closed_loop_ok"])
    summary = {"_sentinel": "DATAFIELD_LOOP_OK", "n_cases": n,
               "closed_loop": f"{n_ok}/{n}=" + (f"{n_ok/n:.3f}" if n else "NA"),
               "note": "offline synthetic page.data; real-device swaps in minium page.data"}
    json.dump({"summary": summary, "rows": rows},
              open(os.path.join(OUT, "datafield_loop.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
