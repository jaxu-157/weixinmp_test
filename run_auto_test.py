#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  Vision-Triage 一键自动化测试脚本
============================================================

【每次测试流程】

  1. 打开微信开发者工具（项目已导入，会自动加载）
  2. 终端执行:
      conda activate vision-triage
      python run_auto_test.py

  就这么简单。脚本自动完成:
    启动后端(8900) → 连接Minium → 执行14个矩阵用例 → 生成报告 → 关闭后端

【改完前端代码后需要重新编译】

  cd demo-uniapp && npx uni build -p mp-weixin && cd ..

【可选参数】

  --launch-ide      自动启动微信开发者工具
  --skip-check      跳过前置检查
  --backend-only    仅启动后端（手动调试用）

【输出位置】

  终端:  实时进度 + 最终矩阵表格
  文件:  reports/auto_test_report_{时间戳}.json
         reports/auto_test_matrix_{时间戳}.txt
"""
import os
import sys
import json
import time
import signal
import subprocess
import argparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)


def load_minium_config():
    config_path = os.path.join(PROJECT_ROOT, "minium_config.json")
    if not os.path.exists(config_path):
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_prerequisites():
    """检查前置条件"""
    print("=" * 56)
    print("  检查前置条件")
    print("=" * 56)

    ok = True
    mc = load_minium_config()
    if not mc:
        print("[FAIL] minium_config.json 不存在")
        return False

    proj = mc.get("project_path", "")
    tool = mc.get("dev_tool_path", "")
    if not os.path.exists(proj):
        print(f"[WARN] 小程序项目路径不存在: {proj}")
        print("       请修改 minium_config.json 中的 project_path")
        ok = False
    else:
        print(f"[ OK ] 小程序项目: {proj}")
    if not os.path.exists(tool):
        print(f"[WARN] 开发者工具 CLI 不存在: {tool}")
        print("       请修改 minium_config.json 中的 dev_tool_path")
        ok = False
    else:
        print(f"[ OK ] 开发者工具 CLI: {tool}")

    for mod in ["fastapi", "uvicorn", "cv2", "numpy"]:
        try:
            __import__(mod if mod != "cv2" else "cv2")
        except ImportError:
            print(f"[WARN] Python 模块未安装: {mod}")
            ok = False
    print("[ OK ] Python 依赖检查完成")

    static = os.path.join(PROJECT_ROOT, "diagnosis", "static")
    blurs = [f for f in os.listdir(static) if f.startswith("blur_")] if os.path.exists(static) else []
    if len(blurs) < 8:
        print("[WARN] 模糊测试图片不足，需先运行: python diagnosis/generate_blur_images.py")
        ok = False
    else:
        print(f"[ OK ] 模糊测试图片 ({len(blurs)} 张)")

    return ok


def launch_devtools():
    """自动启动微信开发者工具并加载项目"""
    mc = load_minium_config()
    if not mc:
        print("[FAIL] 无法读取 minium_config.json")
        return False

    cli = mc.get("dev_tool_path", "")
    proj = mc.get("project_path", "")

    if not os.path.exists(cli):
        print(f"[FAIL] CLI 不存在: {cli}")
        return False
    if not os.path.exists(proj):
        print(f"[FAIL] 项目路径不存在: {proj}")
        return False

    # 检查是否已登录
    try:
        result = subprocess.run(
            [cli, "islogin"],
            capture_output=True, text=True, timeout=10,
            shell=True,
        )
        # cli islogin 输出通常为 "{"login":true}" 或含 "true"
        if "true" not in result.stdout.lower():
            print("[WARN] 微信开发者工具可能未登录，请检查")
    except Exception:
        pass  # islogin 可能不支持，忽略

    print(f"[INFO] 启动微信开发者工具...")
    print(f"       项目: {proj}")

    try:
        # cli auto: 打开项目 + 启用自动化端口
        # --port 对应 minium_config 中的 test_port
        port = mc.get("test_port", 9420)
        proc = subprocess.Popen(
            [cli, "auto", "--project", proj, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )
        # cli auto 会后台运行，不需要持进程；等 IDE 启动
        print("[INFO] 等待开发者工具启动 (15秒)...")
        time.sleep(15)
        print("[ OK ] 开发者工具应已就绪")
        return True
    except Exception as e:
        print(f"[FAIL] 启动失败: {e}")
        return False


def start_backend():
    """启动诊断后端"""
    print("\n" + "=" * 56)
    print("  启动诊断后端 (端口 8900)")
    print("=" * 56)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app",
         "--host", "0.0.0.0", "--port", "8900"],
        cwd=os.path.join(PROJECT_ROOT, "diagnosis"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    import requests
    for i in range(15):
        try:
            r = requests.get("http://127.0.0.1:8900/fault/status", timeout=2)
            if r.status_code == 200:
                print("[ OK ] 后端已就绪")
                return proc
        except Exception:
            pass
        time.sleep(1)

    print("[FAIL] 后端启动超时")
    proc.terminate()
    return None


def stop_backend(proc):
    """关闭后端"""
    if proc:
        print("\n[INFO] 关闭后端...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[ OK ] 后端已关闭")


def run_tests():
    """执行自动化测试"""
    print("\n" + "=" * 56)
    print("  执行自动化测试")
    print("=" * 56)

    sys.path.insert(0, os.path.join(PROJECT_ROOT, "auto_test"))
    from auto_test_runner import VisionTriageAutoTester

    tester = VisionTriageAutoTester(
        config_path=os.path.join(PROJECT_ROOT, "minium_config.json")
    )
    success = tester.run_full_test_suite()
    return success, tester


def main():
    parser = argparse.ArgumentParser(description="Vision-Triage 一键自动化测试")
    parser.add_argument("--launch-ide", action="store_true",
                        help="自动启动微信开发者工具（否则需手动打开）")
    parser.add_argument("--skip-check", action="store_true",
                        help="跳过前置检查")
    parser.add_argument("--backend-only", action="store_true",
                        help="仅启动后端（手动测试用）")
    args = parser.parse_args()

    if args.backend_only:
        proc = start_backend()
        if proc:
            print("\n后端运行中，按 Ctrl+C 停止...")
            try:
                signal.pause()
            except (KeyboardInterrupt, AttributeError):
                pass
            finally:
                stop_backend(proc)
        return

    # 1. 前置检查
    if not args.skip_check:
        if not check_prerequisites():
            print("\n[FAIL] 前置检查未通过，请修复后重试")
            sys.exit(1)
        print()

    # 2. 启动微信开发者工具
    if args.launch_ide:
        print("=" * 56)
        print("  启动微信开发者工具")
        print("=" * 56)
        if not launch_devtools():
            print("\n[FAIL] 开发者工具启动失败")
            sys.exit(1)
        print()

    # 3. 启动后端
    backend = start_backend()
    if not backend:
        print("\n[FAIL] 无法启动后端，退出")
        sys.exit(1)

    # 4. 执行测试
    try:
        success, tester = run_tests()
    finally:
        stop_backend(backend)

    # 5. 最终摘要
    passed = sum(1 for r in tester.results if r["success"])
    total = len(tester.results)

    print("\n" + "=" * 56)
    print(f"  最终结果: {passed}/{total} 通过")
    print("=" * 56)

    failed = [r for r in tester.results if not r["success"]]
    if failed:
        print("\n失败用例:")
        for r in failed:
            print(f"  ✗ {r['test_name']}: {r['message']}")

    print(f"\n报告目录: {os.path.join(PROJECT_ROOT, 'auto_test', 'reports')}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
