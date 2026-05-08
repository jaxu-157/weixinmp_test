"""布局/模板匹配检测模块"""
import cv2
import numpy as np


def template_match(image: np.ndarray, template: np.ndarray, threshold: float = 0.8) -> dict:
    """
    在图像中匹配模板，用于检测关键区域是否存在。
    
    Args:
        image: BGR格式大图
        template: BGR格式模板图
        threshold: 匹配阈值
    
    Returns:
        {
            "matched": bool,
            "score": float,
            "location": tuple or None,
            "threshold": float
        }
    """
    img_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    result = cv2.matchTemplate(img_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    return {
        "matched": max_val >= threshold,
        "score": round(float(max_val), 4),
        "location": max_loc if max_val >= threshold else None,
        "threshold": threshold,
    }


def detect_overlap(image: np.ndarray, regions: list) -> dict:
    """
    简单检测指定区域是否存在重叠（基于颜色直方图相似度）。
    
    Args:
        image: BGR格式图像
        regions: 区域列表 [{"x": int, "y": int, "w": int, "h": int}, ...]
    
    Returns:
        {
            "has_overlap": bool,
            "overlap_pairs": list,
            "region_count": int
        }
    """
    if len(regions) < 2:
        return {"has_overlap": False, "overlap_pairs": [], "region_count": len(regions)}

    histograms = []
    for r in regions:
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        roi = image[y:y+h, x:x+w]
        if roi.size == 0:
            continue
        hist = cv2.calcHist([roi], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        histograms.append(hist)

    overlap_pairs = []
    for i in range(len(histograms)):
        for j in range(i + 1, len(histograms)):
            sim = cv2.compareHist(histograms[i], histograms[j], cv2.HISTCMP_CORREL)
            if sim > 0.9:
                overlap_pairs.append((i, j, round(float(sim), 4)))

    return {
        "has_overlap": len(overlap_pairs) > 0,
        "overlap_pairs": overlap_pairs,
        "region_count": len(regions),
    }
