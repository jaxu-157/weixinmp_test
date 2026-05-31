"""Vision-Triage 全量测试运行器

运行所有断言测试集，汇总结果，生成报告
"""
import sys
import os
import json
import time

# Windows 默认 GBK 控制台无法输出 ▶ 等符号会崩（PROJECT_REVIEW P1）。强制 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_blur import run_blur_tests
from tests.test_screen import run_screen_tests
from tests.test_layout import run_layout_tests
from tests.test_triage import run_triage_tests
from tests.test_api import run_api_tests
from tests.test_perf_fields import run_perf_field_tests


def run_all():
    """运行全部测试并生成报告"""
    start_time = time.time()

    print("=" * 70)
    print("  Vision-Triage 三重断言验证测试集")
    print("  功能断言 | 性能断言 | 视觉断言")
    print("=" * 70)

    all_summaries = {}

    # 1. 视觉断言 - 模糊检测
    print("\n" + "─" * 70)
    print("▶ 视觉断言：模糊检测")
    print("─" * 70)
    all_summaries["blur"] = run_blur_tests()

    # 2. 视觉断言 - 黑/白屏检测
    print("\n" + "─" * 70)
    print("▶ 视觉断言：黑/白屏检测")
    print("─" * 70)
    all_summaries["screen"] = run_screen_tests()

    # 3. 视觉断言 - 布局/模板匹配
    print("\n" + "─" * 70)
    print("▶ 视觉断言：布局与模板匹配")
    print("─" * 70)
    all_summaries["layout"] = run_layout_tests()

    # 4. 分诊决策矩阵（三重断言融合）
    print("\n" + "─" * 70)
    print("▶ 三重断言融合：分诊决策矩阵")
    print("─" * 70)
    all_summaries["triage"] = run_triage_tests()

    # 5. API 集成测试
    print("\n" + "─" * 70)
    print("▶ API 集成测试")
    print("─" * 70)
    all_summaries["api"] = run_api_tests()

    # 6. 性能字段兼容性回归（camelCase + snake_case）
    print("\n" + "─" * 70)
    print("▶ 性能字段兼容性回归")
    print("─" * 70)
    all_summaries["perf_fields"] = run_perf_field_tests()

    elapsed = time.time() - start_time

    # 汇总
    print("\n" + "=" * 70)
    print("  测试报告汇总")
    print("=" * 70)

    total_passed = 0
    total_failed = 0
    total_all = 0

    for name, summary in all_summaries.items():
        status = "✓" if summary["failed"] == 0 else "✗"
        print(f"  {status} {name:12s} | 通过: {summary['passed']:3d} | 失败: {summary['failed']:3d} | 总计: {summary['total']:3d}")
        total_passed += summary["passed"]
        total_failed += summary["failed"]
        total_all += summary["total"]

    print("─" * 70)
    print(f"  {'✓' if total_failed == 0 else '✗'} 总计        | 通过: {total_passed:3d} | 失败: {total_failed:3d} | 总计: {total_all:3d}")
    print(f"  耗时: {elapsed:.2f}s")
    print(f"  通过率: {total_passed/total_all*100:.1f}%")
    print("=" * 70)

    # 保存报告
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 2),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_tests": total_all,
        "pass_rate": round(total_passed / total_all * 100, 1),
        "suites": {},
    }
    for name, summary in all_summaries.items():
        report["suites"][name] = {
            "passed": summary["passed"],
            "failed": summary["failed"],
            "total": summary["total"],
            "failures": [r for r in summary["results"] if r["status"] != "PASS"],
        }

    report_path = os.path.join(os.path.dirname(__file__), "..", "test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {os.path.abspath(report_path)}")

    return total_failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
