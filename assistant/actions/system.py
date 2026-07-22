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


# Cụm chỉ "vị trí hiện tại" -> để trống origin cho Maps tự định vị
_HERE_WORDS = ("vị trí hiện tại", "vi tri hien tai", "chỗ tôi", "cho toi",
               "chỗ mình", "cho minh", "đây", "day", "hiện tại", "hien tai",
               "vị trí của tôi", "nơi tôi đang đứng")


_ROUTE_PREFIX = (
    r"(cho\s+tôi\s+xem|cho\s+tôi|giúp\s+tôi|giup\s+toi|xem|tính|tinh|"
    r"chỉ\s+đường|chi\s+duong|chỉ|đường\s+đi|duong\s+di|khoảng\s+cách|"
    r"khoang\s+cach|quãng\s+đường|quang\s+duong|dẫn\s+đường|dan\s+duong|"
    r"làm\s+sao\s+để|lam\s+sao\s+de|cách\s+đi|cach\s+di|đường|duong|đi)"
)
_ROUTE_MODE_WORDS = ("đi bộ", "di bo", "cuốc bộ", "xe máy", "xe may", "ô tô",
                     "o to", "xe hơi", "xe hoi", "xe đạp", "xe dap", "đạp xe",
                     "xe buýt", "xe buyt", "xe bus", "bằng xe", "bang xe")


def _parse_route(spec: str) -> tuple[str, str]:
    """Tách 'từ A đến B' thành (điểm đi, điểm đến).

    Hỗ trợ 'từ A đến B', 'A đến B', 'A tới B', 'A -> B'. Không có dấu tách thì
    coi cả câu là điểm đến (điểm đi = vị trí hiện tại). Tự bỏ các cụm dẫn
    ('cho tôi xem', 'khoảng cách', 'chỉ đường'...) và từ chỉ phương tiện.
    """
    import re
    s = (spec or "").strip()

    # Bỏ từ chỉ phương tiện (đã xử lý riêng ở _travel_mode)
    for mw in _ROUTE_MODE_WORDS:
        s = re.sub(re.escape(mw), " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()

    # Bỏ LẶP các cụm dẫn ở đầu cho tới khi hết
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"^\s*" + _ROUTE_PREFIX + r"\s+", "", s,
                   flags=re.IGNORECASE).strip()

    # Bỏ đuôi hỏi ('bao xa', 'bao nhiêu km', 'mất bao lâu'...)
    s = re.sub(r"\s+(bao\s+xa|bao\s+nhiêu.*|bao\s+lâu.*|mất\s+bao.*|"
               r"hết\s+bao.*|nhé|nha|ạ|đi|với)$", "", s,
               flags=re.IGNORECASE).strip(" ,.!?")

    low = s.lower()
    for sep in (" đến ", " tới ", " den ", " toi ", " -> ", "->", " → ", "→", " ra "):
        idx = low.find(sep)
        if idx >= 0:
            origin = s[:idx].strip()
            dest = s[idx + len(sep):].strip()
            origin = re.sub(r"^(từ|tu)\s+", "", origin, flags=re.IGNORECASE).strip()
            return origin, dest.strip(" ,.!?")

    # Không có dấu tách -> chỉ có điểm đến
    dest = re.sub(r"^(từ|tu|đến|den|tới|toi)\s+", "", s, flags=re.IGNORECASE).strip()
    return "", dest


def _travel_mode(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("đi bộ", "di bo", "cuốc bộ", "walk")):
        return "walking"
    if any(k in t for k in ("xe buýt", "xe buyt", "xe bus", "bus", "phương tiện công cộng")):
        return "transit"
    if any(k in t for k in ("xe đạp", "xe dap", "đạp xe", "bike", "bicycle")):
        return "bicycling"
    return "driving"


def directions(spec: str, mode: str = "") -> str:
    """Chỉ đường A->B trên Google Maps (đường ngắn nhất, kèm quãng đường & thời gian).

    `spec`: mô tả tuyến, vd 'từ chợ Bến Đồn đến vòng xoay Hiệp Thành 3'.
    Google Maps sẽ tự vẽ đường đi tối ưu, hiện khoảng cách, thời gian, dẫn đường.
    """
    spec = (spec or "").strip()
    if not spec:
        return "Bạn cho mình biết đi từ đâu đến đâu nhé."

    origin, dest = _parse_route(spec)
    if not dest:
        return "Mình chưa rõ điểm đến. Bạn nói lại kiểu 'từ A đến B' giúp mình nhé."

    travel = mode or _travel_mode(spec)

    url = "https://www.google.com/maps/dir/?api=1"
    use_origin = origin and origin.lower() not in _HERE_WORDS
    if use_origin:
        url += "&origin=" + quote_plus(origin)
    url += "&destination=" + quote_plus(dest)
    url += "&travelmode=" + travel
    open_url(url)

    if use_origin:
        return (f"Đang chỉ đường từ '{origin}' đến '{dest}' — Google Maps sẽ hiện "
                "đường ngắn nhất, quãng đường và thời gian đi.")
    return (f"Đang chỉ đường tới '{dest}' từ vị trí hiện tại của bạn — kèm quãng "
            "đường, thời gian và hướng dẫn đi.")


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


_BROWSER_CLASSES = ("chrome", "chromium", "firefox", "navigator", "brave",
                    "msedge", "microsoft-edge", "opera", "vivaldi")


