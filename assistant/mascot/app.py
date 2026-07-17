"""Khởi chạy nhân vật mascot trên desktop."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..config import Config
from .pet import MascotWindow


def run():
    cfg = Config.load()
    app = QApplication(sys.argv)
    # Không thoát khi cửa sổ bị ẩn (mascot có thể tạm ẩn); chỉ thoát qua menu.
    app.setQuitOnLastWindowClosed(False)
    pet = MascotWindow(cfg)
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
