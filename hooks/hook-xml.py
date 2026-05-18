# hook-xml.py
"""
XML模块钩子，确保正确打包XML相关依赖
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 收集所有XML相关模块
hiddenimports = []

# 添加XML核心模块
hiddenimports.extend([
    'xml',
    'xml.etree',
    'xml.etree.ElementTree',
    'xml.parsers',
    'xml.parsers.expat',
    'xml.dom',
    'xml.dom.minidom',
    'xml.sax',
    'xml.sax.handler',
])

# 收集子模块
hiddenimports.extend(collect_submodules('xml'))

# 收集数据文件
datas = collect_data_files('xml')

print(f"XML钩子: 收集了 {len(hiddenimports)} 个隐藏导入")
