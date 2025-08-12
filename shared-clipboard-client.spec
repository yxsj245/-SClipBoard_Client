# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 获取当前目录和fun目录
current_dir = os.path.dirname(os.path.abspath(SPEC))
fun_dir = os.path.join(current_dir, 'fun')

# 数据文件
datas = [
    ('config_example.json', '.'),
    ('network_config.json', '.'),
    ('fun', 'fun'),
]

# 添加图标文件（如果存在）
png_icon_path = os.path.join(current_dir, '画板 1.png')
ico_icon_path = os.path.join(current_dir, 'icon.ico')

# 如果ICO文件不存在但PNG文件存在，尝试转换
if not os.path.exists(ico_icon_path) and os.path.exists(png_icon_path):
    try:
        from PIL import Image
        img = Image.open(png_icon_path)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_icon_path, format='ICO', sizes=sizes)
        print(f"✅ 已自动转换图标: {ico_icon_path}")
    except Exception as e:
        print(f"⚠️ 图标转换失败: {e}")
        ico_icon_path = None

# 添加图标到数据文件
if os.path.exists(png_icon_path):
    datas.append((png_icon_path, '.'))
if os.path.exists(ico_icon_path):
    datas.append((ico_icon_path, '.'))

# 隐藏导入列表
hiddenimports = [
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'websockets',
    'requests',
    'pyperclip',
    'PIL',
    'PIL.Image',
    'PIL.ImageQt',
    'asyncio',
    'json',
    'base64',
    'io',
    'hashlib',
    'datetime',
    'typing',
    'logging',
    'clipboard_api',
    'websocket_api',
    'network_config',
    'clipboard_client',
    'devices_api',
    'health_api',
    'config_api',
    'files_api',
    'ws_monitor'
]

a = Analysis(
    ['main.py'],
    pathex=[current_dir, fun_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='shared-clipboard-client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ico_icon_path if os.path.exists(ico_icon_path) else None,
)
