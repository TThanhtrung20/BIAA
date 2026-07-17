"""Điều phối và thực thi hành động SAU KHI đã được người dùng xác nhận."""
from __future__ import annotations

from . import llm
from .actions import office, system
from .intents import (
    CHAT,
    CREATE_EXCEL,
    CREATE_PPTX,
    CREATE_WORD,
    OPEN_APP,
    OPEN_URL,
    SEARCH_WEB,
    Intent,
)


def execute(intent: Intent, cfg=None) -> str:
    """Thực thi intent, trả về câu mô tả kết quả (thân thiện với người dùng)."""
    try:
        if intent.action == OPEN_URL:
            return system.open_url(intent.target)
        if intent.action == SEARCH_WEB:
            return system.search_web(intent.target)
        if intent.action == OPEN_APP:
            return system.open_app(intent.target)
        if intent.action in (CREATE_WORD, CREATE_EXCEL, CREATE_PPTX):
            return _create_office(intent, cfg)
        if intent.action == CHAT:
            return intent.reply or "..."
        return "Mình chưa hỗ trợ hành động này."
    except Exception as exc:  # noqa: BLE001 - gom lỗi để báo lại thân thiện
        return f"Có lỗi khi thực hiện: {exc}"


def _create_office(intent: Intent, cfg) -> str:
    """Sinh nội dung bằng LLM rồi xuất ra file Office tương ứng."""
    if cfg is None:
        from .config import Config
        cfg = Config.load()

    topic = intent.target or "tài liệu"

    if intent.action == CREATE_WORD:
        data = llm.generate_office_content("word", topic, cfg)
        title = data.get("title") or topic
        path = office.create_word(
            title=title,
            blocks=data.get("blocks", []),
            path=office.slug_filename(title, ".docx"),
        )
        return f"Đã tạo file Word: {path}"

    if intent.action == CREATE_EXCEL:
        data = llm.generate_office_content("excel", topic, cfg)
        name = data.get("sheet_name") or topic
        path = office.create_excel(
            headers=data.get("headers"),
            rows=data.get("rows", []),
            sheet_name=data.get("sheet_name", "Sheet1"),
            path=office.slug_filename(name, ".xlsx"),
        )
        return f"Đã tạo file Excel: {path}"

    # CREATE_PPTX
    data = llm.generate_office_content("powerpoint", topic, cfg)
    title = data.get("title") or topic
    path = office.create_powerpoint(
        title=title,
        subtitle=data.get("subtitle"),
        slides=data.get("slides", []),
        path=office.slug_filename(title, ".pptx"),
    )
    return f"Đã tạo file PowerPoint: {path}"
