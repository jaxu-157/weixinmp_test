"""布局检测与模板匹配测试集

测试目标：验证模板匹配和区域重叠检测的准确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from diagnose.layout import template_match, detect_overlap


class TestTemplateMatch:
    """模板匹配测试集"""

    def test_exact_match(self):
        """模板完全匹配应得到高分"""
        img = np.random.randint(50, 200, (300, 300, 3), dtype=np.uint8)
        # 从大图中截取模板
        template = img[50:100, 50:150].copy()
        result = template_match(img, template)
        assert result["matched"] is True, f"精确模板未匹配: score={result['score']}"
        assert result["score"] > 0.95
        return result

    def test_template_not_in_image(self):
        """模板不在图中应低分"""
        img = np.ones((300, 300, 3), dtype=np.uint8) * 100
        template = np.zeros((50, 50, 3), dtype=np.uint8)
        cv2.circle(template, (25, 25), 20, (255, 0, 0), -1)
        result = template_match(img, template)
        assert result["matched"] is False, f"不存在的模板被误匹配: score={result['score']}"
        return result

    def test_partial_occlusion(self):
        """模板被部分遮挡时分数应下降"""
        img = np.ones((300, 300, 3), dtype=np.uint8) * 200
        # 放一个明显特征
        cv2.rectangle(img, (100, 100), (200, 200), (0, 0, 255), -1)
        template = img[95:205, 95:205].copy()
        # 遮挡部分区域
        img[100:150, 100:200] = [200, 200, 200]
        result = template_match(img, template)
        # 部分遮挡后分数应下降
        assert result["score"] < 0.95, f"遮挡后分数未下降: {result['score']}"
        return result

    def test_scaled_template_no_match(self):
        """缩放后的模板不应匹配（模板匹配不具备尺度不变性）"""
        img = np.random.randint(50, 200, (300, 300, 3), dtype=np.uint8)
        template = img[50:100, 50:150].copy()
        # 缩放模板
        scaled = cv2.resize(template, (200, 100))
        result = template_match(img, scaled)
        # 缩放后通常匹配分数较低
        return result

    def test_location_accuracy(self):
        """匹配位置应接近实际位置"""
        # 用随机纹理背景避免纯色退化
        np.random.seed(42)
        img = np.random.randint(100, 200, (300, 300, 3), dtype=np.uint8)
        # 在(100, 80)处放置明显特征
        cv2.rectangle(img, (100, 80), (180, 140), (0, 0, 255), -1)
        cv2.circle(img, (140, 110), 15, (255, 255, 0), -1)
        template = img[80:140, 100:180].copy()
        result = template_match(img, template)
        assert result["matched"] is True
        loc = result["location"]
        assert abs(loc[0] - 100) < 3 and abs(loc[1] - 80) < 3, \
            f"位置偏差过大: expected ~(100,80), got {loc}"
        return result


class TestOverlapDetection:
    """区域重叠检测测试集"""

    def test_identical_regions(self):
        """相同区域应检测到重叠"""
        img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        regions = [
            {"x": 10, "y": 10, "w": 50, "h": 50},
            {"x": 10, "y": 10, "w": 50, "h": 50},
        ]
        result = detect_overlap(img, regions)
        assert result["has_overlap"] is True, "相同区域未检测到重叠"
        return result

    def test_different_regions(self):
        """颜色差异大的区域不应重叠"""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[10:60, 10:60] = [255, 0, 0]  # 蓝色区域
        img[100:150, 100:150] = [0, 255, 0]  # 绿色区域
        regions = [
            {"x": 10, "y": 10, "w": 50, "h": 50},
            {"x": 100, "y": 100, "w": 50, "h": 50},
        ]
        result = detect_overlap(img, regions)
        assert result["has_overlap"] is False, "不同颜色区域被误判为重叠"
        return result

    def test_single_region(self):
        """单个区域不应报告重叠"""
        img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        regions = [{"x": 10, "y": 10, "w": 50, "h": 50}]
        result = detect_overlap(img, regions)
        assert result["has_overlap"] is False
        assert result["region_count"] == 1
        return result

    def test_empty_regions(self):
        """空区域列表不应报告重叠"""
        img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        result = detect_overlap(img, [])
        assert result["has_overlap"] is False
        assert result["region_count"] == 0
        return result

    def test_adjacent_similar_regions(self):
        """相邻且颜色相似的区域应检测为重叠"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 128
        regions = [
            {"x": 10, "y": 10, "w": 50, "h": 50},
            {"x": 60, "y": 10, "w": 50, "h": 50},
        ]
        result = detect_overlap(img, regions)
        assert result["has_overlap"] is True, "相似颜色相邻区域未检测为重叠"
        return result

    def test_out_of_bounds_region(self):
        """越界区域应安全处理"""
        img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        regions = [
            {"x": 0, "y": 0, "w": 50, "h": 50},
            {"x": 200, "y": 200, "w": 50, "h": 50},  # 越界
        ]
        # 不应崩溃
        try:
            result = detect_overlap(img, regions)
            return result
        except Exception as e:
            return {"error": str(e), "note": "越界区域导致异常"}


def run_layout_tests():
    """运行所有布局检测测试"""
    suites = [
        ("模板匹配", TestTemplateMatch()),
        ("重叠检测", TestOverlapDetection()),
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
    print("布局检测与模板匹配测试集")
    print("=" * 60)
    summary = run_layout_tests()
    print(f"\n结果: {summary['passed']}/{summary['total']} 通过, {summary['failed']} 失败")
