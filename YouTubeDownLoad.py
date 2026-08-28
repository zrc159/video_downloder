# -*- coding: utf-8 -*-
"""YouTube 视频下载器 —— 现代深色圆角界面（customtkinter + yt-dlp）"""
import os
import sys
import json
import queue
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

import yt_dlp

# 让界面在高分屏上不模糊
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 打包成无控制台程序（console=False）后 stdout/stderr 可能为 None，
# 而 yt-dlp 会往 stderr 写日志，会导致崩溃；这里兜底到空设备
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ===== 外观设置 =====
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# 配色
BG = "#12121a"          # 窗口背景
CARD = "#1c1c28"        # 卡片背景
ACCENT = "#5b7cfa"      # 主色（下载按钮）
ACCENT_HOVER = "#6c8cff"
ACCENT_TEXT = "#ffffff"
MUTED = "#8a8aa3"       # 次要文字

# 字体
FONT_TITLE = ("Microsoft YaHei UI", 24, "bold")
FONT_LABEL = ("Microsoft YaHei UI", 13)
FONT_BUTTON = ("Microsoft YaHei UI", 15, "bold")
FONT_LOG = ("Consolas", 10)
FONT_STATUS = ("Microsoft YaHei UI", 12)

# 项目目录与配置（打包成 exe 后 __file__ 会指向临时目录，需特殊处理）
if getattr(sys, "frozen", False):
    # 打包后：应用目录 = exe 所在文件夹（ffmpeg.exe 放这里，config.json 也存这里）
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)  # PyInstaller 解压资源目录
else:
    # 直接跑脚本时：脚本所在目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DEFAULT_PROXY = "http://127.0.0.1:7897"


