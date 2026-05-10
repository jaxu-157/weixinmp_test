"""分析截图的模糊分数差异"""
import cv2
import numpy as np
import sys
import glob
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diagnose.blur import detect_blur

base = r"d:\weixinmp_test\auto_test\reports\screenshots"
files = glob.glob(os.path.join(base, "*012*.png"))

print(f"{'截图':16s} | {'全图score':>10s} | {'ROI score':>10s} | {'卡片score':>10s} | {'边缘密度':>8s}")
print("-" * 80)

for f in sorted(files):
    name = os.path.basename(f)
    data = np.fromfile(f, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        print(f"{name}: READ FAILED")
        continue

    h, w = img.shape[:2]
    roi = img[int(h * 0.15):int(h * 0.85), :]
    card_roi = img[int(h * 0.06):int(h * 0.32), int(w * 0.02):int(w * 0.48)]

    edges = cv2.Canny(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), 50, 150)
    edge_ratio = np.sum(edges > 0) / edges.size

    r_full = detect_blur(img)
    r_roi = detect_blur(roi)
    r_card = detect_blur(card_roi)

    short = name[:20]
    print(f"{short:20s} | {r_full['score']:10.1f} | {r_roi['score']:10.1f} | {r_card['score']:10.1f} | {edge_ratio:.4f}")
