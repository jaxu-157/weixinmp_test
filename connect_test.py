# connect_test.py
import minium
import json
import os
import time

print('=== 端口17225连接测试 ===')
print('='*50)

# 加载配置
with open('minium_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

print('配置摘要:')
print('  端口:', config.get('test_port'))
print('  项目路径:', config.get('project_path'))

# 设置较短超时
config['request_timeout'] = 10

print('\n尝试连接微信开发者工具(端口17225)...')
try:
    start_time = time.time()
    mini = minium.Minium(config)
    connect_time = time.time() - start_time
    
    print('✅ 连接成功! (用时: {:.2f}秒)'.format(connect_time))
    
    # 快速验证
    print('\n基本功能验证:')
    print('1. 获取当前页面...')
    try:
        page = mini.app.get_current_page()
        print('   当前页面:', page)
    except:
        print('   无法获取当前页面')
    
    print('2. 导航到feed页面...')
    try:
        mini.app.navigate_to('/pages/feed/index')
        print('   导航指令已发送')
    except Exception as e:
        print('   导航异常:', e)
    
    print('3. 截图测试...')
    try:
        mini.app.screen_shot('connection_test.png')
        if os.path.exists('connection_test.png'):
            print('   截图已保存: connection_test.png')
    except:
        print('   截图失败')
    
    mini.app.disconnect()
    print('\n✅ 连接测试通过! 端口17225配置正确。')
    
except Exception as e:
    print('\n❌ 连接失败:', type(e).__name__)
    print('错误详情:', str(e)[:200])
    
    # 常见问题诊断
    print('\n🔧 诊断建议:')
    if '17225' in str(e):
        print('1. 确认微信开发者工具已打开')
        print("2. 确认'设置->安全设置->服务端口'已开启")
        print('3. 确认端口号显示为17225')
    elif 'project_path' in str(e):
        print('1. 确认项目路径存在: demo-uniapp/dist/dev/mp-weixin')
        print('2. 确认小程序已编译: cd demo-uniapp && npm run dev:mp-weixin')
    elif 'timeout' in str(e).lower():
        print('1. 检查防火墙设置')
        print('2. 尝试重启微信开发者工具')
    print('\n请修正上述问题后重试。')