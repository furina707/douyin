import httpx
import re
import json
import subprocess
import os
import sys
import time
import glob

# 强制设置标准输出为 UTF-8 (解决 Windows 下 GUI 管道编码问题)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except: pass

def get_subprocess_kwargs(show_window=False):
    """
    获取 subprocess 的参数，用于隐藏 Windows 下的控制台窗口
    如果 show_window 为 True，则不强制隐藏主窗口（适用于 ffplay 等 GUI 程序）
    """
    kwargs = {}
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        
        # 仅当不需要显示窗口时，才设置 SW_HIDE
        # 对于 ffplay，我们希望它显示视频窗口，所以不设置 SW_HIDE (也不设置 STARTF_USESHOWWINDOW)
        # 但我们仍然使用 CREATE_NO_WINDOW 来隐藏它的控制台窗口
        if not show_window:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return kwargs

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
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **get_subprocess_kwargs())
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

def get_ttwid_from_browser():
    """
    通过模拟浏览器访问流程获取 ttwid
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        # 使用 http1=True 避开某些 HTTP/2 指纹检测
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10, http2=False) as client:
            # 1. 访问首页
            client.get("https://www.douyin.com/")
            # 2. 访问直播根目录 (很多 Cookie 是在这里设置的)
            client.get("https://live.douyin.com/")
            return client.cookies.get("ttwid")
    except:
        return None

def get_douyin_live_status(room_id):
    """
    获取抖音直播间状态及流地址 (2026 稳定修复版)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://live.douyin.com/",
        "Accept": "application/json, text/plain, */*",
    }
    
    room_title = "未知"
    ttwid = get_ttwid_from_browser()
    
    try:
        # 使用 http2=False 增加兼容性
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15, http2=False) as client:
            if ttwid:
                client.cookies.set("ttwid", ttwid)

            # 1. 使用 Webcast API (携带丰富参数以绕过空返回)
            try:
                api_url = "https://live.douyin.com/webcast/room/web/enter/"
                params = {
                    "web_rid": room_id,
                    "aid": "6383",
                    "device_platform": "web",
                    "browser_name": "chrome",
                    "cookie_enabled": "true",
                    "screen_width": "1920",
                    "screen_height": "1080",
                    "browser_language": "zh-CN",
                    "browser_platform": "Win32",
                    "browser_version": "120.0.0.0"
                }
                res = client.get(api_url, params=params)
                if res.status_code == 200 and len(res.content) > 0:
                    data = res.json()
                    if data.get("status_code") == 0:
                        room_data_list = data.get("data", {}).get("data", [])
                        if room_data_list:
                             room_info = room_data_list[0]
                             status = room_info.get("status")
                             room_title = room_info.get("title", "未知")
                             
                             if status == 2:
                                 stream_url_data = room_info.get("stream_url", {})
                                 flv_url_list = stream_url_data.get("flv_pull_url", {})
                                 
                                 # 优先级排序：原画 > 蓝光 > 高清 > 标清
                                 target_url = (flv_url_list.get("FULL_HD1") or 
                                              flv_url_list.get("HD1") or 
                                              flv_url_list.get("SD1") or 
                                              flv_url_list.get("SD2"))
                                 
                                 if target_url:
                                     print(f"[+] 成功通过 API 获取直播: {room_title}")
                                     return True, target_url, ttwid, room_title
                             elif status == 4:
                                 return False, None, ttwid, room_title
            except Exception:
                pass


            # 3. 备用：HTML 解析 (处理 API 被封禁的情况)
            try:
                resp_html = client.get(f"https://live.douyin.com/{room_id}")
                content = resp_html.text
                
                # 检查是否是验证码页面 (仅记录，不报错)
                # if "captcha" in content or "verify" in content:
                #      pass

                # 尝试解析 RENDER_DATA
                render_data_match = re.search(r'<script id="RENDER_DATA" type="application/json">(.*?)</script>', content)
                if render_data_match:
                    import urllib.parse
                    data_str = urllib.parse.unquote(render_data_match.group(1))
                    data = json.loads(data_str)
                    
                    # 递归寻找 roomInfo
                    def find_room_data(obj):
                        if not isinstance(obj, dict): return None
                        if 'roomInfo' in obj: return obj['roomInfo']
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
                        room_title = room_data.get('title', room_title)
                        if room_status == 2:
                            # 提取流地址
                            stream_url_data = room_data.get('stream_url', {})
                            flv_url_list = stream_url_data.get('flv_pull_url', {})
                            target_url = flv_url_list.get('FULL_HD1') or flv_url_list.get('HD1') or flv_url_list.get('SD1')
                            if target_url:
                                print(f"[+] HTML 检测到直播中: {room_title}")
                                return True, target_url, ttwid, room_title
                        elif room_status == 4:
                            return False, None, ttwid, room_title
            except Exception:
                pass

            # 4. 暴力搜索流地址 (最后的倔强)
            if 'content' in locals():
                flv_matches = re.findall(r'https?://[^\s"\\\]]+?\.flv[^\s"\\\]]*', content)
                if flv_matches:
                     url = flv_matches[0].replace('\\/', '/').replace("&amp;", "&").split('\\"')[0]
                     return True, url, ttwid, room_title

            # 5. 移动端接口尝试
            try:
                mobile_url = "https://webcast.amemv.com/webcast/room/reflow/info/"
                res_mobile = client.get(mobile_url, params={"room_id": room_id, "app_id": "1128"})
                if res_mobile.status_code == 200:
                    m_data = res_mobile.json()
                    m_room = m_data.get("data", {}).get("room", {})
                    if m_room and m_room.get("status") == 2:
                        target_url = m_room.get("stream_url", {}).get("flv_pull_url", {}).get("FULL_HD1")
                        if target_url:
                             return True, target_url, ttwid, m_room.get("title", room_title)
            except Exception:
                pass

            return False, None, ttwid, room_title
    except Exception as e:
        print(f"[-] 请求出错: {e}")
        return False, None, ttwid, f"出错: {str(e)}"

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
            "-f", "flv",      # 使用 flv 格式进行管道传输，兼容性更好
            "pipe:1"
        ]
        ffplay_command = [
            "ffplay",
            "-f", "flv", # 明确指定输入格式
            "-i", "pipe:0",
            "-window_title", f"Preview: {output_name}",
            "-fflags", "nobuffer+genpts",
            "-flags", "low_delay",
            "-framedrop",
            "-probesize", "1000000",
            "-analyzeduration", "1000000",
            "-x", "300", 
            "-loglevel", "warning" # 显示警告和错误
        ]
        
        print(f"[+] 开始下载并预览: {output_name}")
        try:
            # 启动 ffmpeg 进程
            # 注意：不应使用 time.sleep 等待，因为如果 pipe 缓冲区填满，ffmpeg 会阻塞，导致死锁
            p_ffmpeg = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **get_subprocess_kwargs())
            
            # 立即启动 ffplay 进程，接收 ffmpeg 的 stdout 作为 stdin
            # 去掉 stderr=subprocess.DEVNULL 以便看到 ffplay 的报错
            # show_window=True 允许 ffplay 显示其视频窗口 (虽然 CREATE_NO_WINDOW 隐藏了控制台)
            p_ffplay = subprocess.Popen(ffplay_command, stdin=p_ffmpeg.stdout, **get_subprocess_kwargs(show_window=True))
            
            # 关闭父进程中的 ffmpeg stdout 句柄，避免资源泄漏
            # 这样当 ffplay 退出时，ffmpeg 会收到 SIGPIPE (或写入错误) 而退出
            p_ffmpeg.stdout.close() 
            
            # 等待 ffplay 结束 (用户关闭窗口)
            p_ffplay.wait()
            
            if p_ffmpeg.poll() is None:
                print("[*] 预览窗口已关闭，停止下载...")
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
            process = subprocess.Popen(command, **get_subprocess_kwargs())
            process.wait()
        except KeyboardInterrupt:
            print("\n[!] 用户停止下载")
        except Exception as e:
            print(f"[-] 下载出错: {e}")
            return False
    return True

