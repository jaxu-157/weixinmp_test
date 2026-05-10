"""生成模糊测试图片，供 blur_image 故障注入使用"""
import os
import cv2
import numpy as np

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

def generate_blurred_images(count=8, size=(400, 300)):
    """生成极度模糊的图片（Laplacian方差<50）"""
    for i in range(count):
        # 生成有内容的原图
        img = np.random.randint(80, 200, (size[1], size[0], 3), dtype=np.uint8)
        # 添加一些形状让它看起来像照片
        cv2.rectangle(img, (50, 50), (350, 250), (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255)), -1)
        cv2.circle(img, (200, 150), 80, (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255)), -1)
        
        # 施加极重模糊（kernel=51确保Laplacian方差极低）
        blurred = cv2.GaussianBlur(img, (51, 51), 0)
        blurred = cv2.GaussianBlur(blurred, (31, 31), 0)  # 双重模糊
        
        filepath = os.path.join(STATIC_DIR, f"blur_{i+1}.png")
        cv2.imwrite(filepath, blurred)
        
        # 验证
        from diagnose.blur import detect_blur
        result = detect_blur(blurred)
        print(f"  blur_{i+1}.png -> score={result['score']}, is_blur={result['is_blur']}")
    
    print(f"\n已生成 {count} 张模糊图片到 {STATIC_DIR}/")


if __name__ == "__main__":
    generate_blurred_images()
