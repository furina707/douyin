import httpx
import re
import json
import subprocess
import os
import sys
import time

def extract_room_id(input_str):
    """
    从输入字符串中提取房间 ID (支持纯数字 ID 或 抖音链接)
    """
    if input_str.isdigit():
        return input_str
    
    # 匹配 https://live.douyin.com/123456
    live_match = re.search(r'live\.douyin\.com/(\d+)', input_str)
    if live_match:
        return live_match.group(1)
        
    # 匹配 https://www.douyin.com/follow/live/123456
    www_match = re.search(r'douyin\.com/follow/live/(\d+)', input_str)
    if www_match:
        return www_match.group(1)
        
    return input_str

def check_single_instance(room_id):
    """
    通过文件锁确保同一个直播间只有一个实例在运行
    如果发现已有实例，尝试清理旧实例（强制替换模式）
    """
    lock_file = os.path.join(os.getcwd(), f".lock_{room_id}")
    current_pid = os.getpid()
    
    def try_kill_old_process(pid):
        try:
            if os.name == 'nt':
                # Windows 使用 taskkill 及其子进程
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.kill(pid, signal.SIGKILL)
            return True
        except:
            return False

    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                old_pid = int(f.read().strip())
            
            if old_pid != current_pid:
                print(f"[*] 检测到直播间 {room_id} 已有实例 (PID: {old_pid}) 正在运行，正在尝试强制替换...")
                try_kill_old_process(old_pid)
                # 等待一会儿让旧进程释放文件
                time.sleep(1)
                if os.path.exists(lock_file):
                    os.remove(lock_file)
        except Exception as e:
            # 如果文件损坏或无法读取，尝试直接删除
            try: os.remove(lock_file)
            except: pass

    if os.name == 'nt':
        try:
            # 首先尝试以可读写模式打开，如果文件已存在则不会报错
            if os.path.exists(lock_file):
                # 尝试直接打开并写入（如果旧进程已死，这应该成功）
                handle = os.open(lock_file, os.O_RDWR | os.O_BINARY)
                os.ftruncate(handle, 0)
                os.lseek(handle, 0, os.SEEK_SET)
                os.write(handle, str(current_pid).encode())
                return handle, lock_file
            else:
                # 文件不存在，正常创建
                handle = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_BINARY)
                os.write(handle, str(current_pid).encode())
                return handle, lock_file
        except Exception:
            # 如果还是失败（例如文件被深度锁定），说明旧进程可能还在占坑
            return None, None
    else:
        try:
            f = open(lock_file, 'w')
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.write(str(current_pid))
            f.flush()
            return f, lock_file
        except Exception:
            return None, None

