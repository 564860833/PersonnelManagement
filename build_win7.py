#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Windows 7 完全兼容的 PyInstaller 构建脚本
解决多进程和 DLL 加载问题的完整方案
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def setup_directories():
    """设置必要的目录结构"""
    directories = ['hooks', 'build', 'dist']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    print("✓ 目录结构已创建")


def create_custom_hook():
    """创建自定义运行时钩子"""
    hook_content = '''# pyi_rth_disable_multiprocessing.py
import sys
import os

class FakeMultiprocessingModule:
    def __getattr__(self, name):
        def dummy_function(*args, **kwargs):
            raise NotImplementedError("多进程功能已禁用以提高 Windows 7 兼容性")
        return dummy_function

# 替换问题模块
fake_mp = FakeMultiprocessingModule()
problematic_modules = [
    'multiprocessing', 'multiprocessing.context', 'multiprocessing.spawn',
    'multiprocessing.forkserver', 'multiprocessing.reduction', '_multiprocessing',
    'concurrent.futures', 'concurrent.futures.process'
]

for module_name in problematic_modules:
    sys.modules[module_name] = fake_mp

# 禁用多进程环境变量
os.environ.update({
    'DISABLE_MULTIPROCESSING': '1',
    'MULTIPROCESSING_FORCE': '0',
    'PYTHONDONTWRITEBYTECODE': '1'
})

print("✓ Windows 7 兼容性钩子已加载")
'''

    hook_file = Path('hooks/pyi_rth_disable_multiprocessing.py')
    with open(hook_file, 'w', encoding='utf-8') as f:
        f.write(hook_content)
    print(f"✓ 自定义钩子已创建: {hook_file}")
    return str(hook_file)


def create_spec_file():
    """创建 .spec 配置文件"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

# 完全排除多进程模块
EXCLUDED_MODULES = [
    'multiprocessing', 'multiprocessing.spawn', 'multiprocessing.forkserver',
    'multiprocessing.context', 'multiprocessing.reduction', '_multiprocessing',
    'concurrent.futures', 'asyncio'
]

HIDDEN_IMPORTS = [
    'PyQt5.sip', 'sqlite3', 'pandas', 'openpyxl', 'xlrd', 'logging.handlers', 'llama_cpp'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app_icon.ico', '.')], 
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=['hooks'],
    runtime_hooks=['hooks/pyi_rth_disable_multiprocessing.py'],
    excludes=EXCLUDED_MODULES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤多进程模块
filtered_pure = [(name, path, typecode) for name, path, typecode in a.pure 
                 if not any(name.startswith(excluded) for excluded in EXCLUDED_MODULES)]
a.pure = filtered_pure

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='人员信息管理系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
'''

    spec_file = Path('win7_compatible.spec')
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print(f"✓ Spec 文件已创建: {spec_file}")
    return str(spec_file)


def clean_build():
    """清理之前的构建文件"""
    dirs_to_clean = ['build', 'dist']
    files_to_clean = ['*.spec']

    for directory in dirs_to_clean:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            print(f"✓ 已清理: {directory}")

    import glob
    for pattern in files_to_clean:
        for file in glob.glob(pattern):
            if 'win7_compatible.spec' not in file:  # 保留我们的spec文件
                os.remove(file)
                print(f"✓ 已清理: {file}")


def check_environment():
    """检查构建环境"""
    print("检查构建环境...")

    # 检查 Python 版本
    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")

    if version >= (3, 9):
        print("⚠️  警告: Python 3.9+ 对 Windows 7 支持有限，建议使用 Python 3.8")

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
        if PyInstaller.__version__.startswith('5.') or PyInstaller.__version__.startswith('6.'):
            print("⚠️  警告: PyInstaller 5.x/6.x 对 Windows 7 支持有限，建议使用 4.10")
    except ImportError:
        print("❌ 未安装 PyInstaller")
        return False

    # 检查必要文件
    if not os.path.exists('main.py'):
        print("❌ 未找到 main.py 文件")
        return False

    print("✓ 环境检查完成")
    return True


def build_application():
    """构建应用程序"""
    print("\n开始构建 Windows 7 兼容版本...")

    # 设置目录
    setup_directories()

    # 创建钩子
    hook_file = create_custom_hook()

    # 创建 spec 文件
    spec_file = create_spec_file()

    # 清理之前的构建
    clean_build()

    try:
        # 使用 spec 文件构建
        cmd = ['pyinstaller', '--clean', '--noconfirm', spec_file]
        print(f"执行命令: {' '.join(cmd)}")

        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')

        print("✓ 构建成功!")

        # 检查输出文件
        exe_path = Path('dist/人员信息管理系统.exe')
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / 1024 / 1024
            print(f"✓ 输出文件: {exe_path} ({size_mb:.1f} MB)")
            return True
        else:
            print("❌ 未找到输出文件")
            return False

    except subprocess.CalledProcessError as e:
        print("❌ 构建失败!")
        print("错误输出:")
        print(e.stderr)
        return False
    except Exception as e:
        print(f"❌ 构建过程出错: {e}")
        return False


def create_test_script():
    """创建测试脚本"""
    test_content = '''@echo off
chcp 65001
echo 测试 Windows 7 兼容性程序...
echo.

if not exist "dist\\人员信息管理系统.exe" (
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
'''

    with open('test_win7.bat', 'w', encoding='utf-8') as f:
        f.write(test_content)
    print("✓ 测试脚本已创建: test_win7.bat")


def main():
    """主函数"""
    print("=" * 60)
    print("Windows 7 兼容构建工具")
    print("解决多进程和 DLL 加载问题")
    print("=" * 60)

    # 检查环境
    if not check_environment():
        print("\n❌ 环境检查失败，请解决上述问题后重试")
        return

    # 构建应用
    success = build_application()

    if success:
        # 创建测试脚本
        create_test_script()

        print("\n" + "=" * 60)
        print("✓ 构建完成!")
        print("=" * 60)
        print("下一步:")
        print("1. 运行 test_win7.bat 进行本地测试")
        print("2. 将 dist/人员信息管理系统.exe 复制到 Windows 7 系统")
        print("3. 在 Windows 7 上以管理员权限运行程序")
        print("\n如果仍有问题:")
        print("- 确保 Windows 7 已安装 VC++ 2015-2019 运行库")
        print("- 尝试兼容模式运行")
        print("- 检查防病毒软件是否阻止程序运行")
    else:
        print("\n❌ 构建失败，请检查错误信息")


if __name__ == "__main__":
    main()
