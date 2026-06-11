@echo off
chcp 65001 >nul
echo ============================================
echo   虚拟货币箱体震荡选币软件 - 打包构建脚本
echo   Crypto Box Scanner - Build Script
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo        下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/4] 安装 PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo [错误] PyInstaller 安装失败
    pause
    exit /b 1
)

echo.
echo [3/4] 开始打包为 EXE...
echo       这可能需要几分钟，请耐心等待...

REM 清除Python字节码缓存，确保使用最新代码
rmdir /s /q __pycache__ 2>nul
rmdir /s /q gui\__pycache__ 2>nul

pyinstaller --onefile ^
    --windowed ^
    --name "CryptoBoxScanner" ^
    --icon=NONE ^
    --add-data "crypto_box_scanner.py;." ^
    --add-data "sentiment.py;." ^
    --add-data "funding_rate.py;." ^
    --add-data "gui\analysis_engine.py;gui" ^
    --add-data "gui\trend_engine.py;gui" ^
    --add-data "gui\scan_worker.py;gui" ^
    --add-data "gui\main_window.py;gui" ^
    --add-data "gui\settings_dialog.py;gui" ^
    --add-data "gui\styles.py;gui" ^
    --add-data "gui\chart_widget.py;gui" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "requests" ^
    --hidden-import "sentiment" ^
    --hidden-import "funding_rate" ^
    --hidden-import "gui.analysis_engine" ^
    --hidden-import "gui.trend_engine" ^
    --hidden-import "gui.scan_worker" ^
    --hidden-import "gui.main_window" ^
    --hidden-import "gui.settings_dialog" ^
    --hidden-import "gui.styles" ^
    --hidden-import "gui.chart_widget" ^
    --clean ^
    --noconfirm ^
    main.py

if %errorlevel% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo [4/4] 打包完成！
echo.
echo ============================================
echo   可执行文件位置:
echo   dist\CryptoBoxScanner.exe
echo ============================================
echo.
echo 提示: 可以直接双击运行，或创建桌面快捷方式。
echo.

REM 复制到项目根目录方便使用
copy /Y "dist\CryptoBoxScanner.exe" "CryptoBoxScanner.exe" >nul 2>&1
if %errorlevel% equ 0 (
    echo 已复制 CryptoBoxScanner.exe 到当前目录
)

pause
