"""Hành động lấy THÔNG TIN THỜI GIAN THỰC.

- get_datetime(): ngày/giờ/thứ hiện tại — offline, lấy từ đồng hồ máy.
- fetch_news(): lấy tiêu đề tin tức mới nhất qua Google News RSS (không cần API key).
- web_answer(): tra tin/thông tin hiện tại (tin tức, luật mới, thời tiết...) rồi nhờ
  LLM tóm tắt NGẮN GỌN, CHỈ dựa trên tiêu đề lấy được (chống bịa).

Chỉ dùng thư viện chuẩn (urllib + xml.etree). Cần internet cho phần tin tức.
"""
from __future__ import annotations

import datetime
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree

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


def fetch_news(topic: str = "", limit: int = 6) -> list[str]:
    """Lấy tối đa `limit` tiêu đề tin mới nhất (Google News RSS)."""
    url = _news_url(topic)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read()
    root = ElementTree.fromstring(raw)
    titles: list[str] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if title:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def web_answer(target: str, cfg=None) -> str:
    """Tra thông tin hiện tại theo `target` rồi tóm tắt ngắn gọn (có dẫn nguồn)."""
    try:
        titles = fetch_news(target, limit=6)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
            ElementTree.ParseError):
        return ("Mình chưa lấy được thông tin — có vẻ máy đang không có mạng. "
                "Bạn kiểm tra kết nối rồi thử lại nhé.")
    if not titles:
        return f"Mình không tìm thấy tin nào về '{target}'."

    # Nhờ LLM tóm tắt (grounded). Lỗi thì đọc thẳng vài tiêu đề đầu.
    summary = ""
    if cfg is not None:
        try:
            from ..llm import summarize_web
            summary = summarize_web(target, titles, cfg).strip()
        except Exception:   # noqa: BLE001
            summary = ""

    if summary:
        return summary + "\n(Nguồn: Google Tin tức)"

    top = titles[:4]
    lines = "\n".join(f"• {t}" for t in top)
    label = target.strip() or "tin mới nhất"
    return f"Vài tin mới nhất về '{label}':\n{lines}\n(Nguồn: Google Tin tức)"
