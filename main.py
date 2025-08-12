#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享剪切板客户端 - 主程序
基于PyQt5的Windows剪切板同步软件
"""

import sys
import os
import json
import asyncio
import pyperclip
from typing import Dict, Any, Optional
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QSystemTrayIcon, QMenu, QAction, QMessageBox,
                             QTabWidget, QGroupBox, QCheckBox, QSpinBox,
                             QDialog, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QIcon, QPixmap, QFont

# 添加fun目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'fun'))

from clipboard_api import ClipboardAPI
from websocket_api import WebSocketAPI
from clipboard_client import ClipboardSyncClient
from devices_api import DevicesAPI


class DeviceListDialog(QDialog):
    """设备列表对话框"""

    def __init__(self, device_data, parent=None):
        super().__init__(parent)
        self.device_data = device_data
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("在线设备列表")
        self.setGeometry(200, 200, 500, 400)

        layout = QVBoxLayout(self)

        # 标题
        title_label = QLabel("当前在线设备:")
        title_label.setFont(QFont("", 12, QFont.Bold))
        layout.addWidget(title_label)

        # 设备列表
        self.device_list = QListWidget()
        layout.addWidget(self.device_list)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        # 填充设备数据
        self.populate_device_list()

    def populate_device_list(self):
        """填充设备列表"""
        if not self.device_data:
            item = QListWidgetItem("暂无在线设备")
            self.device_list.addItem(item)
            return

        device_count_map = {}

        # 统计每个设备的连接数
        for device_item in self.device_data:
            if isinstance(device_item, dict) and 'deviceId' in device_item:
                device_id = device_item['deviceId']
                connection_id = device_item.get('connectionId', '未知')

                if device_id not in device_count_map:
                    device_count_map[device_id] = []
                device_count_map[device_id].append(connection_id)

        # 添加到列表
        for device_id, connections in device_count_map.items():
            connection_count = len(connections)
            item_text = f"{device_id} ({connection_count} 个连接)"
            item = QListWidgetItem(item_text)

            # 添加详细信息到工具提示
            tooltip_text = f"设备ID: {device_id}\n连接数: {connection_count}\n连接ID:\n"
            for i, conn_id in enumerate(connections, 1):
                tooltip_text += f"  {i}. {conn_id}\n"
            item.setToolTip(tooltip_text.strip())

            self.device_list.addItem(item)


class WebSocketThread(QThread):
    """WebSocket连接线程"""

    message_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, ws_url: str, device_id: str, security_headers: Dict[str, str] = None):
        super().__init__()
        self.ws_url = ws_url
        self.device_id = device_id
        self.security_headers = security_headers or {}
        self.websocket = None
        self.is_running = False

    def run(self):
        """运行WebSocket连接"""
        self.is_running = True
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 运行WebSocket客户端
            loop.run_until_complete(self.connect_websocket())

        except Exception as e:
            self.error_occurred.emit(f"WebSocket连接错误: {str(e)}")
        finally:
            self.is_running = False

    async def connect_websocket(self):
        """连接WebSocket服务器"""
        try:
            import websockets

            # 构建WebSocket URL
            ws_url = self.ws_url
            if '?' in ws_url:
                ws_url += f"&deviceId={self.device_id}"
            else:
                ws_url += f"?deviceId={self.device_id}"

            # 添加安全参数到URL中
            if self.security_headers:
                for key, value in self.security_headers.items():
                    ws_url += f"&authKey={key}&authValue={value}"

            # 直接使用websockets库连接
            self.websocket = await websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10
            )

            self.connection_status_changed.emit(True)

            # 监听消息
            await self.listen_messages()

        except Exception as e:
            self.error_occurred.emit(f"WebSocket连接失败: {str(e)}")

    async def listen_messages(self):
        """监听WebSocket消息"""
        try:
            while self.is_running and self.websocket:
                try:
                    # 直接从websocket接收消息
                    message = await self.websocket.recv()
                    data = json.loads(message)
                    self.message_received.emit(data)

                except Exception as e:
                    if self.is_running:
                        self.error_occurred.emit(f"接收消息失败: {str(e)}")
                    break

        except Exception as e:
            self.error_occurred.emit(f"监听消息失败: {str(e)}")
        finally:
            self.connection_status_changed.emit(False)

    def stop(self):
        """停止WebSocket连接"""
        self.is_running = False
        if self.websocket:
            try:
                # 创建一个新的事件循环来关闭websocket
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket.close())
                loop.close()
            except:
                pass
        self.quit()
        self.wait()


class ClipboardSyncApp(QMainWindow):
    """剪切板同步应用主窗口"""
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings('ClipboardSync', 'Settings')
        self.clipboard_client = None
        self.websocket_thread = None
        self.is_monitoring = False
        self.is_syncing = False

        # 初始化UI
        self.init_ui()
        self.init_system_tray()
        self.load_settings()

        # 初始化剪切板监听
        self.clipboard_timer = QTimer()
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.last_clipboard_content = ""

        # 初始化设备统计定时器（延迟启动，确保UI完全初始化）
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_connection_stats)
        self.current_device_data = []  # 存储当前设备数据
        QTimer.singleShot(2000, self.start_stats_timer)  # 2秒后启动统计定时器
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("共享剪切板同步工具")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 状态页面
        self.create_status_tab()
        
        # 设置页面
        self.create_settings_tab()
        
        # 日志页面
        self.create_log_tab()
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        self.start_monitor_btn = QPushButton("开始单向同步")
        self.start_monitor_btn.clicked.connect(self.toggle_monitoring)
        button_layout.addWidget(self.start_monitor_btn)
        
        self.start_sync_btn = QPushButton("开始双向同步")
        self.start_sync_btn.clicked.connect(self.toggle_syncing)
        button_layout.addWidget(self.start_sync_btn)
        
        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.show_settings)
        button_layout.addWidget(self.settings_btn)
        
        button_layout.addStretch()
        
        self.hide_btn = QPushButton("隐藏到托盘")
        self.hide_btn.clicked.connect(self.hide_to_tray)
        button_layout.addWidget(self.hide_btn)
        
        main_layout.addLayout(button_layout)
        
    def create_status_tab(self):
        """创建状态页面"""
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)
        
        # 连接状态组
        connection_group = QGroupBox("连接状态")
        connection_layout = QVBoxLayout(connection_group)
        
        self.server_status_label = QLabel("服务器状态: 未连接")
        self.websocket_status_label = QLabel("WebSocket状态: 未连接")
        self.monitor_status_label = QLabel("监听状态: 未启动")
        self.sync_status_label = QLabel("同步状态: 未启动")
        
        connection_layout.addWidget(self.server_status_label)
        connection_layout.addWidget(self.websocket_status_label)
        connection_layout.addWidget(self.monitor_status_label)
        connection_layout.addWidget(self.sync_status_label)
        
        layout.addWidget(connection_group)
        
        # 统计信息组
        stats_group = QGroupBox("统计信息")
        stats_layout = QVBoxLayout(stats_group)

        self.items_count_label = QLabel("剪切板项目数: 0")
        self.last_sync_label = QLabel("最后同步时间: 无")

        stats_layout.addWidget(self.items_count_label)
        stats_layout.addWidget(self.last_sync_label)

        layout.addWidget(stats_group)

        # 设备连接统计组
        devices_group = QGroupBox("设备连接统计")
        devices_layout = QVBoxLayout(devices_group)

        self.total_connections_label = QLabel("总连接数: 0")
        self.active_connections_label = QLabel("活跃连接数: 0")
        self.connected_devices_label = QLabel("在线设备数: 0")

        # 设备列表按钮
        self.device_list_btn = QPushButton("查看设备列表")
        self.device_list_btn.clicked.connect(self.show_device_list)
        self.device_list_btn.setEnabled(False)  # 初始状态禁用

        devices_layout.addWidget(self.total_connections_label)
        devices_layout.addWidget(self.active_connections_label)
        devices_layout.addWidget(self.connected_devices_label)
        devices_layout.addWidget(self.device_list_btn)

        layout.addWidget(devices_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(status_widget, "状态")
        
    def create_settings_tab(self):
        """创建设置页面"""
        settings_widget = QWidget()
        layout = QVBoxLayout(settings_widget)
        
        # 服务器配置组
        server_group = QGroupBox("服务器配置")
        server_layout = QVBoxLayout(server_group)
        
        from PyQt5.QtWidgets import QLineEdit, QFormLayout
        
        form_layout = QFormLayout()
        
        self.server_ip_edit = QLineEdit()
        self.server_ip_edit.setPlaceholderText("例如: 192.168.1.100")
        form_layout.addRow("服务器IP地址:", self.server_ip_edit)
        
        self.api_port_edit = QLineEdit()
        self.api_port_edit.setPlaceholderText("默认: 3001")
        self.api_port_edit.setText("3001")
        form_layout.addRow("API端口:", self.api_port_edit)
        
        self.ws_port_edit = QLineEdit()
        self.ws_port_edit.setPlaceholderText("默认: 3002")
        self.ws_port_edit.setText("3002")
        form_layout.addRow("WebSocket端口:", self.ws_port_edit)
        
        server_layout.addLayout(form_layout)
        layout.addWidget(server_group)
        
        # 安全配置组
        security_group = QGroupBox("安全配置")
        security_layout = QVBoxLayout(security_group)
        
        security_form = QFormLayout()
        
        self.auth_key_edit = QLineEdit()
        self.auth_key_edit.setPlaceholderText("例如: X-API-Key")
        security_form.addRow("认证头名称:", self.auth_key_edit)
        
        self.auth_value_edit = QLineEdit()
        self.auth_value_edit.setPlaceholderText("例如: your-api-key")
        self.auth_value_edit.setEchoMode(QLineEdit.Password)
        security_form.addRow("认证头值:", self.auth_value_edit)
        
        security_layout.addLayout(security_form)
        layout.addWidget(security_group)
        
        # 其他设置组
        other_group = QGroupBox("其他设置")
        other_layout = QVBoxLayout(other_group)
        
        self.auto_start_check = QCheckBox("开机自启动")
        self.minimize_to_tray_check = QCheckBox("启动时最小化到托盘")
        self.enable_notifications_check = QCheckBox("启用通知")
        self.enable_notifications_check.setChecked(True)
        self.check_interval_spin = QSpinBox()
        self.check_interval_spin.setRange(100, 5000)
        self.check_interval_spin.setValue(500)
        self.check_interval_spin.setSuffix(" ms")

        other_layout.addWidget(self.auto_start_check)
        other_layout.addWidget(self.minimize_to_tray_check)
        other_layout.addWidget(self.enable_notifications_check)
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("剪切板检查间隔:"))
        interval_layout.addWidget(self.check_interval_spin)
        interval_layout.addStretch()
        other_layout.addLayout(interval_layout)
        
        layout.addWidget(other_group)
        
        # 保存按钮
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        self.tab_widget.addTab(settings_widget, "设置")
        
    def create_log_tab(self):
        """创建日志页面"""
        log_widget = QWidget()
        layout = QVBoxLayout(log_widget)
        
        # 日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # 日志控制按钮
        log_button_layout = QHBoxLayout()
        
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.clear_log)
        log_button_layout.addWidget(clear_log_btn)
        
        log_button_layout.addStretch()
        
        layout.addLayout(log_button_layout)
        
        self.tab_widget.addTab(log_widget, "日志")
        
    def init_system_tray(self):
        """初始化系统托盘"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(self, "系统托盘", "系统不支持托盘功能")
            return
            
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置图标 (这里使用默认图标，实际应用中应该使用自定义图标)
        self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        self.tray_icon.setToolTip("共享剪切板同步工具")
        
        # 创建托盘菜单
        tray_menu = QMenu()
        
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        start_monitor_action = QAction("开始单向同步", self)
        start_monitor_action.triggered.connect(self.toggle_monitoring)
        tray_menu.addAction(start_monitor_action)
        
        start_sync_action = QAction("开始双向同步", self)
        start_sync_action.triggered.connect(self.toggle_syncing)
        tray_menu.addAction(start_sync_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # 托盘图标双击事件
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
    def tray_icon_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_main_window()
            
    def show_main_window(self):
        """显示主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()
        
    def hide_to_tray(self):
        """隐藏到托盘"""
        self.hide()
        self.tray_icon.showMessage(
            "共享剪切板",
            "应用程序已最小化到托盘",
            QSystemTrayIcon.Information,
            2000
        )
        
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.tray_icon.isVisible():
            self.hide_to_tray()
            event.ignore()
        else:
            event.accept()
            
    def quit_application(self):
        """退出应用程序"""
        self.cleanup()
        QApplication.quit()
        
    def cleanup(self):
        """清理资源"""
        if self.clipboard_timer.isActive():
            self.clipboard_timer.stop()
        if self.is_monitoring:
            self.stop_monitoring()
        if self.is_syncing:
            self.stop_syncing()
        if self.websocket_thread:
            self.websocket_thread.stop()
        
    def log_message(self, message: str):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)

    def show_notification(self, title: str, message: str, icon=QSystemTrayIcon.Information):
        """显示系统通知"""
        if self.enable_notifications_check.isChecked() and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon, 3000)
        
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        
    def show_settings(self):
        """显示设置页面"""
        self.tab_widget.setCurrentIndex(1)  # 切换到设置页面
        
    def load_settings(self):
        """加载设置"""
        self.server_ip_edit.setText(self.settings.value('server_ip', ''))
        self.api_port_edit.setText(self.settings.value('api_port', '3001'))
        self.ws_port_edit.setText(self.settings.value('ws_port', '3002'))
        self.auth_key_edit.setText(self.settings.value('auth_key', ''))
        self.auth_value_edit.setText(self.settings.value('auth_value', ''))
        self.auto_start_check.setChecked(self.settings.value('auto_start', False, type=bool))
        self.minimize_to_tray_check.setChecked(self.settings.value('minimize_to_tray', False, type=bool))
        self.enable_notifications_check.setChecked(self.settings.value('enable_notifications', True, type=bool))
        self.check_interval_spin.setValue(self.settings.value('check_interval', 500, type=int))
        
    def save_settings(self):
        """保存设置"""
        self.settings.setValue('server_ip', self.server_ip_edit.text())
        self.settings.setValue('api_port', self.api_port_edit.text())
        self.settings.setValue('ws_port', self.ws_port_edit.text())
        self.settings.setValue('auth_key', self.auth_key_edit.text())
        self.settings.setValue('auth_value', self.auth_value_edit.text())
        self.settings.setValue('auto_start', self.auto_start_check.isChecked())
        self.settings.setValue('minimize_to_tray', self.minimize_to_tray_check.isChecked())
        self.settings.setValue('enable_notifications', self.enable_notifications_check.isChecked())
        self.settings.setValue('check_interval', self.check_interval_spin.value())
        
        self.log_message("设置已保存")
        QMessageBox.information(self, "设置", "设置已保存成功！")
        
    def get_api_base_url(self) -> str:
        """获取API基础URL"""
        server_ip = self.server_ip_edit.text().strip()
        api_port = self.api_port_edit.text().strip()
        if not server_ip:
            return "http://localhost:3001"
        return f"http://{server_ip}:{api_port}"
        
    def get_ws_url(self) -> str:
        """获取WebSocket URL"""
        server_ip = self.server_ip_edit.text().strip()
        ws_port = self.ws_port_edit.text().strip()
        if not server_ip:
            return "ws://localhost:3002/ws"
        return f"ws://{server_ip}:{ws_port}/ws"
        
    def get_security_headers(self) -> Dict[str, str]:
        """获取安全请求头"""
        auth_key = self.auth_key_edit.text().strip()
        auth_value = self.auth_value_edit.text().strip()
        if auth_key and auth_value:
            return {auth_key: auth_value}
        return {}
        
    def toggle_monitoring(self):
        """切换监听状态"""
        if not self.is_monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self):
        """开始剪切板监听"""
        try:
            # 检查是否已经在双向同步模式
            if self.is_syncing:
                QMessageBox.warning(self, "冲突提示", "双向同步已启动，无需再启动单向同步！\n双向同步已包含本地剪切板监听功能。")
                return

            # 检查服务器配置
            server_ip = self.server_ip_edit.text().strip()
            if not server_ip:
                QMessageBox.warning(self, "配置错误", "请先配置服务器IP地址！")
                return

            # 初始化API客户端
            base_url = self.get_api_base_url()
            security_headers = self.get_security_headers()

            self.clipboard_client = ClipboardAPI(base_url=base_url)
            if security_headers:
                self.clipboard_client.session.headers.update(security_headers)

            # 测试连接
            from health_api import HealthAPI
            health_api = HealthAPI(base_url=base_url)
            if security_headers:
                health_api.session.headers.update(security_headers)

            result = health_api.check_health()
            if not result.get('success'):
                QMessageBox.warning(self, "连接失败", f"无法连接到服务器: {result.get('message', '未知错误')}")
                return

            # 获取当前剪切板内容作为初始状态
            try:
                self.last_clipboard_content = pyperclip.paste()
            except Exception as e:
                self.log_message(f"获取剪切板内容失败: {str(e)}")
                self.last_clipboard_content = ""

            # 启动定时器
            interval = self.check_interval_spin.value()
            self.clipboard_timer.start(interval)

            self.is_monitoring = True
            self.start_monitor_btn.setText("停止单向同步")
            self.monitor_status_label.setText("监听状态: 运行中")
            self.server_status_label.setText("服务器状态: 已连接")

            self.log_message("剪切板监听已启动")
            self.show_notification("剪切板同步", "单向同步已启动")

        except Exception as e:
            self.log_message(f"启动监听失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"启动监听失败: {str(e)}")

    def stop_monitoring(self):
        """停止剪切板监听"""
        self.clipboard_timer.stop()
        self.is_monitoring = False
        self.start_monitor_btn.setText("开始单向同步")
        self.monitor_status_label.setText("监听状态: 未启动")
        self.server_status_label.setText("服务器状态: 未连接")

        self.log_message("剪切板监听已停止")
        self.show_notification("剪切板同步", "单向同步已停止")

    def toggle_syncing(self):
        """切换同步状态"""
        if not self.is_syncing:
            self.start_syncing()
        else:
            self.stop_syncing()

    def start_syncing(self):
        """开始双向同步"""
        try:
            # 检查是否已经在单向同步模式
            if self.is_monitoring:
                QMessageBox.warning(self, "冲突提示", "单向同步已启动，将自动停止单向同步并启动双向同步。")
                self.stop_monitoring()

            # 检查服务器配置
            server_ip = self.server_ip_edit.text().strip()
            if not server_ip:
                QMessageBox.warning(self, "配置错误", "请先配置服务器IP地址！")
                return

            # 立即初始化剪切板客户端和本地监听（双向同步的关键）
            base_url = self.get_api_base_url()
            security_headers = self.get_security_headers()

            self.clipboard_client = ClipboardAPI(base_url)
            if security_headers:
                self.clipboard_client.session.headers.update(security_headers)

            # 获取当前剪切板内容作为初始状态
            try:
                self.last_clipboard_content = pyperclip.paste()
            except Exception as e:
                self.log_message(f"获取剪切板内容失败: {str(e)}")
                self.last_clipboard_content = ""

            # 立即启动本地剪切板监听定时器
            interval = self.check_interval_spin.value()
            self.clipboard_timer.start(interval)
            self.log_message("双向同步：本地剪切板监听已启动")

            # 生成设备ID
            device_id = f"windows-client-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # 获取WebSocket URL和安全配置
            ws_url = self.get_ws_url()
            security_headers = self.get_security_headers()

            # 创建WebSocket线程
            self.websocket_thread = WebSocketThread(ws_url, device_id, security_headers)

            # 连接信号
            self.websocket_thread.message_received.connect(self.handle_websocket_message)
            self.websocket_thread.connection_status_changed.connect(self.handle_websocket_status)
            self.websocket_thread.error_occurred.connect(self.handle_websocket_error)

            # 启动线程
            self.websocket_thread.start()

            self.is_syncing = True
            self.start_sync_btn.setText("停止双向同步")
            self.sync_status_label.setText("同步状态: 连接中...")

            self.log_message("正在启动双向同步...")
            self.show_notification("剪切板同步", "双向同步已启动（包含本地监听）")

        except Exception as e:
            self.log_message(f"启动双向同步失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"启动双向同步失败: {str(e)}")

            # 如果启动失败，清理已启动的组件
            if self.clipboard_timer.isActive():
                self.clipboard_timer.stop()
            self.is_syncing = False

    def stop_syncing(self):
        """停止双向同步"""
        if self.websocket_thread:
            self.websocket_thread.stop()
            self.websocket_thread = None

        # 停止本地剪切板监听定时器
        if self.clipboard_timer.isActive():
            self.clipboard_timer.stop()
            self.log_message("双向同步：本地剪切板监听已停止")

        self.is_syncing = False
        self.start_sync_btn.setText("开始双向同步")
        self.sync_status_label.setText("同步状态: 未启动")
        self.websocket_status_label.setText("WebSocket状态: 未连接")

        self.log_message("双向同步已停止")
        self.show_notification("剪切板同步", "双向同步已停止")

    def handle_websocket_message(self, data: dict):
        """处理WebSocket消息"""
        try:
            # 根据消息类型处理
            message_type = data.get('type', '')

            if message_type == 'sync_content' or message_type == 'content_update' or message_type == 'sync':
                # 同步内容到剪切板
                # 处理不同的数据结构
                if 'data' in data and isinstance(data['data'], dict):
                    # 格式: {'type': 'sync', 'data': {'content': '...', 'type': 'text'}}
                    sync_data = data['data']
                    content = sync_data.get('content', '')
                    content_type = sync_data.get('type', 'text')
                else:
                    # 格式: {'type': 'sync_content', 'content': '...', 'contentType': 'text'}
                    content = data.get('content', '')
                    content_type = data.get('contentType', 'text')

                if content and content != self.last_clipboard_content:
                    if content_type == 'text':
                        pyperclip.copy(content)
                        self.last_clipboard_content = content
                        self.log_message(f"收到同步内容: {content[:50]}{'...' if len(content) > 50 else ''}")
                        self.show_notification("剪切板同步", f"收到新内容: {content[:30]}{'...' if len(content) > 30 else ''}")
                    else:
                        self.log_message(f"收到非文本内容，类型: {content_type}")

            elif message_type == 'ping' or message_type == 'heartbeat':
                # 心跳消息
                self.log_message("收到心跳消息")

            elif message_type == 'device_connected':
                # 设备连接通知
                device_id = data.get('deviceId', '未知设备')
                self.log_message(f"设备已连接: {device_id}")

            elif message_type == 'device_disconnected':
                # 设备断开通知
                device_id = data.get('deviceId', '未知设备')
                self.log_message(f"设备已断开: {device_id}")

            elif message_type == 'connection_stats':
                # 连接统计信息
                # 尝试不同的数据结构
                if 'stats' in data:
                    stats = data['stats']
                elif 'data' in data:
                    stats = data['data']
                else:
                    stats = data

                connected_devices = stats.get('connectedDevices', stats.get('connected_devices', 0))
                total_connections = stats.get('totalConnections', stats.get('total_connections', 0))
                active_connections = stats.get('activeConnections', stats.get('active_connections', 0))

                # 如果统计数据都是0，可能是数据结构不对，记录原始数据
                if connected_devices == 0 and total_connections == 0 and active_connections == 0:
                    self.log_message(f"连接统计数据结构: {str(data)}")
                else:
                    self.log_message(f"连接统计: {connected_devices} 个设备在线，总连接数: {total_connections}，活跃连接: {active_connections}")

            elif message_type == 'server_info':
                # 服务器信息
                server_info = data.get('info', {})
                version = server_info.get('version', '未知')
                self.log_message(f"服务器信息: 版本 {version}")

            elif message_type == 'welcome':
                # 欢迎消息
                welcome_msg = data.get('message', '欢迎连接')
                self.log_message(f"服务器欢迎: {welcome_msg}")

            elif message_type == 'error':
                # 错误消息
                error_msg = data.get('message', '未知错误')
                self.log_message(f"服务器错误: {error_msg}")
                self.show_notification("剪切板同步", f"服务器错误: {error_msg}", QSystemTrayIcon.Warning)

            else:
                # 记录未知消息类型，但不显示为错误
                self.log_message(f"收到消息类型: {message_type} (数据: {str(data)[:100]}{'...' if len(str(data)) > 100 else ''})")

        except Exception as e:
            self.log_message(f"处理WebSocket消息失败: {str(e)}")

    def handle_websocket_status(self, connected: bool):
        """处理WebSocket连接状态变化"""
        if connected:
            self.websocket_status_label.setText("WebSocket状态: 已连接")
            self.sync_status_label.setText("同步状态: 运行中")
            self.log_message("WebSocket连接成功，双向同步完全启动")
            self.show_notification("剪切板同步", "双向同步已完全连接")
        else:
            self.websocket_status_label.setText("WebSocket状态: 未连接")
            if self.is_syncing:
                self.sync_status_label.setText("同步状态: WebSocket断开（本地监听仍运行）")
                self.show_notification("剪切板同步", "WebSocket连接断开", QSystemTrayIcon.Warning)
                self.log_message("WebSocket连接断开，但本地剪切板监听继续运行")
            else:
                self.log_message("WebSocket连接断开")

    def handle_websocket_error(self, error_message: str):
        """处理WebSocket错误"""
        self.log_message(f"WebSocket错误: {error_message}")
        self.websocket_status_label.setText("WebSocket状态: 错误")
        if self.is_syncing:
            self.sync_status_label.setText("同步状态: 错误")

    def check_clipboard(self):
        """检查剪切板变化"""
        try:
            current_content = pyperclip.paste()

            # 检查内容是否发生变化
            if current_content != self.last_clipboard_content and current_content.strip():
                self.last_clipboard_content = current_content
                self.send_clipboard_content(current_content)

        except Exception as e:
            self.log_message(f"检查剪切板失败: {str(e)}")

    def send_clipboard_content(self, content: str):
        """发送剪切板内容到服务器"""
        try:
            if not self.clipboard_client:
                self.log_message("剪切板客户端未初始化")
                return

            # 检查内容长度
            if len(content) > 10000:  # 限制内容长度
                self.log_message(f"剪切板内容过长({len(content)}字符)，跳过同步")
                return

            # 生成设备ID
            device_id = f"windows-client-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # 发送文本内容
            result = self.clipboard_client.create_text_item(content, device_id)

            if result.get('success'):
                self.log_message(f"剪切板内容已同步: {content[:50]}{'...' if len(content) > 50 else ''}")
                self.last_sync_label.setText(f"最后同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                # 更新统计信息
                try:
                    items_result = self.clipboard_client.get_clipboard_items(limit=1)
                    if items_result.get('success'):
                        data = items_result.get('data')
                        if isinstance(data, dict):
                            # 如果data是字典，尝试获取total字段
                            total = data.get('total', 0)
                        elif isinstance(data, list):
                            # 如果data是列表，使用列表长度作为近似值
                            total = len(data)
                            # 但这只是当前页的数量，不是总数，所以显示不同的信息
                            self.items_count_label.setText(f"剪切板项目数: ≥{total}")
                            return
                        else:
                            total = 0
                        self.items_count_label.setText(f"剪切板项目数: {total}")
                except Exception as stats_error:
                    self.log_message(f"更新统计信息失败: {str(stats_error)}")

            else:
                error_msg = result.get('message', '未知错误')
                self.log_message(f"同步失败: {error_msg}")

                # 如果是网络错误，可能需要重新连接
                if "连接" in error_msg or "网络" in error_msg:
                    self.server_status_label.setText("服务器状态: 连接异常")

        except Exception as e:
            self.log_message(f"发送剪切板内容失败: {str(e)}")
            self.server_status_label.setText("服务器状态: 发送失败")

    def start_stats_timer(self):
        """启动统计定时器"""
        self.stats_timer.start(5000)  # 每5秒更新一次统计信息
        self.update_connection_stats()  # 立即更新一次

    def show_device_list(self):
        """显示设备列表对话框"""
        dialog = DeviceListDialog(self.current_device_data, self)
        dialog.exec_()

    def format_device_name(self, device_id: str) -> str:
        """
        格式化设备名称显示

        Args:
            device_id: 原始设备ID

        Returns:
            str: 格式化后的设备名称
        """
        if not device_id:
            return "未知设备"

        # 处理常见的设备ID格式
        if device_id.startswith('device_'):
            # 格式: device_1754909073348_j1bgar934 -> j1bgar934
            parts = device_id.split('_')
            if len(parts) >= 3:
                return parts[-1]  # 返回最后一部分作为设备标识
            elif len(parts) == 2:
                return f"设备{parts[1][:6]}"  # 返回时间戳的前6位
        elif device_id.startswith('windows-client-'):
            # 格式: windows-client-20250812165436 -> Windows客户端
            timestamp = device_id.replace('windows-client-', '')
            if len(timestamp) >= 8:
                # 提取日期部分: 20250812 -> 08-12
                date_part = timestamp[4:6] + "-" + timestamp[6:8]
                return f"Windows({date_part})"
            return "Windows客户端"
        elif device_id == 'cs':
            # 特殊设备ID
            return "控制台"
        elif len(device_id) > 20:
            # 长ID截断显示
            return device_id[:15] + "..."
        else:
            # 短ID直接显示
            return device_id

    def update_connection_stats(self):
        """更新设备连接统计信息"""
        try:
            # 检查UI元素是否已初始化
            if not hasattr(self, 'server_ip_edit') or not hasattr(self, 'total_connections_label'):
                return

            # 获取服务器配置
            server_ip = self.server_ip_edit.text() or "localhost"
            api_port = self.api_port_edit.text() or "3001"
            base_url = f"http://{server_ip}:{api_port}"

            # 获取安全认证配置
            security_headers = self.get_security_headers()

            # 创建设备API客户端
            devices_api = DevicesAPI(base_url, security_headers)

            # 获取连接统计
            stats_result = devices_api.get_connection_stats()

            if stats_result.get('success'):
                data = stats_result.get('data', {})

                # 更新统计标签
                total_connections = data.get('totalConnections', 0)
                active_connections = data.get('activeConnections', 0)
                connected_devices = data.get('connectedDevices', [])

                self.total_connections_label.setText(f"总连接数: {total_connections}")
                self.active_connections_label.setText(f"活跃连接数: {active_connections}")

                # 保存设备数据并更新设备数量显示
                self.current_device_data = connected_devices
                if connected_devices and isinstance(connected_devices, list):
                    # 统计唯一设备数量
                    unique_devices = set()
                    for device_item in connected_devices:
                        if isinstance(device_item, dict) and 'deviceId' in device_item:
                            unique_devices.add(device_item['deviceId'])

                    device_count = len(unique_devices)
                    self.connected_devices_label.setText(f"在线设备数: {device_count}")
                    self.device_list_btn.setEnabled(device_count > 0)
                    self.device_list_btn.setText(f"查看设备列表 ({device_count})")
                else:
                    self.connected_devices_label.setText("在线设备数: 0")
                    self.device_list_btn.setEnabled(False)
                    self.device_list_btn.setText("查看设备列表")

            else:
                # 连接失败时显示详细错误信息
                error_msg = stats_result.get('message', '未知错误')
                status_code = stats_result.get('status_code', 'N/A')

                self.total_connections_label.setText(f"总连接数: 获取失败 ({status_code})")
                self.active_connections_label.setText(f"活跃连接数: 获取失败")
                self.connected_devices_label.setText(f"在线设备数: 获取失败")
                self.device_list_btn.setEnabled(False)
                self.device_list_btn.setText("查看设备列表")
                self.current_device_data = []

                # 记录详细错误到日志
                self.log_message(f"获取连接统计失败: {error_msg} (状态码: {status_code})")

        except Exception as e:
            # 异常时显示错误信息
            error_detail = str(e)
            self.total_connections_label.setText("总连接数: 连接异常")
            self.active_connections_label.setText("活跃连接数: 连接异常")
            self.connected_devices_label.setText("在线设备数: 连接异常")
            self.device_list_btn.setEnabled(False)
            self.device_list_btn.setText("查看设备列表")
            self.current_device_data = []

            # 记录详细错误到日志
            self.log_message(f"连接统计异常: {error_detail}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序信息
    app.setApplicationName("共享剪切板同步工具")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ClipboardSync")
    
    # 检查是否支持系统托盘
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "系统托盘", 
                           "系统不支持托盘功能，程序将无法正常运行。")
        sys.exit(1)
    
    # 创建主窗口
    window = ClipboardSyncApp()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
