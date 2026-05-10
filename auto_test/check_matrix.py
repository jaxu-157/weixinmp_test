"""检查矩阵用例生成"""
import sys
sys.path.insert(0, '.')
from auto_test_runner import VisionTriageAutoTester

t = VisionTriageAutoTester.__new__(VisionTriageAutoTester)
suite = t._build_test_suite_from_matrix()
print(f"有效用例: {len(suite)}")
print(f"{'页面':8s} | {'Profile':18s} | 期望Verdict")
print("-" * 50)
for c in suite:
    print(f"{c['page']:8s} | {c['profile']:18s} | {c['expected']}")
