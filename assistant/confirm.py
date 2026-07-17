"""Luồng xác nhận trước khi thực thi hành động.

Đây là lớp an toàn cốt lõi: trợ lý luôn nói lại ý định và chờ người dùng chốt
trước khi thao tác lên máy.
"""
from __future__ import annotations

_AFFIRMATIVE = {
    "có", "co", "y", "yes", "ok", "oke", "okay", "ừ", "u", "uh",
    "đúng", "dung", "đồng ý", "ừm", "chạy", "phải", "ừa", "vâng", "duyệt",
}
_NEGATIVE = {
    "không", "khong", "no", "n", "khỏi", "thôi", "hủy", "huy",
    "dừng", "sai", "đừng", "dung",
}


def is_affirmative(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if t in _AFFIRMATIVE:
        return True
    return t.split()[0] in _AFFIRMATIVE


def is_negative(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if t in _NEGATIVE:
        return True
    return t.split()[0] in _NEGATIVE


def ask_confirmation(reply: str, prompt_fn=input) -> bool:
    """Hiển thị câu xác nhận. Trả True nếu người dùng đồng ý.

    Mặc định AN TOÀN: nếu câu trả lời không rõ ràng -> coi như KHÔNG đồng ý.
    """
    print(f"🤖 {reply}")
    answer = prompt_fn("   (có/không) > ").strip()
    if is_affirmative(answer):
        return True
    return False
