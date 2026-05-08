"""黑/白屏检测断言测试集

测试目标：验证黑屏/白屏在不同比例和亮度下的检测准确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from diagnose.screen import detect_blank_screen


class TestScreenDetection:
    """黑/白屏检测测试集"""

    def test_pure_white(self):
        """纯白图像应判定为白屏"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        result = detect_blank_screen(img)
        assert result["is_white"] is True, f"纯白未检测为白屏: {result}"
        assert result["is_black"] is False
        assert result["white_ratio"] == 1.0
        return result

    def test_pure_black(self):
        """纯黑图像应判定为黑屏"""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        result = detect_blank_screen(img)
        assert result["is_black"] is True, f"纯黑未检测为黑屏: {result}"
        assert result["is_white"] is False
        assert result["black_ratio"] == 1.0
        return result

    def test_mostly_white_96(self):
        """96%白+4%其他应判定为白屏"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        # 添加4%的非白区域
        img[0:8, :] = [100, 100, 100]
        result = detect_blank_screen(img)
        assert result["is_white"] is True, f"96%白未检测为白屏: ratio={result['white_ratio']}"
        return result

    def test_mostly_white_90(self):
        """90%白+10%其他不应判定为白屏（低于95%阈值）"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        img[0:20, :] = [100, 100, 100]
        result = detect_blank_screen(img)
        assert result["is_white"] is False, f"90%白被误判为白屏: ratio={result['white_ratio']}"
        return result

    def test_mostly_black_96(self):
        """96%黑+4%其他应判定为黑屏"""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[0:8, :] = [200, 200, 200]
        result = detect_blank_screen(img)
        assert result["is_black"] is True, f"96%黑未检测为黑屏: ratio={result['black_ratio']}"
        return result

    def test_normal_image_not_blank(self):
        """正常图像不应判定为黑屏或白屏"""
        img = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)
        result = detect_blank_screen(img)
        assert result["is_black"] is False, "正常图像被误判为黑屏"
        assert result["is_white"] is False, "正常图像被误判为白屏"
        return result

    def test_gray_image_not_blank(self):
        """中灰图像不应判定为黑或白"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 128
        result = detect_blank_screen(img)
        assert result["is_black"] is False
        assert result["is_white"] is False
        assert abs(result["mean_brightness"] - 128) < 2
        return result

    def test_dark_ui_not_black(self):
        """暗色 UI（深色主题）不应误判为黑屏"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 40
        # 添加一些 UI 元素
        cv2.rectangle(img, (20, 20), (180, 40), (200, 200, 200), -1)
        cv2.rectangle(img, (20, 60), (180, 80), (100, 100, 200), -1)
        cv2.rectangle(img, (20, 100), (100, 120), (150, 150, 150), -1)
        result = detect_blank_screen(img)
        assert result["is_black"] is False, f"暗色UI被误判为黑屏: ratio={result['black_ratio']}"
        return result

    def test_light_ui_not_white(self):
        """浅色 UI 页面不应误判为白屏"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 245
        # 添加一些 UI 元素
        cv2.rectangle(img, (10, 10), (190, 30), (50, 50, 50), -1)
        cv2.putText(img, "Hello", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        cv2.rectangle(img, (10, 90), (190, 110), (100, 150, 200), -1)
        result = detect_blank_screen(img)
        assert result["is_white"] is False, f"浅色UI被误判为白屏: ratio={result['white_ratio']}"
        return result

    def test_white_with_status_bar(self):
        """白屏+顶部状态栏：仍应判定为白屏（状态栏面积小）"""
        img = np.ones((400, 300, 3), dtype=np.uint8) * 255
        # 顶部状态栏（约5%面积）
        img[0:20, :] = [30, 30, 30]
        result = detect_blank_screen(img)
        assert result["is_white"] is True, f"白屏+状态栏未检测: ratio={result['white_ratio']}"
        return result

    def test_custom_thresholds(self):
        """自定义阈值应正确生效"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 200
        # 默认不是白屏
        result_default = detect_blank_screen(img)
        assert result_default["is_white"] is False
        # 降低白屏阈值到180，应该判为白屏
        result_custom = detect_blank_screen(img, white_threshold=180)
        assert result_custom["is_white"] is True
        return {"default": result_default, "custom": result_custom}

    def test_mean_brightness_accuracy(self):
        """亮度均值应准确"""
        # 全128灰
        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        result = detect_blank_screen(img)
        assert abs(result["mean_brightness"] - 128) < 1
        # 全0黑
        img2 = np.zeros((100, 100, 3), dtype=np.uint8)
        result2 = detect_blank_screen(img2)
        assert result2["mean_brightness"] == 0
        return result


def run_screen_tests():
    """运行所有黑/白屏检测测试"""
    suite = TestScreenDetection()
    tests = [
        ("纯白=白屏", suite.test_pure_white),
        ("纯黑=黑屏", suite.test_pure_black),
        ("96%白=白屏", suite.test_mostly_white_96),
        ("90%白≠白屏", suite.test_mostly_white_90),
        ("96%黑=黑屏", suite.test_mostly_black_96),
        ("正常图像≠空屏", suite.test_normal_image_not_blank),
        ("中灰≠空屏", suite.test_gray_image_not_blank),
        ("暗色UI≠黑屏", suite.test_dark_ui_not_black),
        ("浅色UI≠白屏", suite.test_light_ui_not_white),
        ("白屏+状态栏=白屏", suite.test_white_with_status_bar),
        ("自定义阈值", suite.test_custom_thresholds),
        ("亮度均值准确", suite.test_mean_brightness_accuracy),
    ]

    passed = 0
    failed = 0
    results = []

    for name, test_fn in tests:
        try:
            result = test_fn()
            passed += 1
            results.append({"name": name, "status": "PASS", "detail": result})
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            results.append({"name": name, "status": "FAIL", "error": str(e)})
            print(f"  ✗ {name}: {e}")
        except Exception as e:
            failed += 1
            results.append({"name": name, "status": "ERROR", "error": str(e)})
            print(f"  ! {name}: {e}")

    return {"passed": passed, "failed": failed, "total": len(tests), "results": results}


if __name__ == "__main__":
    print("=" * 60)
    print("黑/白屏检测断言测试集")
    print("=" * 60)
    summary = run_screen_tests()
    print(f"\n结果: {summary['passed']}/{summary['total']} 通过, {summary['failed']} 失败")
