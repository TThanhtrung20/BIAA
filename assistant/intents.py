"""Định nghĩa cấu trúc ý định (intent) và mức độ rủi ro của hành động."""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Các hành động được hỗ trợ ---
OPEN_URL = "open_url"                # mở một trang web
OPEN_APP = "open_app"                # mở một ứng dụng trên máy
SEARCH_WEB = "search_web"            # tìm kiếm trên web (mở trình duyệt)
CREATE_WORD = "create_word"          # tạo file Word (.docx)
CREATE_EXCEL = "create_excel"        # tạo file Excel (.xlsx)
CREATE_PPTX = "create_powerpoint"    # tạo file PowerPoint (.pptx)
GET_DATETIME = "get_datetime"        # trả lời ngày/giờ hiện tại (offline)
WEB_ANSWER = "web_answer"            # tra thông tin mới trên internet rồi trả lời
SHOW_LOCATION = "show_location"      # mở vị trí/địa điểm trên bản đồ (Google Maps)
PLAY_MUSIC = "play_music"            # phát nhạc/video trên YouTube
SCROLL = "scroll"                    # cuộn màn hình lên/xuống (target = 'up'|'down')
SET_VOLUME = "set_volume"            # chỉnh âm lượng (target = 'up'|'down'|'mute'|'0-100')
CHAT = "chat"                        # chỉ trò chuyện/trả lời
UNKNOWN = "unknown"                  # không hiểu

VALID_ACTIONS = {
    OPEN_URL, OPEN_APP, SEARCH_WEB,
    CREATE_WORD, CREATE_EXCEL, CREATE_PPTX,
    GET_DATETIME, WEB_ANSWER, SHOW_LOCATION,
    PLAY_MUSIC, SCROLL, SET_VOLUME,
    CHAT, UNKNOWN,
}

# Hành động chỉ ĐỌC/trả lời thông tin, an toàn -> không cần xác nhận
NO_CONFIRM_ACTIONS = {GET_DATETIME, WEB_ANSWER, SHOW_LOCATION, PLAY_MUSIC, SCROLL,
                      SET_VOLUME, CHAT, UNKNOWN}

# --- Mức độ rủi ro ---
SAFE = "safe"            # không thay đổi dữ liệu, dễ đảo ngược
MODERATE = "moderate"    # tạo/sửa tệp
DANGEROUS = "dangerous"  # xoá, chạy lệnh hệ thống, quyền cao

RISK_LEVEL = {
    OPEN_URL: SAFE,
    OPEN_APP: SAFE,
    SEARCH_WEB: SAFE,
    GET_DATETIME: SAFE,
    WEB_ANSWER: SAFE,
    SHOW_LOCATION: SAFE,
    PLAY_MUSIC: SAFE,
    SCROLL: SAFE,
    SET_VOLUME: SAFE,
    CHAT: SAFE,
    UNKNOWN: SAFE,
    # Tạo file -> có thay đổi dữ liệu trên ổ đĩa
    CREATE_WORD: MODERATE,
    CREATE_EXCEL: MODERATE,
    CREATE_PPTX: MODERATE,
}


@dataclass
class Intent:
    """Kết quả phân tích một câu nói của người dùng."""

    action: str = UNKNOWN
    target: str = ""              # đích của hành động (url, tên app, từ khoá...)
    reply: str = ""               # câu trợ lý nói lại để xác nhận / trả lời
    needs_confirmation: bool = True
    raw: dict = field(default_factory=dict)  # JSON gốc từ LLM (để debug)

    @property
    def risk(self) -> str:
        return RISK_LEVEL.get(self.action, MODERATE)
