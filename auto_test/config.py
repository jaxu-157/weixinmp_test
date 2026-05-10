#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vision-Triage 项目配置文件
适用于 Minium 1.6.0
"""

import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 小程序项目路径 - 必须与 minium_config.json 中的 project_path 一致！
# 已修正：指向编译后的目录而非源码目录
MINI_PROJECT_PATH = r"C:\Users\17303\Desktop\2026spring\ruance_2026spring\work_dazuoye\filework\weixinmp_test\demo-uniapp\dist\dev\mp-weixin"

# 微信开发者工具路径
DEV_TOOL_PATH = r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"

# 诊断服务地址 - 已补充
DIAGNOSE_SERVICE_URL = "http://127.0.0.1:8900"

# 测试配置 - 此配置可能被测试用例通过 minium.Minium(config) 使用
# 确保其中的关键参数与 minium_config.json 匹配
# 已补充完整的配置字段
TEST_CONFIG = {
    "project_path": MINI_PROJECT_PATH,  # 确保这一行正确
    "dev_tool_path": DEV_TOOL_PATH,
    "test_port": 63987,  # 您的端口
    "appid": "wx90551d59d41885eb",  # 您的 AppID
    "debug_mode": "info",
    "enable_app_log": True,
    "auto_relaunch": True,
    "auto_quit_ide": False,
    "device_desktop": {
        "width": 375,
        "height": 667
    },
    "request_timeout": 30,
    "assert_capture": True
}

# 故障Profile映射表
FAULT_PROFILES = {
    "normal": "Pass",
    "slow_api": "PerformanceRisk",
    "blur_image": "RenderBug",
    "stale_ui": "FunctionalFail",
    "wrong_mapping": "FunctionalFail",
    "layout_overlap": "RenderBug",
    "memory_pressure": "PerformanceRisk",
    "mixed_fault": "Mixed"
}

# 页面路径映射
PAGE_PATHS = {
    "feed": "/pages/feed/index",
    "counter": "/pages/counter/index",
    "layout": "/pages/layout/index"
}