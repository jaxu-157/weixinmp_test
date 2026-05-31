"""纯只读验证：不注入、不还原、尽量不 relaunch。
确认三件事各自能否在本机 connect 会话稳定工作：
  1. screen_shot 能否真的写出文件（你内存里的最大未知）
  2. wx.getPerformance 真机 entries 原始结构（为何解析出 None）
  3. 几何 overflow / overlap（overlap 健康页假阳是否收敛）

用法: python auto_test/v2_modules/devtools_readonly_verify.py --port 33676 \
        --project D:\\weixinmp_test\\third-youzouzou-wxapp
"""
from __future__ import annotations
import os, sys, json, time, argparse, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.dirname(AUTO)
for p in (HERE, AUTO, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

from devtools_probe import DevtoolsProbe  # noqa: E402


def jd(x, n=1400):
    try: return json.dumps(x, ensure_ascii=False, indent=2, default=str)[:n]
    except Exception: return str(x)[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--cli", default=r"D:\wx_mp_tool2\微信web开发者工具\cli.bat")
    args = ap.parse_args()

    out_dir = os.path.join(AUTO, "reports", "v2_driver", "readonly_verify")
    os.makedirs(out_dir, exist_ok=True)

    config = {
        "project_path": args.project, "dev_tool_path": args.cli, "test_port": args.port,
        "appid": "", "debug_mode": "error", "enable_app_log": True,
        "auto_relaunch": False, "auto_quit_ide": False, "request_timeout": 60,
        "device_desktop": {"width": 375, "height": 667},
    }
    import minium
    print("[ro] connecting (connect mode, port %d, NO relaunch)..." % args.port)
    mini = minium.Minium(config)
    print("[ro] connected.\n")
    probe = DevtoolsProbe(mini)
    report = {}

    try:
        cur = None
        try:
            cur = mini.app.get_current_page()
            print("[ro] current page:", getattr(cur, "path", "?"), "(不切页，就地验证)\n")
        except Exception as e:
            print("[ro] get_current_page err:", e)

        # ---------- 验证 1: screen_shot 能否写文件 ----------
        print("===== [1] SCREENSHOT write test =====")
        shot = os.path.join(out_dir, "ro_shot.png")
        if os.path.exists(shot):
            os.remove(shot)
        ss = {"method_tried": [], "written": False, "size": 0, "path": shot}
        # 1a) minium screen_shot
        try:
            mini.app.screen_shot(shot)
            ok = os.path.exists(shot) and os.path.getsize(shot) > 0
            ss["method_tried"].append(("minium.screen_shot", ok, os.path.getsize(shot) if os.path.exists(shot) else 0))
            print(f"  minium.screen_shot -> written={ok} size={os.path.getsize(shot) if os.path.exists(shot) else 0}")
            ss["written"], ss["size"] = ok, (os.path.getsize(shot) if os.path.exists(shot) else 0)
        except Exception as e:
            ss["method_tried"].append(("minium.screen_shot", False, str(e)))
            print("  minium.screen_shot EXC:", e)
        # 1b) page.get_element('view') 首元素 .clientRect 截图? (no) — 退化用 PIL 窗口截图兜底（只读）
        if not ss["written"]:
            print("  [fallback] 尝试 Win32 窗口截图（只读，不动小程序）...")
            try:
                ok2 = _win_capture(shot)
                ss["method_tried"].append(("win32_grab", ok2, os.path.getsize(shot) if os.path.exists(shot) else 0))
                print(f"  win32 grab -> written={ok2} size={os.path.getsize(shot) if os.path.exists(shot) else 0}")
                ss["written"] = ss["written"] or ok2
                if ok2: ss["size"] = os.path.getsize(shot)
            except Exception as e:
                print("  win32 grab EXC:", e)
        report["screenshot"] = ss

        # ---------- 验证 2: perf 原始结构 ----------
        print("\n===== [2] PERF raw structure =====")
        # 2a) wx.getPerformance via evaluate —— 打原始返回
        raw_eval = None
        try:
            js = ("function(){try{var p=wx.getPerformance&&wx.getPerformance();"
                  "if(!p||!p.getEntries)return {ok:false,reason:'no_api'};"
                  "var es=p.getEntries()||[];"
                  "return {ok:true,count:es.length,entries:es.slice(0,20).map(function(e){"
                  "return {name:e.name,entryType:e.entryType,duration:e.duration,"
                  "startTime:e.startTime,endTime:e.endTime};})};"
                  "}catch(e){return {ok:false,err:String(e)};}}")
            raw_eval = mini.app.evaluate(js, sync=True)
            print("  RAW evaluate return:")
            print(jd(raw_eval, 1600))
        except Exception as e:
            print("  evaluate EXC:", e)
        report["perf_raw_evaluate"] = raw_eval
        # 2b) 经 probe 解析
        parsed = probe.perf_via_api()
        print("\n  probe.perf_via_api parsed ->")
        print(jd({k: v for k, v in parsed.items() if k != "entries"}, 600))
        report["perf_parsed"] = {k: v for k, v in parsed.items() if k != "entries"}

        # ---------- 验证 3: 几何 overflow/overlap ----------
        print("\n===== [3] GEOMETRY (current page, no inject) =====")
        geo = probe.collect_geometry()
        print(f"  page_overflow_x={geo.get('page_overflow_x')} scrollW={geo.get('scroll_width')} clientW={geo.get('client_width')}")
        print(f"  n_elements={geo.get('n_elements')} overflow_elements={len(geo.get('overflow_elements',[]))} overlap_pairs={len(geo.get('overlap_pairs',[]))}")
        print(f"  has_overflow={geo.get('has_overflow')} has_overlap={geo.get('has_overlap')}  <- 健康页应 overflow=False")
        report["geometry"] = {k: v for k, v in geo.items() if k not in ("overflow_elements",)}

        # ---------- 验证 4: data（只读，确认 token 扫描）----------
        print("\n===== [4] DATA (page.data token scan) =====")
        data = probe.collect_data()
        print(f"  available={data.get('available')} has_suspicious={data.get('has_suspicious')} "
              f"tokens={data.get('suspicious_tokens')} keys={data.get('data_keys')}")
        report["data"] = {k: v for k, v in data.items() if k != "text_sample"}

    finally:
        try: mini.shutdown()
        except Exception: pass

    out = os.path.join(out_dir, "readonly_verify.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[ro] report -> {out}")
    # 结论速览
    print("\n===== VERDICT =====")
    print("  screenshot_works :", report.get("screenshot", {}).get("written"))
    print("  perf_parsed_ok   :", report.get("perf_parsed", {}).get("available"),
          "max_script_ms=", report.get("perf_parsed", {}).get("max_script_ms"),
          "app_launch_ms=", report.get("perf_parsed", {}).get("app_launch_ms"))
    g = report.get("geometry", {})
    print("  geometry_overflow_fp:", g.get("has_overflow"), "(健康页应 False)")
    print("  geometry_overlap_fp :", g.get("has_overlap"), "(健康页若 True=仍假阳)")


def _win_capture(filepath):
    """Win32 抓微信开发者工具模拟器区域（只读，不操作小程序）。"""
    import ctypes, ctypes.wintypes
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    target = []

    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if "微信开发者工具" in buf.value:
            target.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not target:
        return False
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(target[0], ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    bbox = (rect.left + int(w * 0.02), rect.top + int(h * 0.08),
            rect.left + int(w * 0.42), rect.bottom - int(h * 0.02))
    ImageGrab.grab(bbox=bbox).save(filepath)
    return os.path.exists(filepath) and os.path.getsize(filepath) > 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
