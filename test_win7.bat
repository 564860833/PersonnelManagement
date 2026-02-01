@echo off
chcp 65001
echo 测试 Windows 7 兼容性程序...
echo.

if not exist "dist\人员信息管理系统.exe" (
    echo ❌ 未找到可执行文件
    pause
    exit /b 1
)

echo 启动程序...
cd dist
start "" "人员信息管理系统.exe"
cd ..

echo ✓ 程序已启动，请检查是否正常运行
echo.
echo 💡 如果程序无法运行，请确保目标 Windows 7 系统已安装:
echo    - Visual C++ 2015-2019 运行库 (x86)
echo    - 以管理员权限运行程序
echo.
pause
