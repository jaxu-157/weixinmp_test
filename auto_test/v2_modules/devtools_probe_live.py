"""真机探针验证：连已手动打开的微信开发者工具，读真实 devtools 信号并打印结构。

目的：用真实返回校准 devtools_probe.py 的解析（之前按文档推断的字段名要对准真值）。
只读、不注入、不改小程序。connect 模式（auto_relaunch=False）连用户手动开的前台会话。

用法：
    python auto_test/v2_modules/devtools_probe_live.py --port 33676 \
        --project D:\\weixinmp_test\\third-youzouzou-wxapp
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (HERE, AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from devtools_probe import DevtoolsProbe, signals_to_business  # noqa: E402


def jdump(x, n=1500):
    try:
        s = json.dumps(x, ensure_ascii=False, indent=2, default=str)
    except Exception:
        s = str(x)
    return s[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--cli", default=r"D:\wx_mp_tool2\微信web开发者工具\cli.bat")
    args = ap.parse_args()

    config = {
        "project_path": args.project,
        "dev_tool_path": args.cli,
        "test_port": args.port,
        "appid": "",                 # 让 minium 从 project.config.json 读
        "debug_mode": "error",
        "enable_app_log": True,
        "auto_relaunch": False,      # connect 模式：连手动开的前台会话，别重启
        "auto_quit_ide": False,
        "request_timeout": 60,
        "device_desktop": {"width": 375, "height": 667},
    }
    print("[live] config:", jdump(config, 600))

    import minium
    print("[live] connecting minium (connect mode) ...")
    mini = minium.Minium(config)
    print("[live] connected.\n")

    probe = DevtoolsProbe(mini)
    report = {}

    try:
        # 当前页路径
        cur = None
        try:
            cur = mini.app.get_current_page()
            print("[live] current page:", getattr(cur, "path", "?"))
        except Exception as e:
            print("[live] get_current_page error:", e)

        # ---- 1) 性能：start → 触发渲染 → best_perf（自动选可用通道）----
        print("\n===== PERF: start_perf → render → best_perf =====")
        started = probe.start_perf()
        print("start_perf ->", started)
        try:
            mini.app.go_home()
        except Exception:
            pass
        import time
        time.sleep(2.0)
        perf = probe.best_perf()
        print("best_perf (parsed) ->", jdump(perf, 1000))
        report["perf_signal"] = perf

        print("\n===== PERF (raw get_perf_time path) =====")
        probe.start_perf(); time.sleep(1.0)
        perf_gpt = probe.stop_perf()
        print("stop_perf ->", jdump({k: v for k, v in perf_gpt.items() if k != 'entries'}, 500))
        report["perf_get_perf_time"] = {k: v for k, v in perf_gpt.items() if k != 'entries'}

        # ---- 2) 数据：page.data + wxml token 扫描 ----
        print("\n===== DATA: page.data + wxml suspicious tokens =====")
        data_sig = probe.collect_data()
        print("collect_data ->", jdump(data_sig))
        report["data_signal"] = data_sig

        # ---- 3) 几何：元素 rect/size/offset + 页面 scroll ----
        print("\n===== GEOMETRY: element rect / page scroll =====")
        geo = probe.collect_geometry()
        print("collect_geometry ->", jdump(geo))
        report["geometry_signal"] = geo

        # ---- 原始 rect 样例（直接打 minium 返回，校准字段名）----
        print("\n===== RAW element.rect/size/offset sample =====")
        try:
            page = mini.app.get_current_page()
            for sel in ("view", "image", "text"):
                els = page.get_elements(sel) or []
                if els:
                    el = els[0]
                    raw = {
                        "selector": sel,
                        "rect": _safe_attr(el, "rect"),
                        "size": _safe_attr(el, "size"),
                        "offset": _safe_attr(el, "offset"),
                        "clientRect": _safe_attr(el, "clientRect"),
                        "inner_text": _safe_attr(el, "inner_text"),
                    }
                    print(jdump(raw, 600))
                    report.setdefault("raw_rect_samples", []).append(raw)
        except Exception as e:
            print("raw rect sample error:", e)

        # ---- 翻译成 business/perf ----
        print("\n===== signals_to_business =====")
        biz = signals_to_business({
            "perf_signal": perf, "data_signal": data_sig, "geometry_signal": geo,
        })
        print(jdump(biz))
        report["translated"] = biz

    finally:
        try:
            mini.shutdown()
        except Exception:
            pass

    out = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", "devtools_live_probe.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[live] full report -> {out}")


def _safe_attr(el, name):
    try:
        return getattr(el, name)
    except Exception as e:
        return f"<err: {e}>"


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
