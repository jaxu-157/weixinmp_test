"""模糊检测模块 - 基于 Laplacian 方差"""
import cv2
import numpy as np


def detect_blur(image: np.ndarray, threshold: float = 500.0) -> dict:
    """
    检测图像是否模糊。
    
    Args:
        image: BGR格式图像
        threshold: 模糊阈值，方差低于此值认为模糊
    
    Returns:
        {
            "is_blur": bool,
            "score": float,  # Laplacian方差，越低越模糊
            "threshold": float
        }
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    score = float(laplacian.var())

    return {
        "is_blur": score < threshold,
        "score": round(score, 2),
        "threshold": threshold,
    }
