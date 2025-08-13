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
import base64
import io
from typing import Dict, Any, Optional
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QSystemTrayIcon, QMenu, QAction, QMessageBox,
                             QTabWidget, QGroupBox, QCheckBox, QSpinBox,
                             QDialog, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QIcon, QPixmap, QFont, QClipboard
from PIL import Image

# 添加fun目录到路径
def add_fun_to_path():
    """添加fun目录到Python路径"""
    # 获取当前脚本的目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的可执行文件
        current_dir = os.path.dirname(sys.executable)
    else:
        # 如果是普通Python脚本
        current_dir = os.path.dirname(os.path.abspath(__file__))

    fun_dir = os.path.join(current_dir, 'fun')
    if os.path.exists(fun_dir) and fun_dir not in sys.path:
        sys.path.insert(0, fun_dir)

    # 也尝试添加当前目录，以防fun目录在同级
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

# 调用函数添加路径
add_fun_to_path()

try:
    from clipboard_api import ClipboardAPI
    from websocket_api import WebSocketAPI
    from network_config import get_network_config, update_timeouts, get_timeout
    from clipboard_client import ClipboardSyncClient
    from devices_api import DevicesAPI
    from auto_start import AutoStartManager
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保fun目录中的所有模块文件都存在")
    # 尝试从fun子包导入
    try:
        from fun.clipboard_api import ClipboardAPI
        from fun.websocket_api import WebSocketAPI
        from fun.network_config import get_network_config, update_timeouts, get_timeout
        from fun.clipboard_client import ClipboardSyncClient
        from fun.devices_api import DevicesAPI
        from fun.auto_start import AutoStartManager
        print("使用fun子包导入成功")
    except ImportError as e2:
        print(f"从fun子包导入也失败: {e2}")
        sys.exit(1)


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


