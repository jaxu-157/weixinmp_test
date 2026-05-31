"""DevTools 真实信号探针 —— 用 minium 从微信开发者工具读取运行时观测量。

动机（见 docs 维度覆盖真相表）：
  现状 auto_test_runner 把 page_state / perf_data **硬编码**（按故障名猜值），
  所以 functional（无 token 空绑定）和 performance 两维**没有真实信号源**。
  本模块把它们换成 minium 从真实小程序读到的**观测值**：

    1. page.data / 元素文本     → 真实业务数据（抓"空绑定 / NaN / undefined"数据故障）
    2. 元素 rect/size/offset    → 真实几何（抓溢出/重叠 layout 故障，不再像素猜）
    3. wx.getPerformance + get_perf_time → 真实运行时耗时（抓 performance 故障）

设计原则：
  - **纯只读观测，零应用改动** → 不影响被测应用原有功能。
  - **优雅降级**：任一探针失败都返回 {"available": False, ...}，绝不抛异常打断上层。
  - 全部基于 minium 1.6.0 已确认存在的 API（见模块自检 __main__）。

真机验证要点（2026-05-30, youzouzou, connect 模式, port 33676）：
  - mini.app.screen_shot 在 connect 会话能真正写文件（30KB），不受"relaunch 后截图坏"影响。
  - wx.getPerformance via evaluate 返回 {id, result:{result:{ok, count, entries:[...]}}}，
    entries 形如 {name:'appLaunch'|'firstRender'|'evaluateScript'..., entryType, duration, startTime}。
"""
from __future__ import annotations

from typing import Any, Optional

# 可疑数据 token：渲染到界面上几乎一定是 bug（异步回调字段错配的典型症状）
SUSPICIOUS_TOKENS = ("undefined", "null", "NaN", "[object Object]", "{{", "}}")


# ============================================================ 模块级工具
def _safe(fn, default=None):
    """跑一个可能抛异常的 minium 调用，失败返回 default。"""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - 探针必须永不打断上层
        return default


def _entry_dur(entries: list, name_key: str):
    """从 perf entries 里取名字含 name_key 的条目 duration（取最大值）。"""
    best = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name", "")).lower()
        if name_key in nm:
            d = e.get("duration")
            if d is None and e.get("startTime") is not None and e.get("endTime") is not None:
                d = e["endTime"] - e["startTime"]
            if isinstance(d, (int, float)):
                best = d if best is None else max(best, float(d))
    return best


def _max_script_dur(entries: list):
    """最长 script/evaluate 任务耗时（抓主线程阻塞/同步计算故障）。"""
    best = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name", "")).lower()
        if "script" in nm or "evaluate" in nm:
            d = e.get("duration")
            if isinstance(d, (int, float)):
                best = d if best is None else max(best, float(d))
    return best


def _unwrap_result(res):
    """逐层下钻 evaluate 的嵌套 result 包装，返回最内层含 ok/entries 的 dict。

    实测形态：{'id':..,'result':{'result':{ok:..,entries:[..]}}}（双层 result）。
    """
    cur = res
    for _ in range(4):
        if isinstance(cur, dict) and ("ok" in cur or "entries" in cur):
            return cur
        if isinstance(cur, dict) and "result" in cur:
            cur = cur["result"]
        else:
            break
    return cur


