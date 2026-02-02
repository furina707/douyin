@echo off
setlocal enabledelayedexpansion

title Douyin Live Downloader

echo ========================================
echo       Douyin Live Downloader
echo ========================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 错误: 未检测到 Python，请先安装 Python 并添加到环境变量。
    pause
    exit /b
)

:: 检查 FFmpeg 是否安装
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 错误: 未检测到 FFmpeg，请先安装 FFmpeg 并添加到环境变量。
    pause
    exit /b
)

:: 输入直播间 ID
set /p room_id="请输入抖音直播间 ID (默认: 742788270877): "
if "!room_id!"=="" set room_id=742788270877

:: 选择是否预览
set /p use_preview="是否开启一边下载一边预览? (y/n, 默认 y): "
if "!use_preview!"=="" set use_preview=y

set params=!room_id!
if /i "!use_preview!"=="y" (
    set params=!params! --preview
)

echo.
echo [*] 正在启动下载器...
echo [*] 房间 ID: !room_id!
echo [*] 预览模式: !use_preview!
echo.

python douyin_downloader.py !params!

echo.
echo [*] 运行结束。
pause