class ClipboardContentDialog(QDialog):
    """剪切板内容列表对话框"""

    def __init__(self, clipboard_data, parent=None):
        super().__init__(parent)
        self.clipboard_data = clipboard_data
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("云端剪切板内容")
        self.setGeometry(200, 200, 700, 500)

        layout = QVBoxLayout(self)

        # 标题和统计信息
        title_label = QLabel(f"云端剪切板内容 (共 {len(self.clipboard_data)} 项):")
        title_label.setFont(QFont("", 12, QFont.Bold))
        layout.addWidget(title_label)

        # 内容列表
        self.content_list = QListWidget()
        self.content_list.itemDoubleClicked.connect(self.copy_selected_content)
        layout.addWidget(self.content_list)

        # 按钮布局
        button_layout = QHBoxLayout()

        # 复制按钮
        copy_btn = QPushButton("复制选中内容")
        copy_btn.clicked.connect(self.copy_selected_content)
        button_layout.addWidget(copy_btn)

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_content)
        button_layout.addWidget(refresh_btn)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # 填充剪切板数据
        self.populate_content_list()

    def populate_content_list(self):
        """填充剪切板内容列表"""
        self.content_list.clear()

        if not self.clipboard_data:
            item = QListWidgetItem("暂无剪切板内容")
            self.content_list.addItem(item)
            return

        for i, content_item in enumerate(self.clipboard_data):
            if isinstance(content_item, dict):
                content_type = content_item.get('type', 'unknown')
                content = content_item.get('content', '')
                device_id = content_item.get('deviceId', '未知设备')
                created_at = content_item.get('createdAt', content_item.get('timestamp', ''))

                # 格式化显示文本
                if content_type == 'text':
                    # 限制显示长度
                    display_content = content[:100] + ('...' if len(content) > 100 else '')
                    item_text = f"[文本] {display_content}"
                elif content_type == 'image':
                    item_text = f"[图片] {content_item.get('fileName', '图片文件')}"
                elif content_type == 'file':
                    item_text = f"[文件] {content_item.get('fileName', '文件')}"
                else:
                    item_text = f"[{content_type}] {str(content)[:50]}..."

                item = QListWidgetItem(item_text)

                # 设置工具提示
                tooltip_text = f"类型: {content_type}\n设备: {device_id}\n时间: {created_at}\n"
                if content_type == 'text' and content:
                    tooltip_text += f"内容: {content[:200]}{'...' if len(content) > 200 else ''}"
                elif content_type in ['image', 'file']:
                    tooltip_text += f"文件名: {content_item.get('fileName', '未知')}"

                item.setToolTip(tooltip_text)

                # 存储完整数据到item
                item.setData(Qt.UserRole, content_item)

                self.content_list.addItem(item)

    def copy_selected_content(self):
        """复制选中的内容到剪切板"""
        current_item = self.content_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择要复制的内容")
            return

        content_data = current_item.data(Qt.UserRole)
        if not content_data:
            QMessageBox.warning(self, "错误", "无法获取内容数据")
            return

        content_type = content_data.get('type', '')
        content = content_data.get('content', '')

        if content_type == 'text' and content:
            try:
                import pyperclip
                pyperclip.copy(content)
                QMessageBox.information(self, "成功", f"已复制文本内容到剪切板\n内容: {content[:50]}{'...' if len(content) > 50 else ''}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"复制失败: {str(e)}")
        elif content_type == 'image' and content:
            try:
                # 获取图片ID
                item_id = content_data.get('id')
                if not item_id:
                    QMessageBox.warning(self, "错误", "图片缺少ID信息")
                    return

                # 通过文件API下载图片
                parent_window = self.parent()
                if not parent_window:
                    QMessageBox.warning(self, "错误", "无法获取父窗口")
                    return

                try:
                    from files_api import FilesAPI
                    base_url = parent_window.get_api_base_url()
                    security_headers = parent_window.get_security_headers()

                    files_api = FilesAPI(base_url=base_url)
                    if security_headers:
                        files_api.session.headers.update(security_headers)

                    # 下载图片文件
                    result = files_api.download_file(item_id)

                    if not result.get('success'):
                        QMessageBox.warning(self, "错误", f"下载图片失败: {result.get('message', '未知错误')}")
                        return

                    image_bytes = result.get('content')
                    if not image_bytes:
                        QMessageBox.warning(self, "错误", "下载的图片数据为空")
                        return

                    # 转换为PIL Image
                    pil_image = Image.open(io.BytesIO(image_bytes))

                    # 转换为QPixmap
                    pixmap = parent_window.pil_image_to_pixmap(pil_image)

                    if not pixmap.isNull():
                        # 设置到剪切板
                        clipboard = QApplication.clipboard()
                        clipboard.setPixmap(pixmap)

                        file_name = content_data.get('fileName', '图片')
                        QMessageBox.information(self, "成功", f"已复制图片到剪切板\n文件: {file_name}")
                    else:
                        QMessageBox.warning(self, "错误", "图片转换失败")

                except Exception as inner_e:
                    QMessageBox.warning(self, "错误", f"处理图片时发生错误: {str(inner_e)}")

            except Exception as e:
                QMessageBox.warning(self, "错误", f"复制图片失败: {str(e)}")
                import traceback
                print(f"图片复制错误详情: {traceback.format_exc()}")
        else:
            QMessageBox.information(self, "提示", f"暂不支持复制 {content_type} 类型的内容")

    def refresh_content(self):
        """刷新内容列表"""
        # 通知父窗口刷新数据
        if self.parent():
            self.parent().request_clipboard_content_refresh()
        QMessageBox.information(self, "提示", "已请求刷新，请稍候...")


class NetworkTimeoutDialog(QDialog):
    """网络超时设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("网络超时设置")
        self.setFixedSize(400, 350)
        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()

        # 说明文本
        info_label = QLabel("调整网络连接超时时间，较短的超时可以更快发现连接问题，但可能导致网络较慢时连接失败。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # 超时设置组
        timeout_group = QGroupBox("超时设置（秒）")
        timeout_layout = QVBoxLayout()

        # 健康检查超时
        health_layout = QHBoxLayout()
        health_layout.addWidget(QLabel("健康检查超时:"))
        self.health_spin = QSpinBox()
        self.health_spin.setRange(1, 30)
        self.health_spin.setValue(5)
        self.health_spin.setToolTip("检查服务器是否可用的超时时间，建议3-10秒")
        health_layout.addWidget(self.health_spin)
        health_layout.addWidget(QLabel("秒"))
        health_layout.addStretch()
        timeout_layout.addLayout(health_layout)

        # API请求超时
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API请求超时:"))
        self.api_spin = QSpinBox()
        self.api_spin.setRange(3, 60)
        self.api_spin.setValue(10)
        self.api_spin.setToolTip("普通API请求的超时时间，建议5-15秒")
        api_layout.addWidget(self.api_spin)
        api_layout.addWidget(QLabel("秒"))
        api_layout.addStretch()
        timeout_layout.addLayout(api_layout)

        # WebSocket连接超时
        ws_layout = QHBoxLayout()
        ws_layout.addWidget(QLabel("WebSocket连接超时:"))
        self.ws_spin = QSpinBox()
        self.ws_spin.setRange(3, 60)
        self.ws_spin.setValue(10)
        self.ws_spin.setToolTip("WebSocket连接建立的超时时间，建议5-15秒")
        ws_layout.addWidget(self.ws_spin)
        ws_layout.addWidget(QLabel("秒"))
        ws_layout.addStretch()
        timeout_layout.addLayout(ws_layout)

        # 文件操作超时
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("文件操作超时:"))
        self.file_spin = QSpinBox()
        self.file_spin.setRange(10, 300)
        self.file_spin.setValue(30)
        self.file_spin.setToolTip("文件上传下载的超时时间，建议30-120秒")
        file_layout.addWidget(self.file_spin)
        file_layout.addWidget(QLabel("秒"))
        file_layout.addStretch()
        timeout_layout.addLayout(file_layout)

        timeout_group.setLayout(timeout_layout)
        layout.addWidget(timeout_group)

        # 预设按钮
        preset_group = QGroupBox("快速设置")
        preset_layout = QHBoxLayout()

        fast_btn = QPushButton("快速模式")
        fast_btn.setToolTip("适合网络良好的环境（超时时间较短）")
        fast_btn.clicked.connect(self.set_fast_mode)
        preset_layout.addWidget(fast_btn)

        normal_btn = QPushButton("标准模式")
        normal_btn.setToolTip("适合一般网络环境（默认设置）")
        normal_btn.clicked.connect(self.set_normal_mode)
        preset_layout.addWidget(normal_btn)

        slow_btn = QPushButton("慢速模式")
        slow_btn.setToolTip("适合网络较慢的环境（超时时间较长）")
        slow_btn.clicked.connect(self.set_slow_mode)
        preset_layout.addWidget(slow_btn)

        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        # 按钮
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("重置默认")
        reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setDefault(True)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def load_current_settings(self):
        """加载当前设置"""
        try:
            config = get_network_config()
            self.health_spin.setValue(config.timeouts.health_check)
            self.api_spin.setValue(config.timeouts.api_request)
            self.ws_spin.setValue(config.timeouts.websocket_connect)
            self.file_spin.setValue(config.timeouts.file_operation)
        except Exception as e:
            print(f"加载超时设置失败: {e}")

    def set_fast_mode(self):
        """设置快速模式"""
        self.health_spin.setValue(3)
        self.api_spin.setValue(5)
        self.ws_spin.setValue(5)
        self.file_spin.setValue(15)

    def set_normal_mode(self):
        """设置标准模式"""
        self.health_spin.setValue(5)
        self.api_spin.setValue(10)
        self.ws_spin.setValue(10)
        self.file_spin.setValue(30)

    def set_slow_mode(self):
        """设置慢速模式"""
        self.health_spin.setValue(10)
        self.api_spin.setValue(20)
        self.ws_spin.setValue(20)
        self.file_spin.setValue(60)

    def reset_defaults(self):
        """重置为默认值"""
        self.set_normal_mode()

    def save_settings(self):
        """保存设置"""
        try:
            success = update_timeouts(
                health_check=self.health_spin.value(),
                api_request=self.api_spin.value(),
                websocket_connect=self.ws_spin.value(),
                file_operation=self.file_spin.value()
            )

            if success:
                QMessageBox.information(self, "成功", "超时设置已保存！\n重新连接后生效。")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "保存设置失败！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置时发生错误：{str(e)}")


class HealthCheckThread(QThread):
    """健康检查线程"""

    health_check_completed = pyqtSignal(dict)  # 健康检查完成信号

    def __init__(self, base_url: str, security_headers: Dict[str, str] = None):
        super().__init__()
        self.base_url = base_url
        self.security_headers = security_headers or {}

    def run(self):
        """执行健康检查"""
        try:
            # 创建健康检查API客户端
            from health_api import HealthAPI
            health_api = HealthAPI(base_url=self.base_url, timeout=get_timeout('health_check'))
            if self.security_headers:
                health_api.session.headers.update(self.security_headers)

            # 执行健康检查
            result = health_api.check_health()
            self.health_check_completed.emit(result)

        except Exception as e:
            # 发送错误结果
            error_result = {
                "success": False,
                "message": f"健康检查异常: {str(e)}",
                "status_code": None,
                "response_time": None,
                "data": None
            }
            self.health_check_completed.emit(error_result)


class StatsUpdateThread(QThread):
    """统计信息更新线程"""

    stats_updated = pyqtSignal(dict)  # 统计信息更新信号

    def __init__(self, base_url: str, security_headers: Dict[str, str] = None):
        super().__init__()
        self.base_url = base_url
        self.security_headers = security_headers or {}

    def run(self):
        """执行统计信息更新"""
        try:
            from devices_api import DevicesAPI
            from fun.clipboard_api import ClipboardAPI

            # 创建API客户端
            devices_api = DevicesAPI(self.base_url, self.security_headers, timeout=get_timeout('api_request'))
            clipboard_api = ClipboardAPI(self.base_url, timeout=get_timeout('api_request'))

            # 获取连接统计
            stats_result = devices_api.get_connection_stats()

            # 获取剪切板统计
            clipboard_result = clipboard_api.get_clipboard_items(limit=1000)

            # 合并结果
            result = {
                "success": stats_result.get('success', False),
                "stats_data": stats_result.get('data', {}),
                "clipboard_data": clipboard_result.get('data', []) if clipboard_result.get('success') else [],
                "message": stats_result.get('message', '')
            }

            self.stats_updated.emit(result)

        except Exception as e:
            # 发送错误结果
            error_result = {
                "success": False,
                "stats_data": {},
                "clipboard_data": [],
                "message": f"统计更新异常: {str(e)}"
            }
            self.stats_updated.emit(error_result)


class WebSocketThread(QThread):
    """WebSocket连接线程"""

    message_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, ws_url: str, device_id: str, security_headers: Dict[str, str] = None, connect_timeout: int = 10):
        super().__init__()
        self.ws_url = ws_url
        self.device_id = device_id
        self.security_headers = security_headers or {}
        self.connect_timeout = connect_timeout
        self.websocket = None
        self.is_running = False
        self.message_queue = []  # 消息队列

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

            # 使用asyncio.wait_for添加连接超时
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    ping_interval=30,
                    ping_timeout=10
                ),
                timeout=self.connect_timeout
            )

            self.connection_status_changed.emit(True)

            # 连接成功后立即请求获取所有内容
            await self.send_message({
                "type": "get_all_content",
                "data": {
                    "limit": 1000
                }
            })

            # 监听消息
            await self.listen_messages()

        except asyncio.TimeoutError:
            self.error_occurred.emit(f"WebSocket连接超时: 无法在{self.connect_timeout}秒内连接到服务器")
        except Exception as e:
            self.error_occurred.emit(f"WebSocket连接失败: {str(e)}")

    async def listen_messages(self):
        """监听WebSocket消息"""
        try:
            while self.is_running and self.websocket:
                try:
                    # 处理消息队列中的待发送消息
                    while self.message_queue:
                        queued_message = self.message_queue.pop(0)
                        await self.send_message(queued_message)

                    # 设置超时接收消息，避免阻塞队列处理
                    try:
                        message = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
                        data = json.loads(message)
                        self.message_received.emit(data)
                    except asyncio.TimeoutError:
                        # 超时是正常的，继续循环
                        continue

                except Exception as e:
                    if self.is_running:
                        self.error_occurred.emit(f"接收消息失败: {str(e)}")
                    break

        except Exception as e:
            self.error_occurred.emit(f"监听消息失败: {str(e)}")
        finally:
            self.connection_status_changed.emit(False)

    async def send_message(self, message: Dict[str, Any]):
        """发送消息到WebSocket服务器"""
        if not self.websocket:
            return False

        try:
            message_str = json.dumps(message, ensure_ascii=False)
            await self.websocket.send(message_str)
            return True
        except Exception as e:
            self.error_occurred.emit(f"发送消息失败: {str(e)}")
            return False

    def queue_message(self, message: Dict[str, Any]):
        """将消息加入队列（线程安全）"""
        self.message_queue.append(message)

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

        # 开机自启动管理器
        self.auto_start_manager = AutoStartManager()

        # 连接状态管理
        self.connection_status = "未连接"  # 连接状态: "未连接", "正常", "已连接"
        self.health_check_timer = QTimer()
        self.health_check_timer.timeout.connect(self.perform_health_check)
        self.health_check_thread = None  # 健康检查线程
        self.stats_update_thread = None  # 统计更新线程

        # 初始化UI
        self.init_ui()
        self.init_system_tray()
        self.load_settings()

        # 初始化剪切板监听
        self.clipboard_timer = QTimer()
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.last_clipboard_content = ""
        self.last_clipboard_image = None  # 存储最后的图片数据，避免重复同步
        self.last_clipboard_image_hash = None  # 存储最后的图片哈希值
        self.last_received_image_hash = None  # 存储最后接收到的图片哈希值
        self.is_setting_clipboard = False  # 标记是否正在设置剪切板（避免循环）
        # 注意：enable_image_sync 将在 load_settings() 中设置，不在这里硬编码
        self.image_processing_time = 0  # 记录最后一次图片处理时间

        # 初始化设备统计定时器（延迟启动，确保UI完全初始化）
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_connection_stats)
        self.current_device_data = []  # 存储当前设备数据
        self.current_clipboard_data = []  # 存储当前剪切板数据
        QTimer.singleShot(2000, self.start_stats_timer)  # 2秒后启动统计定时器

        # 启动时自动检查连接状态
        QTimer.singleShot(1000, self.auto_check_connection)  # 1秒后自动检查连接

    def auto_check_connection(self):
        """程序启动时自动检查连接状态"""
        try:
            # 检查是否配置了服务器地址
            server_ip = self.server_ip_edit.text().strip()
            if not server_ip:
                self.log_message("未配置服务器地址，跳过自动连接检查")
                self.connection_status = "未连接"
                self.update_connection_status_display()
                return

            self.log_message("正在进行启动时连接检查...")
            self.perform_health_check_async()

        except Exception as e:
            self.log_message(f"自动连接检查失败: {str(e)}")
            self.connection_status = "未连接"
            self.update_connection_status_display()

    def perform_health_check_async(self):
        """异步执行健康检查"""
        try:
            # 如果已有健康检查线程在运行，先停止它
            if self.health_check_thread and self.health_check_thread.isRunning():
                self.health_check_thread.quit()
                self.health_check_thread.wait()

            # 获取API配置
            base_url = self.get_api_base_url()
            security_headers = self.get_security_headers()

            # 创建并启动健康检查线程
            self.health_check_thread = HealthCheckThread(base_url, security_headers)
            self.health_check_thread.health_check_completed.connect(self.on_health_check_completed)
            self.health_check_thread.start()

        except Exception as e:
            self.log_message(f"启动健康检查线程失败: {str(e)}")
            self.connection_status = "未连接"
            self.update_connection_status_display()

    def on_health_check_completed(self, result: dict):
        """健康检查完成回调"""
        try:
            if result.get('success'):
                # 健康检查通过
                if self.connection_status == "未连接":
                    self.connection_status = "正常"
                    self.log_message(f"健康检查通过，连接状态更新为: {self.connection_status}")
                    self.show_notification("连接状态", "服务器连接正常")
                else:
                    self.log_message("健康检查通过，连接状态保持正常")

                self.update_connection_status_display()

                # 启动定期健康检查（每30秒检查一次）
                if not self.health_check_timer.isActive():
                    self.health_check_timer.start(30000)
            else:
                # 健康检查失败
                self.connection_status = "未连接"
                error_msg = result.get('message', '未知错误')
                self.log_message(f"健康检查失败: {error_msg}")
                self.update_connection_status_display()

                # 启动重试定时器（10秒后重试）
                QTimer.singleShot(10000, self.perform_health_check_async)

        except Exception as e:
            self.log_message(f"处理健康检查结果失败: {str(e)}")
            self.connection_status = "未连接"
            self.update_connection_status_display()

    def perform_health_check(self):
        """执行健康检查（定时器调用的版本，使用异步方式）"""
        self.perform_health_check_async()

    def update_connection_status_display(self):
        """更新连接状态显示"""
        try:
            if self.connection_status == "未连接":
                self.server_status_label.setText("服务器状态: 未连接")
            elif self.connection_status == "正常":
                self.server_status_label.setText("服务器状态: 正常")
            elif self.connection_status == "已连接":
                self.server_status_label.setText("服务器状态: 已连接")
        except Exception as e:
            self.log_message(f"更新连接状态显示失败: {str(e)}")

    def update_connection_status_on_sync(self):
        """使用同步功能后更新连接状态为已连接"""
        if self.connection_status == "正常":
            self.connection_status = "已连接"
            self.log_message(f"使用同步功能，连接状态更新为: {self.connection_status}")
            self.update_connection_status_display()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("共享剪切板同步工具")
        self.setGeometry(100, 100, 800, 600)

        # 设置窗口图标
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "画板 1.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            self.log_message(f"设置窗口图标失败: {str(e)}")
        
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

        self.timeout_btn = QPushButton("超时设置")
        self.timeout_btn.clicked.connect(self.show_timeout_settings)
        self.timeout_btn.setToolTip("配置网络连接超时时间")
        button_layout.addWidget(self.timeout_btn)

        button_layout.addStretch()

        self.hide_btn = QPushButton("隐藏到托盘")
        self.hide_btn.clicked.connect(self.hide_to_tray)
        button_layout.addWidget(self.hide_btn)

        self.quit_btn = QPushButton("退出程序")
        self.quit_btn.clicked.connect(self.quit_application)
        button_layout.addWidget(self.quit_btn)

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
        stats_group = QGroupBox("云端剪切板统计")
        stats_layout = QVBoxLayout(stats_group)

        self.items_count_label = QLabel("剪切板项目数: 0")
        self.last_sync_label = QLabel("最后同步时间: 无")

        # 剪切板内容列表按钮
        self.clipboard_content_btn = QPushButton("查看云端内容")
        self.clipboard_content_btn.clicked.connect(self.show_clipboard_content)
        self.clipboard_content_btn.setEnabled(False)  # 初始状态禁用

        stats_layout.addWidget(self.items_count_label)
        stats_layout.addWidget(self.last_sync_label)
        stats_layout.addWidget(self.clipboard_content_btn)

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
        self.auto_start_check.toggled.connect(self.toggle_auto_start)
        self.minimize_to_tray_check = QCheckBox("启动时最小化到托盘")
        self.enable_notifications_check = QCheckBox("启用通知")
        self.enable_notifications_check.setChecked(True)

        # 图片同步开关
        self.enable_image_sync_check = QCheckBox("启用图片同步 (实验性功能)")
        self.enable_image_sync_check.setChecked(False)  # 默认禁用
        self.enable_image_sync_check.toggled.connect(self.toggle_image_sync)

        self.check_interval_spin = QSpinBox()
        self.check_interval_spin.setRange(100, 5000)
        self.check_interval_spin.setValue(500)
        self.check_interval_spin.setSuffix(" ms")

        other_layout.addWidget(self.auto_start_check)
        other_layout.addWidget(self.minimize_to_tray_check)
        other_layout.addWidget(self.enable_notifications_check)
        other_layout.addWidget(self.enable_image_sync_check)
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("剪切板检查间隔:"))
        interval_layout.addWidget(self.check_interval_spin)
        interval_layout.addStretch()
        other_layout.addLayout(interval_layout)
        
        layout.addWidget(other_group)
        
        # 保存按钮
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(lambda: self.save_settings(show_message=True))
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
            self.tray_icon = None  # 确保属性存在
            return

        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)

        # 设置图标
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "画板 1.png")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                # 如果自定义图标不存在，使用默认图标
                self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        except Exception as e:
            # 如果设置自定义图标失败，使用默认图标
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
            self.log_message(f"设置托盘图标失败，使用默认图标: {str(e)}")

        self.tray_icon.setToolTip("共享剪切板同步工具")

        # 创建托盘菜单
        self.tray_menu = QMenu()

        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        self.tray_menu.addAction(show_action)

        self.tray_menu.addSeparator()

        # 保存菜单项的引用以便后续更新文本
        self.tray_monitor_action = QAction("开始单向同步", self)
        self.tray_monitor_action.triggered.connect(self.toggle_monitoring)
        self.tray_menu.addAction(self.tray_monitor_action)

        self.tray_sync_action = QAction("开始双向同步", self)
        self.tray_sync_action.triggered.connect(self.toggle_syncing)
        self.tray_menu.addAction(self.tray_sync_action)

        self.tray_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # 托盘图标双击事件
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def update_tray_menu_text(self):
        """更新托盘菜单项的文本"""
        try:
            if hasattr(self, 'tray_monitor_action'):
                if self.is_monitoring:
                    self.tray_monitor_action.setText("停止单向同步")
                else:
                    self.tray_monitor_action.setText("开始单向同步")

            if hasattr(self, 'tray_sync_action'):
                if self.is_syncing:
                    self.tray_sync_action.setText("停止双向同步")
                else:
                    self.tray_sync_action.setText("开始双向同步")
        except Exception as e:
            self.log_message(f"更新托盘菜单文本失败: {str(e)}")

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
        if self.health_check_timer.isActive():
            self.health_check_timer.stop()
        if self.is_monitoring:
            self.stop_monitoring()
        if self.is_syncing:
            self.stop_syncing()
        if self.websocket_thread:
            self.websocket_thread.stop()

        # 清理健康检查线程
        if self.health_check_thread and self.health_check_thread.isRunning():
            self.health_check_thread.quit()
            self.health_check_thread.wait(3000)  # 等待最多3秒

        # 清理统计更新线程
        if self.stats_update_thread and self.stats_update_thread.isRunning():
            self.stats_update_thread.quit()
            self.stats_update_thread.wait(3000)  # 等待最多3秒
        
    def log_message(self, message: str):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)

    def show_notification(self, title: str, message: str, icon=QSystemTrayIcon.Information):
        """显示系统通知"""
        try:
            # 检查通知是否启用
            if not self.enable_notifications_check.isChecked():
                self.log_message(f"通知已禁用，跳过通知: {title} - {message}")
                return

            # 检查托盘图标是否存在
            if not hasattr(self, 'tray_icon') or self.tray_icon is None:
                self.log_message(f"托盘图标不存在，无法显示通知: {title} - {message}")
                return

            # 检查托盘图标是否可见
            if not self.tray_icon.isVisible():
                self.log_message(f"托盘图标不可见，无法显示通知: {title} - {message}")
                return

            # 检查系统是否支持托盘通知
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.log_message(f"系统不支持托盘通知: {title} - {message}")
                return

            # 显示通知
            self.tray_icon.showMessage(title, message, icon, 5000)  # 延长显示时间到5秒
            self.log_message(f"已显示通知: {title} - {message}")

        except Exception as e:
            self.log_message(f"显示通知失败: {str(e)}")
            import traceback
            self.log_message(f"通知错误详情: {traceback.format_exc()}")
        
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        
    def show_settings(self):
        """显示设置页面"""
        self.tab_widget.setCurrentIndex(1)  # 切换到设置页面

    def show_timeout_settings(self):
        """显示超时设置对话框"""
        dialog = NetworkTimeoutDialog(self)
        dialog.exec_()

    def load_settings(self):
        """加载设置"""
        self.server_ip_edit.setText(self.settings.value('server_ip', ''))
        self.api_port_edit.setText(self.settings.value('api_port', '3001'))
        self.ws_port_edit.setText(self.settings.value('ws_port', '3002'))
        self.auth_key_edit.setText(self.settings.value('auth_key', ''))
        self.auth_value_edit.setText(self.settings.value('auth_value', ''))

        # 先设置开机自启动复选框的初始状态（不触发信号）
        self.auto_start_check.blockSignals(True)
        self.auto_start_check.setChecked(self.settings.value('auto_start', False, type=bool))
        self.auto_start_check.blockSignals(False)

        # 然后同步实际的开机自启动状态
        self.sync_auto_start_status()

        self.minimize_to_tray_check.setChecked(self.settings.value('minimize_to_tray', False, type=bool))
        self.enable_notifications_check.setChecked(self.settings.value('enable_notifications', True, type=bool))

        # 加载图片同步设置
        enable_image_sync = self.settings.value('enable_image_sync', False, type=bool)
        self.enable_image_sync_check.setChecked(enable_image_sync)
        # 确保内部状态变量与UI状态一致
        self.enable_image_sync = enable_image_sync

        # 确保UI和内部状态一致
        self.log_message(f"加载图片同步设置: UI={'启用' if self.enable_image_sync_check.isChecked() else '禁用'}, 内部={'启用' if self.enable_image_sync else '禁用'}")

        self.check_interval_spin.setValue(self.settings.value('check_interval', 500, type=int))
        
    def save_settings(self, show_message=True):
        """保存设置"""
        self.settings.setValue('server_ip', self.server_ip_edit.text())
        self.settings.setValue('api_port', self.api_port_edit.text())
        self.settings.setValue('ws_port', self.ws_port_edit.text())
        self.settings.setValue('auth_key', self.auth_key_edit.text())
        self.settings.setValue('auth_value', self.auth_value_edit.text())
        self.settings.setValue('auto_start', self.auto_start_check.isChecked())
        self.settings.setValue('minimize_to_tray', self.minimize_to_tray_check.isChecked())
        self.settings.setValue('enable_notifications', self.enable_notifications_check.isChecked())
        # 保存图片同步设置并确保内部状态同步
        image_sync_enabled = self.enable_image_sync_check.isChecked()
        self.settings.setValue('enable_image_sync', image_sync_enabled)
        self.enable_image_sync = image_sync_enabled  # 确保内部状态与UI一致

        self.settings.setValue('check_interval', self.check_interval_spin.value())

        self.log_message(f"设置已保存 (图片同步: {'启用' if image_sync_enabled else '禁用'})")
        if show_message:
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

            self.clipboard_client = ClipboardAPI(base_url=base_url, timeout=get_timeout('api_request'))
            if security_headers:
                self.clipboard_client.session.headers.update(security_headers)

            # 测试连接
            from health_api import HealthAPI
            health_api = HealthAPI(base_url=base_url, timeout=get_timeout('health_check'))
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

            # 更新托盘菜单文本
            self.update_tray_menu_text()

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

        # 更新托盘菜单文本
        self.update_tray_menu_text()

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

            self.clipboard_client = ClipboardAPI(base_url, timeout=get_timeout('api_request'))
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
            self.websocket_thread = WebSocketThread(ws_url, device_id, security_headers, connect_timeout=get_timeout('websocket_connect'))

            # 连接信号
            self.websocket_thread.message_received.connect(self.handle_websocket_message)
            self.websocket_thread.connection_status_changed.connect(self.handle_websocket_status)
            self.websocket_thread.error_occurred.connect(self.handle_websocket_error)

            # 启动线程
            self.websocket_thread.start()

            self.is_syncing = True
            self.start_sync_btn.setText("停止双向同步")
            self.sync_status_label.setText("同步状态: 连接中...")

            # 更新托盘菜单文本
            self.update_tray_menu_text()

            self.log_message("正在启动双向同步...")
            self.show_notification("剪切板同步", "双向同步已启动（包含本地监听）")

        except Exception as e:
            self.log_message(f"启动双向同步失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"启动双向同步失败: {str(e)}")

            # 如果启动失败，清理已启动的组件
            if self.clipboard_timer.isActive():
                self.clipboard_timer.stop()
            self.is_syncing = False
            # 更新托盘菜单文本
            self.update_tray_menu_text()

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

        # 更新托盘菜单文本
        self.update_tray_menu_text()

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

                if content:
                    if content_type == 'text' and content != self.last_clipboard_content:
                        # 设置标记，避免触发剪切板检查循环
                        self.is_setting_clipboard = True
                        try:
                            pyperclip.copy(content)
                            self.last_clipboard_content = content
                            self.log_message(f"收到同步内容: {content[:50]}{'...' if len(content) > 50 else ''}")
                            # 显示通知
                            self.show_notification("剪切板同步", f"收到新文本: {content[:30]}{'...' if len(content) > 30 else ''}")
                        finally:
                            # 延迟重置标记
                            QTimer.singleShot(500, lambda: setattr(self, 'is_setting_clipboard', False))
                    elif content_type == 'image':
                        # 安全检查：确保应用程序状态正常
                        if hasattr(self, 'handle_received_image') and callable(getattr(self, 'handle_received_image')):
                            try:
                                self.handle_received_image(content, sync_data if 'data' in data else data)
                                # 显示图片同步通知
                                self.show_notification("剪切板同步", "收到新图片内容")
                            except Exception as img_error:
                                self.log_message(f"处理图片消息时发生严重错误: {str(img_error)}")
                                import traceback
                                self.log_message(f"图片处理错误堆栈: {traceback.format_exc()}")
                        else:
                            self.log_message("图片处理方法不可用")
                    else:
                        self.log_message(f"收到非文本内容，类型: {content_type}")
                        # 显示其他类型内容的通知
                        self.show_notification("剪切板同步", f"收到新内容 (类型: {content_type})")

            elif message_type == 'ping' or message_type == 'heartbeat':
                # 心跳消息
                self.log_message("收到心跳消息")

            elif message_type == 'device_connected':
                # 设备连接通知
                device_id = data.get('deviceId', '未知设备')
                self.log_message(f"设备已连接: {device_id}")
                self.show_notification("设备连接", f"设备 {device_id} 已连接")

            elif message_type == 'device_disconnected':
                # 设备断开通知
                device_id = data.get('deviceId', '未知设备')
                self.log_message(f"设备已断开: {device_id}")
                self.show_notification("设备断开", f"设备 {device_id} 已断开", QSystemTrayIcon.Warning)

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

            elif message_type == 'all_content' or message_type == 'get_all_content':
                # 收到所有剪切板内容
                content_data = data.get('data', [])
                if isinstance(content_data, list):
                    self.current_clipboard_data = content_data
                    total_count = len(content_data)
                    self.items_count_label.setText(f"剪切板项目数: {total_count}")

                    if total_count > 0:
                        self.clipboard_content_btn.setEnabled(True)
                        self.clipboard_content_btn.setText(f"查看云端内容 ({total_count})")
                    else:
                        self.clipboard_content_btn.setEnabled(False)
                        self.clipboard_content_btn.setText("查看云端内容")

                    self.log_message(f"收到云端剪切板内容: {total_count} 项")
                else:
                    self.log_message(f"收到剪切板内容数据格式异常: {str(data)[:100]}")

            elif message_type == 'all_text':
                # 收到所有文本内容
                content_data = data.get('data', [])
                if isinstance(content_data, list):
                    # 过滤并更新当前数据
                    text_items = [item for item in content_data if item.get('type') == 'text']
                    self.current_clipboard_data = text_items
                    self.log_message(f"收到云端文本内容: {len(text_items)} 项")

            elif message_type == 'all_images':
                # 收到所有图片内容
                content_data = data.get('data', [])
                if isinstance(content_data, list):
                    # 过滤并更新当前数据
                    image_items = [item for item in content_data if item.get('type') == 'image']
                    self.current_clipboard_data = image_items
                    self.log_message(f"收到云端图片内容: {len(image_items)} 项")

            elif message_type == 'latest':
                # 收到最新内容
                content_data = data.get('data', [])
                count = data.get('count', 0)
                if isinstance(content_data, list):
                    self.current_clipboard_data = content_data
                    self.log_message(f"收到最新剪切板内容: {len(content_data)} 项 (请求: {count})")

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

            # WebSocket连接成功时更新连接状态为"已连接"
            self.update_connection_status_on_sync()
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
            # 如果正在设置剪切板，跳过检查避免循环
            if getattr(self, 'is_setting_clipboard', False):
                return

            # 获取系统剪切板
            clipboard = QApplication.clipboard()

            # 检查是否有图片（如果启用了图片同步）
            if self.enable_image_sync and clipboard.mimeData().hasImage():
                try:
                    # 检查是否在图片处理时间窗口内（10秒内不重复检测）
                    import time
                    current_time = time.time()
                    if current_time - self.image_processing_time < 10:
                        return

                    pixmap = clipboard.pixmap()
                    if not pixmap.isNull():
                        # 将图片转换为字节数据
                        image_data = self.pixmap_to_bytes(pixmap)
                        if image_data:
                            # 计算图片的哈希值进行比较
                            import hashlib
                            current_hash = hashlib.md5(image_data).hexdigest()
                            last_hash = getattr(self, 'last_clipboard_image_hash', None)

                            # 只有哈希值不同才发送（简化逻辑）
                            if current_hash != last_hash:
                                self.last_clipboard_image = image_data
                                self.last_clipboard_image_hash = current_hash
                                self.log_message(f"检测到新图片，哈希: {current_hash[:8]}...")
                                self.send_clipboard_image(image_data)
                                return
                            else:
                                # 图片相同，跳过
                                return
                except Exception as img_check_error:
                    self.log_message(f"检查图片时发生错误: {str(img_check_error)}")
                    # 继续处理文本，不要因为图片错误而中断

            # 检查文本内容
            current_content = pyperclip.paste()
            if current_content != self.last_clipboard_content and current_content.strip():
                self.last_clipboard_content = current_content
                self.send_clipboard_content(current_content)

        except Exception as e:
            self.log_message(f"检查剪切板失败: {str(e)}")

    def pixmap_to_bytes(self, pixmap: QPixmap) -> bytes:
        """将QPixmap转换为字节数据"""
        try:
            # 将QPixmap转换为QImage
            image = pixmap.toImage()

            # 创建字节缓冲区
            byte_array = io.BytesIO()

            # 将QImage转换为PIL Image
            width = image.width()
            height = image.height()
            ptr = image.bits()
            ptr.setsize(image.byteCount())

            # 转换为PIL Image
            pil_image = Image.frombuffer("RGBA", (width, height), ptr, "raw", "BGRA", 0, 1)

            # 转换为RGB模式（去除透明度）
            if pil_image.mode == 'RGBA':
                # 创建白色背景
                background = Image.new('RGB', pil_image.size, (255, 255, 255))
                background.paste(pil_image, mask=pil_image.split()[-1])  # 使用alpha通道作为mask
                pil_image = background

            # 保存为PNG格式
            pil_image.save(byte_array, format='PNG')
            return byte_array.getvalue()

        except Exception as e:
            self.log_message(f"图片转换失败: {str(e)}")
            return None

    def send_clipboard_image(self, image_data: bytes):
        """发送剪切板图片到服务器"""
        try:
            # 更新图片处理时间戳
            import time
            self.image_processing_time = time.time()

            if not self.clipboard_client:
                self.log_message("剪切板客户端未初始化")
                return

            # 检查图片大小（限制为5MB）
            if len(image_data) > 5 * 1024 * 1024:
                self.log_message(f"图片过大({len(image_data)/1024/1024:.1f}MB)，跳过同步")
                return

            # 验证图片数据
            try:
                pil_image = Image.open(io.BytesIO(image_data))
                pil_image.verify()
                self.log_message(f"发送图片验证成功: {pil_image.format} {pil_image.size}")
            except Exception as e:
                self.log_message(f"发送图片验证失败: {str(e)}")
                return

            # 生成设备ID和文件名
            device_id = f"windows-client-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            file_name = f"clipboard_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            # 发送图片内容
            result = self.clipboard_client.create_image_item(
                image_data=image_data,
                device_id=device_id,
                file_name=file_name,
                mime_type="image/png"
            )

            if result.get('success'):
                # 更新哈希值，避免重复发送
                import hashlib
                sent_hash = hashlib.md5(image_data).hexdigest()
                self.last_clipboard_image_hash = sent_hash

                self.log_message(f"剪切板图片已同步: {file_name} ({len(image_data)/1024:.1f}KB) 哈希: {sent_hash[:8]}...")
                self.last_sync_label.setText(f"最后同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.show_notification("剪切板同步", f"图片已同步: {file_name}")

                # 使用同步功能后更新连接状态为"已连接"
                self.update_connection_status_on_sync()

                # 更新统计信息（通过统计定时器自动更新）
            else:
                error_msg = result.get('message', '未知错误')
                self.log_message(f"图片同步失败: {error_msg}")

        except Exception as e:
            self.log_message(f"发送图片失败: {str(e)}")
            import traceback
            self.log_message(f"发送图片详细错误: {traceback.format_exc()}")

    def handle_received_image(self, content: str, data: dict):
        """处理接收到的图片内容"""
        # 检查图片同步是否启用
        if not getattr(self, 'enable_image_sync', True):
            self.log_message("图片同步已禁用，跳过处理")
            return

        try:
            # 更新图片处理时间戳
            import time
            self.image_processing_time = time.time()

            self.log_message("开始处理接收到的图片...")

            # 获取图片ID，通过API下载完整图片数据
            item_id = data.get('id')
            if not item_id:
                self.log_message("图片消息缺少ID信息")
                return

            self.log_message(f"图片ID: {item_id}")

            # 检查必要的组件是否存在
            if not hasattr(self, 'clipboard_client') or not self.clipboard_client:
                self.log_message("剪切板客户端未初始化，无法下载图片")
                return

            # 暂时禁用图片同步，避免在处理过程中触发循环
            original_enable_state = self.enable_image_sync
            self.enable_image_sync = False

            try:
                # 通过文件API下载图片
                try:
                    from files_api import FilesAPI
                    base_url = self.get_api_base_url()
                    security_headers = self.get_security_headers()

                    self.log_message(f"使用API地址: {base_url}")

                    files_api = FilesAPI(base_url=base_url)
                    if security_headers:
                        files_api.session.headers.update(security_headers)

                    # 下载图片文件
                    self.log_message("开始下载图片文件...")
                    result = files_api.download_file(item_id)

                    if not result.get('success'):
                        self.log_message(f"下载图片失败: {result.get('message', '未知错误')}")
                        return

                    image_bytes = result.get('content')
                    if not image_bytes:
                        self.log_message("下载的图片数据为空")
                        return

                    self.log_message(f"成功下载图片，大小: {len(image_bytes)} 字节")

                except Exception as download_error:
                    self.log_message(f"下载图片时发生错误: {str(download_error)}")
                    return

                # 使用更安全的方式处理图片
                self.log_message("开始安全处理图片...")
                success = self.ultra_safe_set_image_to_clipboard(image_bytes, data)

                if success:
                    file_name = data.get('fileName', '图片')
                    self.log_message(f"图片处理成功: {file_name}")
                    self.show_notification("剪切板同步", f"收到新图片: {file_name}")
                else:
                    self.log_message("图片处理失败")

            finally:
                # 延迟恢复图片同步状态
                QTimer.singleShot(2000, lambda: setattr(self, 'enable_image_sync', original_enable_state))

        except Exception as e:
            self.log_message(f"处理接收图片失败: {str(e)}")
            import traceback
            self.log_message(f"总体错误详情: {traceback.format_exc()}")

    def safe_set_image_to_clipboard(self, image_bytes: bytes, data: dict) -> bool:
        """安全地将图片设置到剪切板"""
        try:
            # 导入必要的模块
            from PyQt5.QtGui import QImage

            # 验证图片数据
            pil_image = Image.open(io.BytesIO(image_bytes))
            self.log_message(f"图片验证成功: {pil_image.format} {pil_image.size} {pil_image.mode}")

            # 限制图片大小，避免内存问题
            max_size = (2048, 2048)
            if pil_image.size[0] > max_size[0] or pil_image.size[1] > max_size[1]:
                self.log_message(f"图片过大，进行缩放: {pil_image.size} -> {max_size}")
                pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 转换为RGB模式
            if pil_image.mode not in ('RGB', 'RGBA'):
                self.log_message(f"转换图片模式: {pil_image.mode} -> RGB")
                pil_image = pil_image.convert('RGB')

            # 使用更简单的方式创建QPixmap
            width, height = pil_image.size

            # 转换为字节数组
            if pil_image.mode == 'RGBA':
                image_data = pil_image.tobytes('raw', 'RGBA')
                format_type = QImage.Format_RGBA8888
            else:
                image_data = pil_image.tobytes('raw', 'RGB')
                format_type = QImage.Format_RGB888

            # 创建QImage
            qimage = QImage(image_data, width, height, format_type)

            if qimage.isNull():
                self.log_message("QImage创建失败")
                return False

            # 转换为QPixmap
            pixmap = QPixmap.fromImage(qimage)

            if pixmap.isNull():
                self.log_message("QPixmap转换失败")
                return False

            # 使用更安全的方式设置到剪切板
            try:
                clipboard = QApplication.clipboard()

                # 先清空剪切板
                clipboard.clear()

                # 使用事件循环确保操作完成
                QApplication.processEvents()

                # 设置图片
                clipboard.setPixmap(pixmap)

                # 再次处理事件
                QApplication.processEvents()

                self.log_message("图片已写入系统剪切板")

            except Exception as clipboard_error:
                self.log_message(f"写入剪切板时发生错误: {str(clipboard_error)}")
                return False

            # 更新哈希值
            import hashlib
            self.last_clipboard_image = image_bytes
            self.last_clipboard_image_hash = hashlib.md5(image_bytes).hexdigest()

            self.log_message(f"图片已成功写入剪切板: {width}x{height}")
            return True

        except Exception as e:
            self.log_message(f"安全设置图片到剪切板失败: {str(e)}")
            import traceback
            self.log_message(f"安全设置错误详情: {traceback.format_exc()}")
            return False

    def ultra_safe_set_image_to_clipboard(self, image_bytes: bytes, data: dict) -> bool:
        """超级安全地将图片设置到剪切板 - 使用临时文件方式"""
        import tempfile
        import os

        temp_file = None
        try:
            self.log_message("使用超级安全模式处理图片...")

            # 验证图片数据
            pil_image = Image.open(io.BytesIO(image_bytes))
            self.log_message(f"图片验证成功: {pil_image.format} {pil_image.size} {pil_image.mode}")

            # 限制图片大小
            max_size = (1024, 1024)  # 更保守的大小限制
            if pil_image.size[0] > max_size[0] or pil_image.size[1] > max_size[1]:
                self.log_message(f"图片过大，进行缩放: {pil_image.size} -> {max_size}")
                pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 转换为RGB模式
            if pil_image.mode != 'RGB':
                self.log_message(f"转换图片模式: {pil_image.mode} -> RGB")
                pil_image = pil_image.convert('RGB')

            # 保存到临时文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                pil_image.save(temp_file.name, 'PNG')
                temp_file_path = temp_file.name
                self.log_message(f"图片已保存到临时文件: {temp_file_path}")

            # 从临时文件加载到QPixmap
            pixmap = QPixmap(temp_file_path)

            if pixmap.isNull():
                self.log_message("从临时文件加载QPixmap失败")
                return False

            self.log_message(f"QPixmap加载成功: {pixmap.width()}x{pixmap.height()}")

            # 设置到剪切板
            try:
                clipboard = QApplication.clipboard()
                clipboard.clear()
                QApplication.processEvents()

                clipboard.setPixmap(pixmap)
                QApplication.processEvents()

                self.log_message("图片已写入系统剪切板")

                # 更新哈希值 - 需要记录处理后的图片哈希
                import hashlib

                # 计算处理后图片的哈希（从剪切板读取）
                try:
                    clipboard_pixmap = QApplication.clipboard().pixmap()
                    if not clipboard_pixmap.isNull():
                        processed_image_data = self.pixmap_to_bytes(clipboard_pixmap)
                        if processed_image_data:
                            processed_hash = hashlib.md5(processed_image_data).hexdigest()
                            self.last_clipboard_image = processed_image_data
                            self.last_clipboard_image_hash = processed_hash
                            self.log_message(f"记录处理后图片哈希: {processed_hash[:8]}...")
                        else:
                            # 如果无法获取处理后的数据，使用原始数据
                            original_hash = hashlib.md5(image_bytes).hexdigest()
                            self.last_clipboard_image = image_bytes
                            self.last_clipboard_image_hash = original_hash
                            self.log_message(f"记录原始图片哈希: {original_hash[:8]}...")
                    else:
                        # 如果剪切板为空，使用原始数据
                        original_hash = hashlib.md5(image_bytes).hexdigest()
                        self.last_clipboard_image = image_bytes
                        self.last_clipboard_image_hash = original_hash
                        self.log_message(f"记录原始图片哈希: {original_hash[:8]}...")
                except Exception as hash_error:
                    self.log_message(f"计算处理后哈希失败: {str(hash_error)}")
                    # 使用原始数据作为备选
                    original_hash = hashlib.md5(image_bytes).hexdigest()
                    self.last_clipboard_image = image_bytes
                    self.last_clipboard_image_hash = original_hash
                    self.log_message(f"使用原始图片哈希: {original_hash[:8]}...")

                return True

            except Exception as clipboard_error:
                self.log_message(f"写入剪切板失败: {str(clipboard_error)}")
                return False

        except Exception as e:
            self.log_message(f"超级安全设置图片失败: {str(e)}")
            import traceback
            self.log_message(f"超级安全错误详情: {traceback.format_exc()}")
            return False
        finally:
            # 清理临时文件
            if temp_file and hasattr(temp_file, 'name') and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                    self.log_message("临时文件已清理")
                except:
                    pass

    def toggle_image_sync(self, enabled: bool):
        """切换图片同步功能"""
        # 确保内部状态与UI状态一致
        self.enable_image_sync = enabled
        status = "启用" if enabled else "禁用"
        self.log_message(f"图片同步已{status} (UI: {'启用' if self.enable_image_sync_check.isChecked() else '禁用'}, 内部: {'启用' if self.enable_image_sync else '禁用'})")

        if enabled:
            self.log_message("警告: 图片同步是实验性功能，可能导致程序不稳定")

        # 静默保存设置，不显示消息
        self.save_settings(show_message=False)

    def pil_image_to_pixmap(self, pil_image: Image.Image) -> QPixmap:
        """将PIL Image转换为QPixmap"""
        try:
            # 导入必要的模块
            from PyQt5.QtGui import QImage

            self.log_message(f"开始转换PIL图片: {pil_image.mode} {pil_image.size}")

            # 确保图片是RGB模式
            if pil_image.mode != 'RGB':
                self.log_message(f"转换图片模式从 {pil_image.mode} 到 RGB")
                pil_image = pil_image.convert('RGB')

            # 获取图片数据
            width, height = pil_image.size
            self.log_message(f"图片尺寸: {width}x{height}")

            # 获取图片字节数据
            image_data = pil_image.tobytes('raw', 'RGB')
            self.log_message(f"图片数据大小: {len(image_data)} 字节")

            # 创建QImage
            qimage = QImage(image_data, width, height, QImage.Format_RGB888)

            if qimage.isNull():
                self.log_message("创建QImage失败")
                return QPixmap()

            self.log_message("QImage创建成功")

            # 转换为QPixmap
            pixmap = QPixmap.fromImage(qimage)

            if pixmap.isNull():
                self.log_message("QPixmap转换失败")
                return QPixmap()

            self.log_message(f"QPixmap转换成功: {pixmap.width()}x{pixmap.height()}")
            return pixmap

        except Exception as e:
            self.log_message(f"PIL转QPixmap失败: {str(e)}")
            import traceback
            self.log_message(f"转换错误详情: {traceback.format_exc()}")
            return QPixmap()

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

                # 使用同步功能后更新连接状态为"已连接"
                self.update_connection_status_on_sync()

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

    def show_clipboard_content(self):
        """显示剪切板内容对话框"""
        dialog = ClipboardContentDialog(self.current_clipboard_data, self)
        dialog.exec_()

    def request_clipboard_content_refresh(self):
        """请求刷新剪切板内容"""
        if self.websocket_thread and self.is_syncing:
            # 通过WebSocket请求获取所有内容
            try:
                # 发送获取所有内容的请求
                message = {
                    "type": "get_all_content",
                    "data": {
                        "limit": 1000
                    }
                }
                # 将消息加入队列
                self.websocket_thread.queue_message(message)
                self.log_message("已请求刷新剪切板内容")
            except Exception as e:
                self.log_message(f"请求刷新剪切板内容失败: {str(e)}")
        else:
            # 如果WebSocket未连接，通过统计定时器获取
            self.log_message("WebSocket未连接，将通过定时器更新统计信息")

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
        """更新设备连接统计信息（异步版本）"""
        try:
            # 检查UI元素是否已初始化
            if not hasattr(self, 'server_ip_edit') or not hasattr(self, 'total_connections_label'):
                return

            # 如果已有统计更新线程在运行，跳过本次更新
            if self.stats_update_thread and self.stats_update_thread.isRunning():
                return

            # 获取服务器配置
            server_ip = self.server_ip_edit.text() or "localhost"
            api_port = self.api_port_edit.text() or "3001"
            base_url = f"http://{server_ip}:{api_port}"

            # 获取安全认证配置
            security_headers = self.get_security_headers()

            # 创建并启动统计更新线程
            self.stats_update_thread = StatsUpdateThread(base_url, security_headers)
            self.stats_update_thread.stats_updated.connect(self.on_stats_updated)
            self.stats_update_thread.start()

        except Exception as e:
            self.log_message(f"启动统计更新线程失败: {str(e)}")

    def on_stats_updated(self, result: dict):
        """统计信息更新完成回调"""
        try:
            if result.get('success'):
                stats_data = result.get('stats_data', {})
                clipboard_data = result.get('clipboard_data', [])

                # 更新统计标签
                total_connections = stats_data.get('totalConnections', 0)
                active_connections = stats_data.get('activeConnections', 0)
                connected_devices = stats_data.get('connectedDevices', [])

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

                # 更新剪切板统计
                self.current_clipboard_data = clipboard_data

                # 更新剪切板统计UI
                if hasattr(self, 'items_count_label'):
                    total = len(clipboard_data)
                    self.items_count_label.setText(f"剪切板项目数: {total}")

                    # 启用或禁用查看内容按钮
                    if hasattr(self, 'clipboard_content_btn'):
                        if total > 0:
                            self.clipboard_content_btn.setEnabled(True)
                            self.clipboard_content_btn.setText(f"查看云端内容 ({total})")
                        else:
                            self.clipboard_content_btn.setEnabled(False)
                            self.clipboard_content_btn.setText("查看云端内容")

            else:
                # 连接失败时显示详细错误信息
                error_msg = result.get('message', '未知错误')

                self.total_connections_label.setText("总连接数: 获取失败")
                self.active_connections_label.setText("活跃连接数: 获取失败")
                self.connected_devices_label.setText("在线设备数: 获取失败")
                self.device_list_btn.setEnabled(False)
                self.device_list_btn.setText("查看设备列表")
                self.current_device_data = []

                # 记录详细错误到日志
                self.log_message(f"获取连接统计失败: {error_msg}")

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
            self.log_message(f"处理统计信息异常: {error_detail}")

        # 剪切板统计信息已在统计更新线程中一起获取，无需额外调用

    def update_clipboard_stats_via_api(self):
        """更新剪切板统计信息（已废弃，现在通过统计更新线程获取）"""
        # 这个方法已被统计更新线程替代，避免在主线程中进行网络请求
        # 剪切板统计信息现在通过 on_stats_updated 方法更新
        pass

    def toggle_auto_start(self, checked: bool):
        """切换开机自启动状态"""
        try:
            if not self.auto_start_manager.is_supported():
                QMessageBox.warning(self, "不支持", "当前系统不支持开机自启动功能")
                # 重置复选框状态
                self.auto_start_check.blockSignals(True)
                self.auto_start_check.setChecked(False)
                self.auto_start_check.blockSignals(False)
                return

            success, error = self.auto_start_manager.toggle(checked)

            if success:
                if checked:
                    self.log_message("开机自启动已启用")
                    self.show_notification("设置成功", "开机自启动已启用")
                else:
                    self.log_message("开机自启动已禁用")
                    self.show_notification("设置成功", "开机自启动已禁用")
            else:
                self.log_message(f"开机自启动设置失败: {error}")
                QMessageBox.warning(self, "设置失败", f"开机自启动设置失败:\n{error}")

                # 重置复选框状态
                self.auto_start_check.blockSignals(True)
                self.auto_start_check.setChecked(not checked)
                self.auto_start_check.blockSignals(False)

        except Exception as e:
            self.log_message(f"开机自启动设置异常: {str(e)}")
            QMessageBox.critical(self, "设置异常", f"开机自启动设置时发生异常:\n{str(e)}")

            # 重置复选框状态
            self.auto_start_check.blockSignals(True)
            self.auto_start_check.setChecked(not checked)
            self.auto_start_check.blockSignals(False)

    def sync_auto_start_status(self):
        """同步开机自启动状态（从注册表读取实际状态）"""
        try:
            if self.auto_start_manager.is_supported():
                enabled, error = self.auto_start_manager.is_enabled()
                if error:
                    self.log_message(f"检查开机自启动状态失败: {error}")
                else:
                    # 阻止信号触发，直接设置UI状态
                    self.auto_start_check.blockSignals(True)
                    self.auto_start_check.setChecked(enabled)
                    self.auto_start_check.blockSignals(False)

                    self.log_message(f"开机自启动状态同步: {'已启用' if enabled else '未启用'}")
            else:
                # 如果不支持，禁用复选框
                self.auto_start_check.setEnabled(False)
                self.auto_start_check.setToolTip("当前系统不支持开机自启动功能")

        except Exception as e:
            self.log_message(f"同步开机自启动状态异常: {str(e)}")
            self.auto_start_check.setEnabled(False)
            self.auto_start_check.setToolTip(f"开机自启动功能异常: {str(e)}")


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

    # 检查是否启动时最小化到托盘
    if window.minimize_to_tray_check.isChecked():
        # 启动时最小化到托盘，不显示主窗口
        window.log_message("程序启动时最小化到托盘")
        window.show_notification("剪切板同步工具", "程序已启动并最小化到托盘")
    else:
        # 正常显示主窗口
        window.show()

    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
