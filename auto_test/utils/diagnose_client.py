import requests
import json
import os
from datetime import datetime

class DiagnoseClient:
    def __init__(self, base_url="http://127.0.0.1:8900"):
        self.base_url = base_url
        self.diagnose_url = f"{base_url}/diagnose"
        
    def activate_fault(self, profile):
        """激活故障profile"""
        url = f"{self.base_url}/fault/activate"
        try:
            response = requests.post(url, json={"profile": profile}, timeout=5)
            return response.json()
        except Exception as e:
            print(f"激活故障失败: {e}")
            return {"code": -1, "message": str(e)}
    
    def get_fault_status(self):
        """获取当前故障状态"""
        url = f"{self.base_url}/fault/status"
        try:
            response = requests.get(url, timeout=5)
            return response.json()
        except Exception as e:
            print(f"获取故障状态失败: {e}")
            return {"code": -1, "message": str(e)}
    
    def submit_diagnose(self, screenshot_path, page, profile):
        """提交截图进行诊断"""
        if not os.path.exists(screenshot_path):
            raise FileNotFoundError(f"截图文件不存在: {screenshot_path}")
        
        context = {
            "page": page,
            "profile": profile,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            with open(screenshot_path, "rb") as f:
                files = {"image": f}
                data = {"context": json.dumps(context)}
                response = requests.post(self.diagnose_url, files=files, data=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"提交诊断失败: {e}")
            return {"code": -1, "message": str(e)}
    
    def verify_diagnosis(self, result, expected_diagnosis):
        """验证诊断结果"""
        if result.get("code") != 0:
            return False, f"接口返回错误: {result.get('message', '未知错误')}"
        
        data = result.get("data", {})
        actual_diagnosis = data.get("diagnosis")
        
        if actual_diagnosis == expected_diagnosis:
            return True, f"诊断正确: {actual_diagnosis}"
        else:
            return False, f"诊断不符: 期望{expected_diagnosis}, 实际{actual_diagnosis}"