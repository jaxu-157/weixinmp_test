import os
from datetime import datetime

class ScreenshotManager:
    def __init__(self, base_dir="./reports/screenshots"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
    
    def get_screenshot_path(self, test_name, profile):
        """生成截图文件路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{test_name}_{profile}_{timestamp}.png"
        return os.path.join(self.base_dir, filename)
    
    def cleanup_old_screenshots(self, keep_days=7):
        """清理旧截图"""
        import time
        current_time = time.time()
        for filename in os.listdir(self.base_dir):
            filepath = os.path.join(self.base_dir, filename)
            if os.path.isfile(filepath):
                file_time = os.path.getmtime(filepath)
                if (current_time - file_time) > (keep_days * 24 * 3600):
                    os.remove(filepath)
                    print(f"已删除旧截图: {filename}")