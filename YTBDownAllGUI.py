#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 万能下载器 GUI 版本
基于 Python + tkinter
"""

import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path
import time
import re
from datetime import datetime

def bring_to_front(window):
    """将窗口带到最前面（相对于父窗口）"""
    window.lift()
    window.focus_force()

# 配置文件路径
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ytbdownall"
BOOTSTRAP_FILE = DEFAULT_CONFIG_DIR / "bootstrap.json"

def get_config_dir():
    """获取配置文件目录"""
    try:
        if BOOTSTRAP_FILE.exists():
            with open(BOOTSTRAP_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                path = data.get("config_dir", "")
                if path and os.path.isabs(path):
                    return Path(path)
    except:
        pass
    return DEFAULT_CONFIG_DIR

CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_DIR = CONFIG_DIR / "history"

# 启用 faulthandler，段错误时输出到 crash.log 便于排查
# 注意：faulthandler.enable 需要真实的文件对象（支持 fileno），因此不再同时 tee 到 stderr，
# 而是将崩溃日志可靠地写入文件，并在 stderr 中打印日志路径。
try:
    import faulthandler
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _crash_log_path = CONFIG_DIR / "crash.log"
    # faulthandler 在发生段错误时直接写入字节，使用二进制模式避免类型错误
    _crash_log_file = open(_crash_log_path, "wb")
    _crash_log_file.write(
        f"faulthandler enabled at {datetime.now()}\n".encode("utf-8")
    )
    _crash_log_file.flush()
    faulthandler.enable(_crash_log_file)
    print(f"faulthandler 已启用，崩溃日志将写入: {_crash_log_path}", file=sys.stderr)
except Exception as e:
    print(f"faulthandler 启动失败: {e}", file=sys.stderr)

# 默认配置
DEFAULT_CONFIG = {
    "save_dir": "",
    "ask_save_dir": True,
    "default_checks": {
        "video": True,
        "cover": True,
        "srt": False,
        "vtt": False,
        "audio": False
    },
    "default_sub_langs": ["en", "zh-Hans"],
    "cookie_type": "none",  # none, file, firefox, chrome
    "cookie_file": "",
    "max_concurrent": 1,
    "history_count": 1,
    "history_dir": "",  # 默认为空，使用 CONFIG_DIR/history
    "skip_video_lists": True,  # 不下载视频列表（播放列表/频道页）
    "skip_live": True,  # 检测到直播时跳过
    "link_subtitle_keyword": False,  # 是否启用链接行尾字幕关键字识别
    "link_subtitle_format": "srt",  # 行尾字幕关键字识别时默认勾选 SRT 或 VTT
    "legacy_server_connect": False,  # 是否使用 --legacy-server-connect 解决 SSL 握手失败
    "no_check_certificates": False,  # 是否使用 --no-check-certificates 解决部分 SSL/EOF 错误
    "add_metadata": False,  # 下载视频时是否添加元数据
    "download_log_enabled": False,  # 是否记录下载日志
    "download_log_count": 5,  # 下载日志文件数量限制
    "download_log_dir": "",  # 下载日志保存目录，默认使用 CONFIG_DIR/logs/downloads
    "yt_dlp_path": "",
    "ffmpeg_path": "",
    "deno_path": ""
}


def set_config_dir(new_dir):
    """设置配置文件目录"""
    global CONFIG_DIR, CONFIG_FILE, HISTORY_DIR
    new_path = Path(new_dir)
    new_path.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(BOOTSTRAP_FILE, 'w', encoding='utf-8') as f:
        json.dump({"config_dir": str(new_path)}, f, indent=2, ensure_ascii=False)
    CONFIG_DIR = new_path
    CONFIG_FILE = CONFIG_DIR / "config.json"
    HISTORY_DIR = CONFIG_DIR / "history"


class ConfigManager:
    """配置管理器"""
    
    _lock = threading.Lock()
    
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        history_dir = DEFAULT_CONFIG.get("history_dir", "")
        if history_dir:
            Path(history_dir).mkdir(parents=True, exist_ok=True)
        else:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self.load()
    
    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    config = DEFAULT_CONFIG.copy()
                    config.update(saved)
                    return config
            except (json.JSONDecodeError, IOError, OSError):
                # 配置文件损坏或无法读取，使用默认配置
                pass
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get(self, key, default=None):
        with self._lock:
            return self.config.get(key, default)
    
    def set(self, key, value):
        with self._lock:
            self.config[key] = value
        self.save()


def cleanup_old_logs(log_dir, max_count):
    """清理超出数量限制的旧日志文件"""
    try:
        log_files = sorted(Path(log_dir).glob("*.log"))
        while len(log_files) > max_count:
            try:
                log_files[0].unlink()
            except OSError:
                pass
            log_files = log_files[1:]
    except Exception:
        pass


def get_download_log_path(config_manager):
    """获取本次下载日志文件路径（如启用），否则返回 None"""
    try:
        if not config_manager.get("download_log_enabled", False):
            return None
        download_log_dir = config_manager.get("download_log_dir", "")
        if not download_log_dir:
            download_log_dir = str(CONFIG_DIR / "logs" / "downloads")
        Path(download_log_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = Path(download_log_dir) / f"download_{timestamp}.log"
        cleanup_old_logs(download_log_dir, config_manager.get("download_log_count", 5))
        return log_file
    except Exception:
        return None


def map_sub_langs_for_url(url, sub_langs):
    """根据站点将字幕语言代码映射为对应站点支持的代码"""
    lower_url = url.lower()
    if any(host in lower_url for host in ["bilibili.com", "b23.tv"]):
        # Bilibili 常见代码：zh-CN、zh-TW、en、ja 等；扩展匹配提高命中率
        mapping = {
            "zh-Hans": ["zh-CN", "zh", "zh-Hans"],
            "zh-Hant": ["zh-TW", "zh-HK", "zh", "zh-Hant"],
            "zh": ["zh-CN", "zh-TW", "zh"],
            "en": ["en"],
            "ja": ["ja"],
            "ko": ["ko"],
        }
        expanded = []
        seen = set()
        for lang in sub_langs:
            for mapped in mapping.get(lang, [lang]):
                if mapped not in seen:
                    seen.add(mapped)
                    expanded.append(mapped)
        return expanded
    return sub_langs


class EnvChecker:
    """环境检测器"""
    
    @staticmethod
    def check_yt_dlp():
        pip_path = Path.home() / ".local" / "bin" / "yt-dlp"
        if pip_path.exists():
            return str(pip_path)
        try:
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return "yt-dlp"
        except:
            pass
        return None
    
    @staticmethod
    def check_ffmpeg():
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return "ffmpeg"
        except:
            pass
        return None
    
    @staticmethod
    def check_deno():
        deno_path = Path.home() / ".deno" / "bin" / "deno"
        if deno_path.exists():
            return str(deno_path)
        try:
            result = subprocess.run(["deno", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return "deno"
        except:
            pass
        return None
    
    @staticmethod
    def check_python():
        return sys.executable


class InstallDialog(tk.Toplevel):
    """安装对话框"""
    
    def __init__(self, parent, component_name):
        super().__init__(parent)
        self.title(f"安装 {component_name}")
        self.geometry("400x300")
        self.resizable(False, False)
        self.component_name = component_name
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        self.create_widgets()
        bring_to_front(self)
    
    def create_widgets(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text=f"选择发行版安装 {self.component_name}:", font=("", 12, "bold")).pack(pady=10)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.BOTH, expand=True, pady=20)
        
        # Arch Linux
        ttk.Button(btn_frame, text="Arch Linux", command=lambda: self.install("arch")).grid(row=0, column=0, padx=20, pady=10, sticky=tk.EW)
        
        # Debian/Ubuntu
        ttk.Button(btn_frame, text="Debian / Ubuntu", command=lambda: self.install("debian")).grid(row=1, column=0, padx=20, pady=10, sticky=tk.EW)
        
        # Fedora
        ttk.Button(btn_frame, text="Fedora", command=lambda: self.install("fedora")).grid(row=2, column=0, padx=20, pady=10, sticky=tk.EW)
        
        ttk.Button(frame, text="取消", command=self.destroy).pack(pady=10)
    
    def install(self, distro):
        self.result = (self.component_name, distro)
        self.destroy()


class EnvCheckFrame(ttk.Frame):
    """可复用的环境检测框架"""
    
    def __init__(self, parent, config_manager, show_buttons=True):
        super().__init__(parent)
        self.config_manager = config_manager
        self.show_buttons = show_buttons
        self.create_widgets()
    
    def create_widgets(self):
        result_frame = ttk.Frame(self)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.env_results = {}
        self.yt_path_var = tk.StringVar()
        self.ff_path_var = tk.StringVar()
        
        self.refresh_env()
    
    def refresh_env(self):
        for widget in self.winfo_children():
            widget.destroy()
        
        result_frame = ttk.Frame(self)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 检测 yt-dlp
        ttk.Label(result_frame, text="yt-dlp: ", font=("", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        yt_result = EnvChecker.check_yt_dlp()
        if yt_result:
            ttk.Label(result_frame, text=f"✓ 已找到 ({yt_result})", foreground="green").grid(row=0, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到", foreground="red").grid(row=0, column=1, sticky=tk.W)
        self.yt_path_var.set(yt_result or "")
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("yt-dlp")).grid(row=0, column=2, padx=5, pady=5)
        
        # 检测 ffmpeg
        ttk.Label(result_frame, text="ffmpeg: ", font=("", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        ff_result = EnvChecker.check_ffmpeg()
        if ff_result:
            ttk.Label(result_frame, text="✓ 已找到", foreground="green").grid(row=1, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到", foreground="red").grid(row=1, column=1, sticky=tk.W)
        self.ff_path_var.set(ff_result or "")
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("ffmpeg")).grid(row=1, column=2, padx=5, pady=5)
        
        # 检测 deno
        ttk.Label(result_frame, text="deno: ", font=("", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        deno_result = EnvChecker.check_deno()
        if deno_result:
            ttk.Label(result_frame, text=f"✓ 已找到 ({deno_result})", foreground="green").grid(row=2, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到 (可选，但建议安装)", foreground="orange").grid(row=2, column=1, sticky=tk.W)
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("deno")).grid(row=2, column=2, padx=5, pady=5)
        
        # 检测 Python
        ttk.Label(result_frame, text="Python: ", font=("", 10)).grid(row=3, column=0, sticky=tk.W, pady=5)
        py_result = EnvChecker.check_python()
        ttk.Label(result_frame, text=f"✓ {py_result}", foreground="green").grid(row=3, column=1, sticky=tk.W)
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("python3")).grid(row=3, column=2, padx=5, pady=5)
        
        # 手动选择路径
        path_frame = ttk.LabelFrame(self, text="手动指定路径 (可选)")
        path_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(path_frame, text="yt-dlp:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.yt_path_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(path_frame, text="浏览", command=lambda: self.browse_path("yt")).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(path_frame, text="ffmpeg:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.ff_path_var, width=50).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(path_frame, text="浏览", command=lambda: self.browse_path("ff")).grid(row=1, column=2, padx=5, pady=5)
        
        if self.show_buttons:
            btn_frame = ttk.Frame(self)
            btn_frame.pack(fill=tk.X, pady=10)
            ttk.Button(btn_frame, text="重新检测", command=self.refresh_env).pack(side=tk.LEFT, padx=5)
    
    def show_install(self, component):
        dialog = InstallDialog(self, component)
        self.wait_window(dialog)
        if dialog.result:
            comp, distro = dialog.result
            self.run_install(comp, distro)
    
    def run_install(self, component, distro):
        """执行安装命令"""
        install_cmds = {
            "yt-dlp": {
                "arch": "sudo pacman -S yt-dlp",
                "debian": "pip install -U yt-dlp --break-system-packages",
                "fedora": "sudo dnf install yt-dlp"
            },
            "ffmpeg": {
                "arch": "sudo pacman -S ffmpeg",
                "debian": "sudo apt install ffmpeg",
                "fedora": "sudo dnf install ffmpeg"
            },
            "deno": {
                "arch": "sudo pacman -S deno",
                "debian": "curl -fsSL https://deno.land/install.sh | sh",
                "fedora": "sudo dnf install deno"
            },
            "python3": {
                "arch": "sudo pacman -S python python-pip",
                "debian": "sudo apt install python3 python3-pip",
                "fedora": "sudo dnf install python3 python3-pip"
            }
        }
        
        cmd = install_cmds.get(component, {}).get(distro, "")
        if not cmd:
            messagebox.showerror("错误", f"未找到 {component} 在 {distro} 上的安装命令", parent=self)
            return
        
        # 在新终端中执行
        try:
            if distro == "debian" and component == "yt-dlp":
                # pip 安装不需要终端
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    messagebox.showinfo("成功", f"{component} 安装成功", parent=self)
                else:
                    messagebox.showerror("失败", f"安装失败: {result.stderr}", parent=self)
            else:
                # 需要终端的命令
                messagebox.showinfo("安装", f"请在终端中执行以下命令:\n\n{cmd}", parent=self)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)
        
        self.refresh_env()
    
    def browse_path(self, tool):
        path = filedialog.askopenfilename(title="选择可执行文件", parent=self)
        if path:
            if tool == "yt":
                self.yt_path_var.set(path)
            elif tool == "ff":
                self.ff_path_var.set(path)
    
    def save_paths(self):
        yt_path = self.yt_path_var.get()
        ff_path = self.ff_path_var.get()
        if yt_path:
            self.config_manager.set("yt_dlp_path", yt_path)
        if ff_path:
            self.config_manager.set("ffmpeg_path", ff_path)


class FirstRunWizard(tk.Toplevel):
    """首次运行向导"""
    
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.title("首次配置向导")
        self.geometry("600x550")
        self.resizable(False, False)
        self.config_manager = config_manager
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        self.current_step = 0
        self.steps = [
            self.step_welcome,
            self.step_config_dir,
            self.step_yt_dlp,
            self.step_ffmpeg,
            self.step_deno,
            self.step_python,
            self.step_cookie,
            self.step_finish
        ]
        
        self.yt_path_var = tk.StringVar()
        self.ff_path_var = tk.StringVar()
        self.config_dir_var = tk.StringVar(value=str(CONFIG_DIR))
        
        self.show_step()
        bring_to_front(self)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def show_step(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.steps[self.current_step]()
    
    def step_welcome(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="欢迎使用 YouTube 万能下载器", font=("", 16, "bold")).pack(pady=20)
        ttk.Label(frame, text="本向导将帮助您完成初始配置", font=("", 10)).pack(pady=10)
        ttk.Label(frame, text="• 检测运行环境\n• 配置认证方式\n• 设置默认选项", font=("", 10)).pack(pady=10)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        ttk.Button(btn_frame, text="开始配置", command=self.next_step).pack(side=tk.RIGHT)
    
    def step_config_dir(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="配置文件目录", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="选择配置文件的存放位置", font=("", 10)).pack(pady=5)
        ttk.Label(frame, text=f"当前目录: {CONFIG_DIR}", font=("", 9)).pack(pady=5)
        
        dir_frame = ttk.Frame(frame)
        dir_frame.pack(fill=tk.X, pady=20)
        
        ttk.Label(dir_frame, text="目录:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(dir_frame, textvariable=self.config_dir_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(dir_frame, text="浏览", command=self.browse_config_dir).pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def browse_config_dir(self):
        path = filedialog.askdirectory(title="选择配置文件目录", parent=self)
        if path:
            self.config_dir_var.set(path)
    
    def step_yt_dlp(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="环境检测 - yt-dlp", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="yt-dlp 是 YouTube 视频下载的核心组件", font=("", 10)).pack(pady=5)
        
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(result_frame, text="yt-dlp: ", font=("", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        yt_result = EnvChecker.check_yt_dlp()
        if yt_result:
            ttk.Label(result_frame, text=f"✓ 已找到 ({yt_result})", foreground="green").grid(row=0, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到", foreground="red").grid(row=0, column=1, sticky=tk.W)
        self.yt_path_var.set(yt_result or "")
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("yt-dlp")).grid(row=0, column=2, padx=5, pady=5)
        
        path_frame = ttk.LabelFrame(frame, text="手动指定路径 (可选)")
        path_frame.pack(fill=tk.X, pady=10)
        ttk.Label(path_frame, text="yt-dlp:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.yt_path_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(path_frame, text="浏览", command=lambda: self.browse_path("yt")).grid(row=0, column=2, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def step_ffmpeg(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="环境检测 - ffmpeg", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="ffmpeg 用于视频和音频处理", font=("", 10)).pack(pady=5)
        
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(result_frame, text="ffmpeg: ", font=("", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        ff_result = EnvChecker.check_ffmpeg()
        if ff_result:
            ttk.Label(result_frame, text=f"✓ 已找到 ({ff_result})", foreground="green").grid(row=0, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到", foreground="red").grid(row=0, column=1, sticky=tk.W)
        self.ff_path_var.set(ff_result or "")
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("ffmpeg")).grid(row=0, column=2, padx=5, pady=5)
        
        path_frame = ttk.LabelFrame(frame, text="手动指定路径 (可选)")
        path_frame.pack(fill=tk.X, pady=10)
        ttk.Label(path_frame, text="ffmpeg:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.ff_path_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(path_frame, text="浏览", command=lambda: self.browse_path("ff")).grid(row=0, column=2, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def step_deno(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="环境检测 - deno", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="deno 用于执行 JavaScript 代码 (可选，但建议安装)", font=("", 10)).pack(pady=5)
        
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(result_frame, text="deno: ", font=("", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        deno_result = EnvChecker.check_deno()
        if deno_result:
            ttk.Label(result_frame, text=f"✓ 已找到 ({deno_result})", foreground="green").grid(row=0, column=1, sticky=tk.W)
        else:
            ttk.Label(result_frame, text="✗ 未找到 (可选，但建议安装)", foreground="orange").grid(row=0, column=1, sticky=tk.W)
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("deno")).grid(row=0, column=2, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def step_python(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="环境检测 - Python", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="Python 是运行本程序的必要环境", font=("", 10)).pack(pady=5)
        
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(result_frame, text="Python: ", font=("", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        py_result = EnvChecker.check_python()
        ttk.Label(result_frame, text=f"✓ {py_result}", foreground="green").grid(row=0, column=1, sticky=tk.W)
        ttk.Button(result_frame, text="安装", command=lambda: self.show_install("python3")).grid(row=0, column=2, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def step_cookie(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Cookie 认证方式", font=("", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="选择如何获取 YouTube 认证信息", font=("", 10)).pack(pady=5)
        
        cookie_frame = ttk.Frame(frame)
        cookie_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.cookie_type_var = tk.StringVar(value="none")
        
        ttk.Radiobutton(cookie_frame, text="跳过认证 (不推荐，可能无法下载)", variable=self.cookie_type_var, value="none").pack(anchor=tk.W, pady=5)
        ttk.Radiobutton(cookie_frame, text="使用 cookies.txt 文件", variable=self.cookie_type_var, value="file").pack(anchor=tk.W, pady=5)
        ttk.Radiobutton(cookie_frame, text="从 Firefox 浏览器导入", variable=self.cookie_type_var, value="firefox").pack(anchor=tk.W, pady=5)
        ttk.Radiobutton(cookie_frame, text="从 Chrome 浏览器导入", variable=self.cookie_type_var, value="chrome").pack(anchor=tk.W, pady=5)
        
        file_frame = ttk.Frame(cookie_frame)
        file_frame.pack(fill=tk.X, pady=5, padx=20)
        ttk.Label(file_frame, text="cookies.txt 路径:").pack(side=tk.LEFT)
        self.cookie_file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.cookie_file_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="浏览", command=self.browse_cookie).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下一步", command=self.next_step).pack(side=tk.RIGHT, padx=5)
    
    def step_finish(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="配置完成", font=("", 14, "bold")).pack(pady=20)
        ttk.Label(frame, text="您可以随时在设置中修改这些选项", font=("", 10)).pack(pady=10)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        ttk.Button(btn_frame, text="上一步", command=self.prev_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="完成", command=self.finish).pack(side=tk.RIGHT, padx=5)
    
    def browse_cookie(self):
        path = filedialog.askopenfilename(title="选择 cookies.txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], parent=self)
        if path:
            self.cookie_file_var.set(path)
    
    def browse_path(self, tool):
        path = filedialog.askopenfilename(title="选择可执行文件", parent=self)
        if path:
            if tool == "yt":
                self.yt_path_var.set(path)
            elif tool == "ff":
                self.ff_path_var.set(path)
    
    def show_install(self, component):
        dialog = InstallDialog(self, component)
        self.wait_window(dialog)
        if dialog.result:
            comp, distro = dialog.result
            self.run_install(comp, distro)
    
    def run_install(self, component, distro):
        """执行安装命令"""
        install_cmds = {
            "yt-dlp": {
                "arch": "sudo pacman -S yt-dlp",
                "debian": "pip install -U yt-dlp --break-system-packages",
                "fedora": "sudo dnf install yt-dlp"
            },
            "ffmpeg": {
                "arch": "sudo pacman -S ffmpeg",
                "debian": "sudo apt install ffmpeg",
                "fedora": "sudo dnf install ffmpeg"
            },
            "deno": {
                "arch": "sudo pacman -S deno",
                "debian": "curl -fsSL https://deno.land/install.sh | sh",
                "fedora": "sudo dnf install deno"
            },
            "python3": {
                "arch": "sudo pacman -S python python-pip",
                "debian": "sudo apt install python3 python3-pip",
                "fedora": "sudo dnf install python3 python3-pip"
            }
        }
        
        cmd = install_cmds.get(component, {}).get(distro, "")
        if not cmd:
            messagebox.showerror("错误", f"未找到 {component} 在 {distro} 上的安装命令", parent=self)
            return
        
        # 在新终端中执行
        try:
            if distro == "debian" and component == "yt-dlp":
                # pip 安装不需要终端
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    messagebox.showinfo("成功", f"{component} 安装成功", parent=self)
                else:
                    messagebox.showerror("失败", f"安装失败: {result.stderr}", parent=self)
            else:
                # 需要终端的命令
                messagebox.showinfo("安装", f"请在终端中执行以下命令:\n\n{cmd}", parent=self)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)
        
        self.show_step()
    
    def next_step(self):
        if self.current_step == 1:  # config_dir 步骤
            new_dir = self.config_dir_var.get()
            if new_dir and new_dir != str(CONFIG_DIR):
                set_config_dir(new_dir)
                # 重新加载配置管理器
                self.config_manager = ConfigManager()
                # 同步更新历史目录到新配置目录下
                self.config_manager.set("history_dir", str(HISTORY_DIR))
        elif self.current_step == 2:  # yt-dlp 步骤
            self.config_manager.set("yt_dlp_path", self.yt_path_var.get())
        elif self.current_step == 3:  # ffmpeg 步骤
            self.config_manager.set("ffmpeg_path", self.ff_path_var.get())
        elif self.current_step == 6:  # cookie 步骤
            self.config_manager.set("cookie_type", self.cookie_type_var.get())
            if self.cookie_type_var.get() == "file":
                self.config_manager.set("cookie_file", self.cookie_file_var.get())
        
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.finish()
        else:
            self.show_step()
    
    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.show_step()
    
    def finish(self):
        self.config_manager.save()
        self.result = True
        self.destroy()
    
    def on_close(self):
        if messagebox.askyesno("确认", "确定要退出配置向导吗？", parent=self):
            self.destroy()


class SettingsWindow(tk.Toplevel):
    """设置窗口"""
    
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.title("设置")
        self.geometry("750x620")
        self.minsize(600, 450)
        self.config_manager = config_manager
        self.parent = parent
        
        self.transient(parent)
        
        self.create_widgets()
        bring_to_front(self)
    
    def _make_scrollable_tab(self, notebook, tab_text):
        """为 Notebook 标签页创建可滚动容器，inner 宽度跟随 outer 宽度变化"""
        outer = ttk.Frame(notebook, padding=0)
        notebook.add(outer, text=tab_text)
        
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        pending_width_update = [None]

        def _update_scrollregion(event=None):
            try:
                if canvas.winfo_exists():
                    canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def _do_update_inner_width():
            pending_width_update[0] = None
            try:
                if not canvas.winfo_exists() or not inner.winfo_exists():
                    return
                sb_width = scrollbar.winfo_width()
                if sb_width <= 1:
                    sb_width = 16  # 滚动条未布局完成前使用保守估计值
                canvas_width = max(1, canvas.winfo_width() - sb_width)
                canvas.itemconfig(inner_id, width=canvas_width)
            except tk.TclError:
                pass

        def _update_inner_width(event=None):
            if pending_width_update[0] is not None:
                try:
                    outer.after_cancel(pending_width_update[0])
                except tk.TclError:
                    pass
            pending_width_update[0] = outer.after(50, _do_update_inner_width)

        inner.bind("<Configure>", _update_scrollregion)
        outer.bind("<Configure>", lambda e: _update_inner_width())
        canvas.bind("<Configure>", lambda e: _update_inner_width())
        
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky=tk.W+tk.E+tk.N+tk.S)
        scrollbar.grid(row=0, column=1, sticky=tk.N+tk.S)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        
        def _on_mousewheel(event, c=canvas):
            c.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def _on_linux_up(event, c=canvas):
            c.yview_scroll(-3, "units")
        
        def _on_linux_down(event, c=canvas):
            c.yview_scroll(3, "units")
        
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Button-4>", _on_linux_up)
        canvas.bind("<Button-5>", _on_linux_down)
        inner.bind("<Button-4>", _on_linux_up)
        inner.bind("<Button-5>", _on_linux_down)
        
        return inner
    
    def create_widgets(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky=tk.W+tk.E+tk.N+tk.S, padx=10, pady=10)
        
        # 配置目录设置
        config_dir_frame = ttk.Frame(notebook, padding=10)
        notebook.add(config_dir_frame, text="配置目录")
        
        ttk.Label(config_dir_frame, text="配置文件存放目录:", font=("", 10, "bold")).pack(anchor=tk.W, pady=5)
        ttk.Label(config_dir_frame, text="修改后需要重启程序生效", foreground="orange").pack(anchor=tk.W, pady=2)
        
        dir_entry_frame = ttk.Frame(config_dir_frame)
        dir_entry_frame.pack(fill=tk.X, pady=10)
        self.config_dir_var = tk.StringVar(value=str(CONFIG_DIR))
        ttk.Entry(dir_entry_frame, textvariable=self.config_dir_var, width=45).pack(side=tk.LEFT, padx=5)
        ttk.Button(dir_entry_frame, text="浏览", command=self.browse_config_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_entry_frame, text="打开", command=self.open_config_dir).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(config_dir_frame, text="当前配置文件:", font=("", 10)).pack(anchor=tk.W, pady=(15, 2))
        ttk.Label(config_dir_frame, text=str(CONFIG_FILE), foreground="gray").pack(anchor=tk.W)
        
        # 下载设置（可滚动）
        download_frame = self._make_scrollable_tab(notebook, "下载设置")
        
        ttk.Label(download_frame, text="默认保存目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.save_dir_var = tk.StringVar(value=self.config_manager.get("save_dir", ""))
        ttk.Entry(download_frame, textvariable=self.save_dir_var, width=45).grid(row=0, column=1, padx=5, pady=5)
        dir_btn_frame = ttk.Frame(download_frame)
        dir_btn_frame.grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(dir_btn_frame, text="浏览", command=self.browse_save_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_btn_frame, text="打开", command=self.open_save_dir).pack(side=tk.LEFT, padx=2)
        
        self.ask_save_dir_var = tk.BooleanVar(value=self.config_manager.get("ask_save_dir", True))
        ttk.Checkbutton(download_frame, text="每次下载时询问保存目录", variable=self.ask_save_dir_var).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)
        
        ttk.Label(download_frame, text="最大并发下载数:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.concurrent_var = tk.IntVar(value=self.config_manager.get("max_concurrent", 1))
        ttk.Spinbox(download_frame, from_=1, to=10, textvariable=self.concurrent_var, width=5).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(download_frame, text="(并发下载可能导致 429 错误)", foreground="orange").grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=5)
        
        # 默认勾选
        check_frame = ttk.LabelFrame(download_frame, text="默认勾选", padding=10)
        check_frame.grid(row=4, column=0, columnspan=3, sticky=tk.W+tk.E, pady=10)
        
        defaults = self.config_manager.get("default_checks", {})
        self.video_check_var = tk.BooleanVar(value=defaults.get("video", True))
        self.cover_check_var = tk.BooleanVar(value=defaults.get("cover", True))
        self.srt_check_var = tk.BooleanVar(value=defaults.get("srt", False))
        self.vtt_check_var = tk.BooleanVar(value=defaults.get("vtt", False))
        self.audio_check_var = tk.BooleanVar(value=defaults.get("audio", False))
        
        ttk.Checkbutton(check_frame, text="视频", variable=self.video_check_var).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Checkbutton(check_frame, text="封面", variable=self.cover_check_var).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(check_frame, text="SRT 字幕", variable=self.srt_check_var).grid(row=1, column=0, sticky=tk.W, padx=5)
        ttk.Checkbutton(check_frame, text="VTT 字幕", variable=self.vtt_check_var).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(check_frame, text="音频", variable=self.audio_check_var).grid(row=2, column=0, sticky=tk.W, padx=5)
        
        # 链接行尾字幕关键字识别
        link_sub_frame = ttk.LabelFrame(download_frame, text="链接字幕识别", padding=10)
        link_sub_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W+tk.E, pady=10)
        
        self.link_subtitle_keyword_var = tk.BooleanVar(value=self.config_manager.get("link_subtitle_keyword", False))
        ttk.Checkbutton(link_sub_frame, text="启用链接行尾字幕关键字识别", variable=self.link_subtitle_keyword_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5)
        ttk.Label(link_sub_frame, text="示例: https://example.com/123 字幕", foreground="gray").grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5)
        
        self.link_subtitle_format_var = tk.StringVar(value=self.config_manager.get("link_subtitle_format", "srt"))
        ttk.Radiobutton(link_sub_frame, text="默认勾选 SRT", variable=self.link_subtitle_format_var, value="srt").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Radiobutton(link_sub_frame, text="默认勾选 VTT", variable=self.link_subtitle_format_var, value="vtt").grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        # 跳过选项
        skip_frame = ttk.LabelFrame(download_frame, text="跳过选项", padding=10)
        skip_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W+tk.E, pady=10)
        
        self.skip_video_lists_var = tk.BooleanVar(value=self.config_manager.get("skip_video_lists", True))
        ttk.Checkbutton(skip_frame, text="不下载视频列表（播放列表 / 频道页）", variable=self.skip_video_lists_var).grid(row=0, column=0, sticky=tk.W, padx=5)
        
        self.skip_live_var = tk.BooleanVar(value=self.config_manager.get("skip_live", True))
        ttk.Checkbutton(skip_frame, text="检测到直播时跳过下载", variable=self.skip_live_var).grid(row=1, column=0, sticky=tk.W, padx=5)
        
        # 网络设置
        network_frame = ttk.LabelFrame(download_frame, text="网络设置", padding=10)
        network_frame.grid(row=7, column=0, columnspan=3, sticky=tk.W+tk.E, pady=10)
        
        self.legacy_server_connect_var = tk.BooleanVar(value=self.config_manager.get("legacy_server_connect", False))
        ttk.Checkbutton(network_frame, text="使用 --legacy-server-connect（解决 SSLV3_ALERT_HANDSHAKE_FAILURE 错误）", variable=self.legacy_server_connect_var).grid(row=0, column=0, sticky=tk.W, padx=5)
        
        self.no_check_certificates_var = tk.BooleanVar(value=self.config_manager.get("no_check_certificates", False))
        ttk.Checkbutton(network_frame, text="忽略 SSL 证书验证（--no-check-certificates，可解决部分 SSL/EOF 错误，但降低安全性）", variable=self.no_check_certificates_var).grid(row=1, column=0, sticky=tk.W, padx=5)
        
        # 元数据设置
        metadata_frame = ttk.LabelFrame(download_frame, text="元数据", padding=10)
        metadata_frame.grid(row=8, column=0, columnspan=3, sticky=tk.W+tk.E, pady=10)
        
        self.add_metadata_var = tk.BooleanVar(value=self.config_manager.get("add_metadata", False))
        ttk.Checkbutton(metadata_frame, text="下载视频时添加元数据（--add-metadata）", variable=self.add_metadata_var).grid(row=0, column=0, sticky=tk.W, padx=5)
        
        # Cookie 设置
        cookie_frame = ttk.Frame(notebook, padding=10)
        notebook.add(cookie_frame, text="Cookie 设置")
        
        ttk.Label(cookie_frame, text="认证方式:").pack(anchor=tk.W, pady=5)
        self.cookie_type_var = tk.StringVar(value=self.config_manager.get("cookie_type", "none"))
        ttk.Radiobutton(cookie_frame, text="跳过认证", variable=self.cookie_type_var, value="none").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(cookie_frame, text="cookies.txt 文件", variable=self.cookie_type_var, value="file").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(cookie_frame, text="Firefox 浏览器", variable=self.cookie_type_var, value="firefox").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(cookie_frame, text="Chrome 浏览器", variable=self.cookie_type_var, value="chrome").pack(anchor=tk.W, pady=2)
        
        file_frame = ttk.Frame(cookie_frame)
        file_frame.pack(fill=tk.X, pady=5)
        ttk.Label(file_frame, text="cookies.txt 路径:").pack(side=tk.LEFT)
        self.cookie_file_var = tk.StringVar(value=self.config_manager.get("cookie_file", ""))
        ttk.Entry(file_frame, textvariable=self.cookie_file_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="浏览", command=self.browse_cookie).pack(side=tk.LEFT)
        
        # 字幕设置
        sub_frame = ttk.Frame(notebook, padding=10)
        notebook.add(sub_frame, text="字幕设置")
        
        ttk.Label(sub_frame, text="默认下载字幕语言:").pack(anchor=tk.W, pady=5)
        
        lang_frame = ttk.Frame(sub_frame)
        lang_frame.pack(fill=tk.X, pady=5)
        
        self.sub_langs = self.config_manager.get("default_sub_langs", ["en", "zh-Hans"])
        self.lang_vars = {}
        
        langs = [("英语", "en"), ("简体中文", "zh-Hans"), ("日语", "ja"), 
                 ("繁体中文", "zh-Hant"), ("韩语", "ko"), ("西班牙语", "es"),
                 ("法语", "fr"), ("德语", "de"), ("俄语", "ru"), ("葡萄牙语", "pt")]
        for i, (name, code) in enumerate(langs):
            var = tk.BooleanVar(value=code in self.sub_langs)
            self.lang_vars[code] = var
            ttk.Checkbutton(lang_frame, text=name, variable=var).grid(row=i//3, column=i%3, sticky=tk.W, padx=10, pady=2)
        
        # 历史记录
        history_frame = ttk.Frame(notebook, padding=10)
        notebook.add(history_frame, text="历史记录")
        
        ttk.Label(history_frame, text="历史记录保存目录:").pack(anchor=tk.W, pady=5)
        dir_frame = ttk.Frame(history_frame)
        dir_frame.pack(fill=tk.X, pady=5)
        self.history_dir_var = tk.StringVar(value=self.config_manager.get("history_dir", str(HISTORY_DIR)))
        ttk.Entry(dir_frame, textvariable=self.history_dir_var, width=45).pack(side=tk.LEFT, padx=5)
        ttk.Button(dir_frame, text="浏览", command=self.browse_history_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_frame, text="打开", command=self.open_history_dir).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(history_frame, text="历史记录文件数量:").pack(anchor=tk.W, pady=5)
        self.history_count_var = tk.IntVar(value=self.config_manager.get("history_count", 1))
        ttk.Spinbox(history_frame, from_=0, to=100, textvariable=self.history_count_var, width=5).pack(anchor=tk.W, pady=5)
        ttk.Label(history_frame, text="(设置为 0 表示不保存历史记录)", foreground="gray").pack(anchor=tk.W)
        
        # 下载日志
        download_log_frame = ttk.LabelFrame(history_frame, text="下载日志", padding=10)
        download_log_frame.pack(fill=tk.X, pady=10)
        
        self.download_log_enabled_var = tk.BooleanVar(value=self.config_manager.get("download_log_enabled", False))
        ttk.Checkbutton(download_log_frame, text="启用下载日志记录（记录每次下载的完整 yt-dlp 输出）", variable=self.download_log_enabled_var).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=5)
        
        ttk.Label(download_log_frame, text="保存目录:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5)
        self.download_log_dir_var = tk.StringVar(value=self.config_manager.get("download_log_dir", str(CONFIG_DIR / "logs" / "downloads")))
        ttk.Entry(download_log_frame, textvariable=self.download_log_dir_var, width=40).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(download_log_frame, text="浏览", command=self.browse_download_log_dir).grid(row=1, column=2, padx=2, pady=5)
        
        ttk.Label(download_log_frame, text="保留文件数量:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.download_log_count_var = tk.IntVar(value=self.config_manager.get("download_log_count", 5))
        ttk.Spinbox(download_log_frame, from_=1, to=100, textvariable=self.download_log_count_var, width=5).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 环境检测（可滚动）
        env_frame = self._make_scrollable_tab(notebook, "环境检测")
        
        self.env_notebook = ttk.Notebook(env_frame)
        self.env_notebook.grid(row=0, column=0, sticky=tk.W+tk.E+tk.N+tk.S, pady=5)
        env_frame.columnconfigure(0, weight=1)
        env_frame.rowconfigure(0, weight=1)
        
        # yt-dlp 检测
        yt_frame = ttk.Frame(self.env_notebook, padding=10)
        self.env_notebook.add(yt_frame, text="yt-dlp")
        self.yt_env_frame = self._create_env_page(yt_frame, "yt-dlp", "yt-dlp 是 YouTube 视频下载的核心组件", "yt")
        
        # ffmpeg 检测
        ff_frame = ttk.Frame(self.env_notebook, padding=10)
        self.env_notebook.add(ff_frame, text="ffmpeg")
        self.ff_env_frame = self._create_env_page(ff_frame, "ffmpeg", "ffmpeg 用于视频和音频处理", "ff")
        
        # deno 检测
        deno_frame = ttk.Frame(self.env_notebook, padding=10)
        self.env_notebook.add(deno_frame, text="deno")
        self.deno_env_frame = self._create_env_page(deno_frame, "deno", "deno 用于执行 JavaScript 代码 (可选，但建议安装)", "deno", optional=True)
        
        # Python 检测
        py_frame = ttk.Frame(self.env_notebook, padding=10)
        self.env_notebook.add(py_frame, text="Python")
        self.py_env_frame = self._create_env_page(py_frame, "python3", "Python 是运行本程序的必要环境", None)
        
        # 重新检测按钮
        ttk.Button(env_frame, text="重新检测全部", command=self.refresh_all_env).grid(row=1, column=0, pady=5)
        
        # 保存按钮
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, sticky=tk.E, padx=10, pady=10)
        ttk.Button(btn_frame, text="保存", command=self.save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)
    
    def browse_save_dir(self):
        path = filedialog.askdirectory(title="选择保存目录", parent=self)
        if path:
            self.save_dir_var.set(path)
    
    def open_save_dir(self):
        path = self.save_dir_var.get()
        if path and os.path.exists(path):
            subprocess.run(["xdg-open", path])
        else:
            messagebox.showwarning("警告", "目录不存在", parent=self)
    
    def browse_config_dir(self):
        path = filedialog.askdirectory(title="选择配置文件目录", parent=self)
        if path:
            self.config_dir_var.set(path)
    
    def open_config_dir(self):
        path = self.config_dir_var.get()
        if path and os.path.exists(path):
            subprocess.run(["xdg-open", path])
        else:
            messagebox.showwarning("警告", "目录不存在", parent=self)
    
    def browse_cookie(self):
        path = filedialog.askopenfilename(title="选择 cookies.txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], parent=self)
        if path:
            self.cookie_file_var.set(path)
    
    def browse_history_dir(self):
        path = filedialog.askdirectory(title="选择历史记录保存目录", parent=self)
        if path:
            self.history_dir_var.set(path)
    
    def open_history_dir(self):
        path = self.history_dir_var.get()
        if path and os.path.exists(path):
            subprocess.run(["xdg-open", path])
        else:
            messagebox.showwarning("警告", "目录不存在", parent=self)
    
    def browse_download_log_dir(self):
        path = filedialog.askdirectory(title="选择下载日志保存目录", parent=self)
        if path:
            self.download_log_dir_var.set(path)
    
    def _create_env_page(self, parent, component, description, path_key, optional=False):
        """创建环境检测页面"""
        frame_info = {"result_label": None, "path_var": None}
        
        ttk.Label(parent, text=description, font=("", 10)).pack(pady=5)
        
        # 检测结果
        result_frame = ttk.Frame(parent)
        result_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(result_frame, text=f"{component}: ", font=("", 10)).pack(side=tk.LEFT)
        
        # 检测组件
        check_func = {
            "yt-dlp": EnvChecker.check_yt_dlp,
            "ffmpeg": EnvChecker.check_ffmpeg,
            "deno": EnvChecker.check_deno,
            "python3": EnvChecker.check_python
        }.get(component, lambda: None)
        
        result = check_func()
        if result:
            result_text = f"✓ 已找到 ({result})" if component != "python3" else f"✓ {result}"
            result_color = "green"
        else:
            result_text = "✗ 未找到" + (" (可选，但建议安装)" if optional else "")
            result_color = "red" if not optional else "orange"
        
        frame_info["result_label"] = ttk.Label(result_frame, text=result_text, foreground=result_color)
        frame_info["result_label"].pack(side=tk.LEFT, padx=5)
        
        # 安装按钮
        ttk.Button(result_frame, text="安装", 
                  command=lambda: self._install_component(component, frame_info["result_label"], optional)).pack(side=tk.LEFT, padx=5)
        
        # 手动指定路径（仅 yt-dlp 和 ffmpeg）
        if path_key:
            path_frame = ttk.LabelFrame(parent, text="手动指定路径 (可选)")
            path_frame.pack(fill=tk.X, pady=10)
            
            frame_info["path_var"] = tk.StringVar(value=result or "")
            path_entry = ttk.Entry(path_frame, textvariable=frame_info["path_var"], width=50)
            path_entry.pack(side=tk.LEFT, padx=5, pady=5)
            ttk.Button(path_frame, text="浏览", 
                      command=lambda: self._browse_env_path(frame_info["path_var"])).pack(side=tk.LEFT, padx=5, pady=5)
        
        frame_info["component"] = component
        return frame_info
    
    def _install_component(self, component, result_label, optional):
        """安装组件"""
        dialog = InstallDialog(self, component)
        self.wait_window(dialog)
        if dialog.result:
            comp, distro = dialog.result
            self._run_install(comp, distro, result_label, optional)
    
    def _run_install(self, component, distro, result_label, optional):
        """执行安装命令"""
        install_cmds = {
            "yt-dlp": {
                "arch": "sudo pacman -S yt-dlp",
                "debian": "pip install -U yt-dlp --break-system-packages",
                "fedora": "sudo dnf install yt-dlp"
            },
            "ffmpeg": {
                "arch": "sudo pacman -S ffmpeg",
                "debian": "sudo apt install ffmpeg",
                "fedora": "sudo dnf install ffmpeg"
            },
            "deno": {
                "arch": "sudo pacman -S deno",
                "debian": "curl -fsSL https://deno.land/install.sh | sh",
                "fedora": "sudo dnf install deno"
            },
            "python3": {
                "arch": "sudo pacman -S python python-pip",
                "debian": "sudo apt install python3 python3-pip",
                "fedora": "sudo dnf install python3 python3-pip"
            }
        }
        
        cmd = install_cmds.get(component, {}).get(distro, "")
        if not cmd:
            messagebox.showerror("错误", f"未找到 {component} 在 {distro} 上的安装命令", parent=self)
            return
        
        try:
            if distro == "debian" and component == "yt-dlp":
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    messagebox.showinfo("成功", f"{component} 安装成功", parent=self)
                    # 更新检测结果
                    check_func = {
                        "yt-dlp": EnvChecker.check_yt_dlp,
                        "ffmpeg": EnvChecker.check_ffmpeg,
                        "deno": EnvChecker.check_deno,
                        "python3": EnvChecker.check_python
                    }.get(component, lambda: None)
                    new_result = check_func()
                    if new_result:
                        result_text = f"✓ 已找到 ({new_result})" if component != "python3" else f"✓ {new_result}"
                        result_label.config(text=result_text, foreground="green")
                else:
                    messagebox.showerror("失败", f"安装失败: {result.stderr}", parent=self)
            else:
                messagebox.showinfo("安装", f"请在终端中执行以下命令:\n\n{cmd}", parent=self)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)
    
    def _browse_env_path(self, path_var):
        """浏览环境路径"""
        path = filedialog.askopenfilename(title="选择可执行文件", parent=self)
        if path:
            path_var.set(path)
    
    def refresh_all_env(self):
        """重新检测所有环境"""
        # 刷新 yt-dlp
        yt_result = EnvChecker.check_yt_dlp()
        if yt_result:
            self.yt_env_frame["result_label"].config(text=f"✓ 已找到 ({yt_result})", foreground="green")
            if self.yt_env_frame.get("path_var"):
                self.yt_env_frame["path_var"].set(yt_result)
        else:
            self.yt_env_frame["result_label"].config(text="✗ 未找到", foreground="red")
        
        # 刷新 ffmpeg
        ff_result = EnvChecker.check_ffmpeg()
        if ff_result:
            self.ff_env_frame["result_label"].config(text=f"✓ 已找到 ({ff_result})", foreground="green")
            if self.ff_env_frame.get("path_var"):
                self.ff_env_frame["path_var"].set(ff_result)
        else:
            self.ff_env_frame["result_label"].config(text="✗ 未找到", foreground="red")
        
        # 刷新 deno
        deno_result = EnvChecker.check_deno()
        if deno_result:
            self.deno_env_frame["result_label"].config(text=f"✓ 已找到 ({deno_result})", foreground="green")
        else:
            self.deno_env_frame["result_label"].config(text="✗ 未找到 (可选，但建议安装)", foreground="orange")
        
        # 刷新 Python
        py_result = EnvChecker.check_python()
        if py_result:
            self.py_env_frame["result_label"].config(text=f"✓ {py_result}", foreground="green")
        else:
            self.py_env_frame["result_label"].config(text="✗ 未找到", foreground="red")
    
    def save_settings(self):
        new_config_dir = self.config_dir_var.get()
        if new_config_dir and new_config_dir != str(CONFIG_DIR):
            set_config_dir(new_config_dir)
            self.config_manager = ConfigManager()
            self.config_manager.set("history_dir", str(HISTORY_DIR))
        
        self.config_manager.set("save_dir", self.save_dir_var.get())
        self.config_manager.set("ask_save_dir", self.ask_save_dir_var.get())
        self.config_manager.set("max_concurrent", self.concurrent_var.get())
        self.config_manager.set("cookie_type", self.cookie_type_var.get())
        self.config_manager.set("cookie_file", self.cookie_file_var.get())
        self.config_manager.set("history_count", self.history_count_var.get())
        self.config_manager.set("history_dir", self.history_dir_var.get())
        self.config_manager.set("skip_video_lists", self.skip_video_lists_var.get())
        self.config_manager.set("skip_live", self.skip_live_var.get())
        self.config_manager.set("link_subtitle_keyword", self.link_subtitle_keyword_var.get())
        self.config_manager.set("link_subtitle_format", self.link_subtitle_format_var.get())
        self.config_manager.set("legacy_server_connect", self.legacy_server_connect_var.get())
        self.config_manager.set("no_check_certificates", self.no_check_certificates_var.get())
        self.config_manager.set("add_metadata", self.add_metadata_var.get())
        self.config_manager.set("download_log_enabled", self.download_log_enabled_var.get())
        self.config_manager.set("download_log_count", self.download_log_count_var.get())
        self.config_manager.set("download_log_dir", self.download_log_dir_var.get())
        
        self.config_manager.set("default_checks", {
            "video": self.video_check_var.get(),
            "cover": self.cover_check_var.get(),
            "srt": self.srt_check_var.get(),
            "vtt": self.vtt_check_var.get(),
            "audio": self.audio_check_var.get()
        })
        
        selected_langs = [code for code, var in self.lang_vars.items() if var.get()]
        self.config_manager.set("default_sub_langs", selected_langs)
        
        # 保存环境路径
        if self.yt_env_frame.get("path_var"):
            self.config_manager.set("yt_dlp_path", self.yt_env_frame["path_var"].get())
        if self.ff_env_frame.get("path_var"):
            self.config_manager.set("ffmpeg_path", self.ff_env_frame["path_var"].get())
        
        self.config_manager.save()
        messagebox.showinfo("成功", "设置已保存", parent=self)
        self.destroy()


class ProgressWindow(tk.Toplevel):
    """进度窗口"""
    
    def __init__(self, parent, download_items, config_manager):
        super().__init__(parent)
        self.title("下载进度")
        self.geometry("800x600")
        self.download_items = download_items
        self.config_manager = config_manager
        self.parent = parent
        self.running = True
        self.auto_scroll = True
        self.results = []
        self.current_process = None
        self.skip_current = False
        self.download_log_file = get_download_log_path(config_manager)
        self.download_log_lock = threading.Lock()

        self.transient(parent)
        self.create_widgets()
        self.start_download()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_widgets(self):
        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warning", foreground="orange")
        
        # 进度显示在日志下方
        self.progress_label = ttk.Label(self, text="准备下载...", font=("", 9))
        self.progress_label.pack(fill=tk.X, padx=10, pady=5)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.abort_btn = ttk.Button(btn_frame, text="中止下载", command=self.abort_download)
        self.abort_btn.pack(side=tk.LEFT, padx=5)

        self.skip_btn = ttk.Button(btn_frame, text="终止当前下载项", command=self.skip_current_item)
        self.skip_btn.pack(side=tk.LEFT, padx=5)

        self.retry_btn = ttk.Button(btn_frame, text="重试失败项", command=self.retry_failed, state=tk.DISABLED)
        self.retry_btn.pack(side=tk.LEFT, padx=5)

        self.history_btn = ttk.Button(btn_frame, text="历史记录", command=self.show_history)
        self.history_btn.pack(side=tk.LEFT, padx=5)

        self.auto_scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll_check = ttk.Checkbutton(btn_frame, text="自动滚动", variable=self.auto_scroll_var, command=self.toggle_auto_scroll)
        self.auto_scroll_check.pack(side=tk.RIGHT, padx=5)

        self.close_btn = ttk.Button(btn_frame, text="关闭", command=self.destroy, state=tk.DISABLED)
        self.close_btn.pack(side=tk.RIGHT, padx=5)
    
    def log(self, message, tag=None):
        # 自动将非主线程的日志调用调度到主线程，避免 Tkinter 线程不安全导致段错误
        if threading.current_thread() is not threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda msg=message, t=tag: self.log(msg, t))
            except tk.TclError:
                pass
            return

        try:
            if not self.log_text.winfo_exists():
                return
        except tk.TclError:
            return

        try:
            self.log_text.config(state=tk.NORMAL)
            if tag:
                self.log_text.insert(tk.END, message + "\n", tag)
            else:
                self.log_text.insert(tk.END, message + "\n")

            # 限制日志行数，防止长时间下载后内存与 UI 卡顿
            max_log_lines = 5000
            total_lines = int(self.log_text.index('end-1c').split('.')[0])
            if total_lines > max_log_lines:
                delete_to = f"{total_lines - max_log_lines + 1}.0"
                self.log_text.delete("1.0", delete_to)

            if self.auto_scroll:
                self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except tk.TclError:
            pass
    
    def write_download_log(self, message):
        """将原始输出写入下载日志文件（如启用）"""
        if not self.download_log_file:
            return
        try:
            with self.download_log_lock:
                with open(self.download_log_file, 'a', encoding='utf-8') as f:
                    f.write(message + "\n")
        except Exception:
            pass
    
    def toggle_auto_scroll(self):
        self.auto_scroll = self.auto_scroll_var.get()
    
    def abort_download(self):
        self.running = False
        self._cleanup_process(self.current_process, timeout=3)
        self.abort_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.log("用户中止下载...", "error")
    
    def skip_current_item(self):
        """终止当前正在下载的项"""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.skip_current = True
                self.log("用户终止当前下载项...", "error")
            except Exception as e:
                self.log(f"终止当前项失败: {e}", "error")
        else:
            self.log("当前没有正在下载的项", "warning")
    
    def _cleanup_process(self, proc, timeout=5):
        """安全清理子进程，防止僵尸进程与文件描述符泄漏"""
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=timeout)
        except Exception:
            pass
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass
            try:
                proc.stdin.close()
            except Exception:
                pass
    
    def start_download(self):
        thread = threading.Thread(target=self.download_thread, daemon=True)
        thread.start()
    
    def download_thread(self):
        try:
            total = len(self.download_items)
            success = 0
            failed = 0

            for i, item in enumerate(self.download_items, 1):
                if not self.running:
                    break

                self.after(0, lambda msg=f"[{i}/{total}] 开始下载: {item['url']}": self._safe_set_progress(msg))
                self.after(0, lambda msg=f"\n{'='*60}\n[{i}/{total}] {item['url']}\n{'='*60}": self.log(msg))

                result = self.download_item(item)
                self.results.append(result)
                self.skip_current = False
                self.current_process = None

                if result.get('live'):
                    # 直播跳过，计入失败但显示特殊信息
                    failed += 1
                    self.after(0, lambda msg=f"✗ 检测到直播，跳过下载: {result.get('title', '未知标题')}": self.log(msg, "error"))
                elif result['success']:
                    success += 1
                    self.after(0, lambda msg=f"✓ 下载成功: {result.get('title', '未知标题')}": self.log(msg, "success"))
                else:
                    failed += 1
                    self.after(0, lambda msg=f"✗ 下载失败: {result.get('error', '未知错误')}": self.log(msg, "error"))

            # 显示结果列表（必须在主线程执行，避免 worker 线程直接操作 UI 导致段错误）
            self.after(0, lambda s=success, f=failed: self.show_results(s, f))

            # 置顶完成提示
            self.after(0, lambda s=success, f=failed: self.show_completion_dialog(s, f))
        except Exception as e:
            import traceback
            err_msg = f"下载线程发生未处理异常: {e}\n{traceback.format_exc()}"
            print(err_msg)
            error_str = str(e)
            self.after(0, lambda msg=err_msg: self.log(msg, "error"))
            self.after(0, lambda msg=error_str: messagebox.showerror("错误", f"下载过程中发生错误:\n{msg}\n\n请查看日志或终端输出获取详细信息。", parent=self))

    def _safe_set_progress(self, message):
        """安全更新进度标签，窗口已关闭时直接忽略"""
        try:
            if self.progress_label.winfo_exists():
                self.progress_label.config(text=message)
        except tk.TclError:
            pass
    
    def show_completion_dialog(self, success, failed):
        try:
            if not self.winfo_exists():
                return
            bring_to_front(self)
            messagebox.showinfo("完成", f"下载完成！\n成功: {success}\n失败: {failed}", parent=self)
        except tk.TclError:
            pass

    def show_results(self, success, failed):
        """显示下载结果列表"""
        try:
            if not self.winfo_exists():
                return
            self.log(f"\n{'='*60}")
            self.log(f"下载完成！成功: {success} / 失败: {failed}")
            self.log(f"{'='*60}\n")
            self.log("下载列表:")

            for idx, result in enumerate(self.results, 1):
                if result.get('live'):
                    # 直播跳过项用红色高亮
                    msg = f"  {idx}. [检测到直播，跳过下载] {result.get('title', '未知标题')} | {result['url']}"
                    self.log(msg, "error")
                else:
                    status = "✓" if result['success'] else "✗ [失败]"
                    title = result.get('title', '未知标题')
                    url = result['url']
                    has_sub = result.get('has_sub', False)
                    sub_tag = " [字幕]" if has_sub else ""
                    self.log(f"  {idx}. {status}{sub_tag} {title} | {url}", "success" if result['success'] else "error")

            if self.progress_label.winfo_exists():
                self.progress_label.config(text=f"下载完成！成功: {success} / 失败: {failed}")

            # 保存历史记录
            self.save_history()

            # 更新按钮状态
            remaining_failed = len([r for r in self.results if not r['success'] and not r.get('skipped') and not r.get('live')])
            if remaining_failed > 0:
                self.retry_btn.config(state=tk.NORMAL)
            else:
                self.retry_btn.config(state=tk.DISABLED)
            self.close_btn.config(state=tk.NORMAL)
            # 下载完成后禁用中止相关按钮，避免影响重试等后续操作
            self.abort_btn.config(state=tk.DISABLED)
            self.skip_btn.config(state=tk.DISABLED)
        except tk.TclError:
            pass
    
    def check_url_type(self, url):
        """检测 URL 类型，返回 'video'、'live'、'list' 或 'unknown'"""
        yt_dlp = self.config_manager.get("yt_dlp_path", "yt-dlp") or "yt-dlp"
        lowered = url.lower()
        
        # 明确的播放列表/频道页面直接判定为列表
        if any(k in lowered for k in ["playlist?", "/channel/", "/c/", "/user/", "/@"]):
            return "list", ""
        
        # watch 页面但包含播放列表参数（YouTube Mix / 播放列表）也判定为列表
        if "list=" in lowered or "start_radio" in lowered:
            return "list", ""
        
        try:
            # 常规检测（单视频）
            cmd = [yt_dlp, "--dump-json", "--no-warnings", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return "unknown", ""
            
            lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if not lines:
                return "unknown", ""
            
            data = json.loads(lines[0])
            
            # 检测直播
            if data.get("is_live") or data.get("live_status") == "is_live":
                return "live", data.get("title", "")
            
            # 检测播放列表/频道
            if data.get("_type") == "playlist" or data.get("playlist_count", 0) > 1 or "entries" in data:
                return "list", data.get("title", "")
            
            return "video", data.get("title", "")
        except Exception:
            return "unknown", ""
    
    def download_item(self, item, force=False):
        url = item['url']
        checks = item['checks']
        sub_langs = item.get('sub_langs', ['en', 'zh-Hans'])
        
        # 检测 URL 类型
        self.after(0, lambda msg=f"检测 URL 类型: {url}": self.log(msg))
        url_type, title = self.check_url_type(url)
        self.after(0, lambda msg=f"URL 类型检测结果: {url_type}": self.log(msg))
        
        # 检测到直播时跳过
        if url_type == "live" and self.config_manager.get("skip_live", True):
            return {"success": False, "url": url, "title": title or "未知标题", "error": "检测到直播，已跳过", "has_sub": False, "skipped": True, "live": True}
        
        # 如果是不下载视频列表模式且 URL 是列表，则只下载当前视频
        no_playlist = (url_type == "list" and self.config_manager.get("skip_video_lists", True))
        
        yt_dlp = self.config_manager.get("yt_dlp_path", "yt-dlp")
        if not yt_dlp:
            yt_dlp = "yt-dlp"
        
        cmd = [yt_dlp]
        
        cookie_type = self.config_manager.get("cookie_type", "none")
        if cookie_type == "file":
            cookie_file = self.config_manager.get("cookie_file", "")
            if cookie_file and os.path.exists(cookie_file):
                cmd.extend(["--cookies", cookie_file])
        elif cookie_type == "firefox":
            cmd.extend(["--cookies-from-browser", "firefox"])
        elif cookie_type == "chrome":
            cmd.extend(["--cookies-from-browser", "chrome"])
        
        cmd.extend(["--retries", "infinite", "--fragment-retries", "infinite", "--sleep-interval", "3", "--progress"])
        
        if force:
            # 强制覆盖已有文件，确保重试真正重新下载
            cmd.extend(["--force-overwrites", "--no-continue"])
        
        if self.config_manager.get("legacy_server_connect", False):
            cmd.extend(["--legacy-server-connect"])
        
        if self.config_manager.get("no_check_certificates", False):
            cmd.extend(["--no-check-certificates"])
        
        if no_playlist:
            # 只下载当前视频，不下载播放列表
            cmd.extend(["--no-playlist"])
            self.after(0, lambda msg="检测到视频列表参数，仅下载当前视频": self.log(msg))
        
        save_dir = self.config_manager.get("save_dir", os.getcwd())
        # 限制标题长度，避免日文/中文等长标题导致文件名超出文件系统限制
        output_template = os.path.join(save_dir, "%(title).80s.%(ext)s")
        cmd.extend(["-o", output_template])
        
        if checks.get("video"):
            cmd.extend(["--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
            cmd.extend(["--merge-output-format", "mp4"])
            if self.config_manager.get("add_metadata", False):
                cmd.extend(["--add-metadata"])
        
        if checks.get("cover"):
            cmd.extend(["--write-thumbnail", "--convert-thumbnails", "jpg"])
        
        has_subs = checks.get("srt") or checks.get("vtt")
        if has_subs:
            # Bilibili 等站点使用不同的字幕语言代码与格式，需要转换
            is_bilibili = any(host in url.lower() for host in ["bilibili.com", "b23.tv"])
            actual_sub_langs = map_sub_langs_for_url(url, sub_langs)
            if not actual_sub_langs:
                actual_sub_langs = ["en", "zh-Hans"]
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", ",".join(actual_sub_langs)])
            if is_bilibili:
                # Bilibili 原生字幕多为 JSON，下载后转换为目标格式
                if checks.get("srt"):
                    cmd.extend(["--sub-format", "json/best", "--convert-subs", "srt"])
                elif checks.get("vtt"):
                    cmd.extend(["--sub-format", "json/best", "--convert-subs", "vtt"])
            else:
                if checks.get("srt") and checks.get("vtt"):
                    cmd.extend(["--sub-format", "srt/vtt/best"])
                elif checks.get("srt"):
                    cmd.extend(["--sub-format", "srt/vtt/json/best", "--convert-subs", "srt"])
                elif checks.get("vtt"):
                    cmd.extend(["--sub-format", "srt/vtt/json/best", "--convert-subs", "vtt"])
        
        if checks.get("audio"):
            cmd.extend(["--extract-audio", "--audio-format", "mp3"])
        
        if not checks.get("video") and not checks.get("audio"):
            cmd.extend(["--skip-download"])
        
        cmd.append(url)
        
        # 记录执行的命令
        self.after(0, lambda msg=f"执行命令: {' '.join(cmd)}": self.log(msg))
        self.write_download_log(f"\n{'='*60}\nURL: {url}\n命令: {' '.join(cmd)}\n{'='*60}\n")
        
        # 记录下载前目录中的字幕文件，用于判断本次是否实际下载了字幕
        sub_only = has_subs and not checks.get("video") and not checks.get("audio") and not checks.get("cover")
        sub_files_before = set()
        if sub_only:
            try:
                sub_files_before = set(Path(save_dir).glob("*.srt")) | set(Path(save_dir).glob("*.vtt"))
            except:
                pass
        
        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            title = None
            sub_downloaded = False
            terminated = False
            for line in self.current_process.stdout:
                if not self.running or self.skip_current:
                    terminated = True
                    self._cleanup_process(self.current_process, timeout=3)
                    break
                line = line.rstrip()
                self.write_download_log(line)
                if not line:
                    continue
                
                # 进度行更新到底部标签，不写入日志
                if "[download]" in line and ("%" in line or "at " in line):
                    progress = line.replace("[download]", "").strip()
                    self.after(0, lambda msg=progress: self.progress_label.config(text=msg))
                elif "[download] Destination:" in line:
                    filename = line.split("[download] Destination:")[-1].strip()
                    title = os.path.splitext(os.path.basename(filename))[0]
                    if filename.endswith(('.srt', '.vtt')):
                        sub_downloaded = True
                    self.after(0, lambda msg=line: self.log(msg))
                elif "Already downloaded" in line:
                    match = re.search(r"Already downloaded.*?['\"](.+?)['\"]", line)
                    if match:
                        filename = match.group(1)
                        title = os.path.splitext(os.path.basename(filename))[0]
                        if filename.endswith(('.srt', '.vtt')):
                            sub_downloaded = True
                    self.after(0, lambda msg=line: self.log(msg))
                elif "WARNING" in line:
                    self.after(0, lambda msg=line: self.log(msg, "warning"))
                else:
                    self.after(0, lambda msg=line: self.log(msg))
            
            if not terminated:
                self._cleanup_process(self.current_process, timeout=10)
            
            if self.skip_current:
                return {"success": False, "url": url, "title": title or "未知标题", "error": "用户终止当前下载项", "has_sub": has_subs}
            
            if not self.running:
                return {"success": False, "url": url, "title": title or "未知标题", "error": "用户中止下载", "has_sub": has_subs}
            
            if self.current_process.returncode == 0:
                if not title:
                    title = self.find_latest_title(save_dir, sub_only=sub_only)
                
                # 如果只下载字幕，检查是否有新的字幕文件生成
                if sub_only:
                    found_sub = self.find_new_subtitle_files(save_dir, sub_files_before, title)
                    if not found_sub:
                        return {"success": False, "url": url, "title": title or "未知标题", "error": "未找到可下载的字幕", "has_sub": has_subs}
                
                return {"success": True, "url": url, "title": title or "未知标题", "has_sub": has_subs}
            else:
                return {"success": False, "url": url, "error": f"退出码: {self.current_process.returncode}", "has_sub": has_subs}
        except Exception as e:
            return {"success": False, "url": url, "error": str(e), "has_sub": has_subs}
    
    def find_latest_title(self, save_dir, sub_only=False):
        """查找最近修改的文件标题"""
        try:
            files = []
            if sub_only:
                exts = ['*.srt', '*.vtt']
            else:
                exts = ['*.mp4', '*.mkv', '*.webm', '*.mp3', '*.m4a', '*.jpg', '*.png', '*.srt', '*.vtt']
            for ext in exts:
                files.extend(Path(save_dir).glob(ext))
            if files:
                latest = max(files, key=os.path.getmtime)
                return latest.stem
        except:
            pass
        return None
    
    def find_new_subtitle_files(self, save_dir, sub_files_before, title):
        """检查本次下载是否有新的字幕文件生成"""
        try:
            current_files = set(Path(save_dir).glob("*.srt")) | set(Path(save_dir).glob("*.vtt"))
            new_files = current_files - sub_files_before
            if new_files:
                return True
            # 如果没有新文件，但文件已存在且标题匹配，也算成功
            if title and title != "未知标题":
                for ext in ['*.srt', '*.vtt']:
                    for f in current_files:
                        if title in f.name:
                            return True
        except:
            pass
        return False
    
    def save_history(self):
        history_count = self.config_manager.get("history_count", 1)
        if history_count == 0:
            return
        
        history_dir = self.config_manager.get("history_dir", str(HISTORY_DIR))
        Path(history_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = Path(history_dir) / f"history_{timestamp}.txt"
        
        with open(history_file, 'w', encoding='utf-8') as f:
            f.write(f"下载历史 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write("下载列表:\n")
            for idx, result in enumerate(self.results, 1):
                status = "✓" if result['success'] else "✗ [失败]"
                has_sub = result.get('has_sub', False)
                sub_tag = " [字幕]" if has_sub else ""
                f.write(f"  {idx}. {status}{sub_tag} {result.get('title', '未知标题')} | {result['url']}\n")
        
        # 清理旧历史
        history_files = sorted(Path(history_dir).glob("history_*.txt"))
        while len(history_files) > history_count:
            history_files[0].unlink()
            history_files = history_files[1:]
    
    def retry_failed(self):
        # 仅重试真正失败的项，跳过直播/用户跳过/用户中止的项
        failed_items = [r for r in self.results if not r['success'] and not r.get('skipped') and not r.get('live')]
        if not failed_items:
            self.log("没有可重试的失败项（直播或已跳过的项不会重试）", "warning")
            return
        
        self.retry_btn.config(state=tk.DISABLED)
        # 重试期间恢复中止/跳过按钮，让用户可以中断重试
        self.abort_btn.config(state=tk.NORMAL)
        self.skip_btn.config(state=tk.NORMAL)
        self.log("\n开始重试失败项...")
        
        thread = threading.Thread(target=self.retry_thread, args=(failed_items,), daemon=True)
        thread.start()
    
    def retry_thread(self, failed_items):
        try:
            success = 0
            failed = 0
            
            for item in failed_items:
                if not self.running:
                    break
                
                self.after(0, lambda msg=f"\n重试: {item['url']}": self.log(msg))
                
                original = next((i for i in self.download_items if i['url'] == item['url']), None)
                if original:
                    result = self.download_item(original, force=True)
                    for r in self.results:
                        if r['url'] == item['url']:
                            r.update(result)
                            break
                    
                    if result['success']:
                        success += 1
                        self.after(0, lambda msg=f"✓ 重试成功: {result.get('title', '未知标题')}": self.log(msg, "success"))
                    else:
                        failed += 1
                        self.after(0, lambda msg=f"✗ 重试失败: {result.get('error', '未知错误')}": self.log(msg, "error"))
            
            # 刷新结果列表显示
            total_success = len([r for r in self.results if r['success']])
            total_failed = len([r for r in self.results if not r['success']])
            self.after(0, lambda s=total_success, f=total_failed: self.show_results(s, f))
            self.after(0, lambda: messagebox.showinfo("完成", f"重试完成！\n成功: {success}\n失败: {failed}", parent=self))
        except Exception as e:
            import traceback
            err_msg = f"重试线程发生未处理异常: {e}\n{traceback.format_exc()}"
            print(err_msg)
            self.after(0, lambda msg=err_msg: self.log(msg, "error"))
            self.after(0, lambda: messagebox.showerror("错误", f"重试过程中发生错误:\n{e}\n\n请查看日志或终端输出获取详细信息。", parent=self))
        finally:
            # 重试结束（无论成功/失败/异常）后再次禁用中止相关按钮
            self.after(0, lambda: self.abort_btn.config(state=tk.DISABLED))
            self.after(0, lambda: self.skip_btn.config(state=tk.DISABLED))
    
    def on_close(self):
        self.running = False
        try:
            if self.winfo_exists():
                self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
    
    def show_history(self):
        history_window = tk.Toplevel(self)
        history_window.title("历史下载记录")
        history_window.geometry("800x600")
        bring_to_front(history_window)
        
        history_dir = self.config_manager.get("history_dir", str(HISTORY_DIR))
        history_path = Path(history_dir)
        
        if not history_path.exists():
            messagebox.showinfo("提示", "暂无历史记录", parent=self)
            return
        
        history_files = sorted(history_path.glob("history_*.txt"), reverse=True)
        
        if not history_files:
            messagebox.showinfo("提示", "暂无历史记录", parent=self)
            return
        
        text_widget = scrolledtext.ScrolledText(history_window, wrap=tk.WORD, font=("Courier", 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        for history_file in history_files:
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    text_widget.insert(tk.END, content + "\n\n" + "="*60 + "\n\n")
            except Exception as e:
                text_widget.insert(tk.END, f"读取失败: {history_file.name}\n错误: {e}\n\n")
        
        text_widget.config(state=tk.DISABLED)


class SubLangDialog(tk.Toplevel):
    """字幕语言选择对话框"""
    
    def __init__(self, parent, selected_langs):
        super().__init__(parent)
        self.title("选择字幕语言")
        self.geometry("480x320")
        self.resizable(False, False)
        self.selected_langs = selected_langs.copy() if selected_langs else []
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        self.lang_vars = {}
        self.create_widgets()
        bring_to_front(self)
    
    def create_widgets(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="选择要下载的字幕语言:").pack(anchor=tk.W, pady=5)
        
        lang_frame = ttk.Frame(frame)
        lang_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        langs = [("英语", "en"), ("简体中文", "zh-Hans"), ("日语", "ja"), 
                 ("繁体中文", "zh-Hant"), ("韩语", "ko"), ("西班牙语", "es"),
                 ("法语", "fr"), ("德语", "de"), ("俄语", "ru"), ("葡萄牙语", "pt")]
        
        for i, (name, code) in enumerate(langs):
            var = tk.BooleanVar(value=code in self.selected_langs)
            self.lang_vars[code] = (var, name)
            ttk.Checkbutton(lang_frame, text=name, variable=var).grid(
                row=i//3, column=i%3, sticky=tk.W, padx=10, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="确定", command=self.ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=5)
    
    def ok(self):
        self.result = [code for code, (var, name) in self.lang_vars.items() if var.get()]
        self.destroy()
    
    def cancel(self):
        self.result = None
        self.destroy()


class HeaderRow:
    """表头行，包含每列的全选复选框"""
    
    def __init__(self, parent, row, default_checks):
        self.link_items = []
        self.parent = parent
        
        # 每列的全选复选框
        self.video_var = tk.BooleanVar(value=default_checks.get("video", True))
        self.cover_var = tk.BooleanVar(value=default_checks.get("cover", True))
        self.srt_var = tk.BooleanVar(value=default_checks.get("srt", False))
        self.vtt_var = tk.BooleanVar(value=default_checks.get("vtt", False))
        self.audio_var = tk.BooleanVar(value=default_checks.get("audio", False))
        
        ttk.Checkbutton(parent, text="视频", variable=self.video_var, command=self.toggle_video).grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(parent, text="封面", variable=self.cover_var, command=self.toggle_cover).grid(row=row, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(parent, text="SRT", variable=self.srt_var, command=self.toggle_srt).grid(row=row, column=3, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(parent, text="VTT", variable=self.vtt_var, command=self.toggle_vtt).grid(row=row, column=4, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(parent, text="音频", variable=self.audio_var, command=self.toggle_audio).grid(row=row, column=5, sticky=tk.W, padx=5, pady=2)
    
    def add_link_item(self, item):
        self.link_items.append(item)
    
    def toggle_video(self):
        val = self.video_var.get()
        for item in self.link_items:
            item.video_var.set(val)
    
    def toggle_cover(self):
        val = self.cover_var.get()
        for item in self.link_items:
            item.cover_var.set(val)
    
    def toggle_srt(self):
        val = self.srt_var.get()
        for item in self.link_items:
            item.srt_var.set(val)
    
    def toggle_vtt(self):
        val = self.vtt_var.get()
        for item in self.link_items:
            item.vtt_var.set(val)
    
    def toggle_audio(self):
        val = self.audio_var.get()
        for item in self.link_items:
            item.audio_var.set(val)


class LinkItem:
    """链接列表项"""
    
    def __init__(self, parent, row, url, default_checks, default_sub_langs, dialog_parent=None):
        self.url = url
        self.parent = parent
        self.dialog_parent = dialog_parent or parent
        
        # URL 标签（过长时截断，避免撑开滚动区域）
        display_url = url if len(url) <= 80 else url[:77] + "..."
        ttk.Label(parent, text=display_url, anchor=tk.W).grid(row=row, column=0, sticky=tk.W+tk.E, padx=5, pady=2)
        
        self.video_var = tk.BooleanVar(value=default_checks.get("video", True))
        self.cover_var = tk.BooleanVar(value=default_checks.get("cover", True))
        self.srt_var = tk.BooleanVar(value=default_checks.get("srt", False))
        self.vtt_var = tk.BooleanVar(value=default_checks.get("vtt", False))
        self.audio_var = tk.BooleanVar(value=default_checks.get("audio", False))
        
        self.srt_langs = default_sub_langs.copy() if default_sub_langs else []
        self.vtt_langs = default_sub_langs.copy() if default_sub_langs else []
        
        # 视频 / 封面 / 音频列：复选框 + 文字标签
        self._add_labeled_checkbox(parent, row, 1, "视频", self.video_var)
        self._add_labeled_checkbox(parent, row, 2, "封面", self.cover_var)
        
        # SRT 列：复选框 + 语言选择按钮
        srt_frame = ttk.Frame(parent)
        srt_frame.grid(row=row, column=3, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(srt_frame, variable=self.srt_var).pack(side=tk.LEFT)
        ttk.Button(srt_frame, text="SRT", command=self.show_srt_langs).pack(side=tk.LEFT)
        
        # VTT 列：复选框 + 语言选择按钮
        vtt_frame = ttk.Frame(parent)
        vtt_frame.grid(row=row, column=4, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(vtt_frame, variable=self.vtt_var).pack(side=tk.LEFT)
        ttk.Button(vtt_frame, text="VTT", command=self.show_vtt_langs).pack(side=tk.LEFT)
        
        self._add_labeled_checkbox(parent, row, 5, "音频", self.audio_var)
    
    def _add_labeled_checkbox(self, parent, row, column, text, variable):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky=tk.W, padx=5, pady=2)
        ttk.Checkbutton(frame, variable=variable).pack(side=tk.LEFT)
        ttk.Label(frame, text=text).pack(side=tk.LEFT)
    
    def show_srt_langs(self):
        dialog = SubLangDialog(self.dialog_parent, self.srt_langs)
        self.dialog_parent.wait_window(dialog)
        if dialog.result is not None:
            self.srt_langs = dialog.result
    
    def show_vtt_langs(self):
        dialog = SubLangDialog(self.dialog_parent, self.vtt_langs)
        self.dialog_parent.wait_window(dialog)
        if dialog.result is not None:
            self.vtt_langs = dialog.result
    
    def get_checks(self):
        return {
            "video": self.video_var.get(),
            "cover": self.cover_var.get(),
            "srt": self.srt_var.get(),
            "vtt": self.vtt_var.get(),
            "audio": self.audio_var.get()
        }
    
    def get_sub_langs(self):
        # 只合并当前已勾选的字幕格式的语言列表，避免未勾选格式仍带入默认语言
        combined = []
        seen = set()
        if self.srt_var.get():
            for lang in self.srt_langs:
                if lang not in seen:
                    seen.add(lang)
                    combined.append(lang)
        if self.vtt_var.get():
            for lang in self.vtt_langs:
                if lang not in seen:
                    seen.add(lang)
                    combined.append(lang)
        return combined
    
    def get_srt_langs(self):
        return self.srt_langs
    
    def get_vtt_langs(self):
        return self.vtt_langs
    
    def set_all(self, value):
        self.video_var.set(value)
        self.cover_var.set(value)
        self.srt_var.set(value)
        self.vtt_var.set(value)
        self.audio_var.set(value)


class MainApplication(tk.Tk):
    """主应用"""
    
    def __init__(self):
        super().__init__()
        self.title("YouTube 万能下载器")
        self.geometry("1050x700")

        self.config_manager = ConfigManager()
        self.link_items = []
        self._pending_list_width_update = None

        # 设置全局异常钩子，记录主线程未处理异常
        self._setup_global_exception_hook()
        
        if not CONFIG_FILE.exists():
            self.show_first_run_wizard()
        
        self.create_widgets()
    
    def _setup_global_exception_hook(self):
        """设置全局异常钩子，用于捕获并记录未处理异常"""
        config_manager = self.config_manager
        original_hook = sys.excepthook
        
        def exception_hook(exc_type, exc_value, exc_traceback):
            if exc_type in (KeyboardInterrupt, SystemExit):
                return original_hook(exc_type, exc_value, exc_traceback)
            import traceback
            err_msg = f"未处理异常: {exc_type.__name__}: {exc_value}\n{''.join(traceback.format_tb(exc_traceback))}"
            print(err_msg, file=sys.stderr)
            original_hook(exc_type, exc_value, exc_traceback)
        
        sys.excepthook = exception_hook
    
    def report_callback_exception(self, exc_type, exc_value, exc_traceback):
        """捕获 tkinter 回调中的未处理异常并记录"""
        if exc_type in (KeyboardInterrupt, SystemExit):
            super().report_callback_exception(exc_type, exc_value, exc_traceback)
            return
        import traceback
        err_msg = f"tkinter 回调异常: {exc_type.__name__}: {exc_value}\n{''.join(traceback.format_tb(exc_traceback))}"
        # 同时输出到 stderr，便于调试
        print(err_msg, file=sys.stderr)
        # 调用默认处理
        super().report_callback_exception(exc_type, exc_value, exc_traceback)
    
    def show_first_run_wizard(self):
        wizard = FirstRunWizard(self, self.config_manager)
        self.wait_window(wizard)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部按钮栏
        top_btn_frame = ttk.Frame(main_frame)
        top_btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(top_btn_frame, text="设置", command=self.show_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn_frame, text="历史记录", command=self.show_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn_frame, text="许可", command=self.show_license).pack(side=tk.RIGHT, padx=5)
        
        # 链接输入区域
        input_frame = ttk.LabelFrame(main_frame, text="链接输入 (每行一个链接)", padding=10)
        input_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.link_input = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, height=10)
        self.link_input.pack(fill=tk.BOTH, expand=True)
        # 小数字键盘 Enter 也换行
        self.link_input.bind("<KP_Enter>", lambda e: self.link_input.event_generate("<Return>"))
        
        # 操作按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="解析链接", command=self.parse_links).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="全选", command=self.select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消全选", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="开始下载", command=self.start_download).pack(side=tk.RIGHT, padx=5)
        
        # 链接列表区域
        list_frame = ttk.LabelFrame(main_frame, text="下载列表", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        # 下载列表使用 grid 布局，URL 列可扩展，选择列固定最小宽度
        self.scrollable_frame.columnconfigure(0, weight=1, minsize=200)
        self.scrollable_frame.columnconfigure(1, minsize=85)
        self.scrollable_frame.columnconfigure(2, minsize=85)
        self.scrollable_frame.columnconfigure(3, minsize=130)
        self.scrollable_frame.columnconfigure(4, minsize=130)
        self.scrollable_frame.columnconfigure(5, minsize=85)
        
        inner_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)

        self._pending_list_width_update = None

        def _update_scrollregion(event=None):
            try:
                if canvas.winfo_exists():
                    canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def _do_update_inner_width():
            self._pending_list_width_update = None
            try:
                if not canvas.winfo_exists() or not self.scrollable_frame.winfo_exists():
                    return
                canvas_width = max(1, canvas.winfo_width())
                canvas.itemconfig(inner_id, width=canvas_width)
            except tk.TclError:
                pass

        def _update_inner_width(event=None):
            if self._pending_list_width_update is not None:
                try:
                    list_frame.after_cancel(self._pending_list_width_update)
                except tk.TclError:
                    pass
            self._pending_list_width_update = list_frame.after(50, _do_update_inner_width)

        self.scrollable_frame.bind("<Configure>", _update_scrollregion)
        list_frame.bind("<Configure>", lambda e: _update_inner_width())
        canvas.bind("<Configure>", lambda e: _update_inner_width())
        
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定鼠标滚轮到 canvas 区域（Linux 使用 Button-4/5，Windows/Mac 使用 MouseWheel）
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def _on_linux_scroll_up(event):
            canvas.yview_scroll(-3, "units")
        
        def _on_linux_scroll_down(event):
            canvas.yview_scroll(3, "units")
        
        # Windows/Mac
        canvas.bind("<MouseWheel>", _on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        
        # Linux
        canvas.bind("<Button-4>", _on_linux_scroll_up)
        canvas.bind("<Button-5>", _on_linux_scroll_down)
        self.scrollable_frame.bind("<Button-4>", _on_linux_scroll_up)
        self.scrollable_frame.bind("<Button-5>", _on_linux_scroll_down)
    
    def _is_valid_url(self, url):
        """简单校验字符串是否为可接受的 URL"""
        if not url or len(url) < 4:
            return False
        return url.startswith(("http://", "https://", "ftp://", "ftps://"))
    
    def parse_links(self):
        # 取消可能正在进行的宽度更新，避免在清空/重建控件时触发异常
        if self._pending_list_width_update is not None:
            try:
                self.after_cancel(self._pending_list_width_update)
            except tk.TclError:
                pass
            self._pending_list_width_update = None

        try:
            for widget in list(self.scrollable_frame.winfo_children()):
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
            self.link_items.clear()

            text = self.link_input.get("1.0", tk.END)
            raw_lines = [line.strip() for line in text.split('\n') if line.strip()]

            default_checks = self.config_manager.get("default_checks", {})
            default_sub_langs = self.config_manager.get("default_sub_langs", ["en", "zh-Hans"])
            link_subtitle_keyword = self.config_manager.get("link_subtitle_keyword", False)
            link_subtitle_format = self.config_manager.get("link_subtitle_format", "srt")

            valid_urls = []
            invalid_lines = []
            for line in raw_lines:
                # 解析行尾字幕关键字
                url = line
                if link_subtitle_keyword:
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1] == "字幕":
                        url = " ".join(parts[:-1])

                if self._is_valid_url(url):
                    valid_urls.append((url, line))
                else:
                    invalid_lines.append(line)

            if invalid_lines:
                print(f"跳过的无效链接: {invalid_lines}")

            if not valid_urls:
                messagebox.showwarning("警告", "没有找到有效的链接", parent=self)
                return

            # 限制单次解析数量，防止生成过多控件导致界面卡顿或崩溃
            MAX_LINKS = 1000
            if len(valid_urls) > MAX_LINKS:
                skipped = len(valid_urls) - MAX_LINKS
                messagebox.showwarning(
                    "警告",
                    f"链接数量过多（共 {len(valid_urls)} 条），仅显示前 {MAX_LINKS} 条，\n"
                    f"剩余 {skipped} 条已被忽略。",
                    parent=self
                )
                valid_urls = valid_urls[:MAX_LINKS]

            # 添加表头行（列全选复选框）
            header = HeaderRow(self.scrollable_frame, 0, default_checks)

            row = 1
            for url, original_line in valid_urls:
                has_sub_keyword = link_subtitle_keyword and original_line.endswith(" 字幕")

                item = LinkItem(self.scrollable_frame, row, url, default_checks, default_sub_langs, dialog_parent=self)
                if has_sub_keyword:
                    if link_subtitle_format == "srt":
                        item.srt_var.set(True)
                    else:
                        item.vtt_var.set(True)
                self.link_items.append(item)
                header.add_link_item(item)
                row += 1
        except Exception as e:
            import traceback
            err_msg = f"生成下载列表时发生异常: {e}\n{traceback.format_exc()}"
            print(err_msg)
            messagebox.showerror("错误", f"生成下载列表时发生错误:\n{e}\n\n请查看终端输出获取详细信息。", parent=self)
    
    def select_all(self):
        for item in self.link_items:
            item.set_all(True)
    
    def deselect_all(self):
        for item in self.link_items:
            item.set_all(False)
    
    def clear_list(self):
        if self._pending_list_width_update is not None:
            try:
                self.after_cancel(self._pending_list_width_update)
            except tk.TclError:
                pass
            self._pending_list_width_update = None
        for widget in list(self.scrollable_frame.winfo_children()):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self.link_items.clear()
        self.link_input.delete("1.0", tk.END)
    
    def start_download(self):
        try:
            if not self.link_items:
                messagebox.showwarning("警告", "请先解析链接", parent=self)
                return
            
            if self.config_manager.get("ask_save_dir", True):
                save_dir = filedialog.askdirectory(title="选择保存目录", parent=self)
                if not save_dir:
                    return
                self.config_manager.set("save_dir", save_dir)
            
            download_items = []
            for item in self.link_items:
                checks = item.get_checks()
                if any(checks.values()):
                    download_items.append({
                        "url": item.url,
                        "checks": checks,
                        "sub_langs": item.get_sub_langs()
                    })
            
            if not download_items:
                messagebox.showwarning("警告", "没有选择任何下载项", parent=self)
                return
            
            progress = ProgressWindow(self, download_items, self.config_manager)
            progress.grab_set()
        except Exception as e:
            import traceback
            err_msg = f"开始下载时发生异常: {e}\n{traceback.format_exc()}"
            print(err_msg)
            messagebox.showerror("错误", f"开始下载时发生错误:\n{e}\n\n请查看终端输出获取详细信息。", parent=self)
    
    def show_settings(self):
        settings = SettingsWindow(self, self.config_manager)
        self.wait_window(settings)
    
    def show_license(self):
        license_window = tk.Toplevel(self)
        license_window.title("许可协议")
        license_window.geometry("600x400")
        bring_to_front(license_window)
        
        text_widget = scrolledtext.ScrolledText(license_window, wrap=tk.WORD, font=("Courier", 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        license_text = """Copyright © 2026 Xiaolang47y <rangerstudio@outlook.com>

