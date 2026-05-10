# 保存为：test_fault_injection.py
import requests
import json

def test_backend_fault():
    print("=== 验证后端故障注入 ===")
    
    # 1. 激活模糊图片故障
    print("1. 激活 blur_image 故障...")
    try:
        activate_resp = requests.post(
            "http://127.0.0.1:8900/fault/activate",
            json={"profile": "blur_image"},
            timeout=5
        )
        print(f"   激活结果: {activate_resp.json()}")
    except Exception as e:
        print(f"   激活失败: {e}")
        return
    
    # 2. 获取feed数据，检查图片URL
    print("\n2. 获取feed数据，检查图片链接...")
    try:
        feed_resp = requests.get(
            "http://127.0.0.1:8900/api/feed?page=1&pageSize=3",
            timeout=5
        )
        feed_data = feed_resp.json()
        
        if feed_data.get("code") == 0:
            items = feed_data.get("data", [])
            print(f"   共获取 {len(items)} 条数据")
            
            for i, item in enumerate(items):
                img_url = item.get("imageUrl", "")
                print(f"\n   第{i+1}条数据:")
                print(f"     图片URL: {img_url}")
                
                # 检查是否包含模糊参数
                if "blur" in img_url:
                    print("     ✅ 包含模糊参数 (故障注入成功)")
                else:
                    print("     ❌ 不包含模糊参数 (故障可能未生效)")
        else:
            print(f"   获取数据失败: {feed_data}")
            
    except Exception as e:
        print(f"   获取feed数据失败: {e}")
    
    print("\n" + "="*50)

if __name__ == "__main__":
    test_backend_fault()