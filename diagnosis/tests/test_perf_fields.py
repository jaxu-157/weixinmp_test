"""回归测试：性能断言必须同时兼容 camelCase 与 snake_case 字段（PROJECT_REVIEW P0）。

历史 bug：driver/devtools 路径传 snake_case（interaction_ms/memory_warnings），
而 triage 只读 camelCase（interactionMs/memoryWarningCount），导致性能故障被静默当 0。
"""
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from diagnose.triage import _run_performance_assertions  # noqa: E402


def run_perf_field_tests():
    results = []

    def check(name, perf_data, expect_pass):
        r = _run_performance_assertions(perf_data)
        ok = (r["pass"] == expect_pass)
        results.append({"name": name, "status": "PASS" if ok else "FAIL",
                        "detail": f"pass={r['pass']} expect={expect_pass} reason={r.get('reason')}"})
        return ok

    # 慢交互：两套字段都应判失败
    check("camel_slow_fail", {"interactionMs": 900, "memoryWarningCount": 0}, False)
    check("snake_slow_fail", {"interaction_ms": 900, "memory_warnings": 0}, False)
    # 内存告警：两套字段都应判失败
    check("camel_mem_fail", {"interactionMs": 100, "memoryWarningCount": 1}, False)
    check("snake_mem_fail", {"interaction_ms": 100, "memory_warnings": 1}, False)
    # 正常：两套字段都应通过
    check("camel_ok", {"interactionMs": 100, "memoryWarningCount": 0}, True)
    check("snake_ok", {"interaction_ms": 100, "memory_warnings": 0}, True)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = len(results) - passed
    for r in results:
        mark = "✓" if r["status"] == "PASS" else "✗"
        print(f"    {mark} {r['name']}: {r['detail']}")
    return {"passed": passed, "failed": failed, "total": len(results), "results": results}


if __name__ == "__main__":
    print("▶ 性能字段兼容性回归（camelCase + snake_case）")
    s = run_perf_field_tests()
    print(f"  {s['passed']}/{s['total']} passed")
    sys.exit(0 if s["failed"] == 0 else 1)
