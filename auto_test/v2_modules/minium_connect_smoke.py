"""最小 Minium 连接 smoke —— 仅验证：
  1. cli 能启动微信开发者工具的 automator 模式
  2. minium 能连接上、能 navigate_to、能 screen_shot
不跑完整矩阵，只跑 3 页 × normal profile，用于排错。
"""
from __future__ import annotations

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_TEST_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(AUTO_TEST_DIR)
for p in (AUTO_TEST_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import TEST_CONFIG, PAGE_PATHS  # type: ignore


def main():
    print("[smoke] importing minium ...")
    import minium

    out_dir = os.path.join(AUTO_TEST_DIR, "reports", "v2_driver", "minium_smoke")
    os.makedirs(out_dir, exist_ok=True)

    # Minium 1.6.0 接收一个 conf dict
    print(f"[smoke] project_path = {TEST_CONFIG['project_path']}")
    print(f"[smoke] dev_tool_path = {TEST_CONFIG['dev_tool_path']}")

    if not os.path.exists(TEST_CONFIG["project_path"]):
        print(f"[smoke] FATAL: project_path 不存在")
        sys.exit(2)
    if not os.path.exists(TEST_CONFIG["dev_tool_path"]):
        print(f"[smoke] FATAL: dev_tool_path 不存在")
        sys.exit(2)

    print("[smoke] launching minium (will start dev-tool's automator)...")
    t0 = time.time()
    try:
        mini = minium.Minium(TEST_CONFIG)
    except Exception as e:
        print(f"[smoke] minium.Minium() 启动失败: {e}")
        traceback.print_exc()
        sys.exit(3)
    print(f"[smoke] connected in {time.time() - t0:.1f}s")

    results = []
    try:
        for page_name, page_path in PAGE_PATHS.items():
            try:
                print(f"[smoke] -> {page_name} ({page_path})")
                # demo-uniapp 这 3 页都在 tabBar，必须 switch_tab
                try:
                    mini.app.switch_tab(page_path)
                except Exception:
                    mini.app.navigate_to(page_path)  # fallback for non-tabbar pages
                time.sleep(2)
                shot = os.path.join(out_dir, f"{page_name}_normal.png")
                mini.app.screen_shot(shot)
                ok = os.path.exists(shot)
                size = os.path.getsize(shot) if ok else 0
                results.append({"page": page_name, "ok": ok, "shot": shot, "size": size})
                print(f"[smoke]    screenshot ok={ok} size={size}B")
            except Exception as e:
                results.append({"page": page_name, "ok": False, "err": str(e)})
                print(f"[smoke]    ERROR: {e}")
    finally:
        try:
            mini.shutdown()
        except Exception:
            pass

    print("\n=== smoke summary ===")
    for r in results:
        print(f"  {r['page']:<10} -> ok={r['ok']}  {r.get('shot', r.get('err', ''))}")

    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\n{ok_count}/{len(results)} pages captured")
    sys.exit(0 if ok_count == len(results) else 1)


if __name__ == "__main__":
    main()