def format_timestamp(ts):
    return time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(ts))

def extract_ts_from_filename(fname):
    """
    从文件名中提取时间戳
    """
    # 尝试匹配新格式 Name(ID)TimeStamp.mp4
    # 例如：夏祈(742788270877)1770275465.mp4
    match_new = re.search(r'\)(\d{10})\.mp4$', fname)
    if match_new:
        return int(match_new.group(1))

    # 尝试匹配格式 YYYY-MM-DD_HH-MM-SS
    match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', fname)
    if match:
        try:
            dt = time.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
            return int(time.mktime(dt))
        except: pass
        
    # 尝试匹配紧凑格式 YYYYMMDD_HHMMSS
    match_compact = re.search(r'(\d{8}_\d{6})', fname)
    if match_compact:
        try:
            dt = time.strptime(match_compact.group(1), "%Y%m%d_%H%M%S")
            return int(time.mktime(dt))
        except: pass
    
    # 尝试匹配旧格式 timestamp (10位数字)
    match_ts = re.search(r'_(\d{10})\.mp4$', fname)
    if match_ts:
        return int(match_ts.group(1))
        
    all_timestamps = re.findall(r'(\d{10})', fname)
    if all_timestamps:
        return int(all_timestamps[-1])
        
    return 0

def monitor_live(room_id, room_name=None, preview=False, interval=30, auto_merge=False):
    """
    监控直播间状态，开播自动下载，下播识别通知
    """
    # 房间名显示逻辑：如果有备注名则使用备注名，否则使用房间ID
    # 但为了文件系统安全，我们需要对 room_name 进行清理（去除非法字符）
    sanitized_room_name = re.sub(r'[\\/:*?"<>|]', '_', room_name) if room_name else room_id
    
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
                    
                # 修改输出文件名格式：房间名(房间号)TimeStamp.mp4
                # 用户指定格式：夏祈（房间号）TimeStamp.mp4 (这里使用 ASCII 括号以确保兼容性)
                # 格式：{sanitized_room_name}({room_id}){timestamp}.mp4
                current_ts = int(time.time())
                
                output_file = f"{sanitized_room_name}({room_id}){current_ts}.mp4"
                
                print(f"[*] 正在下载到: {output_file}")
                # download_stream 返回后，我们需要确认是真下播还是网络波动
                download_stream(stream_url, ttwid, output_file, preview=preview)
                
                # 检查最新状态
                print(f"\n[*] 下载暂时中断，正在检查直播间状态...")
                is_live_now, _, _, _ = get_douyin_live_status(room_id)
                
                if not is_live_now:
                    print(f"[!] 确认已下播 (下播识别成功)")
                    if auto_merge:
                        print("[*] 正在执行自动合并 (仅合并原始分段)...")
                        # 自动合并模式下，只合并原始分段，以便删除源文件
                        merge_videos(room_id, include_merged=False, room_name=room_name)
                    
                    # 重新检查直播状态前等待
                    is_currently_live = False
                    time.sleep(interval)
                else:
                    print(f"[!] 直播仍在继续，可能是网络波动导致中断，正在尝试重连...")
                    # 继续循环，会重新获取流地址并开始新的下载
                    is_currently_live = True 
                    continue
            else:
                if is_currently_live:
                    print(f"\n[!] 检测到已下播 (下播识别成功)")
                    if auto_merge:
                        print("[*] 正在执行自动合并 (仅合并原始分段)...")
                        # 自动合并模式下，只合并原始分段，以便删除源文件
                        merge_videos(room_id, include_merged=False, room_name=room_name)
                    
                    # 重新检查直播状态前等待
                    is_currently_live = False
                    time.sleep(interval)
                
                # 在 GUI 模式下，\r 会导致缓冲区等待换行符，从而导致日志不显示
                # 因此我们直接使用 print 输出，虽然会刷屏，但能保证用户看到状态
                print(f"[*] 等待开播中... (最后检查: {time.strftime('%H:%M:%S')}, 状态: {room_title})")
                
        except Exception as e:
            print(f"\n[-] 监控循环出错: {e}")
            
        time.sleep(interval)

