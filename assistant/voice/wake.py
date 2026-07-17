"""Nhận diện tên gọi (wake word) 'Bia' trong câu nói.

Chuẩn hoá bỏ dấu tiếng Việt (1:1, giữ nguyên độ dài để căn chỉ mục) để bắt được
'a lô bia', 'alo bia', 'bia ơi', 'Bia'... rồi tách phần lệnh phía sau.
"""
from __future__ import annotations

# Bảng bỏ dấu 1:1 (giữ nguyên độ dài chuỗi -> vị trí ký tự không đổi)
_FROM = ("àáảãạâầấẩẫậăằắẳẵặ" "èéẻẽẹêềếểễệ" "ìíỉĩị"
         "òóỏõọôồốổỗộơờớởỡợ" "ùúủũụưừứửữự" "ỳýỷỹỵ" "đ")
_TO = "a" * 17 + "e" * 11 + "i" * 5 + "o" * 17 + "u" * 11 + "y" * 5 + "d"
_VI_MAP = str.maketrans(_FROM, _TO)

_FILLERS = {"oi", "a", "alo", "e", "nay", "ne"}


def normalize(text: str) -> str:
    return text.lower().translate(_VI_MAP)


def _strip_fillers(text: str) -> str:
    text = text.strip(" ,.!?:;-")
    words = text.split()
    while words and normalize(words[0]) in _FILLERS:
        words = words[1:]
    return " ".join(words)


def detect_wake(transcript: str, names=("bia",)) -> tuple[bool, str]:
    """Trả (đã_gọi, lệnh). 'lệnh' là phần câu sau tên gọi (có thể rỗng)."""
    if not transcript:
        return False, ""
    norm = normalize(transcript)
    for name in names:
        n = normalize(name)
        idx = norm.find(n)
        if idx >= 0:
            after = transcript[idx + len(n):]
            return True, _strip_fillers(after)
    return False, ""
