"""最小注入-还原验证（1 个故障，秒级，可逆，不关工具）。

目标：在 others 首页注入 1 个数据故障，证明完整闭环安全可用：
  健康基线(截图+data+几何+perf) → 注入1处源码 → relaunch强制重编 →
  故障态(截图+data) → finally 还原 → 字节级校验还原 → 断开但不关 IDE。

注入点：pages/others/others.js  `name: '表单',` → `name: '表单' + undefined,`
  渲染层会变成 "表单undefined"，page.data 出现 undefined token（驱动 data 信号）。
这是数据故障，首页可见，无需导航——同时回答"只停首页"不是问题。

可逆保证：内存备份原文 + try/finally 必还原；脚本尾打印 before/after SHA 供核对。

用法: python auto_test/v2_modules/min_inject_verify.py --port 33676 \
        --project D:\\weixinmp_test\\third-youzouzou-wxapp
"""
from __future__ import annotations
import os, sys, json, time, hashlib, argparse, traceback

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

ENTRY = "/pages/others/others"
TARGET_FILE = "pages/others/others.js"
OLD = "name: '表单',"
NEW = "name: '表单' + undefined,"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def shot_meta(path):
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        return {"written": True, "size": os.path.getsize(path)}
    return {"written": False, "size": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--cli", default=r"D:\wx_mp_tool2\微信web开发者工具\cli.bat")
    ap.add_argument("--recompile-wait", type=float, default=4.0)
    args = ap.parse_args()

    out_dir = os.path.join(AUTO, "reports", "v2_driver", "min_inject")
    os.makedirs(out_dir, exist_ok=True)
    target_path = os.path.join(args.project, TARGET_FILE)

    # 预检：标记唯一。**二进制备份**保证字节级可逆（避免文本模式把 \n 转 \r\n 改字节）。
    orig_bytes = open(target_path, "rb").read()
    src0 = orig_bytes.decode("utf-8")
    if src0.count(OLD) != 1:
        print(f"[FATAL] marker not unique: count={src0.count(OLD)} in {TARGET_FILE}")
        sys.exit(1)
    sha_before = sha(target_path)
    print(f"[min] target={TARGET_FILE} sha_before={sha_before} (marker unique ✓)\n")

    config = {
        "project_path": args.project, "dev_tool_path": args.cli, "test_port": args.port,
        "appid": "", "debug_mode": "error", "enable_app_log": True,
        "auto_relaunch": False, "auto_quit_ide": False, "request_timeout": 60,
        "device_desktop": {"width": 375, "height": 667},
    }
    import minium
    print("[min] connecting (connect mode, NO ide close)...")
    mini = minium.Minium(config)
    print("[min] connected.\n")
    probe = DevtoolsProbe(mini)
    report = {"target": TARGET_FILE, "sha_before": sha_before}
    injected = False

    try:
        # ---------- A. 健康基线 ----------
        print("===== A. 健康基线（relaunch 首页 → 截图 + 信号）=====")
        _relaunch(mini, ENTRY)
        time.sleep(2.5)
        h_shot = os.path.join(out_dir, "healthy.png")
        _try_shot(mini, h_shot)
        h_data = probe.collect_data()
        h_geo = probe.collect_geometry()
        h_perf = probe.best_perf()
        print(f"  截图: {shot_meta(h_shot)}")
        print(f"  data: has_suspicious={h_data.get('has_suspicious')} tokens={h_data.get('suspicious_tokens')}")
        print(f"  几何: has_overflow={h_geo.get('has_overflow')}")
        print(f"  perf: app_launch_ms={h_perf.get('app_launch_ms')} max_script_ms={h_perf.get('max_script_ms')}")
        report["healthy"] = {"shot": shot_meta(h_shot), "data": _d(h_data), "geo": _g(h_geo), "perf": _p(h_perf)}

        # ---------- B. 注入 ----------
        print("\n===== B. 注入 1 处源码（可逆，二进制写避免换行符篡改）=====")
        with open(target_path, "wb") as f:
            f.write(src0.replace(OLD, NEW, 1).encode("utf-8"))
        injected = True
        sha_injected = sha(target_path)
        print(f"  injected: {OLD!r} → {NEW!r}")
        print(f"  sha_injected={sha_injected} (changed={sha_injected != sha_before})")
        report["sha_injected"] = sha_injected

        # ---------- C. 重编译 + 故障态 ----------
        print(f"\n===== C. relaunch 强制重编（等 {args.recompile_wait}s）→ 故障态 =====")
        time.sleep(args.recompile_wait)
        _relaunch(mini, ENTRY)
        time.sleep(2.5)
        b_shot = os.path.join(out_dir, "buggy.png")
        _try_shot(mini, b_shot)
        b_data = probe.collect_data()
        print(f"  截图: {shot_meta(b_shot)}")
        print(f"  data: has_suspicious={b_data.get('has_suspicious')} tokens={b_data.get('suspicious_tokens')}")
        report["buggy"] = {"shot": shot_meta(b_shot), "data": _d(b_data)}

        # ---------- D. 截图视觉对比（健康 vs 故障）----------
        if h_data is not None and shot_meta(h_shot)["written"] and shot_meta(b_shot)["written"]:
            try:
                sys.path.insert(0, os.path.join(REPO, "fault_bench"))
                from vt_diagnose import tiled_min_ssim
                tmin = tiled_min_ssim(h_shot, b_shot)
                print(f"\n  截图分块SSIM(健康 vs 故障)最差tile = {tmin}  (<1=画面有变化，证明注入生效且截图捕到)")
                report["tiled_min_ssim_healthy_vs_buggy"] = tmin
            except Exception as e:
                print("  ssim err:", e)

    finally:
        # ---------- E. 还原（必做，二进制写回原始字节）----------
        print("\n===== E. 还原源码（finally 保证，写回原始字节）=====")
        try:
            with open(target_path, "wb") as f:
                f.write(orig_bytes)
            sha_after = sha(target_path)
            report["sha_after"] = sha_after
            print(f"  restored. sha_after={sha_after}")
            print(f"  ✓ 字节级可逆: {sha_after == sha_before}  (after==before)")
            report["reversible_ok"] = (sha_after == sha_before)
        except Exception as e:
            print("  [CRITICAL] 还原失败:", e)
            report["reversible_ok"] = False
        # connect 模式：**不调 shutdown**（no-arg shutdown 在 connect 模式会关掉用户的项目）。
        # 进程结束自动断开 socket，IDE/项目保持打开。
        print("  (connect 模式不调 shutdown；进程退出自动断连，工具/项目保持打开)")

    # ---------- 结论 ----------
    out = os.path.join(out_dir, "min_inject_verify.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[min] report -> {out}")
    print("\n===== 结论 =====")
    hd = report.get("healthy", {}).get("data", {})
    bd = report.get("buggy", {}).get("data", {})
    print(f"  可逆(字节级)         : {report.get('reversible_ok')}")
    print(f"  注入前后SHA不同       : {report.get('sha_injected') != report.get('sha_before')}")
    print(f"  截图(健康/故障)都写出 : {report.get('healthy',{}).get('shot',{}).get('written')} / {report.get('buggy',{}).get('shot',{}).get('written')}")
    print(f"  data信号 健康→故障    : has_suspicious {hd.get('has_suspicious')} → {bd.get('has_suspicious')}  tokens {hd.get('suspicious_tokens')} → {bd.get('suspicious_tokens')}")
    print(f"  截图捕到画面变化(SSIM<1): {report.get('tiled_min_ssim_healthy_vs_buggy')}")


def _relaunch(mini, path):
    try:
        mini.app.relaunch(path)
    except Exception as e:
        print("  relaunch warn:", e)


def _try_shot(mini, path):
    if os.path.exists(path):
        try: os.remove(path)
        except OSError: pass
    try:
        mini.app.screen_shot(path)
    except Exception as e:
        print("  screenshot err:", e)


def _d(x): return {k: x.get(k) for k in ("available", "has_suspicious", "suspicious_tokens", "data_keys")}
def _g(x): return {k: x.get(k) for k in ("has_overflow", "has_overlap", "page_overflow_x", "scroll_width", "client_width")}
def _p(x): return {k: x.get(k) for k in ("available", "source", "app_launch_ms", "first_render_ms", "max_script_ms")}


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
