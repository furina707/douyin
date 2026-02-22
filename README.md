# 全平台直播监控录制工具 (Live Recorder)

一个基于 Python 和 FFmpeg 的轻量级直播监控下载工具，支持**抖音**和**哔哩哔哩**。

## 主要功能
- **多平台支持**：同时支持抖音 (Douyin) 和 哔哩哔哩 (Bilibili) 直播监控。
- **自动检测开播**：实时监控直播间状态，开播自动启动录制，下播自动停止。
- **最高画质锁定**：自动获取并下载直播间所能提供的最高清晰度流。
- **实时预览**：支持在录制的同时开启预览窗口，音量已自动增强。
- **自动合并**：支持下播后自动将分段的视频文件合并为单个完整视频。
- **智能归档**：录制的文件自动按“主播名(ID)”分类存储到 `Downloads` 文件夹。

## 快速上手

### 1. 准备环境
- 安装 [Python 3.7+](https://www.python.org/)。
- 确保目录下包含 `ffmpeg.exe`, `ffplay.exe`, `ffprobe.exe`（已内置）。

### 2. 配置直播间
编辑 `config_rooms.txt`，按以下格式添加您想监控的直播间：
```text
备注名称,直播间URL或ID
```
例如：
```text
sharmu,https://live.bilibili.com/1848767780
夏祈,https://live.douyin.com/742788270877
```

### 3. 启动程序
**方式一：图形界面 (GUI)**
直接运行：
```bash
python live_recorder.py
```
在弹出的界面中选择直播间并点击“开始监控”。

**方式二：命令行 (CLI)**
```bash
python live_recorder.py [直播间ID] --monitor --auto-merge
```

## 注意事项
- 程序的录制功能依赖于 FFmpeg，请勿移动或删除目录下的 `.exe` 文件。
- 录制过程中请保持网络稳定。
- 本工具仅供技术研究使用，请勿用于非法用途。
