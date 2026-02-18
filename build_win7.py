#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Windows 7 兼容构建脚本 (最终修正版)
修复:
1. 解除对 concurrent.futures 的误封杀，允许 AI 使用线程池
2. 伪造 cpu_count()，防止 AI 查询核心数时报错
3. 强制收集 llama_cpp 所有依赖
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


def create_custom_hook():
    """创建智能兼容钩子"""
    hook_content = '''# pyi_rth_win7_ai_fix.py
import sys
import os

# 1. 定义一个"智能"的伪造多进程模块
# 它允许查询 CPU 数量 (cpu_count)，允许获取当前进程名
# 但会拦截真正危险的创建新进程操作 (Pool, Process)
class SmartFakeMultiprocessing:
    def __init__(self):
        # 拦截危险操作
        self.Process = self._fail
        self.Pool = self._fail
        self.Queue = self._fail
        self.Pipe = self._fail
        self.Manager = self._fail
        self.context = self

    def _fail(self, *args, **kwargs):
        raise NotImplementedError("Win7兼容模式：已禁用多进程生成 (AI应使用多线程)")

    # 【关键修复】允许 AI 读取 CPU 核心数
    def cpu_count(self):
        try:
            return os.cpu_count() or 4
        except:
            return 4

    # 【关键修复】允许获取当前进程信息（防止日志库报错）
    def current_process(self):
        class Proc:
            name = 'MainProcess'
            daemon = False
            pid = os.getpid()
            _identity = ()
        return Proc()

    def active_children(self):
        return []

    # 允许访问锁（concurrent.futures 需要用到锁）
    def __getattr__(self, name):
        if name in ['Lock', 'RLock', 'Event', 'Condition', 'Semaphore', 'BoundedSemaphore']:
             import threading
             if hasattr(threading, name):
                 return getattr(threading, name)
        return self._fail

# 2. 注入到 sys.modules，欺骗 Python 以为多进程模块存在
fake_mp = SmartFakeMultiprocessing()
modules_to_patch = [
    'multiprocessing', 
    'multiprocessing.context', 
    'multiprocessing.process', 
    'multiprocessing.queues', 
    'multiprocessing.pool', 
    'multiprocessing.reduction', 
    '_multiprocessing'
]

for m in modules_to_patch:
    sys.modules[m] = fake_mp

# 3. 注意：我们不再禁用 concurrent.futures，因为它负责管理线程池
print("✓ Windows 7 AI 线程池兼容补丁已加载")
'''

    hook_file = Path('hooks/pyi_rth_win7_ai_fix.py')
    with open(hook_file, 'w', encoding='utf-8') as f:
        f.write(hook_content)
    print(f"✓ 兼容钩子已创建: {hook_file}")
    return str(hook_file)


def create_spec_file():
    """创建 .spec 配置文件"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# 1. 强制收集 llama_cpp 的所有文件（DLLs, libs, data）
llama_datas, llama_binaries, llama_hiddenimports = collect_all('llama_cpp')

# 2. 仅排除危险的多进程模块，保留 concurrent.futures (线程池)
EXCLUDED_MODULES = [
    'multiprocessing', 'multiprocessing.spawn', 'multiprocessing.forkserver',
    '_multiprocessing', 'asyncio'
    # 注意：这里删除了 concurrent.futures，因为 AI 需要它
]

# 3. 补充隐藏导入
BASE_HIDDEN_IMPORTS = [
    'PyQt5.sip', 'sqlite3', 'pandas', 'openpyxl', 'xlrd', 'logging.handlers',
    'secrets', 'random', 'hmac', 'hashlib', 'concurrent.futures'
]

FINAL_HIDDEN_IMPORTS = BASE_HIDDEN_IMPORTS + llama_hiddenimports

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=llama_binaries,
    datas=[('app_icon.ico', '.')] + llama_datas,
    hiddenimports=FINAL_HIDDEN_IMPORTS,
    hookspath=['hooks'],
    runtime_hooks=['hooks/pyi_rth_win7_ai_fix.py'], # 使用新的钩子
    excludes=EXCLUDED_MODULES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤掉不需要的模块
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
    console=False, # 发布版隐藏黑框
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
'''

    spec_file = Path('win7_compatible.spec')
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print(f"✓ Spec 文件已更新: {spec_file}")
    return str(spec_file)


def clean_build():
    try:
        if os.path.exists('dist'): shutil.rmtree('dist')
        if os.path.exists('build'): shutil.rmtree('build')
    except:
        pass


def build_application():
    print("\n开始构建 Windows 7 AI 兼容版...")
    setup_directories()
    create_custom_hook()
    spec_file = create_spec_file()
    clean_build()

    try:
        cmd = ['pyinstaller', '--clean', '--noconfirm', spec_file]
        print(f"执行命令: {' '.join(cmd)}")
        print("-" * 20 + " Log " + "-" * 20)
        # 直接输出日志，避免编码报错
        subprocess.run(cmd, check=True)
        print("-" * 20 + " End " + "-" * 20)

        print("\n✓ 构建成功！请检查 dist 文件夹。")
        print("💡 提示：别忘了把 models 文件夹和模型放入 dist 目录！")

    except Exception as e:
        print(f"\n❌ 构建失败: {e}")


if __name__ == "__main__":
    build_application()
