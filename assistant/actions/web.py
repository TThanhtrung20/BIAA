"""Hành động lấy THÔNG TIN THỜI GIAN THỰC.

- get_datetime(): ngày/giờ/thứ hiện tại — offline, lấy từ đồng hồ máy.
- fetch_news(): lấy tiêu đề tin tức mới nhất qua Google News RSS (không cần API key).
- web_answer(): tra tin/thông tin hiện tại (tin tức, luật mới, thời tiết...) rồi nhờ
  LLM tóm tắt NGẮN GỌN, CHỈ dựa trên tiêu đề lấy được (chống bịa).

Chỉ dùng thư viện chuẩn (urllib + xml.etree). Cần internet cho phần tin tức.
"""
from __future__ import annotations

import datetime
import re
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree

# Lưu tin tức lần tra gần nhất: danh sách (tiêu đề, link) để "mở bài viết đó".
_last_news: list[tuple[str, str]] = []

_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Câu hỏi tin tức chung chung -> lấy trang nhất thay vì tìm theo chủ đề
_GENERIC_NEWS = {
    "", "tin mới nhất", "tin tuc", "tin tức", "ban tin", "bản tin", "tin mới",
    "tin moi", "tin nóng", "tin nong", "hôm nay", "hom nay", "tin trong ngày",
    "thời sự", "thoi su", "tin mới nhất hôm nay",
}


def get_datetime(target: str = "") -> str:
    """Trả câu trả lời ngày/giờ hiện tại bằng tiếng Việt (offline)."""
    now = datetime.datetime.now()
    weekday = _WEEKDAYS[now.weekday()]
    return (f"Bây giờ là {now.hour} giờ {now.minute:02d} phút, "
            f"{weekday}, ngày {now.day} tháng {now.month} năm {now.year}.")


def _news_url(topic: str) -> str:
    base = "hl=vi&gl=VN&ceid=VN:vi"
    topic = (topic or "").strip()
    if topic.lower() in _GENERIC_NEWS:
        return f"https://news.google.com/rss?{base}"
    q = urllib.parse.quote(topic)
    return f"https://news.google.com/rss/search?q={q}&{base}"


def fetch_news(topic: str = "", limit: int = 6) -> list[tuple[str, str]]:
    """Lấy tối đa `limit` tin mới nhất (Google News RSS): [(tiêu đề, link)]."""
    url = _news_url(topic)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read()
    root = ElementTree.fromstring(raw)
    items: list[tuple[str, str]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append((title, link))
        if len(items) >= limit:
            break
    return items


def web_answer(target: str, cfg=None) -> str:
    """Tra thông tin hiện tại theo `target` rồi tóm tắt ngắn gọn (có dẫn nguồn).

    Lưu danh sách bài + link vào `_last_news` để sau có thể "mở bài viết đó".
    """
    global _last_news
    try:
        items = fetch_news(target, limit=6)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
            ElementTree.ParseError):
        return ("Mình chưa lấy được thông tin — có vẻ máy đang không có mạng. "
                "Bạn kiểm tra kết nối rồi thử lại nhé.")
    if not items:
        return f"Mình không tìm thấy tin nào về '{target}'."

    _last_news = items
    titles = [t for t, _ in items]

    # Nhờ LLM tóm tắt (grounded). Lỗi thì đọc thẳng vài tiêu đề đầu.
    summary = ""
    if cfg is not None:
        try:
            from ..llm import summarize_web
            summary = summarize_web(target, titles, cfg).strip()
        except Exception:   # noqa: BLE001
            summary = ""

    if summary:
        return summary + "\n(Nguồn: Google Tin tức — nói \"mở bài viết đó\" để đọc chi tiết)"

    top = titles[:4]
    lines = "\n".join(f"{i+1}. {t}" for i, t in enumerate(top))
    label = target.strip() or "tin mới nhất"
    return (f"Vài tin mới nhất về '{label}':\n{lines}\n"
            "(Nguồn: Google Tin tức — nói \"mở bài số 1\" để đọc)")


def open_article(which: str = "") -> str:
    """Mở bài báo trong danh sách tin vừa tra (`_last_news`).

    `which` có thể chứa số thứ tự ('bài số 2', '2'); mặc định mở bài đầu tiên.
    """
    if not _last_news:
        return ("Mình chưa có tin nào để mở. Bạn hỏi tin tức trước "
                "(vd 'tin mới nhất hôm nay') rồi bảo mình mở nhé.")
    idx = 0
    m = re.search(r"(\d+)", which or "")
    if m:
        idx = int(m.group(1)) - 1
    idx = max(0, min(idx, len(_last_news) - 1))
    title, link = _last_news[idx]
    if not link:
        return f"Bài '{title}' không có đường dẫn để mở."
    from .system import open_url
    open_url(link)
    return f"Đang mở bài: {title}"
