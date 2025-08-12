#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地打包脚本
用于在本地环境中打包应用程序
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_dependencies():
    """检查打包依赖"""
    print("检查打包依赖...")
    
    try:
        import PyInstaller
        print(f"✅ PyInstaller 已安装: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller 未安装")
        print("正在安装 PyInstaller...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("✅ PyInstaller 安装成功")
        except subprocess.CalledProcessError:
            print("❌ PyInstaller 安装失败")
            return False
    
    # 检查其他依赖
    required_modules = ['PyQt5', 'requests', 'websockets', 'pyperclip', 'PIL']
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} 已安装")
        except ImportError:
            print(f"❌ {module} 未安装")
            return False
    
    return True

def clean_build():
    """清理构建目录"""
    print("清理构建目录...")
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"✅ 已清理 {dir_name}")
    
    # 清理spec文件生成的缓存
    for file in Path('.').glob('*.spec'):
        cache_dir = file.stem + '.spec.cache'
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)

def convert_icon():
    """转换图标格式"""
    print("转换图标格式...")

    png_file = "画板 1.png"
    ico_file = "icon.ico"

    if not os.path.exists(png_file):
        print(f"⚠️ 找不到PNG图标文件: {png_file}")
        return True  # 不是致命错误

    if os.path.exists(ico_file):
        print(f"✅ ICO图标已存在: {ico_file}")
        return True

    try:
        from PIL import Image
        img = Image.open(png_file)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_file, format='ICO', sizes=sizes)
        print(f"✅ 图标转换成功: {ico_file}")
        return True
    except Exception as e:
        print(f"⚠️ 图标转换失败: {e}")
        return True  # 不是致命错误

def build_executable():
    """构建可执行文件"""
    print("开始构建可执行文件...")

    # 先转换图标
    convert_icon()

    # 使用spec文件构建
    spec_file = "shared-clipboard-client.spec"
    if os.path.exists(spec_file):
        print(f"使用 {spec_file} 构建...")
        cmd = [sys.executable, "-m", "PyInstaller", spec_file]
    else:
        print("使用命令行参数构建...")
        # 检查图标文件
        icon_arg = []
        if os.path.exists("icon.ico"):
            icon_arg = ["--icon", "icon.ico"]

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--name", "shared-clipboard-client",
            "--add-data", "config_example.json;." if os.name == 'nt' else "config_example.json:.",
            "--add-data", "network_config.json;." if os.name == 'nt' else "network_config.json:.",
            "--add-data", "fun;fun" if os.name == 'nt' else "fun:fun",
            "--hidden-import", "PyQt5.QtCore",
            "--hidden-import", "PyQt5.QtGui",
            "--hidden-import", "PyQt5.QtWidgets",
            "--hidden-import", "websockets",
            "--hidden-import", "requests",
            "--hidden-import", "pyperclip",
            "--hidden-import", "PIL",
            "--hidden-import", "clipboard_api",
            "--hidden-import", "websocket_api",
            "--hidden-import", "network_config",
            "--hidden-import", "clipboard_client",
            "--hidden-import", "devices_api",
            "--hidden-import", "health_api",
            "--hidden-import", "config_api",
            "--hidden-import", "files_api",
            "--hidden-import", "ws_monitor",
            "--noconsole" if os.name == 'nt' else "",
        ] + icon_arg + ["main.py"]

        # 移除空字符串
        cmd = [arg for arg in cmd if arg]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ 构建成功!")
        return True
    except subprocess.CalledProcessError as e:
        print("❌ 构建失败!")
        print(f"错误输出: {e.stderr}")
        if e.stdout:
            print(f"标准输出: {e.stdout}")
        return False

def create_distribution():
    """创建发布包 - 只包含主程序"""
    print("创建发布包（仅主程序）...")

    dist_dir = "release"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)

    os.makedirs(dist_dir)

    # 只复制可执行文件
    exe_name = "shared-clipboard-client.exe" if os.name == 'nt' else "shared-clipboard-client"
    exe_path = os.path.join("dist", exe_name)

    if os.path.exists(exe_path):
        shutil.copy2(exe_path, dist_dir)
        print(f"✅ 已复制主程序: {exe_name}")
    else:
        print(f"❌ 找不到可执行文件: {exe_path}")
        return False

    print(f"✅ 发布包已创建在 {dist_dir} 目录（仅包含主程序）")
    return True

def main():
    """主函数"""
    print("🚀 共享剪切板客户端打包工具")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        print("❌ 依赖检查失败，请先安装所需依赖")
        return 1
    
    # 清理构建目录
    clean_build()
    
    # 构建可执行文件
    if not build_executable():
        print("❌ 构建失败")
        return 1
    
    # 创建发布包
    if not create_distribution():
        print("❌ 创建发布包失败")
        return 1
    
    print("\n🎉 打包完成!")
    print("可执行文件位于 release 目录中")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
