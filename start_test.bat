@echo off
chcp 65001 >nul
echo ========================================
echo  Vision-Triage 自动化测试启动脚本
echo  (Minium 1.6.0 适配版)
echo ========================================
echo.

REM 1. 检查当前目录
echo [1/6] 检查工作目录...
echo   当前目录: %cd%
echo.

REM 2. 激活 conda 环境
echo [2/6] 激活 Python 环境...
call conda activate vision-triage
if errorlevel 1 (
    echo    ❌ 无法激活 vision-triage 环境
    echo    请手动运行: conda activate vision-triage
    pause
    exit /b 1
)
echo    ✅ 环境激活成功
echo.

REM 3. 检查 Minium 安装
echo [3/6] 检查 Minium 安装...
python -c "import minium" 2>nul
if errorlevel 1 (
    echo    ❌ Minium 未安装，正在安装...
    pip install minium==1.6.0
    if errorlevel 1 (
        echo    ❌ Minium 安装失败
        pause
        exit /b 1
    )
    echo    ✅ Minium 安装成功
) else (
    echo    ✅ Minium 已安装
)
echo.

REM 4. 启动诊断后端服务
echo [4/6] 启动诊断后端服务...
echo   正在启动诊断服务（端口 8900）...
start "Vision-Triage 诊断服务" cmd /k "cd /d "%~dp0diagnosis" && python -m uvicorn app:app --host 127.0.0.1 --port 8900 --reload"
echo    ✅ 诊断服务启动中...
echo   等待服务就绪（5秒）...
timeout /t 5 /nobreak >nul
echo.

REM 5. 检查后端状态
echo [5/6] 验证后端状态...
curl http://127.0.0.1:8900/fault/status 2>nul
if errorlevel 1 (
    echo    ⚠️  后端服务可能尚未完全启动
    echo    但将继续测试流程，部分测试可能受影响
) else (
    echo    ✅ 后端服务响应正常
)
echo.

REM 6. 运行自动化测试
echo [6/6] 运行自动化测试套件...
echo   按任意键开始测试，或按 Ctrl+C 取消...
pause >nul
echo.

REM 切换到 auto_test 目录并运行测试
cd /d auto_test
python test_runner.py

echo.
echo ========================================
echo 测试流程执行完毕！
echo.
echo 后续操作建议:
echo 1. 查看测试报告: auto_test/reports/ 目录
echo 2. 查看后端日志: 新打开的'诊断服务'命令行窗口
echo 3. 查看小程序状态: 微信开发者工具
echo 4. 查看截图文件: auto_test/reports/screenshots/
echo.
echo 如需重新运行测试，请再次执行此脚本
echo ========================================
pause