def _find_content_window():
    """Tìm cửa sổ nội dung (ưu tiên trình duyệt) để cuộn.

    Trả (center_x, center_y) hoặc None. Dùng wmctrl -lxG.
    """
    if not shutil.which("wmctrl"):
        return None
    try:
        out = subprocess.check_output(["wmctrl", "-lxG"],
                                      stderr=subprocess.DEVNULL, text=True)
    except Exception:   # noqa: BLE001
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        # ID, desktop, x, y, w, h, class, host, title...
        try:
            x, y, w, h = (int(parts[2]), int(parts[3]),
                          int(parts[4]), int(parts[5]))
        except ValueError:
            continue
        wclass = parts[6].lower()
        if any(b in wclass for b in _BROWSER_CLASSES) and w > 100 and h > 100:
            return (x + w // 2, y + h // 2)
    return None


def scroll(direction: str = "down", amount: int = 8) -> str:
    """Cuộn nội dung trang (ưu tiên trình duyệt) lên/xuống.

    Đưa con trỏ chuột qua cửa sổ trình duyệt rồi cuộn ở đó (không cướp focus
    bàn phím), sau đó trả chuột về vị trí cũ. Nếu không thấy trình duyệt thì
    cuộn ngay tại vị trí chuột hiện tại.

    direction: 'up' | 'down'; amount: số nấc cuộn.
    """
    direction = (direction or "down").strip().lower()
    if direction in ("lên", "len", "up", "trên", "tren"):
        direction = "up"
    elif direction in ("xuống", "xuong", "down", "dưới", "duoi"):
        direction = "down"
    if direction not in ("up", "down"):
        return "Mình chỉ cuộn lên hoặc xuống thôi nhé."

    try:
        from pynput.mouse import Controller
    except ImportError:
        return ("Mình chưa cuộn được vì thiếu thư viện pynput. "
                "Cài bằng: pip install pynput")

    mouse = Controller()
    steps = max(1, int(amount))
    dy = 1 if direction == "up" else -1

    target = _find_content_window()
    old_pos = None
    if target is not None:
        try:
            old_pos = mouse.position          # lưu vị trí chuột hiện tại
            mouse.position = target           # đưa chuột qua trình duyệt
            time.sleep(0.05)
        except Exception:   # noqa: BLE001
            old_pos = None

    for _ in range(steps):
        mouse.scroll(0, dy)
        time.sleep(0.02)

    if old_pos is not None:
        try:
            time.sleep(0.03)
            mouse.position = old_pos          # trả chuột về chỗ cũ
        except Exception:   # noqa: BLE001
            pass

    where = " trang web" if target is not None else ""
    return f"Đã cuộn {'lên' if direction == 'up' else 'xuống'}{where}."


def _current_volume() -> int | None:
    """Đọc âm lượng hiện tại (%) qua pactl. None nếu không đọc được."""
    try:
        out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            stderr=subprocess.DEVNULL, text=True)
        import re
        m = re.search(r"(\d+)%", out)
        return int(m.group(1)) if m else None
    except Exception:   # noqa: BLE001
        return None


def set_volume(target: str = "up", step: int = 10) -> str:
    """Chỉnh âm lượng loa qua pactl (PulseAudio/PipeWire).

    target: 'up' | 'down' | 'mute' | 'unmute' | số 0-100 (đặt mức cụ thể).
    """
    if not shutil.which("pactl"):
        return "Máy chưa có pactl nên mình không chỉnh âm lượng được."

    target = (target or "up").strip().lower()
    # Chuẩn hoá vài cách nói tiếng Việt
    if target in ("lên", "len", "to", "to hơn", "tăng", "tang", "up", "cao"):
        target = "up"
    elif target in ("xuống", "xuong", "nhỏ", "nho", "giảm", "giam", "down", "thấp"):
        target = "down"
    elif target in ("tắt tiếng", "tat tieng", "im", "câm", "cam", "mute"):
        target = "mute"
    elif target in ("bật tiếng", "bat tieng", "unmute", "mở tiếng"):
        target = "unmute"

    sink = "@DEFAULT_SINK@"
    try:
        if target == "up":
            subprocess.run(["pactl", "set-sink-mute", sink, "0"],
                           stderr=subprocess.DEVNULL)
            subprocess.run(["pactl", "set-sink-volume", sink, f"+{step}%"],
                           stderr=subprocess.DEVNULL)
            vol = _current_volume()
            return f"Đã tăng âm lượng{f' lên {vol}%' if vol is not None else ''}."
        if target == "down":
            subprocess.run(["pactl", "set-sink-volume", sink, f"-{step}%"],
                           stderr=subprocess.DEVNULL)
            vol = _current_volume()
            return f"Đã giảm âm lượng{f' còn {vol}%' if vol is not None else ''}."
        if target == "mute":
            subprocess.run(["pactl", "set-sink-mute", sink, "1"],
                           stderr=subprocess.DEVNULL)
            return "Đã tắt tiếng."
        if target == "unmute":
            subprocess.run(["pactl", "set-sink-mute", sink, "0"],
                           stderr=subprocess.DEVNULL)
            return "Đã bật tiếng lại."
        # Đặt mức cụ thể nếu target là số
        if target.isdigit():
            level = max(0, min(100, int(target)))
            subprocess.run(["pactl", "set-sink-mute", sink, "0"],
                           stderr=subprocess.DEVNULL)
            subprocess.run(["pactl", "set-sink-volume", sink, f"{level}%"],
                           stderr=subprocess.DEVNULL)
            return f"Đã đặt âm lượng ở mức {level}%."
    except Exception as exc:   # noqa: BLE001
        return f"Không chỉnh được âm lượng: {exc}"
    return "Mình chưa hiểu ý chỉnh âm lượng của bạn."


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