def find_ffmpeg_dir() -> str:
    """按优先级找 ffmpeg.exe 所在目录：exe 旁 -> 打包资源 -> 脚本目录"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
        candidates.append(getattr(sys, "_MEIPASS", ""))
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    for d in candidates:
        if d and os.path.exists(os.path.join(d, "ffmpeg.exe")):
            return d
    return BASE_DIR


def load_proxy() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("proxy", DEFAULT_PROXY)
        except Exception:
            pass
    return DEFAULT_PROXY


def save_proxy(proxy: str) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"proxy": proxy}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YouTube 视频下载器")
        self.geometry("760x660")
        self.minsize(680, 560)
        self.configure(fg_color=BG)

        self.log_queue: queue.Queue = queue.Queue()
        self.progress_value = 0.0
        self.status_text = "就绪"
        self.is_downloading = False

        self._build_ui()
        self._poll()

    # ---------- 界面 ----------
    def _build_ui(self):
        # 顶部标题
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(26, 16))
        ctk.CTkLabel(header, text="▶  YouTube 视频下载器", font=FONT_TITLE,
                     text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(header, text="粘贴链接即可下载，自动合并高清画质与音轨",
                     font=("Microsoft YaHei UI", 13), text_color=MUTED).pack(anchor="w", pady=(2, 0))

        # 主体
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        # —— 视频链接卡片 ——
        card1 = self._card(body)
        ctk.CTkLabel(card1, text="视频链接", font=FONT_LABEL,
                     text_color="#ffffff").pack(anchor="w", pady=(0, 6))
        url_row = ctk.CTkFrame(card1, fg_color="transparent")
        url_row.pack(fill="x")
        self.url_entry = ctk.CTkEntry(url_row, height=42, corner_radius=10,
                                      placeholder_text="粘贴 YouTube 链接，如 https://www.youtube.com/...",
                                      fg_color="#262636", border_color="#33334a",
                                      font=("Microsoft YaHei UI", 13))
        self.url_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(url_row, text="粘贴", width=72, height=42, corner_radius=10,
                      fg_color="#33334a", hover_color="#3f3f5c", font=FONT_LABEL,
                      command=self._paste_url).pack(side="left", padx=(10, 0))

        # —— 代理 + 目录卡片 ——
        card2 = self._card(body)
        grid = ctk.CTkFrame(card2, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=0)
        grid.columnconfigure(1, weight=1)

        ctk.CTkLabel(grid, text="代理地址", font=FONT_LABEL,
                     text_color="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 14), pady=(0, 6))
        self.proxy_entry = ctk.CTkEntry(grid, height=40, corner_radius=10,
                                        placeholder_text="http://127.0.0.1:7897",
                                        fg_color="#262636", border_color="#33334a",
                                        font=("Microsoft YaHei UI", 13))
        self.proxy_entry.grid(row=0, column=1, sticky="ew")
        self.proxy_entry.insert(0, load_proxy())

        ctk.CTkLabel(grid, text="保存目录", font=FONT_LABEL,
                     text_color="#ffffff").grid(row=1, column=0, sticky="w", padx=(0, 14), pady=(10, 0))
        out_row = ctk.CTkFrame(grid, fg_color="transparent")
        out_row.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        self.out_entry = ctk.CTkEntry(out_row, height=40, corner_radius=10,
                                      fg_color="#262636", border_color="#33334a",
                                      font=("Microsoft YaHei UI", 13))
        self.out_entry.pack(side="left", fill="x", expand=True)
        self.out_entry.insert(0, BASE_DIR)
        ctk.CTkButton(out_row, text="浏览…", width=72, height=40, corner_radius=10,
                      fg_color="#33334a", hover_color="#3f3f5c", font=FONT_LABEL,
                      command=self._browse).pack(side="left", padx=(10, 0))

        # —— 下载按钮 ——
        self.download_btn = ctk.CTkButton(body, text="开 始 下 载", height=50, corner_radius=12,
                                          fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                          text_color=ACCENT_TEXT, font=FONT_BUTTON,
                                          command=self._on_download)
        self.download_btn.pack(fill="x", pady=(16, 8))

        # —— 进度条 + 状态 ——
        self.progress = ctk.CTkProgressBar(body, height=10, corner_radius=5,
                                           fg_color="#262636", progress_color=ACCENT)
        self.progress.pack(fill="x")
        self.progress.set(0)
        self.status_label = ctk.CTkLabel(body, text="就绪", font=FONT_STATUS,
                                         text_color=MUTED, anchor="w")
        self.status_label.pack(fill="x", pady=(4, 10))

        # —— 日志卡片 ——
        card3 = self._card(body, expand=True)
        ctk.CTkLabel(card3, text="日志", font=FONT_LABEL,
                     text_color="#ffffff").pack(anchor="w", pady=(0, 6))
        self.log_box = ctk.CTkTextbox(card3, corner_radius=10, fg_color="#13131c",
                                      border_color="#2a2a3c", border_width=1,
                                      font=FONT_LOG, text_color="#c9c9d6",
                                      wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self._set_log_state("disabled")

    def _card(self, parent, expand: bool = False):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14)
        f.pack(fill="both" if expand else "x", expand=expand, pady=(0, 12))
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        return inner

    def _paste_url(self):
        try:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.clipboard_get())
        except Exception:
            pass

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.out_entry.get() or BASE_DIR)
        if chosen:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, chosen)

    def _set_log_state(self, state: str):
        try:
            self.log_box.configure(state=state)
        except Exception:
            pass

    def _append_log(self, text: str):
        self._set_log_state("normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self._set_log_state("disabled")

    # ---------- 主线程轮询 ----------
    def _poll(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is None:
                    self.is_downloading = False
                    self.download_btn.configure(state="normal", text="开 始 下 载",
                                                fg_color=ACCENT)
                else:
                    self._append_log(item)
        except queue.Empty:
            pass

        self.progress.set(self.progress_value / 100.0)
        self.status_label.configure(text=self.status_text)

        self.after(100, self._poll)

    # ---------- 下载 ----------
    def _progress_hook(self, d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            if total > 0:
                self.progress_value = downloaded / total * 100.0
            speed = d.get("speed")
            if speed:
                self.status_text = (f"已下载 {downloaded/1024/1024:.1f} / {total/1024/1024:.1f} MB"
                                    f"   ·   {speed/1024/1024:.2f} MB/s")
            else:
                self.status_text = f"已下载 {downloaded/1024/1024:.1f} MB"
        elif d.get("status") == "finished":
            self.log_queue.put(f"  ✓ 完成片段: {os.path.basename(d.get('filename', ''))}")

    def _on_download(self):
        if self.is_downloading:
            return
        url = self.url_entry.get().strip()
        proxy = self.proxy_entry.get().strip()
        out_dir = self.out_entry.get().strip() or BASE_DIR

        if not url:
            messagebox.showwarning("提示", "请先填写视频链接")
            return
        if not os.path.isdir(out_dir):
            messagebox.showerror("错误", f"保存目录不存在:\n{out_dir}")
            return

        save_proxy(proxy)

        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="下载中…", fg_color="#33334a")
        self.progress_value = 0.0
        self.progress.set(0)
        self.status_text = "正在连接…"
        self._append_log(f"▶ 开始下载: {url}")

        threading.Thread(target=self._download_worker, args=(url, proxy, out_dir),
                         daemon=True).start()

    def _download_worker(self, url: str, proxy: str, out_dir: str):
        try:
            ydl_opts = {
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best",
                "merge_output_format": "mp4",
                "ffmpeg_location": find_ffmpeg_dir(),
                "noplaylist": True,
                "retries": 5,
                "socket_timeout": 30,
                "progress_hooks": [self._progress_hook],
            }
            if proxy:
                ydl_opts["proxy"] = proxy
                self.log_queue.put(f"  使用代理: {proxy}")
            else:
                self.log_queue.put("  未使用代理（直连）")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.log_queue.put(f"  标题: {info.get('title')}")
                self.log_queue.put(f"  清晰度: {info.get('height')}p")
                ydl.download([url])

            self.status_text = "下载完成"
            self.log_queue.put(f"✅ 下载完成！保存目录: {out_dir}")
        except Exception as e:
            self.status_text = "出错"
            self.log_queue.put(f"❌ 出错: {e}")
        finally:
            self.log_queue.put(None)


def main():
    DownloaderApp().mainloop()


if __name__ == "__main__":
    main()
