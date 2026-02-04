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

:: 检查配置并显示菜单
set config_file=config_rooms.txt
if not exist "!config_file!" (
    echo # 抖音直播间配置列表 > "!config_file!"
    echo 默认房间,742788270877 >> "!config_file!"
)

echo 请选择直播间:
set count=0
for /f "usebackq tokens=1,2 delims=," %%a in ("!config_file!") do (
    set first_char=%%a
    set first_char=!first_char:~0,1!
    if not "!first_char!"=="#" (
        set /a count+=1
        set "room_name_!count!=%%a"
        set "room_val_!count!=%%b"
        echo [!count!] %%a (%%b)
    )
)
echo [0] 手动输入其他 ID 或 URL
echo.

set /p choice="请输入序号 (0-!count!, 默认 1): "
if "!choice!"=="" set choice=1

if "!choice!"=="0" (
    set /p room_id="请输入抖音直播间 ID 或 URL: "
) else (
    set room_id=!room_val_%choice%!
    set room_name=!room_name_%choice%!
    echo [*] 已选择: !room_name! (!room_id!)
)

if "!room_id!"=="" (
    echo [!] 房间 ID 不能为空，请重新运行。
    pause
    exit /b
)

:: 检查是否已有锁文件
set lock_file=.lock_!room_id!
if exist "!lock_file!" (
    echo [*] 检测到直播间 !room_id! 已有实例，将尝试替换。
    timeout /t 1 >nul
)

echo.
echo 请选择运行模式:
echo [1] 智能监控 (监控 + 自动下载 + 下播自动合并)
echo [2] 立即合并 (合并该直播间所有视频，包含历史件)
echo [3] 彻底清理 (删除该直播间所有分段视频)
echo.

set /p mode="请输入模式序号 (1-3, 默认 1): "
if "!mode!"=="" set mode=1

echo.
if "!mode!"=="1" (
    echo [*] 正在启动智能融合模式...
    python douyin_downloader.py !room_id! --name "!room_name!" --monitor --auto-merge --preview
) else if "!mode!"=="2" (
    echo [*] 正在执行手动合并...
    python douyin_downloader.py !room_id! --name "!room_name!" --merge
) else if "!mode!"=="3" (
    echo [!] 准备执行清理操作...
    python douyin_downloader.py !room_id! --name "!room_name!" --delete-segments
) else (
    echo [!] 无效模式，默认启动监控...
    python douyin_downloader.py !room_id! --name "!room_name!" --monitor --auto-merge --preview
)

:end
echo.
echo [*] 运行结束。
pause
