# -*- mode: python ; coding: utf-8 -*-
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
    'PyQt5.sip', 'sqlite3', 'pandas', 'openpyxl', 'xlrd', 'logging.handlers'
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
