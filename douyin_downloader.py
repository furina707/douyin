import httpx
import re
import json
import subprocess
import os
import sys

def get_douyin_live_stream(room_id):
    """
    获取抖音直播流地址
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://live.douyin.com/",
    }
    
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        # 1. 获取 ttwid 
        response = client.get("https://live.douyin.com/")
        ttwid = response.cookies.get("ttwid")
        if not ttwid:
            print("[-] 未能获取 ttwid cookie")
            return None
        
        # 2. 访问直播间页面
        headers["Cookie"] = f"ttwid={ttwid}"
        url = f"https://live.douyin.com/{room_id}"
        response = client.get(url)
        if response.status_code != 200:
            print(f"[-] 访问直播间失败，状态码: {response.status_code}")
            return None
        
        # 3. 提取流地址
        content = response.text
        # 搜索 flv 地址
        flv_matches = re.findall(r'https?://[^\s"\\\]]+?\.flv[^\s"\\\]]*', content)
        # 搜索转义的 flv 地址
        escaped_flv_matches = re.findall(r'https?:\\\/\\\/[^\s"\\\]]+?\.flv[^\s"\\\]]*', content)
        
        all_urls = list(set(flv_matches + [u.replace('\\/', '/') for u in escaped_flv_matches]))
        
        # 清理地址中的 HTML 转义和多余引号
        cleaned_urls = []
        for u in all_urls:
            # 移除 &amp; 和尾部的转义引号
            u = u.replace("&amp;", "&").split('&quot;')[0].split('\\"')[0]
            cleaned_urls.append(u)
        
        # 优先级排序：原画(or4/origin) > 蓝光(uhd) > 超清(hd) > 标清(sd)
        def get_priority(url):
            url_lower = url.lower()
            if "_or4" in url_lower or "origin" in url_lower:
                return 0
            if "uhd" in url_lower:
                return 1
            if "hd" in url_lower:
                return 2
            if "sd" in url_lower:
                return 3
            return 4

        # 优先选择包含 auth_key 的地址
        auth_urls = [u for u in cleaned_urls if "auth_key" in u]
        if auth_urls:
            auth_urls.sort(key=get_priority)
            return auth_urls[0], ttwid
            
        if cleaned_urls:
            cleaned_urls.sort(key=get_priority)
            return cleaned_urls[0], ttwid
            
    return None, None

def download_stream(stream_url, ttwid, output_name="live_record.mp4", preview=False):
    """
    使用 ffmpeg 下载直播流，可选开启预览
    """
    headers = (
        f"Referer: https://live.douyin.com/\r\n"
        f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        f"Cookie: ttwid={ttwid}\r\n"
    )
    
    if preview:
        # 一边下载一边预览的命令逻辑
        # 优化参数说明：
        # -fflags nobuffer: 减少缓冲区导致的延迟
        # -flags low_delay: 强制低延迟
        # -framedrop: 丢帧补偿，防止音画不同步
        ffmpeg_command = [
            "ffmpeg",
            "-headers", headers,
            "-i", stream_url,
            "-c", "copy",
            "-y",
            output_name,
            "-c", "copy",
            "-f", "nut",
            "-copyts", # 复制时间戳，维持同步
            "pipe:1"
        ]
        ffplay_command = [
            "ffplay",
            "-i", "pipe:0",
            "-window_title", f"Preview: {output_name}",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-framedrop",
            "-x", "300", # 考虑到 150% 缩放，将宽度限制为 300，高度自动按比例缩放
            "-loglevel", "error"
        ]
        
        print(f"[+] 开始下载并预览: {output_name}")
        try:
            # 启动 ffmpeg 进程
            p_ffmpeg = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            # 启动 ffplay 进程，接收 ffmpeg 的 stdout 作为 stdin
            p_ffplay = subprocess.Popen(ffplay_command, stdin=p_ffmpeg.stdout)
            
            # 等待进程结束
            p_ffplay.wait()
            if p_ffmpeg.poll() is None:
                p_ffmpeg.terminate()
        except KeyboardInterrupt:
            print("\n[!] 用户停止下载和预览")
        except Exception as e:
            print(f"[-] 出错: {e}")
    else:
        # 仅下载
        command = [
            "ffmpeg",
            "-headers", headers,
            "-i", stream_url,
            "-c", "copy",
            "-y",
            output_name
        ]
        print(f"[+] 开始下载: {output_name}")
        try:
            process = subprocess.Popen(command)
            process.wait()
        except KeyboardInterrupt:
            print("\n[!] 用户停止下载")
        except Exception as e:
            print(f"[-] 下载出错: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="抖音直播下载器")
    parser.add_argument("room_id", nargs="?", default="742788270877", help="直播间ID")
    parser.add_argument("--preview", action="store_true", help="是否开启一边下载一边预览")
    
    args = parser.parse_args()
    room_id = args.room_id
    
    print(f"[*] 正在获取直播间 {room_id} 的流地址...")
    stream_url, ttwid = get_douyin_live_stream(room_id)
    
    if stream_url:
        print(f"[+] 找到流地址: {stream_url}")
        output_file = f"douyin_{room_id}.mp4"
        download_stream(stream_url, ttwid, output_file, preview=args.preview)
    else:
        print("[-] 未能找到有效的直播流地址，可能主播已下播或页面结构变化。")
