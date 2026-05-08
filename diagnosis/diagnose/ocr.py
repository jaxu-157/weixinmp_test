"""OCR 文字识别模块 - 基于 PaddleOCR"""
import numpy as np

_ocr_instance = None


def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_instance = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        except ImportError:
            _ocr_instance = None
    return _ocr_instance


def extract_text(image: np.ndarray) -> dict:
    """
    从图像中提取文字。
    
    Args:
        image: BGR格式图像
    
    Returns:
        {
            "texts": list[str],
            "boxes": list,
            "confidences": list[float],
            "full_text": str
        }
    """
    ocr = _get_ocr()
    if ocr is None:
        return {
            "texts": [],
            "boxes": [],
            "confidences": [],
            "full_text": "",
            "error": "PaddleOCR not available",
        }

    results = ocr.ocr(image, cls=True)

    texts = []
    boxes = []
    confidences = []

    if results and results[0]:
        for line in results[0]:
            box = line[0]
            text = line[1][0]
            conf = line[1][1]
            texts.append(text)
            boxes.append(box)
            confidences.append(round(conf, 4))

    return {
        "texts": texts,
        "boxes": boxes,
        "confidences": confidences,
        "full_text": " ".join(texts),
    }


def verify_text(image: np.ndarray, expected: str) -> dict:
    """
    验证图像中是否包含预期文本。
    
    Args:
        image: BGR格式图像
        expected: 预期文本
    
    Returns:
        {
            "found": bool,
            "expected": str,
            "ocr_text": str,
            "match_ratio": float
        }
    """
    result = extract_text(image)
    full_text = result["full_text"]

    found = expected in full_text

    # 简单匹配率
    if not full_text:
        match_ratio = 0.0
    else:
        common = sum(1 for c in expected if c in full_text)
        match_ratio = common / max(len(expected), 1)

    return {
        "found": found,
        "expected": expected,
        "ocr_text": full_text,
        "match_ratio": round(match_ratio, 4),
    }
