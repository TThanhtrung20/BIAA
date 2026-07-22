"""Hành động thao tác hệ thống: mở web, mở ứng dụng, tìm kiếm trên web."""
from __future__ import annotations

import shutil
import subprocess
import time
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


def show_location(place: str) -> str:
    """Mở vị trí/địa điểm trên Google Maps.

    `place` có thể là địa chỉ, tên địa điểm, hoặc toạ độ "lat,long".
    Nếu để trống -> mở bản đồ tại vị trí hiện tại (Maps tự định vị theo IP).
    """
    place = (place or "").strip()
    if not place:
        url = "https://www.google.com/maps"
        open_url(url)
        return "Đã mở Google Maps ở vị trí hiện tại của bạn."
    url = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(place)
    open_url(url)
    return f"Đã mở vị trí '{place}' trên Google Maps."


_YT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def _first_youtube_video(query: str) -> str | None:
    """Tìm videoId của kết quả đầu tiên trên YouTube cho `query`."""
    import re
    import urllib.request
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    req = urllib.request.Request(
        url, headers={"User-Agent": _YT_UA, "Accept-Language": "vi,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", "ignore")
    m = re.search(r'"videoId":"([0-9A-Za-z_-]{11})"', html)
    return m.group(1) if m else None


def play_music(query: str) -> str:
    """Phát nhạc/video trên YouTube.

    Tự tìm bài đầu tiên khớp `query` rồi mở TRANG XEM (tự phát ngay).
    Nếu không tra được (mất mạng...) -> mở trang kết quả tìm kiếm.
    Nếu `query` trống -> mở YouTube Music.
    """
    query = (query or "").strip()
    if not query:
        open_url("https://music.youtube.com")
        return "Đã mở YouTube Music cho bạn."

    try:
        vid = _first_youtube_video(query)
    except Exception:   # noqa: BLE001 - mất mạng/parse lỗi -> fallback
        vid = None

    if vid:
        open_url("https://www.youtube.com/watch?v=" + vid)
        return f"Đang phát '{query}' trên YouTube 🎵"

    # Fallback: mở trang tìm kiếm để người dùng tự chọn
    open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
    return f"Đã tìm '{query}' trên YouTube để bạn chọn nghe."


def scroll(direction: str = "down", amount: int = 8) -> str:
    """Cuộn màn hình lên/xuống ở cửa sổ đang active (dùng pynput).

    direction: 'up' | 'down' | 'top' | 'bottom'
    amount: số nấc cuộn (mỗi nấc ~ 1 lần lăn chuột).
    """
    direction = (direction or "down").strip().lower()
    # Chuẩn hoá vài cách nói tiếng Việt
    if direction in ("lên", "len", "up", "trên", "tren"):
        direction = "up"
    elif direction in ("xuống", "xuong", "down", "dưới", "duoi"):
        direction = "down"

    try:
        from pynput.mouse import Controller
    except ImportError:
        return ("Mình chưa cuộn được vì thiếu thư viện pynput. "
                "Cài bằng: pip install pynput")

    mouse = Controller()
    steps = max(1, int(amount))
    if direction == "up":
        for _ in range(steps):
            mouse.scroll(0, 1)
            time.sleep(0.02)
        return "Đã cuộn lên."
    elif direction == "down":
        for _ in range(steps):
            mouse.scroll(0, -1)
            time.sleep(0.02)
        return "Đã cuộn xuống."
    else:
        return "Mình chỉ cuộn lên hoặc xuống thôi nhé."


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
