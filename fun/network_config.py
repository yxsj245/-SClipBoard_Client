#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络连接配置管理
用于统一管理网络超时设置和连接参数
"""

import json
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class NetworkTimeouts:
    """网络超时配置"""
    health_check: int = 5      # 健康检查超时（秒）
    api_request: int = 10      # 普通API请求超时（秒）
    file_operation: int = 30   # 文件操作超时（秒）
    websocket_connect: int = 10 # WebSocket连接超时（秒）
    websocket_ping: int = 10   # WebSocket ping超时（秒）
    websocket_ping_interval: int = 30  # WebSocket ping间隔（秒）


@dataclass
class NetworkConfig:
    """网络配置"""
    timeouts: NetworkTimeouts
    retry_count: int = 3       # 重试次数
    retry_delay: float = 1.0   # 重试延迟（秒）
    
    def __post_init__(self):
        if isinstance(self.timeouts, dict):
            self.timeouts = NetworkTimeouts(**self.timeouts)


class NetworkConfigManager:
    """网络配置管理器"""
    
    def __init__(self, config_file: str = "network_config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self._config: Optional[NetworkConfig] = None
    
    def load_config(self) -> NetworkConfig:
        """
        加载网络配置
        
        Returns:
            NetworkConfig: 网络配置对象
        """
        if self._config is not None:
            return self._config
            
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._config = NetworkConfig(**data)
            else:
                # 使用默认配置
                self._config = NetworkConfig(timeouts=NetworkTimeouts())
                self.save_config()
        except Exception as e:
            print(f"加载网络配置失败，使用默认配置: {e}")
            self._config = NetworkConfig(timeouts=NetworkTimeouts())
            
        return self._config
    
    def save_config(self) -> bool:
        """
        保存网络配置
        
        Returns:
            bool: 保存是否成功
        """
        try:
            if self._config is None:
                return False
                
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(self._config), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存网络配置失败: {e}")
            return False
    
    def update_timeouts(self, **kwargs) -> bool:
        """
        更新超时配置
        
        Args:
            **kwargs: 超时参数
            
        Returns:
            bool: 更新是否成功
        """
        try:
            config = self.load_config()
            
            # 更新超时设置
            for key, value in kwargs.items():
                if hasattr(config.timeouts, key):
                    setattr(config.timeouts, key, value)
            
            return self.save_config()
        except Exception as e:
            print(f"更新超时配置失败: {e}")
            return False
    
    def get_timeout(self, timeout_type: str) -> int:
        """
        获取指定类型的超时时间
        
        Args:
            timeout_type: 超时类型
            
        Returns:
            int: 超时时间（秒）
        """
        config = self.load_config()
        return getattr(config.timeouts, timeout_type, 10)
    
    def reset_to_defaults(self) -> bool:
        """
        重置为默认配置
        
        Returns:
            bool: 重置是否成功
        """
        try:
            self._config = NetworkConfig(timeouts=NetworkTimeouts())
            return self.save_config()
        except Exception as e:
            print(f"重置配置失败: {e}")
            return False
    
    def get_config_dict(self) -> Dict[str, Any]:
        """
        获取配置字典
        
        Returns:
            Dict: 配置字典
        """
        config = self.load_config()
        return asdict(config)


# 全局配置管理器实例
_config_manager = NetworkConfigManager()


def get_network_config() -> NetworkConfig:
    """获取网络配置"""
    return _config_manager.load_config()


def get_timeout(timeout_type: str) -> int:
    """获取超时时间"""
    return _config_manager.get_timeout(timeout_type)


def update_timeouts(**kwargs) -> bool:
    """更新超时配置"""
    return _config_manager.update_timeouts(**kwargs)


def save_network_config() -> bool:
    """保存网络配置"""
    return _config_manager.save_config()


if __name__ == "__main__":
    # 测试配置管理
    print("=== 网络配置管理测试 ===")
    
    # 加载配置
    config = get_network_config()
    print(f"当前配置: {asdict(config)}")
    
    # 更新超时设置
    print("\n更新超时设置...")
    update_timeouts(health_check=3, api_request=8)
    
    # 重新加载配置
    _config_manager._config = None  # 强制重新加载
    config = get_network_config()
    print(f"更新后配置: {asdict(config)}")
    
    # 获取特定超时
    print(f"\nAPI请求超时: {get_timeout('api_request')}秒")
    print(f"健康检查超时: {get_timeout('health_check')}秒")
    
    print("\n=== 测试完成 ===")
