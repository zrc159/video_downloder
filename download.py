# -*- coding: utf-8 -*-
"""通过 YouTube 链接下载视频（含 Shorts），依赖 yt-dlp + 项目目录下的 ffmpeg"""
import os
import sys

# Windows 控制台默认用 GBK，遇到繁体中文标题会乱码；强制 UTF-8 输出
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import yt_dlp

# ===== 代理设置（国内访问 YouTube 必须）=====
# 留空 = 不走代理。也可以直接写死，例如 "http://127.0.0.1:7890"（Clash 默认端口）
# 常见代理地址：
#   Clash        -> http://127.0.0.1:7890
#   V2rayN       -> socks5://127.0.0.1:10808  (或 http://127.0.0.1:10809)
PROXY = os.environ.get("YT_PROXY", "http://127.0.0.1:7897")

# 项目目录（本脚本所在文件夹），ffmpeg.exe / ffprobe.exe 就放在这里
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def download_youtube_video(url: str, output_path: str = None) -> None:
    output_path = output_path or BASE_DIR
    ydl_opts = {
        # 输出文件名：视频标题.扩展名
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        # 优先 H.264(video) + AAC(audio)：兼容性最好，QQ影音等所有播放器都能放。
        # 默认的 bestvideo 会选到 AV1（省空间但很多播放器不支持，会只有声音没画面）
        "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best",
        "merge_output_format": "mp4",
        "ffmpeg_location": BASE_DIR,   # 指向项目目录里的 ffmpeg.exe
        "noplaylist": True,            # 只下单个视频
        "retries": 5,                  # 失败重试次数
        "socket_timeout": 30,          # 单次连接超时（秒）
    }
    if PROXY:
        ydl_opts["proxy"] = PROXY
        print(f"使用代理: {PROXY}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # 先只拿信息（不下载），确认能连通
        info = ydl.extract_info(url, download=False)
        print(f"标题: {info.get('title')}")
        print(f"清晰度: {info.get('height')}p")
        # 正式下载
        ydl.download([url])


if __name__ == "__main__":
    video_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/shorts/BHgvtm4Vk8U"
    download_youtube_video(video_url)
