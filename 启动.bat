@echo off
chcp 65001 >nul
title 共享剪切板同步工具

echo.
echo ========================================
echo    共享剪切板同步工具 v1.0.0
echo ========================================
echo.

echo 正在检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python环境！
    echo 请先安装Python 3.7或更高版本
    pause
    exit /b 1
)

echo Python环境检查通过
echo.

echo 正在检查依赖包...
python -c "import PyQt5, requests, websockets, pyperclip" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖包...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo 错误: 依赖包安装失败！
        echo 请手动运行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo 依赖包检查通过
echo.

echo 正在启动应用程序...
python run.py

if errorlevel 1 (
    echo.
    echo 程序异常退出！
    pause
)
