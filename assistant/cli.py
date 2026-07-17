"""Vòng lặp dòng lệnh cho trợ lý (chế độ text)."""
from __future__ import annotations

from . import memory
from .confirm import ask_confirmation
from .config import Config
from .executor import execute
from .intents import CHAT, SAFE, UNKNOWN
from .llm import parse_intent

BANNER = """
============================================
  Bia - trợ lý cá nhân (chế độ text)
  Gõ yêu cầu bằng tiếng Việt.
  Lệnh: 'trí nhớ' = xem đã học gì (kèm mạng nơ-ron)
        'liên tưởng <điều gì>' = xem mạng liên tưởng tới gì
        'quên hết' = xoá | 'thoát' = dừng.
============================================
"""

_EXIT_WORDS = {"thoát", "thoat", "exit", "quit", "q"}
_FORGET_WORDS = {"quên hết", "quen het", "xoá trí nhớ", "xóa trí nhớ", "xoa tri nho"}
_MEMORY_WORDS = {"trí nhớ", "tri nho", "bạn nhớ gì", "ban nho gi", "nhớ gì về tôi"}


def run() -> None:
    cfg = Config.load()
    print(BANNER)
    print(f"[Model: {cfg.model} @ {cfg.ollama_host}]\n")

    while True:
        try:
            text = input("Bạn > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTạm biệt!")
            return

        if not text:
            continue

        low = text.lower()
        if low in _EXIT_WORDS:
            print("Tạm biệt!")
            return
        if low in _FORGET_WORDS:
            memory.clear()
            print("🧹 Đã xoá toàn bộ trí nhớ.\n")
            continue
        if low in _MEMORY_WORDS:
            print(memory.summary() + "\n")
            continue
        _assoc_prefix = next((p for p in ("liên tưởng", "lien tuong")
                              if low.startswith(p)), None)
        if _assoc_prefix:
            q = text[len(_assoc_prefix):].strip()
            assoc = memory.associations(q, cfg) if q else []
            if assoc:
                print("🧠 Mạng nơ-ron liên tưởng tới:")
                for n in assoc:
                    print(f"  • [{n['kind']}] {n['text']}  (kích hoạt {n['activation']})")
            else:
                print("  (chưa có liên tưởng nào — hãy trò chuyện thêm để mạng lớn lên)")
            print()
            continue

        # Lấy ngữ cảnh từ trí nhớ (thói quen + yêu cầu tương tự) để cá nhân hoá
        context = memory.build_context(text, cfg)
        intent = parse_intent(text, cfg, context)

        # Trò chuyện / hỏi giờ ngày / tra tin tức... -> làm ngay, không cần xác nhận
        if intent.action in {CHAT, UNKNOWN} or not intent.needs_confirmation:
            if intent.action not in {CHAT, UNKNOWN}:
                print("⏳ Để mình xem nhé...")
            answer = execute(intent, cfg)   # CHAT/UNKNOWN -> reply; datetime/web -> kết quả thật
            print(f"🤖 {answer}\n")
            memory.add_interaction(text, intent.action, intent.target, cfg)
            memory.learn_async(text, cfg)          # tự học thông tin lâu dài
            continue

        # Có thao tác lên máy hoặc tạo file -> hỏi xác nhận trước
        if intent.risk != SAFE:
            print(f"⚠️  Lưu ý: hành động này sẽ thay đổi dữ liệu (mức: {intent.risk}).")
        if ask_confirmation(intent.reply):
            print("⏳ Đang thực hiện...")
            print(f"✅ {execute(intent, cfg)}\n")
            # Chỉ ghi nhớ khi người dùng thực sự đồng ý thực hiện
            memory.add_interaction(text, intent.action, intent.target, cfg)
            memory.record_feedback(intent.action, intent.target, True)
            memory.learn_async(text, cfg)
        else:
            print("❌ Đã huỷ, không thực hiện.\n")
            memory.record_feedback(intent.action, intent.target, False)


if __name__ == "__main__":
    run()
