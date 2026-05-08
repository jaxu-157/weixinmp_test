"""黑/白屏检测模块"""
import cv2
import numpy as np


def detect_blank_screen(image: np.ndarray, black_threshold: int = 30, white_threshold: int = 225, ratio: float = 0.95) -> dict:
    """
    检测图像是否为黑屏或白屏。
    
    Args:
        image: BGR格式图像
        black_threshold: 灰度低于此值的像素视为"黑"
        white_threshold: 灰度高于此值的像素视为"白"
        ratio: 当黑/白像素占比超过此值时判定为黑/白屏
    
    Returns:
        {
            "is_black": bool,
            "is_white": bool,
            "black_ratio": float,
            "white_ratio": float,
            "mean_brightness": float
        }
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    total_pixels = gray.size

    black_pixels = int(np.sum(gray < black_threshold))
    white_pixels = int(np.sum(gray > white_threshold))

    black_ratio = black_pixels / total_pixels
    white_ratio = white_pixels / total_pixels
    mean_brightness = float(np.mean(gray))

    return {
        "is_black": black_ratio >= ratio,
        "is_white": white_ratio >= ratio,
        "black_ratio": round(black_ratio, 4),
        "white_ratio": round(white_ratio, 4),
        "mean_brightness": round(mean_brightness, 2),
    }
