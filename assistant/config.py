"""Cấu hình cho trợ lý.

Đọc cấu hình từ ~/.config/assistant/config.json (nếu có), phần còn lại dùng
giá trị mặc định. Có thể chỉnh model, host Ollama, ngôn ngữ... tại đây.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

CONFIG_DIR = os.path.expanduser("~/.config/assistant")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
DATA_DIR = os.path.expanduser("~/.local/share/assistant")


@dataclass
class Config:
    # Kết nối tới Ollama đang chạy local
    ollama_host: str = "http://localhost:11434"
    # Model dùng để hiểu ý định + trò chuyện. qwen2.5:3b (general) nhanh + giỏi
    # tiếng Việt hơn bản coder, hợp chạy CPU. Đổi tại đây nếu muốn model khác.
    model: str = "qwen2.5:3b"
    # Model tạo embedding cho "trí nhớ" (bước sau)
    embed_model: str = "nomic-embed-text"
    # Ngôn ngữ giao tiếp mặc định
    language: str = "vi"
    # Nếu True: hành động mức "an toàn" sẽ tự chạy, không hỏi lại.
    # Mặc định False -> luôn hỏi xác nhận (an toàn hơn).
    auto_confirm_safe: bool = False
    # Thời gian chờ tối đa khi gọi Ollama (giây)
    request_timeout: int = 120
    # Đường dẫn ảnh nhân vật mascot 2D (PNG nền trong suốt). Trống -> vẽ mặc định.
    mascot_image: str = ""
    # Đường dẫn mô hình 3D (.glb/.gltf). Nếu có -> dùng mascot 3D thay cho 2D.
    mascot_model: str = ""
    # Đường dẫn .qml do balsam sinh ra (mô hình CÓ animation). Nếu có -> mascot animation.
    mascot_qml: str = ""
    # Căn camera cho mascot animation (tuỳ theo mô hình)
    mascot_cam_y: float = 1.8
    mascot_cam_z: float = 11.0
    # Màu tô cho mascot 3D (mô hình không có texture sẽ được chiếu sáng theo màu này)
    mascot_color: str = "#4aa3ff"
    # --- Giọng nói ---
    # Kích thước model faster-whisper cho STT: tiny/base/small/medium
    whisper_model: str = "small"
    # Đường dẫn model giọng piper (.onnx) cho TTS
    piper_voice: str = ""
    # Kích thước nhân vật mascot (pixel)
    mascot_size: int = 120
    # --- Tên gọi & kích hoạt bằng giọng (wake word) ---
    # Tên của trợ lý (hiển thị + tự xưng)
    assistant_name: str = "Bia"
    # Các cách gọi tên để kích hoạt: nói "a lô Bia ..." là chạy, không cần bấm
    wake_words: list = field(default_factory=lambda: ["bia", "bi a"])
    # Bật chế độ luôn lắng nghe tên gọi (mic mở nền). Tắt -> chỉ dùng double-click.
    wake_enabled: bool = True
    # Ngưỡng năng lượng mic để coi là "có tiếng nói" (0.0-1.0)
    wake_threshold: float = 0.02
    # Tự học hỏi: sau mỗi câu nói, tự trích xuất thông tin lâu dài về người dùng
    auto_learn: bool = True
    # --- Lưu trí nhớ vào PostgreSQL (pgvector) thay vì JSON ---
    # Bật -> ưu tiên lưu mạng nơ-ron + vector vào Postgres; mất kết nối thì tự
    # quay về JSON để không gián đoạn.
    use_postgres: bool = True
    # Chuỗi kết nối psycopg2 tới DB có cài extension pgvector.
    # KHÔNG để mật khẩu thật trong mã nguồn (repo có thể công khai). Đặt DSN thật
    # trong ~/.config/assistant/config.json hoặc biến môi trường BIA_PG_DSN.
    pg_dsn: str = os.environ.get(
        "BIA_PG_DSN",
        "host=localhost port=5432 dbname=agentdb user=agent password=")

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, value in data.items():
                    if hasattr(cfg, key):
                        setattr(cfg, key, value)
            except (json.JSONDecodeError, OSError):
                # Cấu hình hỏng -> bỏ qua, dùng mặc định
                pass
        return cfg

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
