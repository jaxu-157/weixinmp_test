#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  Vision-Triage mitrix — 组合故障 × 多标签诊断
============================================================

【流程】
  1. 启动后端 (8900)
  2. 自动生成组合测试用例（单故障 + 两两组合 + 三故障组合）
  3. 连接微信开发者工具
  4. 逐用例：激活多故障 → 截图 → 诊断 → 多标签检测
  5. 生成故障检测矩阵报告
  6. 输出每故障 Precision / Recall / F1

【用法】
  conda activate vision-triage
  python run_mitrix_test.py

【可选参数】
  --cases FILE      使用自定义测试用例 JSON 文件
  --generate-only   仅生成用例不执行（查看用例列表）
  --single-only     仅测试单故障
  --pairs-only      仅测试两两组合
  --backend-only    仅启动后端

【与原脚本的关系】
  run_auto_test.py   — 8 个预定义 profile，单一判决矩阵
  run_mitrix_test.py — 组合故障生成，多标签检测矩阵

  两者互不影响，独立运行。
"""
import os
import sys
import json
import time
import argparse
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)


def start_backend():
    """启动诊断后端。"""
    print("=" * 56)
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
    if proc:
        print("\n[INFO] 关闭后端...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[ OK ] 后端已关闭")


def connect_wechat(config_path="minium_config.json"):
    """连接微信开发者工具。"""
    import minium

    config_path = os.path.join(PROJECT_ROOT, config_path)
    if not os.path.exists(config_path):
        print(f"[FAIL] 配置文件不存在: {config_path}")
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    config["request_timeout"] = 60

    print("🔌 连接微信开发者工具...")
    try:
        mini = minium.Minium(config)
        print("✅ 连接成功")
        return mini
    except Exception as e:
        if "clickCoverView" in str(e):
            print("⚠️  连接警告已忽略，继续执行")
            return mini
        print(f"❌ 连接失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Vision-Triage mitrix 组合故障测试")
    parser.add_argument("--cases", type=str, default=None,
                        help="自定义测试用例 JSON 文件路径")
    parser.add_argument("--generate-only", action="store_true",
                        help="仅生成用例 JSON 并打印摘要")
    parser.add_argument("--single-only", action="store_true",
                        help="仅测试单故障")
    parser.add_argument("--pairs-only", action="store_true",
                        help="仅测试两两组合")
    parser.add_argument("--backend-only", action="store_true",
                        help="仅启动后端（手动调试）")
    args = parser.parse_args()

    # 导入 mitrix 模块
    sys.path.insert(0, PROJECT_ROOT)
    from mitrix.generator import generate_test_cases, save_test_cases, print_summary

    # ---- 仅生成用例 ----
    if args.generate_only:
        include_pairs = not args.single_only
        include_triples = not args.single_only and not args.pairs_only
        cases = generate_test_cases(
            include_pairs=include_pairs,
            include_triples=include_triples,
        )
        out = os.path.join(PROJECT_ROOT, "mitrix_test_cases.json")
        save_test_cases(cases, out)
        print_summary(cases)
        print(f"\n已写入 {out}")
        return

    # ---- 加载用例 ----
    if args.cases:
        with open(args.cases, "r", encoding="utf-8") as f:
            cases = json.load(f)
        print(f"从文件加载 {len(cases)} 个用例: {args.cases}")
    else:
        include_pairs = not args.single_only
        include_triples = not args.single_only and not args.pairs_only
        cases = generate_test_cases(
            include_pairs=include_pairs,
            include_triples=include_triples,
        )
        out = os.path.join(PROJECT_ROOT, "mitrix_test_cases.json")
        save_test_cases(cases, out)

    print_summary(cases)

    # ---- 仅启动后端 ----
    if args.backend_only:
        proc = start_backend()
        if proc:
            print("\n后端运行中，按 Ctrl+C 停止...")
            try:
                import signal
                signal.pause()
            except (KeyboardInterrupt, AttributeError):
                pass
            finally:
                stop_backend(proc)
        return

    # ---- 完整流程 ----
    backend = start_backend()
    if not backend:
        print("[FAIL] 无法启动后端")
        sys.exit(1)

    try:
        mini = connect_wechat()
        if not mini:
            print("[FAIL] 无法连接微信开发者工具")
            sys.exit(1)

        from mitrix.runner import MitrixRunner
        runner = MitrixRunner(mini)
        runner.run_full_suite(cases)

    finally:
        stop_backend(backend)
        try:
            if mini:
                mini.disconnect()
                print("🔌 已断开微信连接")
        except Exception:
            pass


if __name__ == "__main__":
    main()
