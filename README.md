# 抖音直播下载器 (Douyin Live Downloader)

一个基于 Python 和 FFmpeg 的轻量级抖音直播下载工具，支持**原画质下载**和**实时预览**。

## 功能特性
- **最高画质**：自动锁定直播间最高分辨率流地址（原画/UHD）。
- **实时预览**：支持一边下载一边通过 ffplay 观看直播，预览窗口自动适配屏幕缩放。
- **音画同步**：优化 FFmpeg 参数，解决长时下载导致的音画不同步问题。
- **自动授权**：内置 ttwid 获取逻辑，绕过 403 Forbidden 限制。

## 快速开始

### 前置条件
1. 安装 [Python 3.7+](https://www.python.org/)。
2. 安装 [FFmpeg](https://ffmpeg.org/) 并将其添加到系统环境变量。

### 安装依赖
```bash
pip install -r requirements.txt
```

### 使用方法
#### 1. 仅下载直播
```bash
python douyin_downloader.py [直播间ID]
```
例如：`python douyin_downloader.py 742788270877`

#### 2. 下载并实时预览
```bash
python douyin_downloader.py [直播间ID] --preview
```

## 预览配置
针对高分屏（如 150% 缩放），预览窗口默认宽度设置为 300 像素，以防遮挡屏幕。如需调整，请修改 `douyin_downloader.py` 中的 `-x` 参数。

## 免责声明
本工具仅用于个人学习和技术研究。请尊重主播版权，严禁将下载内容用于商业用途或非法传播。
