#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享剪切板客户端安装脚本
"""

import os
import sys
import subprocess
import platform

def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print("错误: 需要Python 3.7或更高版本")
        print(f"当前版本: {version.major}.{version.minor}.{version.micro}")
        return False
    return True

def install_dependencies():
    """安装依赖包"""
    print("正在安装依赖包...")
    
    try:
        # 升级pip
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        
        # 安装依赖
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        
        print("依赖包安装成功！")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"安装失败: {e}")
        return False

def create_desktop_shortcut():
    """创建桌面快捷方式 (仅Windows)"""
    if platform.system() != "Windows":
        return
        
    try:
        import winshell
        from win32com.client import Dispatch
        
        desktop = winshell.desktop()
        path = os.path.join(desktop, "共享剪切板同步工具.lnk")
        target = os.path.join(os.getcwd(), "启动.bat")
        wDir = os.getcwd()
        icon = target
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(path)
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = wDir
        shortcut.IconLocation = icon
        shortcut.save()
        
        print("桌面快捷方式创建成功！")
        
    except ImportError:
        print("提示: 安装pywin32可以创建桌面快捷方式")
        print("运行: pip install pywin32 winshell")
    except Exception as e:
        print(f"创建快捷方式失败: {e}")

def main():
    """主函数"""
    print("共享剪切板同步工具 - 安装程序")
    print("=" * 40)
    
    # 检查Python版本
    if not check_python_version():
        input("按回车键退出...")
        sys.exit(1)
    
    print(f"Python版本检查通过: {sys.version}")
    
    # 安装依赖
    if not install_dependencies():
        input("按回车键退出...")
        sys.exit(1)
    
    # 创建快捷方式
    create_desktop_shortcut()
    
    print("\n安装完成！")
    print("您可以通过以下方式启动程序:")
    print("1. 双击 启动.bat")
    print("2. 运行 python run.py")
    print("3. 运行 python main.py")
    
    if platform.system() == "Windows":
        print("4. 使用桌面快捷方式")
    
    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