def merge_videos(room_id, include_merged=True, room_name=None):
    """
    按时间顺序合并同一个直播间的视频文件
    """
    sanitized_room_name = re.sub(r'[\\/:*?"<>|]', '_', room_name) if room_name else room_id
    
    # 查找符合命名的所有 mp4 文件
    # 兼容旧格式：douyin_{room_id}_{timestamp}.mp4
    # 新格式：{sanitized_room_name}({room_id})_{readable_time}.mp4
    
    # 我们主要匹配包含 ({room_id}) 的文件，或者旧格式 douyin_{room_id}_
    all_files = []
    all_files.extend(glob.glob(f"*{room_id}*.mp4"))
    
    # 也要查找 Downloads 子目录下的文件 (防止已被归档但未合并)
    all_files.extend(glob.glob(f"Downloads/*/*{room_id}*.mp4"))
    
    # 去重
    all_files = list(set(all_files))
    files = []
    
    # 过滤逻辑
    for f in all_files:
        basename = os.path.basename(f)
        # 排除 merged 文件（除非开启 include_merged）
        if not include_merged and "_merged_" in basename:
            continue
        # 排除 concat 列表文件（虽然 glob mp4 不会匹配到 txt，但防万一）
        if basename.startswith("concat_"):
            continue
            
        # 必须包含 room_id
        if str(room_id) not in basename:
            continue
            
        files.append(f)
    
    if not files:
        print(f"[-] 未找到直播间 {room_id} 的{'视频' if include_merged else '原始分段'}文件。")
        return False
        
    # 按文件名排序（因为日期格式 YYYY-MM-DD_HH-MM-SS 是字母序递增的，所以直接 sort 即可）
    files.sort()
    
    if len(files) < 1:
        print(f"[*] 只有 {len(files)} 个{'视频' if include_merged else '原始分段'}文件，无需合并。")
        return False
        
    print(f"[*] 发现 {len(files)} 个文件，准备合并...")
    
    # 创建 concat 列表文件
    concat_list = f"concat_{room_id}.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for file in files:
            # FFmpeg concat 格式要求路径使用正斜杠或转义
            file_path = os.path.abspath(file).replace("\\", "/")
            f.write(f"file '{file_path}'\n")
            
    # 确定输出文件名的时间范围
    # 尝试从文件名提取时间，如果提取不到则使用文件修改时间
    start_ts = 0
    
    # 获取第一个文件的开始时间戳
    ts = extract_ts_from_filename(files[0])
    if not ts:
        ts = int(os.path.getctime(files[0]))
    
    # 格式化时间戳为可读格式 YYYY-MM-DD_HH-MM-SS
    # t1 = format_timestamp(ts)

    # 创建 Downloads/房间名(房间ID) 目录用于存放合并后的文件
    # 实现按直播间归档，避免所有文件混在一起
    room_folder_name = f"{sanitized_room_name}({room_id})"
    output_dir = os.path.join("Downloads", room_folder_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 输出文件名格式：房间名(房间号)TimeStamp.mp4
    # 恢复完整文件名，确保文件移动后依然可识别
    output_name = f"{sanitized_room_name}({room_id}){ts}.mp4"
    output_path = os.path.join(output_dir, output_name)
    
    # 如果目标文件已存在，为避免覆盖，添加计数器
    if os.path.exists(output_path):
        base, ext = os.path.splitext(output_name)
        counter = 1
        while os.path.exists(os.path.join(output_dir, f"{base}_{counter}{ext}")):
            counter += 1
        output_name = f"{base}_{counter}{ext}"
        output_path = os.path.join(output_dir, output_name)
    
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
        output_path
    ]
    
    try:
        print(f"[*] 正在合并到: {output_path} ...")
        process = subprocess.Popen(command, **get_subprocess_kwargs())
        process.wait()
        
        if process.returncode == 0:
            print(f"[+] 合并完成！生成文件: {output_path}")
            print(f"[*] 合并列表文件已删除。")
            os.remove(concat_list)
            
            # 删除原始分段文件
            if not include_merged:
                print(f"[*] 正在删除原始分段文件...")
                for file in files:
                    try:
                        os.remove(file)
                        print(f"    - 已删除: {file}")
                    except Exception as e:
                        print(f"    - 删除失败 {file}: {e}")
            else:
                print(f"[*] 全量合并模式下，为安全起见，不自动删除源文件。请确认无误后手动删除。")
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

    # 使用正则严格匹配原始分段：douyin_{room_id}_{timestamp}.mp4
    raw_pattern = re.compile(r"douyin_" + re.escape(room_id) + r"_(\d+)\.mp4$")
    all_files = glob.glob(f"douyin_{room_id}_*.mp4")
    
    files = []
    for f in all_files:
        if raw_pattern.match(os.path.basename(f)):
            files.append(f)

    if not files:
        print(f"[*] 未找到直播间 {room_id} 的原始分段视频文件。")
        return False

    print(f"[*] 发现直播间 {room_id} 的以下原始分段视频文件:")
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

