"""分诊决策矩阵完整测试集

测试目标：验证三重断言融合的分诊决策在所有组合下输出正确 verdict
覆盖设计文档 10.2 节定义的全部决策规则
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from diagnose.triage import run_triage, _decide_verdict, PERF_THRESHOLD_MS


def make_image_bytes(img):
    """将 numpy 图像编码为 PNG bytes"""
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def normal_image():
    """正常图像：有纹理、有内容"""
    img = np.random.randint(50, 200, (300, 300, 3), dtype=np.uint8)
    cv2.putText(img, "OK", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 5)
    return img


def white_screen():
    """白屏图像"""
    return np.ones((300, 300, 3), dtype=np.uint8) * 255


def black_screen():
    """黑屏图像"""
    return np.zeros((300, 300, 3), dtype=np.uint8)


def blurry_image():
    """模糊图像"""
    img = normal_image()
    return cv2.GaussianBlur(img, (31, 31), 0)


class TestTriageDecisionMatrix:
    """分诊决策矩阵测试 - 验证所有 verdict 组合"""

    def test_all_pass(self):
        """F=Pass, P=Pass, V=Pass → Pass"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={"interactionMs": 200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "Pass", f"Expected Pass, got {result['verdict']}"
        assert result["functional"]["pass"] is True
        assert result["performance"]["pass"] is True
        assert result["visual"]["pass"] is True
        return result

    def test_performance_risk(self):
        """F=Pass, P=Fail, V=Pass → PerformanceRisk"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={"interactionMs": 1200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "PerformanceRisk", f"Expected PerformanceRisk, got {result['verdict']}"
        assert result["functional"]["pass"] is True
        assert result["performance"]["pass"] is False
        return result

    def test_performance_risk_memory(self):
        """内存告警也应触发 PerformanceRisk"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="feed",
            page_state={"visibleValue": 10, "expectedValue": 10},
            perf_data={"interactionMs": 300, "memoryWarningCount": 2},
        )
        assert result["verdict"] == "PerformanceRisk", f"Expected PerformanceRisk, got {result['verdict']}"
        assert "memory_warnings" in result["performance"]["reason"]
        return result

    def test_render_bug_white_screen(self):
        """F=Pass, P=Pass, V=Fail(白屏) → RenderBug"""
        result = run_triage(
            image_bytes=make_image_bytes(white_screen()),
            page_type="feed",
            page_state={"visibleValue": 10, "expectedValue": 10},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "RenderBug", f"Expected RenderBug, got {result['verdict']}"
        assert result["visual"]["black_white"] is True
        return result

    def test_render_bug_black_screen(self):
        """F=Pass, P=Pass, V=Fail(黑屏) → RenderBug"""
        result = run_triage(
            image_bytes=make_image_bytes(black_screen()),
            page_type="feed",
            page_state={"visibleValue": 10, "expectedValue": 10},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "RenderBug", f"Expected RenderBug, got {result['verdict']}"
        assert result["visual"]["black_white"] is True
        return result

    def test_render_bug_blur(self):
        """F=Pass, P=Pass, V=Fail(模糊) → RenderBug"""
        result = run_triage(
            image_bytes=make_image_bytes(blurry_image()),
            page_type="feed",
            page_state={"visibleValue": 10, "expectedValue": 10},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "RenderBug", f"Expected RenderBug, got {result['verdict']}"
        assert result["visual"]["is_blur"] is True
        return result

    def test_functional_fail(self):
        """F=Fail, P=Pass, V=Pass → FunctionalFail"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 1, "expectedValue": 5},
            perf_data={"interactionMs": 200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "FunctionalFail", f"Expected FunctionalFail, got {result['verdict']}"
        assert result["functional"]["pass"] is False
        assert "visible=1" in result["functional"]["reason"]
        return result

    def test_functional_fail_string_mismatch(self):
        """字符串值不匹配也应触发 FunctionalFail"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": "旧数据", "expectedValue": "新数据"},
            perf_data={"interactionMs": 200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "FunctionalFail", f"Expected FunctionalFail, got {result['verdict']}"
        return result

    def test_mixed_func_perf(self):
        """F=Fail, P=Fail, V=Pass → Mixed"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 1, "expectedValue": 5},
            perf_data={"interactionMs": 1500, "memoryWarningCount": 1},
        )
        assert result["verdict"] == "Mixed", f"Expected Mixed, got {result['verdict']}"
        assert "功能" in result["explanation"]
        assert "性能" in result["explanation"]
        return result

    def test_mixed_func_visual(self):
        """F=Fail, P=Pass, V=Fail → Mixed"""
        result = run_triage(
            image_bytes=make_image_bytes(white_screen()),
            page_type="counter",
            page_state={"visibleValue": 1, "expectedValue": 5},
            perf_data={"interactionMs": 200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "Mixed", f"Expected Mixed, got {result['verdict']}"
        return result

    def test_mixed_perf_visual(self):
        """F=Pass, P=Fail, V=Fail → Mixed"""
        result = run_triage(
            image_bytes=make_image_bytes(blurry_image()),
            page_type="feed",
            page_state={"visibleValue": 10, "expectedValue": 10},
            perf_data={"interactionMs": 1200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "Mixed", f"Expected Mixed, got {result['verdict']}"
        return result

    def test_mixed_all_fail(self):
        """F=Fail, P=Fail, V=Fail → Mixed"""
        result = run_triage(
            image_bytes=make_image_bytes(white_screen()),
            page_type="counter",
            page_state={"visibleValue": 0, "expectedValue": 5},
            perf_data={"interactionMs": 2000, "memoryWarningCount": 3},
        )
        assert result["verdict"] == "Mixed", f"Expected Mixed, got {result['verdict']}"
        return result


class TestTriageEdgeCases:
    """分诊边界条件测试"""

    def test_no_page_state(self):
        """无页面状态时，功能断言默认通过"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="feed",
            page_state={},
            perf_data={"interactionMs": 200, "memoryWarningCount": 0},
        )
        assert result["verdict"] == "Pass"
        assert result["functional"]["reason"] == "no_state_provided"
        return result

    def test_no_perf_data(self):
        """无性能数据时，性能断言默认通过"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="feed",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={},
        )
        assert result["verdict"] == "Pass"
        assert result["performance"]["reason"] == "no_perf_data"
        return result

    def test_perf_at_threshold(self):
        """交互延迟恰好等于阈值时应通过"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={"interactionMs": PERF_THRESHOLD_MS, "memoryWarningCount": 0},
        )
        assert result["performance"]["pass"] is True, \
            f"等于阈值({PERF_THRESHOLD_MS}ms)应通过"
        return result

    def test_perf_just_over_threshold(self):
        """交互延迟刚超阈值时应失败"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={"interactionMs": PERF_THRESHOLD_MS + 1, "memoryWarningCount": 0},
        )
        assert result["performance"]["pass"] is False, \
            f"超过阈值({PERF_THRESHOLD_MS+1}ms)应失败"
        return result

    def test_zero_interaction_ms(self):
        """0ms延迟应通过"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": 5, "expectedValue": 5},
            perf_data={"interactionMs": 0, "memoryWarningCount": 0},
        )
        assert result["performance"]["pass"] is True
        return result

    def test_invalid_image(self):
        """无效图像数据应返回 Unknown"""
        result = run_triage(
            image_bytes=b"not_an_image",
            page_type="feed",
        )
        assert result["verdict"] == "Unknown"
        return result

    def test_same_visible_expected_types(self):
        """相同值不同类型（int vs str）应视为不匹配"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": "5", "expectedValue": 5},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        # Python中 "5" != 5
        assert result["verdict"] == "FunctionalFail"
        return result

    def test_null_values_in_state(self):
        """visibleValue或expectedValue为None时应默认通过"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_type="counter",
            page_state={"visibleValue": None, "expectedValue": 5},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert result["functional"]["pass"] is True
        assert result["functional"]["reason"] == "values_not_applicable"
        return result