# ============================================================ 探针主体
class DevtoolsProbe:
    """对一个已连接的 minium 实例做运行时只读观测。

    用法：
        probe = DevtoolsProbe(mini)          # mini = minium.Minium(config)
        probe.start_perf()                   # 切页/交互前
        ... 切页 / 交互 ...
        signals = probe.collect(page_type="feed")
    """

    def __init__(self, mini):
        self.mini = mini
        self.app = getattr(mini, "app", None)
        self._perf_started = False

    # ---------------------------------------------------------- 性能
    def start_perf(self) -> bool:
        """开始采集运行时性能（导航/交互前）。get_perf_time 无返回值，不抛异常即成功。"""
        if self.app is None:
            return False
        _SENTINEL = object()
        res = _safe(lambda: self.app.get_perf_time(), default=_SENTINEL)
        self._perf_started = res is not _SENTINEL
        return self._perf_started

    def stop_perf(self) -> dict:
        """停止 get_perf_time 采集并解析。注意：实测此通道在 connect 模式偶发空，
        故 best_perf 会在它不可用时回退到 perf_via_api（wx.getPerformance）。"""
        if not self._perf_started or self.app is None:
            return {"available": False, "error": "perf_not_started_or_no_app"}
        raw = _safe(lambda: self.app.stop_get_perf_time())
        self._perf_started = False
        if raw is None:
            return {"available": False, "error": "stop_get_perf_time_failed"}
        entries = self._normalize_perf(raw)
        if not entries:
            return {"available": False, "error": "empty_entries", "n_entries": 0}
        return {
            "available": True,
            "source": "get_perf_time",
            "entries": entries[:50],
            "n_entries": len(entries),
            "app_launch_ms": _entry_dur(entries, "applaunch"),
            "first_render_ms": _entry_dur(entries, "firstrender"),
            "first_paint_ms": _entry_dur(entries, "firstpaint"),
            "max_script_ms": _max_script_dur(entries),
        }

    @staticmethod
    def _normalize_perf(raw: Any) -> list[dict]:
        items = raw
        if isinstance(raw, dict):
            for k in ("data", "entries", "perfData", "result"):
                if isinstance(raw.get(k), list):
                    items = raw[k]
                    break
        if not isinstance(items, list):
            return []
        return [it if isinstance(it, dict) else {"name": str(it)} for it in items]

    def perf_via_api(self) -> dict:
        """主性能通道：wx.getPerformance().getEntries() 经 evaluate 求值（基础库 ≥2.11）。

        实测稳定可用。返回归一化耗时字段。非侵入只读。
        """
        if self.app is None:
            return {"available": False, "error": "no_app"}
        js = (
            "function(){try{var p=wx.getPerformance&&wx.getPerformance();"
            "if(!p||!p.getEntries)return {ok:false,reason:'no_api'};"
            "var es=p.getEntries()||[];"
            "return {ok:true, count:es.length, entries: es.map(function(e){return "
            "{name:e.name||e.entryType, entryType:e.entryType, duration:e.duration, "
            "startTime:e.startTime, endTime:e.endTime};})};"
            "}catch(e){return {ok:false, err:String(e)};}}"
        )
        res = _safe(lambda: self.app.evaluate(js, sync=True))
        if res is None:
            return {"available": False, "error": "evaluate_failed"}
        payload = _unwrap_result(res)
        if isinstance(payload, dict) and payload.get("ok") and isinstance(payload.get("entries"), list):
            entries = payload["entries"]
            return {
                "available": True,
                "source": "wx.getPerformance",
                "entries": entries[:50],
                "n_entries": len(entries),
                "app_launch_ms": _entry_dur(entries, "applaunch"),
                "first_render_ms": _entry_dur(entries, "firstrender"),
                "first_paint_ms": _entry_dur(entries, "firstpaint"),
                "max_script_ms": _max_script_dur(entries),
            }
        return {"available": False, "error": "no_entries", "raw": str(res)[:200]}

    def best_perf(self) -> dict:
        """优先 get_perf_time（若录到非空）→ 否则 wx.getPerformance（实测主通道）。"""
        if self._perf_started:
            p = self.stop_perf()
            if p.get("available"):
                return p
        return self.perf_via_api()

    # ---------------------------------------------------------- 数据
    def collect_data(self) -> dict:
        """读当前页 page.data + wxml，扫可疑 token（空绑定/NaN/undefined）。"""
        if self.app is None:
            return {"available": False, "error": "no_app"}
        page = _safe(lambda: self.app.get_current_page())
        if page is None:
            return {"available": False, "error": "no_current_page"}

        data = _safe(lambda: page.data)
        wxml = _safe(lambda: page.wxml) or ""
        data_str = ""
        data_keys = []
        if isinstance(data, dict):
            data_keys = list(data.keys())
            import json as _json
            data_str = _safe(lambda: _json.dumps(data, ensure_ascii=False, default=str)) or str(data)
        elif data is not None:
            data_str = str(data)

        haystack = data_str + "\n" + (wxml if isinstance(wxml, str) else "")
        hits = sorted({t for t in SUSPICIOUS_TOKENS if t in haystack})
        return {
            "available": data is not None or bool(wxml),
            "suspicious_tokens": hits,
            "has_suspicious": bool(hits),
            "data_keys": data_keys[:40],
            "text_sample": haystack[:300],
        }

    # ---------------------------------------------------------- 几何
    def collect_geometry(self, selectors: Optional[list[str]] = None) -> dict:
        """读页面与元素真实几何，判溢出/重叠（真几何，非像素猜）。

        说明（真机校准 2026-05-30）：
          - overflow（横向 scrollWidth>clientWidth、元素超出右边界）是**可靠**信号，健康页为 False。
          - overlap 在无 DOM 层级信息时易把"相邻/嵌套元素"误判，**仅作参考**，不进 has_overflow 主判。
        """
        if self.app is None:
            return {"available": False, "error": "no_app"}
        page = _safe(lambda: self.app.get_current_page())
        if page is None:
            return {"available": False, "error": "no_current_page"}

        sw = _safe(lambda: page.scroll_width)
        sh = _safe(lambda: page.scroll_height)
        inner = _safe(lambda: page.inner_size) or {}
        cw = inner.get("width") if isinstance(inner, dict) else None
        ch = inner.get("height") if isinstance(inner, dict) else None

        page_overflow_x = bool(sw and cw and sw > cw * 1.05)

        sels = selectors or ["image", "view", "text", "button"]
        rects = []
        for sel in sels:
            els = _safe(lambda s=sel: page.get_elements(s)) or []
            for el in els[:40]:
                r = _safe(lambda e=el: e.rect)
                if isinstance(r, dict) and all(k in r for k in ("left", "top", "width", "height")):
                    rects.append({"sel": sel, **{k: r[k] for k in ("left", "top", "width", "height")}})

        # 元素超出视口右边界 / 左边界（真溢出，可靠）
        overflow_elements = []
        if cw:
            for r in rects:
                if r["left"] + r["width"] > cw + 2 or r["left"] < -2:
                    overflow_elements.append(r)

        # overlap：排除父子嵌套（cover≥0.92=包含），只记部分交叠；仅参考，不进主判
        overlap_pairs = []
        big = [r for r in rects if r["width"] * r["height"] > 400][:30]
        for i in range(len(big)):
            for j in range(i + 1, len(big)):
                a, b = big[i], big[j]
                ox = max(0, min(a["left"] + a["width"], b["left"] + b["width"]) - max(a["left"], b["left"]))
                oy = max(0, min(a["top"] + a["height"], b["top"] + b["height"]) - max(a["top"], b["top"]))
                inter = ox * oy
                if inter <= 0:
                    continue
                smaller = min(a["width"] * a["height"], b["width"] * b["height"])
                if not smaller:
                    continue
                cover = inter / smaller
                if cover >= 0.92:        # 父子嵌套/包含，跳过
                    continue
                if cover > 0.30:
                    overlap_pairs.append({"a": a, "b": b, "cover_small": round(cover, 2)})

        # 主判仅用 overflow（可靠）；overlap 仅信息
        has_overflow = bool(page_overflow_x or overflow_elements)
        return {
            "available": bool(rects) or sw is not None,
            "page_overflow_x": page_overflow_x,
            "scroll_width": sw, "client_width": cw,
            "scroll_height": sh, "client_height": ch,
            "n_elements": len(rects),
            "overflow_elements": overflow_elements[:10],
            "overlap_pairs": overlap_pairs[:10],
            "has_overflow": has_overflow,
            "has_overlap": bool(overlap_pairs),   # 仅参考，调用方自行决定是否采信
        }

    # ---------------------------------------------------------- 汇总
    def collect(self, page_type: str = "feed") -> dict:
        """一次性收集三类信号（性能优先 get_perf_time，回退 wx.getPerformance）。"""
        return {
            "perf_signal": self.best_perf(),
            "data_signal": self.collect_data(),
            "geometry_signal": self.collect_geometry(),
            "page_type": page_type,
        }


