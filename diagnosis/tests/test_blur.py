"""模糊检测断言测试集

测试目标：验证 Laplacian 方差法在不同模糊程度下的准确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from diagnose.blur import detect_blur


def generate_sharp_image(size=(300, 300)):
    """生成清晰图像：高频纹理"""
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    # 棋盘格纹理
    for i in range(0, size[0], 10):
        for j in range(0, size[1], 10):
            if (i // 10 + j // 10) % 2 == 0:
                img[i:i+10, j:j+10] = [200, 200, 200]
            else:
                img[i:i+10, j:j+10] = [50, 50, 50]
    return img


def generate_text_image(text="12345", size=(200, 100)):
    """生成含文字的图像"""
    img = np.ones((size[1], size[0], 3), dtype=np.uint8) * 255
    cv2.putText(img, text, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    return img


def apply_blur(image, ksize):
    """对图像应用高斯模糊"""
    return cv2.GaussianBlur(image, (ksize, ksize), 0)


class TestBlurDetection:
    """模糊检测测试集"""

    def test_sharp_image_not_blur(self):
        """清晰图像应判定为不模糊"""
        img = generate_sharp_image()
        result = detect_blur(img)
        assert result["is_blur"] is False, f"清晰图像被误判为模糊, score={result['score']}"
        assert result["score"] > 100, f"清晰图像分数过低: {result['score']}"
        return result

    def test_heavy_blur_detected(self):
        """重度模糊图像应判定为模糊"""
        img = generate_sharp_image()
        blurred = apply_blur(img, 21)
        result = detect_blur(blurred)
        assert result["is_blur"] is True, f"重度模糊未检测到, score={result['score']}"
        assert result["score"] < 50, f"重度模糊分数过高: {result['score']}"
        return result

    def test_light_blur_borderline(self):
        """轻度模糊应处于边界附近"""
        img = generate_sharp_image()
        blurred = apply_blur(img, 5)
        result = detect_blur(blurred)
        # 轻度模糊分数应降低但可能不触发阈值
        return result

    def test_medium_blur_detected(self):
        """中度模糊（ksize=11）应判定为模糊"""
        img = generate_sharp_image()
        blurred = apply_blur(img, 11)
        result = detect_blur(blurred)
        assert result["is_blur"] is True, f"中度模糊未检测到, score={result['score']}"
        return result

    def test_uniform_color_is_blur(self):
        """纯色图像应判定为模糊（无纹理）"""
        img = np.ones((200, 200, 3), dtype=np.uint8) * 128
        result = detect_blur(img)
        assert result["is_blur"] is True, f"纯色图像未判定为模糊, score={result['score']}"
        return result

    def test_gradient_image(self):
        """渐变图像：有方向但低频"""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        for i in range(200):
            img[i, :] = [int(i * 255 / 200)] * 3
        result = detect_blur(img)
        # 渐变图有一定频率但很低
        return result

    def test_noise_image_sharp(self):
        """随机噪声图像应判定为清晰（高频）"""
        img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        result = detect_blur(img)
        assert result["is_blur"] is False, f"噪声图像被误判为模糊, score={result['score']}"
        return result

    def test_text_image_sharp(self):
        """文字图像应判定为清晰"""
        img = generate_text_image("Hello")
        result = detect_blur(img)
        assert result["is_blur"] is False, f"文字图像被误判为模糊, score={result['score']}"
        return result

    def test_text_image_blurred(self):
        """模糊文字图像应判定为模糊"""
        img = generate_text_image("Hello")
        blurred = apply_blur(img, 15)
        result = detect_blur(blurred)
        assert result["is_blur"] is True, f"模糊文字未检测到, score={result['score']}"
        return result

    def test_custom_threshold(self):
        """自定义阈值应正确生效"""
        img = generate_sharp_image()
        blurred = apply_blur(img, 7)
        # 用很高的阈值，应该判定为模糊
        result_high = detect_blur(blurred, threshold=5000.0)
        assert result_high["is_blur"] is True
        # 用很低的阈值，应该判定为清晰
        result_low = detect_blur(blurred, threshold=1.0)
        assert result_low["is_blur"] is False
        return {"high_threshold": result_high, "low_threshold": result_low}

    def test_small_image(self):
        """极小图像（10x10）应正常处理"""
        img = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
        result = detect_blur(img)
        assert "score" in result
        return result

    def test_blur_score_monotonic(self):
        """模糊程度增加时，分数应单调递减"""
        img = generate_sharp_image()
        scores = []
        for ksize in [1, 3, 5, 7, 11, 15, 21]:
            if ksize == 1:
                blurred = img
            else:
                blurred = apply_blur(img, ksize)
            result = detect_blur(blurred)
            scores.append(result["score"])

        # 验证单调递减
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i-1], \
                f"分数非单调递减: ksize序列得分 {scores}"
        return {"scores": scores, "monotonic": True}


def run_blur_tests():
    """运行所有模糊检测测试"""
    suite = TestBlurDetection()
    tests = [
        ("清晰图像不模糊", suite.test_sharp_image_not_blur),
        ("重度模糊检测", suite.test_heavy_blur_detected),
        ("轻度模糊边界", suite.test_light_blur_borderline),
        ("中度模糊检测", suite.test_medium_blur_detected),
        ("纯色=模糊", suite.test_uniform_color_is_blur),
        ("渐变图像", suite.test_gradient_image),
        ("噪声=清晰", suite.test_noise_image_sharp),
        ("文字=清晰", suite.test_text_image_sharp),
        ("模糊文字检测", suite.test_text_image_blurred),
        ("自定义阈值", suite.test_custom_threshold),
        ("极小图像", suite.test_small_image),
        ("分数单调递减", suite.test_blur_score_monotonic),
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
    print("模糊检测断言测试集")
    print("=" * 60)
    summary = run_blur_tests()
    print(f"\n结果: {summary['passed']}/{summary['total']} 通过, {summary['failed']} 失败")
