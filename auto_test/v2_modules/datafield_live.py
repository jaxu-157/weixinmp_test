"""真机实测:minium 连 devtools 读真实 page.data → 跑字段扫描器 → (若是xtx)定位源码行。

把"离线合成 page.data 4/4 闭环"升级为"真机真实 page.data 实读"。
前提:微信开发者工具已开某小程序 + 服务端口已开(默认 33676,可 MINIUM_PORT 覆盖)。
零侵入只读,不 shutdown(不关用户的 devtools)。
"""
from __future__ import annotations
import json
import os
import sys

PORT = int(os.environ.get("MINIUM_PORT", "33676"))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (HERE, REPO, os.path.join(REPO, "fault_bench")):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from devtools_probe import DevtoolsProbe  # noqa: E402

OUT = os.path.join(REPO, "fault_bench", "campaign_out", "localize_out", "datafield_live.json")


def main():
    import minium
    result = {"port": PORT, "connected": False}
    cfg = {"connect_to_existing": True, "test_port": PORT, "platform": "ide"}
    print(f"[live] connecting minium → devtools port {PORT} ...", flush=True)
    try:
        mini = minium.Minium(cfg)
    except Exception as e:
        result["error"] = f"connect_failed: {e}"
        json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("[live] CONNECT FAILED:", e)
        return
    result["connected"] = True
    print("[live] connected.", flush=True)

    probe = DevtoolsProbe(mini)
    # 当前页路由
    try:
        cur = mini.app.get_current_page()
        result["current_route"] = getattr(cur, "path", None) or str(cur)
    except Exception as e:
        result["current_route_err"] = str(e)[:120]

    # 核心:读真实 page.data + 新字段扫描器
    data = probe.collect_data()
    result["collect_data"] = {
        "available": data.get("available"),
        "data_keys": data.get("data_keys"),
        "has_suspicious": data.get("has_suspicious"),
        "suspicious_tokens": data.get("suspicious_tokens"),
        "suspicious_fields": data.get("suspicious_fields"),       # ← 真机坏字段路径
        "broken_field_paths": data.get("broken_field_paths"),
    }
    # 真几何 + 性能(顺带证明三类真信号都通)
    try:
        geo = probe.collect_geometry()
        result["geometry"] = {k: geo.get(k) for k in ("available", "has_overflow", "scroll_width", "client_width")}
    except Exception as e:
        result["geometry_err"] = str(e)[:120]

    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    print("[live] done, left devtools open. →", OUT)


if __name__ == "__main__":
    main()
