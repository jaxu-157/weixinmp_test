import minium
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.diagnose_client import DiagnoseClient
from utils.screenshot_manager import ScreenshotManager

class TestFeedPage(minium.MiniTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diagnose_client = DiagnoseClient()
        cls.screenshot_manager = ScreenshotManager()
        
    def setUp(self):
        """每个测试用例开始前执行"""
        super().setUp()
        # 确保小程序在初始状态
        self.diagnose_client.activate_fault("normal")
        time.sleep(1)
        self.app.navigate_to("/pages/feed/index")
        time.sleep(2)  # 等待页面加载
    
    def test_blur_image_fault(self):
        """测试模糊图片故障"""
        print("开始测试: blur_image故障")
        
        # 1. 激活故障
        profile = "blur_image"
        result = self.diagnose_client.activate_fault(profile)
        print(f"激活故障结果: {result}")
        time.sleep(3)  # 等待故障生效
        
        # 2. 截图
        screenshot_path = self.screenshot_manager.get_screenshot_path(
            "test_blur_image", profile
        )
        self.app.screen_shot(screenshot_path)
        print(f"截图已保存: {screenshot_path}")
        
        # 3. 提交诊断
        result = self.diagnose_client.submit_diagnose(
            screenshot_path, "feed", profile
        )
        print(f"诊断结果: {result}")
        
        # 4. 验证结果
        success, message = self.diagnose_client.verify_diagnosis(
            result, "RenderBug"
        )
        
        # 5. 断言
        self.assertTrue(success, message)
        print(f"测试结果: {message}")
        
        # 6. 记录详细结果
        if result.get("code") == 0:
            data = result.get("data", {})
            print(f"详细诊断: {data}")
    
    def test_slow_api_fault(self):
        """测试接口延迟故障"""
        print("开始测试: slow_api故障")
        
        profile = "slow_api"
        self.diagnose_client.activate_fault(profile)
        time.sleep(5)  # 等待更长时间，因为接口慢
        
        screenshot_path = self.screenshot_manager.get_screenshot_path(
            "test_slow_api", profile
        )
        self.app.screen_shot(screenshot_path)
        
        result = self.diagnose_client.submit_diagnose(
            screenshot_path, "feed", profile
        )
        
        success, message = self.diagnose_client.verify_diagnosis(
            result, "PerformanceRisk"
        )
        
        self.assertTrue(success, message)
        print(f"测试结果: {message}")
    
    def test_memory_pressure_fault(self):
        """测试内存压力故障"""
        print("开始测试: memory_pressure故障")
        
        profile = "memory_pressure"
        self.diagnose_client.activate_fault(profile)
        time.sleep(3)
        
        # 模拟多次操作增加内存压力
        for i in range(5):
            self.page.scroll_to(100 * (i+1), 500)
            time.sleep(0.5)
        
        screenshot_path = self.screenshot_manager.get_screenshot_path(
            "test_memory_pressure", profile
        )
        self.app.screen_shot(screenshot_path)
        
        result = self.diagnose_client.submit_diagnose(
            screenshot_path, "feed", profile
        )
        
        success, message = self.diagnose_client.verify_diagnosis(
            result, "PerformanceRisk"
        )
        
        self.assertTrue(success, message)
        print(f"测试结果: {message}")