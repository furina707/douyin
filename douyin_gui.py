import tkinter as tk
from tkinter import scrolledtext
import subprocess
import threading
import sys
import os
import time
import ctypes
from ctypes import wintypes
import re

# Windows API Constants
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
SWP_NOZORDER = 0x0004
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

user32 = ctypes.windll.user32

class DouyinGUI:
    def __init__(self, root, cmd_args):
        self.root = root
        self.root.title("Douyin Live Monitor & Downloader")
        self.root.geometry("800x800")
        
        # 1. Video Preview Area (Top)
        self.video_frame = tk.Frame(self.root, bg="black")
        self.video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.placeholder_label = tk.Label(self.video_frame, text="等待直播预览启动...", fg="white", bg="black", font=("Arial", 14))
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # 2. Terminal/Log Area (Bottom)
        self.log_frame = tk.Frame(self.root, height=200)
        self.log_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=10, state='disabled', bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configuration
        self.cmd_args = cmd_args
        self.process = None
        self.embedded_hwnd = None
        
        # Start processes
        self.start_subprocess()
        self.start_window_embedder()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Resize handler
        self.video_frame.bind("<Configure>", self.on_resize)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def start_subprocess(self):
        def run():
            # Force unbuffered output and UTF-8 encoding
            cmd = [sys.executable, "-u", "douyin_downloader.py"] + self.cmd_args
            
            # Set environment variable to force Python to output UTF-8
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            
            # Start process
            try:
                # hide console window for subprocess
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                # Define CREATE_NO_WINDOW if not present (Python < 3.7)
                CREATE_NO_WINDOW = 0x08000000
                
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    startupinfo=startupinfo,
                    creationflags=CREATE_NO_WINDOW,
                    encoding='utf-8',
                    errors='replace',
                    env=env  # Pass the modified environment
                )
                
                for line in self.process.stdout:
                    self.root.after(0, self.log, line)
                    
                self.root.after(0, self.log, "\n[!] 进程已退出\n")
            except Exception as e:
                self.root.after(0, self.log, f"\n[!] 启动失败: {e}\n")

        threading.Thread(target=run, daemon=True).start()

    def start_window_embedder(self):
        def embed_loop():
            while True:
                if not self.embedded_hwnd or not user32.IsWindow(self.embedded_hwnd):
                    self.find_and_embed()
                time.sleep(1)
        
        threading.Thread(target=embed_loop, daemon=True).start()

    def find_and_embed(self):
        # Callback for EnumWindows
        target_hwnd = None
        
        def enum_window_callback(hwnd, _):
            nonlocal target_hwnd
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            
            # Match title pattern from douyin_downloader.py: "Preview: {output_name}"
            if title.startswith("Preview: "):
                # Ensure it's not already our child (though SetParent handles that)
                # Also ensure it's visible
                if user32.IsWindowVisible(hwnd):
                    target_hwnd = hwnd
                    return False # Stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_window_callback), 0)
        
        if target_hwnd:
            self.embed_window(target_hwnd)

    def embed_window(self, hwnd):
        self.embedded_hwnd = hwnd
        parent_hwnd = self.video_frame.winfo_id()
        
        # Modify style to remove borders and make it a child
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style = style & ~WS_CAPTION & ~WS_THICKFRAME
        # Note: ffplay might need WS_POPUP removed and WS_CHILD added, 
        # but sometimes ffplay acts weird if we force WS_CHILD too aggressively.
        # Let's try just parenting it.
        
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.SetParent(hwnd, parent_hwnd)
        
        # Hide placeholder
        self.root.after(0, self.placeholder_label.place_forget)
        
        # Initial resize
        self.on_resize(None)
        self.root.after(0, self.log, f"[*] 已捕获预览窗口 (HWND: {hwnd})\n")

    def on_resize(self, event):
        if self.embedded_hwnd and user32.IsWindow(self.embedded_hwnd):
            width = self.video_frame.winfo_width()
            height = self.video_frame.winfo_height()
            user32.MoveWindow(self.embedded_hwnd, 0, 0, width, height, True)

    def on_close(self):
        if self.process:
            # Use taskkill to kill the process tree (including ffmpeg/ffplay)
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                CREATE_NO_WINDOW = 0x08000000
                
                subprocess.run(
                    f"taskkill /F /T /PID {self.process.pid}", 
                    shell=True, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                    creationflags=CREATE_NO_WINDOW
                )
            except:
                # Fallback
                self.process.terminate()
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If args provided, run directly (Legacy mode / Called from bat)
        args = sys.argv[1:]
        root = tk.Tk()
        app = DouyinGUI(root, args)
        root.mainloop()
    else:
        # If no args, show Room Selector first
        class RoomSelector:
            def __init__(self, root):
                self.root = root
                self.root.title("Douyin Monitor - 选择直播间")
                self.root.geometry("400x500")
                
                tk.Label(root, text="请选择直播间 (支持数字键/回车):", font=("Arial", 12)).pack(pady=10)
                
                self.listbox = tk.Listbox(root, font=("Consolas", 11), selectmode=tk.SINGLE)
                self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
                
                self.rooms = self.load_rooms()
                for i, (name, rid) in enumerate(self.rooms, 1):
                    self.listbox.insert(tk.END, f"{i}. {name} ({rid})")
                
                tk.Label(root, text="或输入 ID/URL:", font=("Arial", 10)).pack(pady=5)
                self.custom_entry = tk.Entry(root, font=("Arial", 10))
                self.custom_entry.pack(fill=tk.X, padx=10)
                
                # Button
                tk.Button(root, text="启动监控", command=self.on_start, font=("Arial", 12), bg="#0078d7", fg="white").pack(pady=20, ipadx=20)

                # Bindings for "Terminal-like" operation
                self.root.bind('<Return>', lambda e: self.on_start())
                self.listbox.bind('<Double-Button-1>', lambda e: self.on_start())
                
                # Bind number keys 1-9
                for i in range(1, 10):
                    self.root.bind(str(i), lambda e, idx=i-1: self.select_by_index(idx))
                
                # Focus listbox by default
                self.listbox.focus_set()
                if self.listbox.size() > 0:
                    self.listbox.selection_set(0)
                    self.listbox.activate(0)

            def select_by_index(self, index):
                # Only trigger if custom entry is not focused
                if self.root.focus_get() == self.custom_entry:
                    return
                    
                if 0 <= index < self.listbox.size():
                    self.listbox.selection_clear(0, tk.END)
                    self.listbox.selection_set(index)
                    self.listbox.activate(index)
                    self.listbox.see(index)
                    # Optional: Auto-start on number press? 
                    # Maybe better to just select, so they hit Enter to confirm.
                    # "Like terminal" usually means type number + enter.

            def load_rooms(self):
                rooms = []
                if os.path.exists("config_rooms.txt"):
                    with open("config_rooms.txt", "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                parts = line.split(",")
                                if len(parts) >= 2:
                                    rooms.append((parts[0].strip(), parts[1].strip()))
                return rooms

            def on_start(self):
                selection = self.listbox.curselection()
                if selection:
                    name, rid = self.rooms[selection[0]]
                    self.launch(rid, name)
                else:
                    custom = self.custom_entry.get().strip()
                    if custom:
                        self.launch(custom, "Unknown")
                    else:
                        tk.messagebox.showwarning("提示", "请选择或输入直播间")

            def launch(self, rid, name):
                self.root.destroy()
                
                # Launch main GUI
                root = tk.Tk()
                # Construct args for DouyinGUI
                # Corresponds to: douyin_downloader.py "!room_id!" --name "!room_name!" --auto-merge --preview --monitor
                args = [rid, "--name", name, "--auto-merge", "--preview", "--monitor"]
                app = DouyinGUI(root, args)
                root.mainloop()

        root = tk.Tk()
        import tkinter.messagebox
        selector = RoomSelector(root)
        root.mainloop()
