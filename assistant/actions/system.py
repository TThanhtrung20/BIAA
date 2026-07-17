"""Hành động thao tác hệ thống: mở web, mở ứng dụng, tìm kiếm trên web."""
from __future__ import annotations

import shutil
import subprocess
from urllib.parse import quote_plus

# Bản đồ tên ứng dụng thân thiện -> danh sách lệnh khả dĩ (thử lần lượt cho tới
# khi tìm được lệnh có thật trên máy).
APP_ALIASES = {
    "firefox": ["firefox"],
    "browser": ["firefox", "google-chrome", "chromium", "brave-browser"],
    "trình duyệt": ["firefox", "google-chrome", "chromium", "brave-browser"],
    "chrome": ["google-chrome", "chromium"],
    "calculator": ["gnome-calculator", "galculator", "xcalc"],
    "máy tính": ["gnome-calculator", "galculator", "xcalc"],
    "files": ["nemo", "nautilus", "thunar", "dolphin"],
    "file": ["nemo", "nautilus", "thunar", "dolphin"],
    "quản lý tệp": ["nemo", "nautilus", "thunar", "dolphin"],
    "terminal": ["gnome-terminal", "x-terminal-emulator", "xterm", "konsole"],
    "text editor": ["xed", "gedit", "kate", "mousepad"],
    "soạn thảo": ["xed", "gedit", "kate", "mousepad"],
    "code": ["code", "codium"],
    "vscode": ["code", "codium"],
}


def open_url(url: str) -> str:
    if not url:
        raise ValueError("URL trống")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    subprocess.Popen(
        ["xdg-open", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Đã mở {url}"


def search_web(query: str) -> str:
    if not query:
        raise ValueError("Từ khoá trống")
    url = "https://www.google.com/search?q=" + quote_plus(query)
    return open_url(url)


def open_app(name: str) -> str:
    if not name:
        raise ValueError("Tên ứng dụng trống")
    candidates = APP_ALIASES.get(name.strip().lower(), [name.strip()])
    for cmd in candidates:
        if shutil.which(cmd):
            subprocess.Popen(
                [cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Đã mở ứng dụng: {cmd}"
    raise FileNotFoundError(
        f"Không tìm thấy ứng dụng cho '{name}'. Đã thử: {', '.join(candidates)}"
    )
