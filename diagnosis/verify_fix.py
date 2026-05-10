"""用真实截图验证修复后的视觉断言"""
import os, sys, glob, json
import cv2
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diagnose.triage import run_triage

base = r"d:\weixinmp_test\auto_test\reports\screenshots"

cases = [
    ("正常基线-图片流",    "normal",          "Pass"),
    ("模糊图片-图片流",    "blur_image",       "RenderBug"),
    ("接口延迟-图片流",    "slow_api",         "PerformanceRisk"),
    ("布局错位-布局页",    "layout_overlap",   "FunctionalFail"),
    ("正常基线-计数器",    "normal",           "Pass"),
    ("旧数据显示-计数器",  "stale_ui",         "FunctionalFail"),
    ("接口延迟-计数器",    "slow_api",         "PerformanceRisk"),
    ("混合故障-计数器",    "mixed_fault",      "Mixed"),
]

perf_map = {
    "normal": {"interactionMs": 100, "memoryWarningCount": 0},
    "blur_image": {"interactionMs": 100, "memoryWarningCount": 0},
    "slow_api": {"interactionMs": 900, "memoryWarningCount": 0},
    "layout_overlap": {"interactionMs": 100, "memoryWarningCount": 0},
    "stale_ui": {"interactionMs": 100, "memoryWarningCount": 0},
    "mixed_fault": {"interactionMs": 900, "memoryWarningCount": 1},
}

state_map = {
    ("normal", "counter"): {"visibleValue": 1, "expectedValue": 1},
    ("stale_ui", "counter"): {"visibleValue": 0, "expectedValue": 1},
    ("slow_api", "counter"): {"visibleValue": 1, "expectedValue": 1},
    ("mixed_fault", "counter"): {"visibleValue": 0, "expectedValue": 1},
    ("layout_overlap", "layout"): {"uiFlags": {"hasOverlap": True}},
}

# 找截图文件
files = glob.glob(os.path.join(base, "*012*.png"))
file_map = {}
for f in files:
    name = os.path.basename(f)
    for c_name, _, _ in cases:
        if c_name in name:
            file_map[c_name] = f

print(f"{'测试':16s} | {'期望':18s} | {'实际':18s} | {'blur_card':>10s} | {'edge':>6s} | {'结果'}")
print("-" * 95)

passed = 0
total = 0
for c_name, profile, expected in cases:
    if c_name not in file_map:
        print(f"{c_name:16s} | 截图未找到")
        continue
    
    data = np.fromfile(file_map[c_name], dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    _, buf = cv2.imencode(".png", img)
    
    page = "counter" if "计数器" in c_name else ("layout" if "布局" in c_name else "feed")
    state = state_map.get((profile, page), {})
    perf = perf_map.get(profile, {})
    
    result = run_triage(buf.tobytes(), page, profile, state, perf)
    verdict = result["verdict"]
    blur_card = result["visual"].get("blur_score", "N/A")
    edge = result["visual"].get("edge_density", "N/A")
    
    ok = verdict == expected
    total += 1
    if ok:
        passed += 1
    
    status = "✓" if ok else "✗"
    print(f"{c_name:16s} | {expected:18s} | {verdict:18s} | {blur_card:>10} | {edge:>6} | {status}")

print(f"\n结果: {passed}/{total} 通过")
