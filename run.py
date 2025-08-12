#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享剪切板客户端启动脚本
"""

import sys
import os

def check_dependencies():
    """检查依赖包"""
    required_packages = [
        ('PyQt5', 'PyQt5'),
        ('requests', 'requests'),
        ('websockets', 'websockets'),
        ('pyperclip', 'pyperclip')
    ]
    
    missing_packages = []
    
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)
    
    if missing_packages:
        print("缺少以下依赖包:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\n请运行以下命令安装依赖:")
        print("pip install -r requirements.txt")
        return False
    
    return True

def main():
    """主函数"""
    print("共享剪切板同步工具 v1.0.0")
    print("=" * 40)
    
    # 检查依赖
    if not check_dependencies():
        input("按回车键退出...")
        sys.exit(1)
    
    # 启动应用程序
    try:
        from main import main as app_main
        app_main()
    except Exception as e:
        print(f"启动失败: {str(e)}")
        input("按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    main()
