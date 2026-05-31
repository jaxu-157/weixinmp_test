"""只读身份探测：连指定端口，确认当前 attach 的是哪个项目。
不注入、不切页、不关工具。用 get_all_pages_path / 当前页 判定。

用法: python auto_test/v2_modules/which_project.py --port 33676 [--project <任一路径>]
"""
from __future__ import annotations
import sys, os, argparse, traceback
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", default=r"D:\weixinmp_test\third-youzouzou-wxapp")
    ap.add_argument("--cli", default=r"D:\wx_mp_tool2\微信web开发者工具\cli.bat")
    a = ap.parse_args()
    cfg = {"project_path": a.project, "dev_tool_path": a.cli, "test_port": a.port,
           "appid": "", "auto_relaunch": False, "auto_quit_ide": False,
           "request_timeout": 60, "debug_mode": "error"}
    import minium
    print(f"[id] connecting port {a.port} (project_path hint={os.path.basename(a.project)})...")
    mini = minium.Minium(cfg)
    try:
        app_id = None
        try: app_id = mini.app.app_id
        except Exception: pass
        pages = []
        try: pages = mini.app.get_all_pages_path() or []
        except Exception as e: print("  get_all_pages_path err:", e)
        cur = None
        try: cur = getattr(mini.app.get_current_page(), "path", None)
        except Exception: pass

        # 判定
        joined = " ".join(pages)
        if "pages/others/others" in joined or "pages/example" in joined:
            ident = "youzouzou (原生WXML, 48页)"
        elif "pages/index/index" in joined and "pages/category" in joined:
            ident = "小兔鲜儿 xtx (uni-app→mp-weixin, 8页)"
        else:
            ident = "未知"
        print(f"\n  app_id        = {app_id}")
        print(f"  current_page  = {cur}")
        print(f"  pages_count   = {len(pages)}")
        print(f"  pages_head    = {pages[:6]}")
        print(f"\n  >>> 当前端口 {a.port} 实际连的是: {ident}")
    finally:
        # connect 模式不调 shutdown（会关用户项目）；进程退出自动断连
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(); sys.exit(1)