# ============================================================ 信号 → 维度
def signals_to_business(devtools_signals: dict) -> dict:
    """把 devtools 真实信号翻译成 DriverEngine.diagnose() 认识的 business/perf 输入。

    让诊断器的 functional/performance 维度吃到**真实观测值**而非硬编码猜值。
    返回 {"business": {...}, "perf": {...}, "extra": {...}}。
    """
    data_sig = devtools_signals.get("data_signal", {})
    geo_sig = devtools_signals.get("geometry_signal", {})
    perf_sig = devtools_signals.get("perf_signal", {})

    business = {}
    if data_sig.get("has_suspicious"):
        business["visible_value"] = "/".join(data_sig.get("suspicious_tokens", [])) or "undefined"
        business["expected_value"] = "<valid>"
    ui_flags = {}
    # 几何主判只用 overflow（可靠）；overlap 不采信（无 DOM 层级易假阳）
    if geo_sig.get("has_overflow"):
        ui_flags["hasOverlap"] = True   # 复用现有 uiFlags 通道表达"布局几何异常"
    business["ui_flags"] = ui_flags

    perf = {}
    cand = [perf_sig.get(k) for k in
            ("first_render_ms", "max_script_ms", "first_paint_ms", "app_launch_ms")]
    cand = [v for v in cand if isinstance(v, (int, float))]
    if cand:
        perf["interaction_ms"] = max(cand)
    return {
        "business": business,
        "perf": perf,
        "extra": {
            "data_signal": data_sig,
            "geometry_signal": {k: v for k, v in geo_sig.items() if k != "overflow_elements"},
            "perf_signal": {k: v for k, v in perf_sig.items() if k != "entries"},
        },
    }