def load_config(config_path="config_rooms.txt"):
    """
    加载直播间配置列表
    返回: {room_id: room_name, ...}
    """
    rooms = {}
    if not os.path.exists(config_path):
        return rooms
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                parts = line.split(",", 1)
                if len(parts) >= 2:
                    name = parts[0].strip()
                    url_or_id = parts[1].strip()
                    rid = extract_room_id(url_or_id)
                    if rid:
                        rooms[rid] = name
    except Exception as e:
        print(f"[-] 加载配置文件出错: {e}")
    return rooms

def load_config(config_path="config_rooms.txt"):
    mapping = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    # 支持 "Name,URL/ID" 格式
                    parts = line.split(",")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        url_or_id = parts[1].strip()
                        rid = extract_room_id(url_or_id)
                        if rid:
                            mapping[rid] = name
        except Exception as e:
            print(f"[-] 加载配置出错: {e}")
    return mapping

def organize_existing_files():
    """
    启动时自动整理根目录下的旧视频文件，将其归档到 Downloads 文件夹，并统一文件名格式
    """
    print("[*] 正在检查并整理现有视频文件...")
    
    # 加载房间名配置，以便为旧文件补全名字
    room_id_map = load_config()
    
    # 扫描当前目录下所有的 mp4 文件
    files = glob.glob("*.mp4")
    
    # 也要扫描 Downloads 子目录下的文件进行重命名
    files.extend(glob.glob("Downloads/*/*.mp4"))
    
    processed_count = 0
    
    for file_path in files:
        filename = os.path.basename(file_path)
        directory = os.path.dirname(file_path)
        if not directory: directory = "."
        
        # 尝试从父目录名称推断房间信息 (针对 Downloads/Room(ID)/... 下的文件)
        parent_dir_name = os.path.basename(directory)
        inferred_room_name = None
        inferred_room_id = None
        
        match_folder = re.match(r"(.*)\((\d+)\)$", parent_dir_name)
        if match_folder:
            inferred_room_name = match_folder.group(1)
            inferred_room_id = match_folder.group(2)

        # 跳过看起来像是正在下载的文件（最近 10 秒内修改）
        if time.time() - os.path.getmtime(file_path) < 10:
            continue
            
        # 1. 解析信息
        room_name = None
        room_id = None
        timestamp = 0
        
        # 尝试匹配新标准格式: Name(ID)TimeStamp.mp4
        match_std = re.match(r"^(.*)\((\d+)\)(\d{10})\.mp4$", filename)
        if match_std:
            # 已经是标准格式，但可能需要移动位置
            room_name = match_std.group(1)
            room_id = match_std.group(2)
            timestamp = int(match_std.group(3))
            
            # 如果在正确的文件夹里，且名字格式正确，就跳过
            if inferred_room_id == room_id:
                continue
        else:
            # 尝试匹配其他格式
            # 格式: Name(ID)_YYYY-MM-DD_HH-MM-SS.mp4
            match_date = re.match(r"^(.*)\((\d+)\)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.mp4$", filename)
            
            # 格式: douyin_ID_Timestamp.mp4
            match_old = re.match(r"^douyin_(\d+)_(\d{10})\.mp4$", filename)
            
            # 格式: Name(ID)....mp4 (通用匹配)
            match_generic = re.match(r"(.*)\((\d+)\).*\.mp4", filename)

            # 纯日期格式 (如 2026-02-10_08-03-26.mp4)，如果在已知的文件夹里
            match_pure_date = re.match(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.mp4$", filename)

            if match_date:
                room_name = match_date.group(1)
                room_id = match_date.group(2)
                try:
                    dt = time.strptime(match_date.group(3), "%Y-%m-%d_%H-%M-%S")
                    timestamp = int(time.mktime(dt))
                except: pass
            elif match_old:
                room_id = match_old.group(1)
                timestamp = int(match_old.group(2))
                room_name = room_id_map.get(room_id, f"Douyin")
            elif match_generic:
                room_name = match_generic.group(1)
                room_id = match_generic.group(2)
                # 尝试从文件名提取时间戳
                timestamp = extract_ts_from_filename(filename)
                if timestamp == 0:
                    # 如果提取不到，使用文件修改时间
                    timestamp = int(os.path.getmtime(file_path))
            elif match_pure_date and inferred_room_id:
                # 这是一个在这个文件夹里的纯日期文件，我们用文件夹的信息来补全它
                room_name = inferred_room_name
                room_id = inferred_room_id
                try:
                    dt = time.strptime(match_pure_date.group(1), "%Y-%m-%d_%H-%M-%S")
                    timestamp = int(time.mktime(dt))
                except: 
                    timestamp = int(os.path.getmtime(file_path))
        
        if room_id:
            # 如果我们识别出了 ID，就进行处理
            
            # 确保有名字
            if not room_name or room_name == "Douyin":
                room_name = room_id_map.get(room_id, room_name or f"Douyin")
                
            sanitized_name = re.sub(r'[\\/:*?"<>|]', '_', room_name)
            
            # 目标文件夹
            room_folder = f"{sanitized_name}({room_id})"
            target_dir = os.path.join("Downloads", room_folder)
            
            # 目标文件名 (新格式)
            if timestamp > 0:
                new_filename = f"{sanitized_name}({room_id}){timestamp}.mp4"
            else:
                # 如果实在没有时间戳，保持原文件名，但可能需要清理特殊字符
                new_filename = filename
            
            target_path = os.path.join(target_dir, new_filename)
            
            # 检查是否需要移动或重命名
            # 如果路径不同 OR 文件名不同
            current_abs = os.path.abspath(file_path)
            target_abs = os.path.abspath(target_path)
            
            if current_abs != target_abs:
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                
                # 处理文件名冲突
                if os.path.exists(target_path):
                    # 如果目标文件已存在且大小相同，可能是重复文件，可以直接删除源文件
                    if os.path.getsize(target_path) == os.path.getsize(file_path):
                        try:
                            os.remove(file_path)
                            print(f"    - 删除重复文件: {filename}")
                            processed_count += 1
                        except: pass
                        continue
                    else:
                        # 大小不同，改名避免覆盖
                        base, ext = os.path.splitext(new_filename)
                        counter = 1
                        while os.path.exists(os.path.join(target_dir, f"{base}_{counter}{ext}")):
                            counter += 1
                        target_path = os.path.join(target_dir, f"{base}_{counter}{ext}")
                
                try:
                    import shutil
                    shutil.move(file_path, target_path)
                    action = "归档并重命名" if filename != os.path.basename(target_path) else "归档"
                    print(f"    - {action}: {filename} -> {os.path.relpath(target_path)}")
                    processed_count += 1
                except Exception as e:
                    print(f"    - 操作失败 {filename}: {e}")

    if processed_count > 0:
        print(f"[*] 整理完成，共处理 {processed_count} 个文件。\n")
    else:
        print("[*] 文件整洁，无需整理。\n")

if __name__ == "__main__":
    import argparse
    
    # 启动时自动整理文件
    organize_existing_files()
    
    parser = argparse.ArgumentParser(description="抖音直播下载与监控器")
    parser.add_argument("room_id", nargs="?", help="直播间ID (如果使用了 --config，此参数可选)")
    parser.add_argument("--name", help="直播间备注名称 (命令行参数优先级高于配置文件)")
    parser.add_argument("--config", nargs="?", const="config_rooms.txt", help="配置文件路径 (默认: config_rooms.txt)")
    parser.add_argument("--preview", action="store_true", help="是否开启一边下载一边预览")
    parser.add_argument("--monitor", action="store_true", help="开启监控模式 (下播自动识别，开播自动下载)")
    parser.add_argument("--interval", type=int, default=30, help="监控检查间隔(秒)")
    parser.add_argument("--merge", action="store_true", help="合并该直播间的所有原始分段视频")
    parser.add_argument("--include-merged", action="store_true", help="合并时包含已合并的视频 (全量合并)")
    parser.add_argument("--auto-merge", action="store_true", help="下播后自动合并所有视频")
    parser.add_argument("--delete-segments", action="store_true", help="删除该直播间的所有分段视频")
    
    args = parser.parse_args()
    
    # 加载配置
    config_rooms = {}
    if args.config:
        config_path = args.config if args.config != "const" else "config_rooms.txt"
        config_rooms = load_config(config_path)
        print(f"[*] 已加载配置文件，包含 {len(config_rooms)} 个直播间")
        
    # 如果没有提供 room_id 但有 config，则可能需要批量监控（目前简单处理：如果不提供ID，列出配置并退出，或者需要支持多进程监控）
    # 这里我们保持逻辑简单：如果提供了 room_id，尝试从配置中查找名字
    
    if not args.room_id:
        if args.config and config_rooms:
            print("\n[*] 配置文件中的直播间列表:")
            for rid, name in config_rooms.items():
                print(f"    - {name}: {rid}")
            print("\n请指定要下载/监控的 room_id，或者使用脚本批量启动。")
            sys.exit(0)
        else:
            # 默认 fallback ID
            room_id = "742788270877"
    else:
        room_id = extract_room_id(args.room_id)

    # 优先使用命令行提供的名字，其次使用配置文件中的名字
    room_name = args.name
    if not room_name and room_id in config_rooms:
        room_name = config_rooms[room_id]
        print(f"[*] 从配置文件识别到房间名: {room_name}")
    
    if args.merge:
        merge_videos(room_id, include_merged=args.include_merged, room_name=room_name)
        sys.exit(0)
    
    if args.delete_segments:
        delete_segments(room_id)
        sys.exit(0)
        
    # 设置终端标题（仅限 Windows）
    # if os.name == 'nt':
    #     title = f"DouyinDownloader - {room_name} ({room_id})" if room_name else f"DouyinDownloader - {room_id}"
    #     os.system(f"title {title}")
        
    # 检查是否已有实例运行
    lock_handle, lock_path = check_single_instance(room_id)
    if not lock_handle:
        print(f"\n[!] 错误: 检测到直播间 {room_id} 已经有一个下载/监控实例在运行。")
        print("[!] 为避免冲突，请勿重复启动同一个房间的程序。")
        sys.exit(1)
    
    try:
        # 启动前先尝试合并一次，防止之前残留
        if args.auto_merge:
             print("[*] 启动前检查：正在尝试合并之前的分段文件...")
             merge_videos(room_id, include_merged=False, room_name=room_name)

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
                
                # 构造文件名逻辑复用 monitor_live 中的逻辑
                sanitized_room_name = re.sub(r'[\\/:*?"<>|]', '_', room_name) if room_name else room_id
                current_ts = int(time.time())
                readable_time = format_timestamp(current_ts)
                output_file = f"{sanitized_room_name}({room_id})_{readable_time}.mp4"
                
                print(f"[*] 正在下载到: {output_file}")
                download_stream(stream_url, ttwid, output_file, preview=args.preview)
                
                if args.auto_merge:
                    print("[*] 正在执行自动合并 (仅合并原始分段)...")
                    # 自动合并模式下，只合并原始分段（include_merged=False），这样可以安全删除源文件
                    merge_videos(room_id, include_merged=False, room_name=room_name)
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
