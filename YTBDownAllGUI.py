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
    """将窗口置顶并带到最前面"""
    window.attributes('-topmost', True)
    window.lift()
    window.focus_force()
    window.after(100, lambda: window.attributes('-topmost', False))

# 配置文件路径
CONFIG_DIR = Path.home() / ".config" / "ytbdownall"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_DIR = CONFIG_DIR / "history"

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
    "history_dir": str(HISTORY_DIR),
    "yt_dlp_path": "",
    "ffmpeg_path": "",
    "deno_path": ""
}


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self.load()
    
    def load(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(saved)
                return config
        return DEFAULT_CONFIG.copy()
    
    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        self.save()


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
            self.step_yt_dlp,
            self.step_ffmpeg,
            self.step_deno,
            self.step_python,
            self.step_cookie,
            self.step_finish
        ]
        
        self.yt_path_var = tk.StringVar()
        self.ff_path_var = tk.StringVar()
        
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
        if self.current_step == 1:  # yt-dlp 步骤
            self.config_manager.set("yt_dlp_path", self.yt_path_var.get())
        elif self.current_step == 2:  # ffmpeg 步骤
            self.config_manager.set("ffmpeg_path", self.ff_path_var.get())
        elif self.current_step == 5:  # cookie 步骤
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
        self.geometry("550x650")
        self.config_manager = config_manager
        self.parent = parent
        
        self.transient(parent)
        
        self.create_widgets()
        bring_to_front(self)
        
    def create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 下载设置
        download_frame = ttk.Frame(notebook, padding=10)
        notebook.add(download_frame, text="下载设置")
        
        ttk.Label(download_frame, text="默认保存目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.save_dir_var = tk.StringVar(value=self.config_manager.get("save_dir", ""))
        ttk.Entry(download_frame, textvariable=self.save_dir_var, width=40).grid(row=0, column=1, padx=5, pady=5)
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
        ttk.Entry(dir_frame, textvariable=self.history_dir_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(dir_frame, text="浏览", command=self.browse_history_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_frame, text="打开", command=self.open_history_dir).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(history_frame, text="历史记录文件数量:").pack(anchor=tk.W, pady=5)
        self.history_count_var = tk.IntVar(value=self.config_manager.get("history_count", 1))
        ttk.Spinbox(history_frame, from_=0, to=100, textvariable=self.history_count_var, width=5).pack(anchor=tk.W, pady=5)
        ttk.Label(history_frame, text="(设置为 0 表示不保存历史记录)", foreground="gray").pack(anchor=tk.W)
        
        # 环境检测
        env_frame = ttk.Frame(notebook, padding=10)
        notebook.add(env_frame, text="环境检测")
        
        self.env_notebook = ttk.Notebook(env_frame)
        self.env_notebook.pack(fill=tk.BOTH, expand=True)
        
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
        ttk.Button(env_frame, text="重新检测全部", command=self.refresh_all_env).pack(pady=5)
        
        # 保存按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
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
        self.config_manager.set("save_dir", self.save_dir_var.get())
        self.config_manager.set("ask_save_dir", self.ask_save_dir_var.get())
        self.config_manager.set("max_concurrent", self.concurrent_var.get())
        self.config_manager.set("cookie_type", self.cookie_type_var.get())
        self.config_manager.set("cookie_file", self.cookie_file_var.get())
        self.config_manager.set("history_count", self.history_count_var.get())
        self.config_manager.set("history_dir", self.history_dir_var.get())
        
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
        self.results = []
        
        self.attributes('-topmost', True)
        
        self.create_widgets()
        self.start_download()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_widgets(self):
        self.progress_label = ttk.Label(self, text="准备下载...")
        self.progress_label.pack(fill=tk.X, padx=10, pady=5)
        
        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.retry_btn = ttk.Button(btn_frame, text="重试失败项", command=self.retry_failed, state=tk.DISABLED)
        self.retry_btn.pack(side=tk.LEFT, padx=5)

        self.history_btn = ttk.Button(btn_frame, text="历史记录", command=self.show_history)
        self.history_btn.pack(side=tk.LEFT, padx=5)

        self.close_btn = ttk.Button(btn_frame, text="关闭", command=self.destroy, state=tk.DISABLED)
        self.close_btn.pack(side=tk.RIGHT, padx=5)
    
    def log(self, message, tag=None):
        self.log_text.config(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, message + "\n", tag)
        else:
            self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def start_download(self):
        thread = threading.Thread(target=self.download_thread, daemon=True)
        thread.start()
    
    def download_thread(self):
        total = len(self.download_items)
        success = 0
        failed = 0
        
        for i, item in enumerate(self.download_items, 1):
            if not self.running:
                break
            
            self.after(0, lambda msg=f"[{i}/{total}] 开始下载: {item['url']}": self.progress_label.config(text=msg))
            self.after(0, lambda msg=f"\n{'='*60}\n[{i}/{total}] {item['url']}\n{'='*60}": self.log(msg))
            
            result = self.download_item(item)
            self.results.append(result)
            
            if result['success']:
                success += 1
                self.after(0, lambda msg=f"✓ 下载成功: {result.get('title', '未知标题')}": self.log(msg, "success"))
            else:
                failed += 1
                self.after(0, lambda msg=f"✗ 下载失败: {result.get('error', '未知错误')}": self.log(msg, "error"))
        
        # 显示结果列表
        self.after(0, lambda: self.log(f"\n{'='*60}"))
        self.after(0, lambda: self.log(f"下载完成！成功: {success} / 失败: {failed}"))
        self.after(0, lambda: self.log(f"{'='*60}\n"))
        self.after(0, lambda: self.log("下载列表:"))
        
        for idx, result in enumerate(self.results, 1):
            status = "✓" if result['success'] else "✗ [失败]"
            title = result.get('title', '未知标题')
            url = result['url']
            self.after(0, lambda msg=f"  {idx}. {status} {title} | {url}": self.log(msg, "success" if result['success'] else "error"))
        
        self.after(0, lambda: self.progress_label.config(text=f"下载完成！成功: {success} / 失败: {failed}"))
        
        # 保存历史记录
        self.after(0, lambda: self.save_history())
        
        if failed > 0:
            self.after(0, lambda: self.retry_btn.config(state=tk.NORMAL))
        self.after(0, lambda: self.close_btn.config(state=tk.NORMAL))
        
        # 置顶完成提示
        self.after(0, lambda: self.show_completion_dialog(success, failed))
    
    def show_completion_dialog(self, success, failed):
        self.attributes('-topmost', True)
        self.lift()
        self.focus_force()
        messagebox.showinfo("完成", f"下载完成！\n成功: {success}\n失败: {failed}", parent=self)
    
    def download_item(self, item):
        url = item['url']
        checks = item['checks']
        sub_langs = item.get('sub_langs', ['en', 'zh-Hans'])
        
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
        
        cmd.extend(["--retries", "infinite", "--fragment-retries", "infinite", "--sleep-interval", "3"])
        
        save_dir = self.config_manager.get("save_dir", os.getcwd())
        output_template = os.path.join(save_dir, "%(title)s.%(ext)s")
        cmd.extend(["-o", output_template])
        
        if checks.get("video"):
            cmd.extend(["--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
            cmd.extend(["--merge-output-format", "mp4"])
        
        if checks.get("cover"):
            cmd.extend(["--write-thumbnail", "--convert-thumbnails", "jpg"])
        
        has_subs = checks.get("srt") or checks.get("vtt")
        if has_subs:
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", ",".join(sub_langs)])
            if checks.get("srt") and checks.get("vtt"):
                cmd.extend(["--sub-format", "srt/vtt/best"])
            elif checks.get("srt"):
                cmd.extend(["--sub-format", "srt"])
            elif checks.get("vtt"):
                cmd.extend(["--sub-format", "vtt"])
        
        if checks.get("audio"):
            cmd.extend(["--extract-audio", "--audio-format", "mp3"])
        
        if not checks.get("video") and not checks.get("audio"):
            cmd.extend(["--skip-download"])
        
        cmd.append(url)
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            title = None
            for line in process.stdout:
                if not self.running:
                    process.terminate()
                    break
                line = line.rstrip()
                if line:
                    self.after(0, lambda msg=line: self.log(msg))
                    if "[download] Destination:" in line:
                        filename = line.split("[download] Destination:")[-1].strip()
                        title = os.path.splitext(os.path.basename(filename))[0]
                    elif "Already downloaded" in line:
                        match = re.search(r"Already downloaded.*?['\"](.+?)['\"]", line)
                        if match:
                            title = os.path.splitext(os.path.basename(match.group(1)))[0]
            
            process.wait()
            
            if process.returncode == 0:
                if not title:
                    title = self.find_latest_title(save_dir)
                return {"success": True, "url": url, "title": title or "未知标题"}
            else:
                return {"success": False, "url": url, "error": f"退出码: {process.returncode}"}
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}
    
    def find_latest_title(self, save_dir):
        try:
            files = []
            for ext in ['*.mp4', '*.mkv', '*.webm', '*.mp3', '*.m4a']:
                files.extend(Path(save_dir).glob(ext))
            if files:
                latest = max(files, key=os.path.getmtime)
                return latest.stem
        except:
            pass
        return None
    
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
                f.write(f"  {idx}. {status} {result.get('title', '未知标题')} | {result['url']}\n")
        
        # 清理旧历史
        history_files = sorted(Path(history_dir).glob("history_*.txt"))
        while len(history_files) > history_count:
            history_files[0].unlink()
            history_files = history_files[1:]
    
    def retry_failed(self):
        failed_items = [r for r in self.results if not r['success']]
        if not failed_items:
            return
        
        self.retry_btn.config(state=tk.DISABLED)
        self.log("\n开始重试失败项...")
        
        thread = threading.Thread(target=self.retry_thread, args=(failed_items,), daemon=True)
        thread.start()
    
    def retry_thread(self, failed_items):
        for item in failed_items:
            if not self.running:
                break
            
            self.after(0, lambda msg=f"\n重试: {item['url']}": self.log(msg))
            
            original = next((i for i in self.download_items if i['url'] == item['url']), None)
            if original:
                result = self.download_item(original)
                for r in self.results:
                    if r['url'] == item['url']:
                        r.update(result)
                        break
                
                if result['success']:
                    self.after(0, lambda msg=f"✓ 重试成功: {result.get('title', '未知标题')}": self.log(msg, "success"))
                else:
                    self.after(0, lambda msg=f"✗ 重试失败: {result.get('error', '未知错误')}": self.log(msg, "error"))
        
        self.after(0, lambda: self.retry_btn.config(state=tk.NORMAL))
        self.after(0, lambda: messagebox.showinfo("完成", "重试完成", parent=self))
    
    def on_close(self):
        self.running = False
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
        self.geometry("300x250")
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


class HeaderRow(tk.Frame):
    """表头行，包含每列的全选复选框"""
    
    def __init__(self, parent, default_checks):
        super().__init__(parent)
        self.link_items = []
        
        # 标签占位（与链接列对齐）
        ttk.Label(self, text="", width=50).pack(side=tk.LEFT, padx=5, pady=2)
        
        # 每列的全选复选框
        self.video_var = tk.BooleanVar(value=default_checks.get("video", True))
        self.cover_var = tk.BooleanVar(value=default_checks.get("cover", True))
        self.srt_var = tk.BooleanVar(value=default_checks.get("srt", False))
        self.vtt_var = tk.BooleanVar(value=default_checks.get("vtt", False))
        self.audio_var = tk.BooleanVar(value=default_checks.get("audio", False))
        
        ttk.Checkbutton(self, text="视频", variable=self.video_var, command=self.toggle_video).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(self, text="封面", variable=self.cover_var, command=self.toggle_cover).pack(side=tk.LEFT, padx=5)
        
        # SRT 表头
        srt_frame = ttk.Frame(self)
        srt_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(srt_frame, variable=self.srt_var, command=self.toggle_srt).pack(side=tk.LEFT)
        ttk.Label(srt_frame, text="SRT").pack(side=tk.LEFT)
        
        # VTT 表头
        vtt_frame = ttk.Frame(self)
        vtt_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(vtt_frame, variable=self.vtt_var, command=self.toggle_vtt).pack(side=tk.LEFT)
        ttk.Label(vtt_frame, text="VTT").pack(side=tk.LEFT)
        
        ttk.Checkbutton(self, text="音频", variable=self.audio_var, command=self.toggle_audio).pack(side=tk.LEFT, padx=5)
    
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


class LinkItem(tk.Frame):
    """链接列表项"""
    
    def __init__(self, parent, url, default_checks, default_sub_langs):
        super().__init__(parent)
        self.url = url
        
        url_label = ttk.Label(self, text=url, width=50, anchor=tk.W)
        url_label.pack(side=tk.LEFT, padx=5, pady=2)
        
        self.video_var = tk.BooleanVar(value=default_checks.get("video", True))
        self.cover_var = tk.BooleanVar(value=default_checks.get("cover", True))
        self.srt_var = tk.BooleanVar(value=default_checks.get("srt", False))
        self.vtt_var = tk.BooleanVar(value=default_checks.get("vtt", False))
        self.audio_var = tk.BooleanVar(value=default_checks.get("audio", False))
        
        self.srt_langs = default_sub_langs.copy() if default_sub_langs else []
        self.vtt_langs = default_sub_langs.copy() if default_sub_langs else []
        
        video_frame = ttk.Frame(self)
        video_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(video_frame, variable=self.video_var).pack(side=tk.LEFT)
        ttk.Label(video_frame, text="视频").pack(side=tk.LEFT)
        
        cover_frame = ttk.Frame(self)
        cover_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(cover_frame, variable=self.cover_var).pack(side=tk.LEFT)
        ttk.Label(cover_frame, text="封面").pack(side=tk.LEFT)
        
        # SRT 字幕按钮
        srt_frame = ttk.Frame(self)
        srt_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(srt_frame, variable=self.srt_var).pack(side=tk.LEFT)
        ttk.Button(srt_frame, text="SRT", command=self.show_srt_langs).pack(side=tk.LEFT)
        
        # VTT 字幕按钮
        vtt_frame = ttk.Frame(self)
        vtt_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(vtt_frame, variable=self.vtt_var).pack(side=tk.LEFT)
        ttk.Button(vtt_frame, text="VTT", command=self.show_vtt_langs).pack(side=tk.LEFT)
        
        audio_frame = ttk.Frame(self)
        audio_frame.pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(audio_frame, variable=self.audio_var).pack(side=tk.LEFT)
        ttk.Label(audio_frame, text="音频").pack(side=tk.LEFT)
    
    def show_srt_langs(self):
        dialog = SubLangDialog(self, self.srt_langs)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.srt_langs = dialog.result
    
    def show_vtt_langs(self):
        dialog = SubLangDialog(self, self.vtt_langs)
        self.wait_window(dialog)
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
        return self.srt_langs
    
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
        self.geometry("900x700")
        
        self.config_manager = ConfigManager()
        self.link_items = []
        
        if not CONFIG_FILE.exists():
            self.show_first_run_wizard()
        
        self.create_widgets()
    
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
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    
    def parse_links(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.link_items.clear()
        
        text = self.link_input.get("1.0", tk.END)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        default_checks = self.config_manager.get("default_checks", {})
        default_sub_langs = self.config_manager.get("default_sub_langs", ["en", "zh-Hans"])
        
        # 添加表头行（列全选复选框）
        header = HeaderRow(self.scrollable_frame, default_checks)
        header.pack(fill=tk.X, pady=2)
        
        for url in lines:
            item = LinkItem(self.scrollable_frame, url, default_checks, default_sub_langs)
            item.pack(fill=tk.X, pady=2)
            self.link_items.append(item)
            header.add_link_item(item)
        
        if not lines:
            messagebox.showwarning("警告", "没有找到有效的链接", parent=self)
    
    def select_all(self):
        for item in self.link_items:
            item.set_all(True)
    
    def deselect_all(self):
        for item in self.link_items:
            item.set_all(False)
    
    def clear_list(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.link_items.clear()
        self.link_input.delete("1.0", tk.END)
    
    def start_download(self):
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
