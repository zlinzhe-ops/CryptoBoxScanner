@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 虚拟货币箱体震荡选币软件

echo ========================================
echo   虚拟货币箱体震荡选币软件
echo   Crypto Box Scanner v1.0
echo ========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 尝试多个可能的 Python 路径（按优先级）
set "FOUND_PYTHON="

REM 1. 项目自带的 venv
if exist "%~dp0.venv\Scripts\python.exe" (
    set "FOUND_PYTHON=%~dp0.venv\Scripts\python.exe"
    echo [信息] 使用项目虚拟环境 Python
    goto :check_deps
)

REM 2. 系统 PATH 中的 python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "FOUND_PYTHON=python"
    echo [信息] 使用系统 PATH 中的 Python
    goto :check_deps
)

REM 3. 常见的 Python 安装位置
for %%d in (
    "C:\Users\%USERNAME%\.local\bin\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
) do (
    if exist %%d (
        set "FOUND_PYTHON=%%d"
        echo [信息] 在 %%d 找到 Python
        goto :check_deps
    )
)

REM 都没找到
echo [错误] 未找到 Python！
echo.
echo 请安装 Python 3.8+：
echo   https://www.python.org/downloads/
echo.
echo 安装时务必勾选 "Add Python to PATH"
echo.
pause
exit /b 1

:check_deps
echo [检测] 检查依赖...
"%FOUND_PYTHON%" -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [安装] 首次运行，正在安装必要组件（需要联网，约2-5分钟）...
    echo.
    "%FOUND_PYTHON%" -m pip install PySide6 requests -q
    if %errorlevel% neq 0 (
        echo.
        echo [错误] 依赖安装失败，请检查网络连接后重试。
        pause
        exit /b 1
    )
    echo [完成] 安装成功！
    echo.
)

echo [启动] 正在启动图形界面...
echo.

REM 启动 GUI
"%FOUND_PYTHON%" "%~dp0main.py"

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo   程序已退出 (退出码: %errorlevel%)
    echo ========================================
)
