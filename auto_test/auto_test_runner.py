#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vision-Triage 全自动化测试脚本
功能：自动连接 -> 自动激活故障 -> 自动截图 -> 自动诊断 -> 自动保存结果
"""
import os
import sys
import json
import time
import requests
import minium
from datetime import datetime
import traceback

# 添加工具模块路径
sys.path.insert(0, os.path.dirname(__file__))

class VisionTriageAutoTester:
    """Vision-Triage 自动化测试器"""
    
    def __init__(self, config_path="../minium_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.mini = None
        self.diagnose_url = "http://127.0.0.1:8900/diagnose"  # 修正1：添加完整的URL
        self.results = []
        self.report_dir = "./reports"
        self.screenshot_dir = "./reports/screenshots"
        
        # 创建目录
        os.makedirs(self.screenshot_dir, exist_ok=True)
    
    def _load_config(self):
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _connect_to_wechat(self):
        """连接到微信开发者工具"""
        print("🔌 连接微信开发者工具...")
        try:
            # 设置更长的超时时间
            original_timeout = self.config.get('request_timeout', 30)
            self.config['request_timeout'] = 60
        
            # 尝试连接
            self.mini = minium.Minium(self.config)
        
            # 恢复超时设置
            self.config['request_timeout'] = original_timeout
        
            print("✅ 连接成功")
            return True
        except Exception as e:
            error_msg = str(e)
            # 检查错误是否为 clickCoverView 相关的非致命错误
            if 'clickCoverView' in error_msg:
                print("⚠️  连接存在警告但已建立: clickCoverView 失败（可忽略）")
                print("✅ 继续执行测试...")
                return True
            else:
                print(f"❌ 连接失败: {e}")
                return False
            
    def _activate_fault(self, profile_name):
        """激活指定故障"""
        print(f"   激活故障: {profile_name}")
        try:
            response = requests.post(
                "http://127.0.0.1:8900/fault/activate",  # 修正2：添加主机地址
                json={"profile": profile_name},
                timeout=10
            )
            result = response.json()
            if result.get("code") == 0:
                print(f"      ✅ 激活成功")
                return True
            else:
                print(f"      ❌ 激活失败: {result}")
                return False
        except Exception as e:
            print(f"      ❌ 激活异常: {e}")
            return False
    
    def _take_screenshot(self, test_name, profile):
        """自动截图"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{test_name}_{profile}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        
        try:
            self.mini.app.screen_shot(filepath)
            if os.path.exists(filepath):
                print(f"      📸 截图已保存: {filepath}")
                return filepath
            else:
                print(f"      ❌ 截图文件未生成")
                return None
        except Exception as e:
            print(f"      ❌ 截图失败: {e}")
            return None
    
    def _call_diagnose(self, screenshot_path, page, profile):
        """调用诊断接口"""
        print(f"      🧠 提交诊断...")
        
        if not os.path.exists(screenshot_path):
            print(f"      ❌ 截图文件不存在: {screenshot_path}")
            return None
        
        try:
            with open(screenshot_path, "rb") as f:
                # 关键修正：文件字段名必须是 "screenshot"
                files = {"screenshot": (os.path.basename(screenshot_path), f, "image/png")}
                
                # 关键修正：表单字段名必须与 app.py 中的定义完全一致
                data = {
                    "page_type": page,           # 对应 app.py 中的 page_type 参数
                    "fault_profile": profile,    # 对应 app.py 中的 fault_profile 参数
                    "page_state": json.dumps({}),           # 必须为JSON格式字符串
                    "perf_data": json.dumps({"interactionMs": 100, "memoryWarningCount": 0})  # 必须为JSON格式字符串
                }
                
                print(f"        发送诊断请求到: {self.diagnose_url}")
                print(f"        请求参数: {data}")
                
                response = requests.post(
                    self.diagnose_url,
                    files=files,
                    data=data,  # 注意：是 data 参数，不是 json
                    timeout=15
                )
            
            print(f"      📊 诊断接口状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"      📊 诊断接口返回: {json.dumps(result, indent=2, ensure_ascii=False)[:200]}")
                return result
            else:
                print(f"      ❌ 诊断接口HTTP错误: {response.status_code}")
                print(f"        错误详情: {response.text[:200]}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"      ❌ 网络请求异常: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"      ❌ 响应不是有效的JSON: {e}")
            print(f"        响应内容: {response.text[:200]}")
            return None
        except Exception as e:
            print(f"      ❌ 诊断调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _verify_diagnosis(self, result, expected_diagnosis):
        """验证诊断结果"""
        if not result or result.get("code") != 0:
            return False, "接口返回错误"
    
        data = result.get("data", {})
    
        # 1. 首先，打印完整的返回数据以便调试
        print(f"        完整诊断返回数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
        # 2. 尝试获取诊断结论，字段名应为 'verdict' (与triage.py一致)
        actual_diagnosis = data.get("verdict")
    
        if actual_diagnosis is None:
            # 如果找不到，列出所有可用字段以便排查
            return False, f"诊断结果字段缺失。返回数据中可用字段: {list(data.keys())}"
    
        if actual_diagnosis == expected_diagnosis:
            return True, f"诊断正确: {actual_diagnosis}"
        else:
            return False, f"期望 {expected_diagnosis}, 实际 {actual_diagnosis}"
    
    def run_test_case(self, test_name, profile, expected_diagnosis, page="feed"):
        """运行单个测试用例"""
        print(f"\n{'='*60}")
        print(f"🧪 测试用例: {test_name}")
        print(f"🔧 故障配置: {profile}")
        print(f"🎯 期望诊断: {expected_diagnosis}")
        print('='*60)
        
        start_time = time.time()
        
        try:
            # 1. 激活故障
            if not self._activate_fault(profile):
                return False, "激活故障失败"
            
            time.sleep(3)  # 等待故障生效
            
            # 2. 导航到页面
            print(f"    📍 导航到页面: {page}")
            try:
                self.mini.app.switch_tab(f"/pages/{page}/index")
                time.sleep(2)
            except Exception as e:
                print(f"      ⚠️ 导航警告: {e}")
            
            # 3. 自动截图
            screenshot_path = self._take_screenshot(test_name, profile)
            if not screenshot_path:
                return False, "截图失败"
            
            # 4. 自动诊断
            diagnose_result = self._call_diagnose(screenshot_path, page, profile)
            if not diagnose_result:
                return False, "诊断调用失败"
            
            # 5. 自动验证
            success, message = self._verify_diagnosis(diagnose_result, expected_diagnosis)
            
            duration = time.time() - start_time
            
            # 记录结果
            result_data = {
                "test_name": test_name,
                "profile": profile,
                "expected": expected_diagnosis,
                "actual": diagnose_result.get("data", {}).get("diagnosis") if diagnose_result else None,
                "success": success,
                "message": message,
                "screenshot": screenshot_path,
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
                "diagnose_result": diagnose_result
            }
            
            self.results.append(result_data)
            
            if success:
                print(f"✅ 测试通过! ({duration:.2f}秒)")
                print(f"   结果: {message}")
            else:
                print(f"❌ 测试失败! ({duration:.2f}秒)")
                print(f"   原因: {message}")
            
            return success, message
            
        except Exception as e:
            duration = time.time() - start_time
            print(f"💥 测试异常! ({duration:.2f}秒)")
            print(f"   异常: {e}")
            traceback.print_exc()
            return False, f"测试异常: {e}"
    
    def generate_report(self):
        """生成测试报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(self.report_dir, f"auto_test_report_{timestamp}.json")
        
        report = {
            "project": "Vision-Triage",
            "timestamp": timestamp,
            "total_tests": len(self.results),
            "passed_tests": sum(1 for r in self.results if r["success"]),
            "failed_tests": sum(1 for r in self.results if not r["success"]),
            "total_duration": sum(r["duration"] for r in self.results),
            "results": self.results,
            "summary": {
                "connection": "成功" if self.mini else "失败",
                "screenshots_taken": sum(1 for r in self.results if r.get("screenshot")),
                "diagnose_calls": sum(1 for r in self.results if r.get("diagnose_result"))
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📊 测试报告已保存: {report_file}")
        
        # 生成简洁的文本报告
        text_report = os.path.join(self.report_dir, f"auto_test_summary_{timestamp}.txt")
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write(f"Vision-Triage 自动化测试报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n")
            f.write(f"总测试数: {report['total_tests']}\n")
            f.write(f"通过数: {report['passed_tests']}\n")
            f.write(f"失败数: {report['failed_tests']}\n")
            f.write(f"总用时: {report['total_duration']:.2f}秒\n")
            f.write("\n详细结果:\n")
            f.write("-"*50 + "\n")
            for i, result in enumerate(report["results"], 1):
                status = "✅ 通过" if result["success"] else "❌ 失败"
                f.write(f"{i}. {result['test_name']} - {result['profile']}\n")
                f.write(f"   状态: {status} ({result['duration']:.2f}秒)\n")
                f.write(f"   期望: {result['expected']}, 实际: {result.get('actual', 'N/A')}\n")
                f.write(f"   截图: {os.path.basename(result.get('screenshot', ''))}\n")
                f.write(f"   信息: {result['message']}\n")
                f.write("\n")
        
        return report_file
    
    def run_full_test_suite(self):
        """运行完整的测试套件"""
        print("="*70)
        print("🚀 Vision-Triage 全自动化测试启动")
        print("="*70)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 测试套件定义
        test_suite = [
            {
                "name": "模糊图片故障测试",
                "profile": "blur_image",
                "expected": "RenderBug",
                "page": "feed"
            },
            {
                "name": "接口延迟故障测试", 
                "profile": "slow_api",
                "expected": "PerformanceRisk",
                "page": "feed"
            },
            {
                "name": "内存压力故障测试",
                "profile": "memory_pressure",
                "expected": "PerformanceRisk", 
                "page": "feed"
            }
        ]
        
        # 1. 连接到微信开发者工具
        if not self._connect_to_wechat():
            return False
        
        all_success = True
        
        try:
            # 2. 运行所有测试用例
            for test_case in test_suite:
                success, _ = self.run_test_case(
                    test_case["name"],
                    test_case["profile"],
                    test_case["expected"],
                    test_case["page"]
                )
                
                if not success:
                    all_success = False
                
                # 用例间等待
                time.sleep(2)
        
        finally:
            # 3. 断开连接
            if self.mini:
                try:
                    if hasattr(self.mini, 'disconnect'):
                        self.mini.disconnect()
                    print("\n🔌 已断开微信开发者工具连接")
                except:
                    pass
        
        # 4. 生成报告
        report_file = self.generate_report()
        
        print("\n" + "="*70)
        print("📋 测试完成总结")
        print("="*70)
        print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总测试数: {len(self.results)}")
        print(f"通过数: {sum(1 for r in self.results if r['success'])}")
        print(f"失败数: {sum(1 for r in self.results if not r['success'])}")
        print(f"总用时: {sum(r['duration'] for r in self.results):.2f}秒")
        print(f"测试报告: {report_file}")
        
        if all_success:
            print("\n🎉 所有测试通过! Vision-Triage 系统运行正常。")
        else:
            print("\n⚠️  部分测试失败，请查看详细报告。")
        
        return all_success


def main():
    """主函数"""
    try:
        tester = VisionTriageAutoTester()
        success = tester.run_full_test_suite()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
        return 130
    except Exception as e:
        print(f"\n💥 测试执行异常: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())