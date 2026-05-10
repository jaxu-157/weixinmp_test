#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minium 1.6.0 适配版 - 测试运行器
"""
import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime

def load_config(config_path):
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(config_path, 'r', encoding='gbk') as f:
            return json.load(f)

def check_diagnose_service():
    """检查诊断后端服务"""
    print("[1/4] 检查诊断后端服务...")
    try:
        response = requests.get("http://127.0.0.1:8900/fault/status", timeout=5)
        if response.status_code == 200:
            print("   ✅ 诊断服务运行正常")
            return True
        else:
            print(f"   ❌ 诊断服务返回异常状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 无法连接到诊断服务: {e}")
        print("      请确保已在 diagnosis/ 目录启动: python -m uvicorn app:app --host 127.0.0.1 --port 8900")
        return False

def check_minium_installed():
    """检查 Minium 安装"""
    print("[2/4] 检查 Minium 环境...")
    try:
        result = subprocess.run([sys.executable, "-c", "import minium; print(minium.__version__)"],
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"   ✅ Minium 已安装 (版本: {version})")
            return True
        else:
            print("   ❌ Minium 未正确安装")
            return False
    except Exception as e:
        print(f"   ❌ 检查 Minium 时出错: {e}")
        return False

def run_minitest_suite(config_path, test_module, generate_report=True):
    """通过 minitest 命令行运行测试套件"""
    print(f"[3/4] 通过 minitest 运行测试模块: {test_module}")
    
    # 使用 minitest 命令（不是 python -m minitest）
    cmd = ["minitest", "-c", config_path, "-m", test_module]
    if generate_report:
        cmd.append("-g")
    
    print(f"   执行命令: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True, 
                                  encoding='utf-8',
                                  bufsize=1,
                                  universal_newlines=True)
        
        # 实时输出 stdout
        for line in iter(process.stdout.readline, ''):
            print(f"    {line.rstrip()}")
        process.stdout.close()
        
        # 等待进程结束
        return_code = process.wait()
        
        # 输出 stderr（如果有）
        stderr_output = process.stderr.read()
        if stderr_output:
            print("\n   ⚠️  minitest 错误输出:")
            print(f"    {stderr_output}")
        
        print(f"\n   minitest 进程退出码: {return_code}")
        return return_code == 0
        
    except FileNotFoundError:
        print("   ❌ 找不到 minitest 命令，请确保 Minium 已正确安装")
        print("      尝试检查: where minitest 或 which minitest")
        return False
    except Exception as e:
        print(f"   ❌ 运行 minitest 时出错: {e}")
        return False

def generate_custom_report(test_module, success):
    """生成自定义测试摘要报告"""
    print(f"[4/4] 生成测试执行摘要...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = "./reports"
    os.makedirs(report_dir, exist_ok=True)
    
    summary_file = os.path.join(report_dir, f"test_summary_{timestamp}.json")
    
    summary = {
        "project": "Vision-Triage",
        "test_module": test_module,
        "timestamp": timestamp,
        "success": success,
        "diagnose_service_available": check_diagnose_service() if not success else True,
        "next_steps": [
            "查看 minitest 生成的详细 HTML 报告（在 reports/ 目录下）",
            "查看截图文件（在 reports/screenshots/ 目录下）",
            "检查后端日志以确认 /diagnose 接口调用情况"
        ]
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"   测试摘要已保存: {summary_file}")
    
    # 尝试定位 minitest 生成的 HTML 报告
    try:
        html_reports = [f for f in os.listdir(report_dir) if f.endswith('.html') and 'minitest' in f.lower()]
        if html_reports:
            latest_report = max(html_reports, key=lambda x: os.path.getmtime(os.path.join(report_dir, x)))
            print(f"   Minitest HTML 报告: {os.path.join(report_dir, latest_report)}")
    except:
        pass  # 忽略查找报告时的错误

def main():
    """主函数"""
    print("=" * 70)
    print("Vision-Triage 自动化测试启动器 (Minium 1.6.0 适配版)")
    print("=" * 70)
    
    # 1. 加载配置
    config_path = "../minium_config.json"
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        print("   请确保在项目根目录存在 minium_config.json")
        return 1
    
    config = load_config(config_path)
    print(f"📁 项目路径: {config.get('project_path', '未配置')}")
    print(f"🔌 开发者工具端口: {config.get('test_port')}")
    print(f"🆔 小程序 AppID: {config.get('appid')}")
    
    # 2. 前置检查
    if not check_minium_installed():
        return 1
    
    if not check_diagnose_service():
        print("\n⚠️  诊断服务未就绪，测试可能无法完整执行。")
        print("   是否继续？(y/n): ", end="")
        choice = input().strip().lower()
        if choice != 'y':
            print("测试已取消。")
            return 1
    
    # 3. 运行测试
    print("\n" + "=" * 70)
    print("开始执行自动化测试...")
    print("=" * 70)
    
    # 默认运行 feed 页面测试，可通过命令行参数扩展
    test_module = "test_cases.test_feed_page"
    
    success = run_minitest_suite(config_path, test_module, generate_report=True)
    
    # 4. 生成报告
    print("\n" + "=" * 70)
    if success:
        print("✅ 测试套件执行完成")
    else:
        print("❌ 测试套件执行失败或部分失败")
    print("=" * 70)
    
    generate_custom_report(test_module, success)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())