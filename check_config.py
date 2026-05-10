import os
import json

def check_config():
    print("检查配置文件...")
    
    # 检查minium_config.json
    config_path = "minium_config.json"
    if os.path.exists(config_path):
        try:
            # 指定使用UTF-8编码打开文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            print("✅ minium_config.json 存在")
            print(f"   项目路径: {config.get('project_path')}")
            print(f"   端口: {config.get('test_port')}")
            print(f"   AppID: {config.get('appid')}")
            
            # 检查项目路径是否存在
            project_path = config.get('project_path', '')
            if project_path and os.path.exists(project_path):
                print("✅ 项目路径存在")
            else:
                print("❌ 项目路径不存在")
                
            # 检查cli路径是否存在
            dev_tool_path = config.get('dev_tool_path', '')
            if dev_tool_path and os.path.exists(dev_tool_path):
                print("✅ 微信开发者工具CLI路径存在")
            else:
                print("❌ 微信开发者工具CLI路径不存在")
                
        except UnicodeDecodeError as e:
            print(f"❌ 文件编码问题: {e}")
            print("尝试使用GBK编码...")
            with open(config_path, 'r', encoding='gbk') as f:
                config = json.load(f)
            print("✅ 使用GBK编码成功读取")
        except Exception as e:
            print(f"❌ 读取配置文件失败: {e}")
    else:
        print("❌ minium_config.json 不存在")
    
    # 检查目录结构
    print("\n检查目录结构...")
    required_dirs = [
        "auto_test",
        "auto_test/test_cases", 
        "auto_test/utils",
        "auto_test/reports/screenshots",
        "diagnosis",
        "demo-uniapp"
    ]
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path} 存在")
        else:
            print(f"❌ {dir_path} 不存在")
    
    print("\n检查完成！")

if __name__ == "__main__":
    check_config()