This work is free. You can redistribute it and/or modify it under the
terms of the Do What The Fuck You Want To Public License, Version 2,
as published by Sam Hocevar. See the http://www.wtfpl.net/ file for more details.

WTFPL Version 2:

        DO WHAT THE FUCK YOU WANT TO - PUBLIC LICENSE
                    Version 2, December 2004

 Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>

 Everyone is permitted to copy and distribute verbatim or modified
 copies of this license document, and changing it is allowed as long
 as the name is changed.

            DO WHAT THE FUCK YOU WANT TO - PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. You just DO WHAT THE FUCK YOU WANT TO.
"""
        text_widget.insert(tk.END, license_text)
        text_widget.config(state=tk.DISABLED)
    
    def show_history(self):
        history_window = tk.Toplevel(self)
        history_window.title("历史下载记录")
        history_window.geometry("800x600")
        bring_to_front(history_window)
        
        history_dir = self.config_manager.get("history_dir", str(HISTORY_DIR))
        history_path = Path(history_dir)
        
        if not history_path.exists():
            messagebox.showinfo("提示", "暂无历史记录", parent=self)
            return
        
        history_files = sorted(history_path.glob("history_*.txt"), reverse=True)
        
        if not history_files:
            messagebox.showinfo("提示", "暂无历史记录", parent=self)
            return
        
        text_widget = scrolledtext.ScrolledText(history_window, wrap=tk.WORD, font=("Courier", 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        for history_file in history_files:
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    text_widget.insert(tk.END, content + "\n\n" + "="*60 + "\n\n")
            except Exception as e:
                text_widget.insert(tk.END, f"读取失败: {history_file.name}\n错误: {e}\n\n")
        
        text_widget.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()
