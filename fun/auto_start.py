#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开机自启动功能模块
支持Windows系统的开机自启动设置
"""

import os
import sys
import platform
import winreg
from typing import Optional, Tuple


class AutoStartManager:
    """开机自启动管理器"""
    
    def __init__(self, app_name: str = "共享剪切板同步工具"):
        self.app_name = app_name
        self.registry_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        
    def get_executable_path(self) -> str:
        """获取可执行文件路径"""
        if getattr(sys, 'frozen', False):
            # 如果是打包后的可执行文件
            return sys.executable
        else:
            # 如果是Python脚本，返回Python解释器和脚本路径
            script_path = os.path.abspath(sys.argv[0])
            if script_path.endswith('main.py'):
                # 如果当前是main.py，直接使用
                return f'"{sys.executable}" "{script_path}"'
            else:
                # 否则查找main.py
                main_py = os.path.join(os.path.dirname(script_path), 'main.py')
                if os.path.exists(main_py):
                    return f'"{sys.executable}" "{main_py}"'
                else:
                    return f'"{sys.executable}" "{script_path}"'
    
    def is_supported(self) -> bool:
        """检查是否支持开机自启动"""
        return platform.system() == "Windows"
    
    def is_enabled(self) -> Tuple[bool, Optional[str]]:
        """
        检查开机自启动是否已启用
        
        Returns:
            Tuple[bool, Optional[str]]: (是否启用, 错误信息)
        """
        if not self.is_supported():
            return False, "不支持的操作系统"
        
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_READ) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, self.app_name)
                    return True, None
                except FileNotFoundError:
                    return False, None
        except Exception as e:
            return False, f"检查注册表失败: {str(e)}"
    
    def enable(self) -> Tuple[bool, Optional[str]]:
        """
        启用开机自启动
        
        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        if not self.is_supported():
            return False, "不支持的操作系统"
        
        try:
            executable_path = self.get_executable_path()
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, executable_path)
            
            return True, None
            
        except Exception as e:
            return False, f"设置开机自启动失败: {str(e)}"
    
    def disable(self) -> Tuple[bool, Optional[str]]:
        """
        禁用开机自启动
        
        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        if not self.is_supported():
            return False, "不支持的操作系统"
        
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_WRITE) as key:
                try:
                    winreg.DeleteValue(key, self.app_name)
                    return True, None
                except FileNotFoundError:
                    # 如果注册表项不存在，认为已经禁用了
                    return True, None
                    
        except Exception as e:
            return False, f"禁用开机自启动失败: {str(e)}"
    
    def toggle(self, enable: bool) -> Tuple[bool, Optional[str]]:
        """
        切换开机自启动状态
        
        Args:
            enable: True为启用，False为禁用
            
        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        if enable:
            return self.enable()
        else:
            return self.disable()
    
    def get_status_info(self) -> dict:
        """
        获取开机自启动状态信息
        
        Returns:
            dict: 包含状态信息的字典
        """
        if not self.is_supported():
            return {
                "supported": False,
                "enabled": False,
                "error": "不支持的操作系统",
                "executable_path": None
            }
        
        enabled, error = self.is_enabled()
        executable_path = self.get_executable_path() if enabled else None
        
        return {
            "supported": True,
            "enabled": enabled,
            "error": error,
            "executable_path": executable_path
        }


def test_auto_start():
    """测试开机自启动功能"""
    print("=== 开机自启动功能测试 ===")
    
    manager = AutoStartManager()
    
    # 检查系统支持
    if not manager.is_supported():
        print("❌ 当前系统不支持开机自启动功能")
        return
    
    print("✅ 系统支持开机自启动功能")
    
    # 获取状态信息
    status = manager.get_status_info()
    print(f"当前状态: {'已启用' if status['enabled'] else '未启用'}")
    
    if status['executable_path']:
        print(f"可执行文件路径: {status['executable_path']}")
    
    if status['error']:
        print(f"错误信息: {status['error']}")
    
    # 测试启用
    print("\n测试启用开机自启动...")
    success, error = manager.enable()
    if success:
        print("✅ 启用成功")
    else:
        print(f"❌ 启用失败: {error}")
    
    # 再次检查状态
    enabled, _ = manager.is_enabled()
    print(f"启用后状态: {'已启用' if enabled else '未启用'}")
    
    # 测试禁用
    print("\n测试禁用开机自启动...")
    success, error = manager.disable()
    if success:
        print("✅ 禁用成功")
    else:
        print(f"❌ 禁用失败: {error}")
    
    # 最终检查状态
    enabled, _ = manager.is_enabled()
    print(f"禁用后状态: {'已启用' if enabled else '未启用'}")


if __name__ == "__main__":
    test_auto_start()
