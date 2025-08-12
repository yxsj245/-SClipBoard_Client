#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图标转换脚本
将PNG图标转换为ICO格式，用于Windows exe文件
"""

import os
import sys
from PIL import Image

def convert_png_to_ico(png_path, ico_path):
    """
    将PNG图标转换为ICO格式
    
    Args:
        png_path: PNG文件路径
        ico_path: 输出的ICO文件路径
    """
    try:
        # 打开PNG图像
        img = Image.open(png_path)
        
        # 确保图像是RGBA模式（支持透明度）
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 创建多个尺寸的图标（Windows推荐的尺寸）
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        
        # 调整图像大小并保存为ICO
        img.save(ico_path, format='ICO', sizes=sizes)
        
        print(f"✅ 图标转换成功: {png_path} -> {ico_path}")
        return True
        
    except Exception as e:
        print(f"❌ 图标转换失败: {str(e)}")
        return False

def main():
    """主函数"""
    print("🎨 图标转换工具")
    print("=" * 30)
    
    # 检查PIL是否安装
    try:
        from PIL import Image
    except ImportError:
        print("❌ 需要安装Pillow库")
        print("请运行: pip install Pillow")
        return 1
    
    # 源PNG文件
    png_file = "画板 1.png"
    ico_file = "icon.ico"
    
    if not os.path.exists(png_file):
        print(f"❌ 找不到PNG文件: {png_file}")
        return 1
    
    # 转换图标
    if convert_png_to_ico(png_file, ico_file):
        print(f"✅ ICO图标已创建: {ico_file}")
        print("现在可以在PyInstaller中使用这个ICO文件了")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