class TestTriageExplanation:
    """分诊解释输出质量测试"""

    def test_pass_explanation(self):
        """Pass 应有明确解释"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_state={"visibleValue": 1, "expectedValue": 1},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert result["explanation"] != ""
        assert "通过" in result["explanation"]
        return result

    def test_performance_explanation_has_ms(self):
        """PerformanceRisk 解释应包含具体延迟数值"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_state={"visibleValue": 1, "expectedValue": 1},
            perf_data={"interactionMs": 1500, "memoryWarningCount": 0},
        )
        assert "1500" in result["explanation"], f"解释缺少延迟数值: {result['explanation']}"
        return result

    def test_functional_explanation_has_values(self):
        """FunctionalFail 解释应包含期望和实际值"""
        result = run_triage(
            image_bytes=make_image_bytes(normal_image()),
            page_state={"visibleValue": 1, "expectedValue": 99},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert "1" in result["explanation"] and "99" in result["explanation"], \
            f"解释缺少具体值: {result['explanation']}"
        return result

    def test_visual_explanation_has_type(self):
        """RenderBug 解释应说明具体视觉异常类型"""
        result = run_triage(
            image_bytes=make_image_bytes(white_screen()),
            page_state={"visibleValue": 1, "expectedValue": 1},
            perf_data={"interactionMs": 100, "memoryWarningCount": 0},
        )
        assert "白屏" in result["explanation"] or "黑" in result["explanation"], \
            f"解释缺少异常类型: {result['explanation']}"
        return result


def run_triage_tests():
    """运行所有分诊测试"""
    suites = [
        ("决策矩阵", TestTriageDecisionMatrix()),
        ("边界条件", TestTriageEdgeCases()),
        ("解释质量", TestTriageExplanation()),
    ]

    total_passed = 0
    total_failed = 0
    all_results = []

    for suite_name, suite in suites:
        print(f"\n  [{suite_name}]")
        methods = [m for m in dir(suite) if m.startswith("test_")]
        for method_name in sorted(methods):
            test_fn = getattr(suite, method_name)
            display_name = method_name.replace("test_", "").replace("_", " ")
            try:
                result = test_fn()
                total_passed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "PASS"})
                print(f"    ✓ {display_name}")
            except AssertionError as e:
                total_failed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "FAIL", "error": str(e)})
                print(f"    ✗ {display_name}: {e}")
            except Exception as e:
                total_failed += 1
                all_results.append({"name": f"{suite_name}/{display_name}", "status": "ERROR", "error": str(e)})
                print(f"    ! {display_name}: {e}")

    total = total_passed + total_failed
    return {"passed": total_passed, "failed": total_failed, "total": total, "results": all_results}


if __name__ == "__main__":
    print("=" * 60)
    print("分诊决策矩阵完整测试集")
    print("=" * 60)
    summary = run_triage_tests()
    print(f"\n结果: {summary['passed']}/{summary['total']} 通过, {summary['failed']} 失败")