if __name__ == "__main__":
    import minium
    need = {
        "App": ["get_perf_time", "stop_get_perf_time", "call_wx_method", "evaluate",
                "get_current_page", "mock_request", "screen_shot"],
        "Page": ["data", "scroll_width", "scroll_height", "inner_size", "get_elements", "wxml"],
        "BaseElement": ["rect", "size", "offset", "clientRect", "inner_text"],
    }
    print("=== minium API presence (minium %s) ===" % getattr(minium, "__version__", "?"))
    allok = True
    for cls_name, attrs in need.items():
        cls = getattr(minium, cls_name)
        for a in attrs:
            ok = hasattr(cls, a)
            allok &= ok
            print(f"  {'OK ' if ok else 'MISS'} {cls_name}.{a}")
    # 解析单元自检（不需 devtools）
    fake = [
        {"name": "appLaunch", "entryType": "navigation", "duration": 8199},
        {"name": "firstRender", "entryType": "render", "duration": 82},
        {"name": "evaluateScript", "entryType": "script", "duration": 2},
    ]
    assert _entry_dur(fake, "applaunch") == 8199
    assert _entry_dur(fake, "firstrender") == 82
    assert _max_script_dur(fake) == 2
    assert _unwrap_result({"result": {"result": {"ok": True, "entries": fake}}})["ok"] is True
    print("PARSE_UNIT_OK")
    print("ALL_PRESENT" if allok else "SOME_MISSING")