def get_douyin_live_status(room_id):
    """
    获取抖音直播间状态及流地址
    返回: (is_live, stream_url, ttwid, room_title)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://live.douyin.com/",
    }
    
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10) as client:
            # 1. 获取 ttwid 
            response = client.get("https://live.douyin.com/")
            ttwid = response.cookies.get("ttwid")
            if not ttwid:
                return False, None, None, "未知 (获取ttwid失败)"
            
            # 2. 访问直播间页面
            headers["Cookie"] = f"ttwid={ttwid}"
            url = f"https://live.douyin.com/{room_id}"
            response = client.get(url)
            if response.status_code != 200:
                return False, None, ttwid, f"未知 (HTTP {response.status_code})"
            
            content = response.text
            
            # 检查是否在直播
            # 抖音网页版通常在 RENDER_DATA 中包含状态
            # status 为 2 表示正在直播，4 表示未开播
            is_live = False
            room_title = "未知"
            
            # 尝试解析 RENDER_DATA
            render_data_match = re.search(r'<script id="RENDER_DATA" type="application/json">(.*?)</script>', content)
            if render_data_match:
                try:
                    import urllib.parse
                    data_str = urllib.parse.unquote(render_data_match.group(1))
                    data = json.loads(data_str)
                    
                    # 抖音 RENDER_DATA 结构可能发生变化，尝试多种路径
                    def find_room_data(obj):
                        if not isinstance(obj, dict): return None
                        # 路径1: common -> roomInfo
                        if 'roomInfo' in obj: return obj['roomInfo']
                        # 路径2: app -> initialState -> roomStore -> roomInfo
                        # 尝试递归搜索
                        for k, v in obj.items():
                            if k == 'roomInfo': return v
                            if isinstance(v, dict):
                                res = find_room_data(v)
                                if res: return res
                        return None

                    room_info = find_room_data(data)
                    if room_info:
                        room_data = room_info.get('room', {})
                        room_status = room_data.get('status')
                        room_title = room_data.get('title', '未知')
                        is_live = (room_status == 2)
                except Exception as e:
                    pass # 忽略解析错误，继续尝试正则

            # 如果 RENDER_DATA 解析失败，退回到正则搜索流地址
            # 3. 提取流地址
            flv_matches = re.findall(r'https?://[^\s"\\\]]+?\.flv[^\s"\\\]]*', content)
            escaped_flv_matches = re.findall(r'https?:\\\/\\\/[^\s"\\\]]+?\.flv[^\s"\\\]]*', content)
            
            all_urls = list(set(flv_matches + [u.replace('\\/', '/') for u in escaped_flv_matches]))
            
            if not all_urls:
                # 尝试匹配 m3u8 (HLS)
                m3u8_matches = re.findall(r'https?://[^\s"\\\]]+?\.m3u8[^\s"\\\]]*', content)
                escaped_m3u8_matches = re.findall(r'https?:\\\/\\\/[^\s"\\\]]+?\.m3u8[^\s"\\\]]*', content)
                all_urls = list(set(m3u8_matches + [u.replace('\\/', '/') for u in escaped_m3u8_matches]))

            cleaned_urls = []
            for u in all_urls:
                u = u.replace("&amp;", "&").split('&quot;')[0].split('\\"')[0]
                cleaned_urls.append(u)
            
            # 如果解析到了标题但没识别出直播状态，根据是否找到链接补充判断
            if cleaned_urls and not is_live:
                is_live = True
            
            # 优先级排序
            def get_priority(url):
                url_lower = url.lower()
                if "_or4" in url_lower or "origin" in url_lower: return 0
                if "uhd" in url_lower: return 1
                if "hd" in url_lower: return 2
                if "sd" in url_lower: return 3
                return 4

            # 如果找到了流地址，基本可以确定是在直播
            if cleaned_urls:
                is_live = True
                cleaned_urls.sort(key=get_priority)
                # 优先选择 auth_key
                auth_urls = [u for u in cleaned_urls if "auth_key" in u]
                if auth_urls:
                    auth_urls.sort(key=get_priority)
                    return True, auth_urls[0], ttwid, room_title
                return True, cleaned_urls[0], ttwid, room_title
            
            return is_live, None, ttwid, room_title
            
    except Exception as e:
        print(f"[-] 请求出错: {e}")
        return False, None, None, f"出错: {str(e)}"

def download_stream(stream_url, ttwid, output_name="live_record.mp4", preview=False):
    """
    使用 ffmpeg 下载直播流，可选开启预览
    """
    # 准备 FFmpeg 命令，确保 Referer 解决 403 问题
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
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof", # 允许在录制中断时文件依然可播放
            "-flush_packets", "1", # 强制实时写入磁盘
            "-y",
            output_name,
            "-c", "copy",
            "-f", "mpegts",      # 使用 mpegts 格式进行管道传输，更稳定
            "pipe:1"
        ]
        ffplay_command = [
            "ffplay",
            "-i", "pipe:0",
            "-window_title", f"Preview: {output_name}",
            "-fflags", "nobuffer+genpts",
            "-flags", "low_delay",
            "-framedrop",
            "-probesize", "1000000",
            "-analyzeduration", "1000000",
            "-x", "300", 
            "-loglevel", "error"
        ]
        
        print(f"[+] 开始下载并预览: {output_name}")
        try:
            # 启动 ffmpeg 进程
            p_ffmpeg = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            # 稍等片刻让 ffmpeg 缓冲一下数据再启动 ffplay
            time.sleep(1)
            
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
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof", # 允许在录制中断时文件依然可播放
            "-flush_packets", "1", # 强制实时写入磁盘
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
            return False
    return True

def monitor_live(room_id, room_name=None, preview=False, interval=30, auto_merge=False):
    """
    监控直播间状态，开播自动下载，下播识别通知
    """
    display_name = f"{room_name} ({room_id})" if room_name else room_id
    print(f"[*] 启动智能监控模式，目标直播间: {display_name}，检查间隔: {interval}s")
    if auto_merge:
        print("[*] 已开启下播自动合并功能")
    is_currently_live = False
    
    while True:
        try:
            is_live, stream_url, ttwid, room_title = get_douyin_live_status(room_id)
            
            if is_live:
                if not is_currently_live:
                    print(f"\n[!] 检测到开播！直播间标题: {room_title}")
                    is_currently_live = True
                    
                output_file = f"douyin_{room_id}_{int(time.time())}.mp4"
                print(f"[*] 正在下载到: {output_file}")
                # download_stream 返回后，我们需要确认是真下播还是网络波动
                download_stream(stream_url, ttwid, output_file, preview=preview)
                
                # 检查最新状态
                print(f"\n[*] 下载暂时中断，正在检查直播间状态...")
                is_live_now, _, _, _ = get_douyin_live_status(room_id)
                
                if not is_live_now:
                    print(f"[!] 确认已下播 (下播识别成功)")
                    if auto_merge:
                        print("[*] 正在执行自动合并...")
                        merge_videos(room_id)
                    print("[*] 正在按设定自动关闭程序...")
                    return # 只有真正下播才退出
                else:
                    print(f"[!] 直播仍在继续，可能是网络波动导致中断，正在尝试重连...")
                    # 继续循环，会重新获取流地址并开始新的下载
                    is_currently_live = True 
                    continue
            else:
                if is_currently_live:
                    print(f"\n[!] 检测到已下播 (下播识别成功)")
                    if auto_merge:
                        print("[*] 正在执行自动合并...")
                        merge_videos(room_id)
                    print("[*] 正在按设定自动关闭程序...")
                    return
                
                # 使用 sys.stdout.write 实现单行刷新显示
                sys.stdout.write(f"\r[*] 等待开播中... (最后检查: {time.strftime('%H:%M:%S')}, 房间: {display_name}, 状态: {room_title})")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"\n[-] 监控循环出错: {e}")
            
        time.sleep(interval)

def merge_videos(room_id, include_merged=True):
    """
    按时间顺序合并同一个直播间的视频文件
    """
    import glob
    import os
    
    # 查找符合命名的所有 mp4 文件
    patterns = [f"douyin_{room_id}_*.mp4", f"douyin_{room_id}.mp4"]
    all_files = []
    for p in patterns:
        all_files.extend(glob.glob(p))
    
    # 去重
    all_files = list(set(all_files))
    
    if include_merged:
        # 默认包含已合并的文件，用于二次合并
        files = all_files
    else:
        # 仅包含未合并的分段文件
        files = [f for f in all_files if "_merged_" not in f]
    
    if not files:
        print(f"[-] 未找到直播间 {room_id} 的视频文件。")
        return False
        
    # 按文件名（包含时间戳）排序
    files.sort()
    
    if len(files) < 2:
        print(f"[*] 只有 {len(files)} 个文件，无需合并。")
        return False
        
    print(f"[*] 发现 {len(files)} 个文件，准备合并...")
    
    # 创建 concat 列表文件
    concat_list = f"concat_{room_id}.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for file in files:
            # FFmpeg concat 格式要求路径使用正斜杠或转义
            file_path = os.path.abspath(file).replace("\\", "/")
            f.write(f"file '{file_path}'\n")
            
    # 从文件名中提取所有时间戳以确定开始和结束时间
    import re
    timestamps = []
    for file in files:
        # 匹配文件名中的 10 位数字时间戳
        ts_matches = re.findall(r'(\d{10})', os.path.basename(file))
        timestamps.extend([int(ts) for ts in ts_matches])
    
    current_ts = int(time.time())
    if timestamps:
        start_ts = min(timestamps)
        # 结束时间取文件名中的最大值和当前时间中的较大者（确保包含最新录制）
        end_ts = max(max(timestamps), current_ts)
    else:
        start_ts = current_ts
        end_ts = current_ts
        
    output_name = f"douyin_{room_id}_{start_ts}_{end_ts}.mp4"
    
    # 执行 FFmpeg 合并命令
    # -f concat: 使用 concat 分离器
    # -safe 0: 允许使用绝对路径
    # -c copy: 仅复制流，不重新编码，速度极快且无损
    command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        "-y",
        output_name
    ]
    
    try:
        print(f"[*] 正在合并到: {output_name} ...")
        process = subprocess.Popen(command)
        process.wait()
        
        if process.returncode == 0:
            print(f"[+] 合并完成！生成文件: {output_name}")
            print(f"[*] 合并列表文件已删除。")
            os.remove(concat_list)
            
            # 删除原始分段文件
            print(f"[*] 正在删除原始分段文件...")
            for file in files:
                try:
                    os.remove(file)
                    print(f"    - 已删除: {file}")
                except Exception as e:
                    print(f"    - 删除失败 {file}: {e}")
            return True
        else:
            print(f"[-] 合并失败，FFmpeg 返回码: {process.returncode}")
            return False
    except Exception as e:
        print(f"[-] 合并过程中出错: {e}")
        return False

def delete_segments(room_id):
    """
    删除指定直播间的所有分段视频文件
    """
    import glob
    import os

    pattern = f"douyin_{room_id}_*.mp4"
    files = glob.glob(pattern)

    if not files:
        print(f"[*] 未找到直播间 {room_id} 的分段视频文件。")
        return False

    print(f"[*] 发现直播间 {room_id} 的以下分段视频文件:")
    for i, file in enumerate(files):
        print(f"    {i+1}. {file}")

    confirm = input("确定要删除以上所有文件吗？(y/N): ").lower()
    if confirm == 'y':
        print("[*] 正在删除分段文件...")
        for file in files:
            try:
                os.remove(file)
                print(f"    - 已删除: {file}")
            except Exception as e:
                print(f"    - 删除失败 {file}: {e}")
        print("[+] 分段文件删除完成。")
        return True
    else:
        print("[*] 已取消删除操作。")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="抖音直播下载与监控器")
    parser.add_argument("room_id", nargs="?", default="742788270877", help="直播间ID")
    parser.add_argument("--name", help="直播间备注名称")
    parser.add_argument("--preview", action="store_true", help="是否开启一边下载一边预览")
    parser.add_argument("--monitor", action="store_true", help="开启监控模式 (下播自动识别，开播自动下载)")
    parser.add_argument("--interval", type=int, default=30, help="监控检查间隔(秒)")
    parser.add_argument("--merge", action="store_true", help="合并该直播间的所有视频 (默认包含已合并的)")
    parser.add_argument("--auto-merge", action="store_true", help="下播后自动合并所有视频")
    parser.add_argument("--delete-segments", action="store_true", help="删除该直播间的所有分段视频")
    
    args = parser.parse_args()
    room_id = extract_room_id(args.room_id)
    room_name = args.name
    
    if args.merge:
        merge_videos(room_id, include_merged=True)
        sys.exit(0)
    
    if args.delete_segments:
        delete_segments(room_id)
        sys.exit(0)
        
    # 设置终端标题（仅限 Windows）
    if os.name == 'nt':
        title = f"DouyinDownloader - {room_name} ({room_id})" if room_name else f"DouyinDownloader - {room_id}"
        os.system(f"title {title}")
        
    # 检查是否已有实例运行
    lock_handle, lock_path = check_single_instance(room_id)
    if not lock_handle:
        print(f"\n[!] 错误: 检测到直播间 {room_id} 已经有一个下载/监控实例在运行。")
        print("[!] 为避免冲突，请勿重复启动同一个房间的程序。")
        sys.exit(1)
    
    try:
        if args.monitor:
            try:
                monitor_live(room_id, room_name=room_name, preview=args.preview, interval=args.interval, auto_merge=args.auto_merge)
            except KeyboardInterrupt:
                print("\n[!] 监控已停止")
        else:
            print(f"[*] 正在获取直播间 {room_id} 的状态...")
            is_live, stream_url, ttwid, room_title = get_douyin_live_status(room_id)
            
            if is_live:
                print(f"[+] 正在直播: {room_title}")
                print(f"[+] 找到流地址: {stream_url}")
                output_file = f"douyin_{room_id}_{int(time.time())}.mp4"
                download_stream(stream_url, ttwid, output_file, preview=args.preview)
            else:
                print(f"[-] 主播目前未在直播 (状态: {room_title})")
    finally:
        # 程序退出时清理锁
        if os.name == 'nt':
            if lock_handle:
                os.close(lock_handle)
        else:
            if lock_handle:
                lock_handle.close()
        
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except:
            pass
