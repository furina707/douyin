@echo off
setlocal enabledelayedexpansion

title Douyin Live Downloader

echo ========================================
echo       Douyin Live Downloader
echo ========================================
echo.

:: 检查 Python 是否安装
set PYTHON_CMD=

:: 尝试检测 py
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto :python_check_done
)

:: 尝试检测 python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :python_check_done
)

:: 如果都失败
echo [!] 错误: 未检测到 Python 环境。
echo 请尝试安装 Python (推荐 3.10+) 并勾选 "Add Python to PATH"。
echo.
echo 调试信息:
echo [DEBUG] py check failed.
echo [DEBUG] python check failed.
pause
exit /b

:python_check_done
echo [*] 检测到 Python 命令: !PYTHON_CMD!
!PYTHON_CMD! --version

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

:menu
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
    goto :menu
)

echo.
echo [*] 正在启动智能监控模式...
!PYTHON_CMD! douyin_downloader.py "!room_id!" --name "!room_name!" --auto-merge --preview --monitor

echo.
echo [*] 运行结束，按任意键退出...
pause >nul
exit

:end
exit
