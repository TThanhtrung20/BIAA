"""Nhân vật mascot trên desktop.

Cửa sổ trong suốt, không viền, luôn nổi trên cùng. Nhân vật tự đi lại quanh
màn hình ("vô tri"), chớp mắt, đổi biểu cảm theo trạng thái. Bấm chuột phải để
ra lệnh: câu lệnh chạy qua đúng bộ não + xác nhận + thực thi đã xây trước đó,
và kết quả hiện ra trong bong bóng thoại.

Chưa có giọng nói (để bước sau) — hiện tại điều khiển bằng cách gõ.
"""
from __future__ import annotations

import os
import random
import time

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

# --- Trạng thái nhân vật ---
IDLE = "idle"
WALK = "walk"
LISTENING = "listening"
THINKING = "thinking"
TALKING = "talking"

_STATE_COLOR = {
    IDLE: QColor("#5aa9e6"),
    WALK: QColor("#5aa9e6"),
    LISTENING: QColor("#7fc97f"),
    THINKING: QColor("#f6c445"),
    TALKING: QColor("#ef8f8f"),
}

_DARK = QColor("#2b2b2b")


class MascotWindow(QWidget):
    def __init__(self, cfg=None):
        super().__init__()
        self.cfg = cfg
        self.size_px = int(getattr(cfg, "mascot_size", 120) or 120)
        self.W = max(self.size_px, 240)          # rộng để chứa bong bóng thoại
        self.H = self.size_px + 84               # phần trên dành cho bong bóng
        self.state = IDLE
        self.facing = 1                          # 1 = nhìn phải, -1 = nhìn trái
        self.vx = 0.0
        self._blink = False
        self._paused = False
        self._drag_offset = None
        self._bubble_text = ""
        self._bubble_until = 0.0
        self._mouth_phase = 0

        self._init_window()
        self._load_image()
        self._init_position()
        self._init_timers()

    # ------------------------------------------------------------------ setup
    def _init_window(self):
        self.setFixedSize(self.W, self.H)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("BIAA")

    def _load_image(self):
        """Nếu người dùng cấu hình ảnh riêng thì dùng, không thì vẽ mặc định."""
        self.pixmap = None
        path = os.path.expanduser(getattr(self.cfg, "mascot_image", "") or "")
        if path and os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                self.pixmap = pm.scaled(
                    self.size_px, self.size_px,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )

    def _init_position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.screen_rect = screen
        x = random.randint(screen.left(), max(screen.left(), screen.right() - self.W))
        y = screen.bottom() - self.H
        self.move(x, y)

    def _init_timers(self):
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._tick)
        self.anim.start(40)                      # ~25 khung hình/giây

        self.brain = QTimer(self)
        self.brain.timeout.connect(self._decide)
        self.brain.start(2500)                   # 2.5s lại "quyết định" làm gì

        self.blinker = QTimer(self)
        self.blinker.timeout.connect(self._start_blink)
        self.blinker.start(4500)

    # ------------------------------------------------- hành vi tự động ("vô tri")
    def _decide(self):
        if self._paused or self.state in (LISTENING, THINKING, TALKING):
            return
        if random.random() < 0.6:
            self.state = WALK
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * random.uniform(1.5, 3.0)
        else:
            self.state = IDLE
            self.vx = 0.0

    def _tick(self):
        if self.state == WALK and not self._paused:
            geo = self.screen_rect
            nx = self.x() + self.vx
            if nx <= geo.left():
                nx, self.facing, self.vx = geo.left(), 1, abs(self.vx)
            elif nx >= geo.right() - self.W:
                nx, self.facing, self.vx = geo.right() - self.W, -1, -abs(self.vx)
            self.move(int(nx), self.y())
        if self.state == TALKING:
            self._mouth_phase = (self._mouth_phase + 1) % 20
        if self._bubble_text and time.time() > self._bubble_until:
            self._bubble_text = ""
            if self.state == TALKING:
                self.state = IDLE
        self.update()

    def _start_blink(self):
        self._blink = True
        self.update()
        QTimer.singleShot(140, self._end_blink)

    def _end_blink(self):
        self._blink = False
        self.update()

    # ------------------------------------------------------------------ vẽ
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        char_rect = QRect((self.W - self.size_px) // 2, self.H - self.size_px,
                          self.size_px, self.size_px)
        if self.pixmap is not None:
            p.drawPixmap(char_rect.topLeft(), self.pixmap)
        else:
            self._draw_character(p, char_rect)
        if self._bubble_text:
            self._draw_bubble(p)

    def _draw_character(self, p, r):
        s = self.size_px
        color = _STATE_COLOR.get(self.state, _STATE_COLOR[IDLE])

        # thân
        p.setBrush(color)
        p.setPen(QPen(_DARK, max(2, s // 40)))
        body = r.adjusted(int(s * 0.08), int(s * 0.12), -int(s * 0.08), -int(s * 0.05))
        p.drawRoundedRect(body, s * 0.35, s * 0.35)

        # mắt
        eye_y = r.top() + int(s * 0.42)
        dx = int(s * 0.06) * self.facing
        left_x = r.left() + int(s * 0.34) + dx
        right_x = r.left() + int(s * 0.58) + dx
        eye_w, eye_h = int(s * 0.12), int(s * 0.16)
        if self._blink:
            p.setPen(QPen(_DARK, max(2, s // 40)))
            p.drawLine(left_x, eye_y + eye_h // 2, left_x + eye_w, eye_y + eye_h // 2)
            p.drawLine(right_x, eye_y + eye_h // 2, right_x + eye_w, eye_y + eye_h // 2)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("white"))
            p.drawEllipse(left_x, eye_y, eye_w, eye_h)
            p.drawEllipse(right_x, eye_y, eye_w, eye_h)
            p.setBrush(_DARK)
            pr = max(2, int(eye_w * 0.5))
            pdx = int(pr * 0.4) * self.facing
            p.drawEllipse(left_x + eye_w // 2 - pr // 2 + pdx, eye_y + eye_h // 2 - pr // 2, pr, pr)
            p.drawEllipse(right_x + eye_w // 2 - pr // 2 + pdx, eye_y + eye_h // 2 - pr // 2, pr, pr)

        self._draw_mouth(p, r)

    def _draw_mouth(self, p, r):
        s = self.size_px
        cx = r.center().x()
        my = r.top() + int(s * 0.66)
        p.setPen(QPen(_DARK, max(2, s // 45)))
        if self.state == LISTENING:
            p.setBrush(QColor("#7a3b3b"))
            p.drawEllipse(cx - int(s * 0.06), my, int(s * 0.12), int(s * 0.10))
        elif self.state == TALKING:
            p.setBrush(QColor("#7a3b3b"))
            h = int(s * 0.06) + (int(s * 0.06) if self._mouth_phase < 10 else 0)
            p.drawEllipse(cx - int(s * 0.07), my, int(s * 0.14), h)
        elif self.state == THINKING:
            p.drawLine(cx - int(s * 0.06), my + int(s * 0.03), cx + int(s * 0.06), my + int(s * 0.03))
        else:  # idle / walk -> mỉm cười
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - int(s * 0.08), my)
            path.quadTo(cx, my + int(s * 0.09), cx + int(s * 0.08), my)
            p.drawPath(path)

    def _draw_bubble(self, p):
        margin = 8
        rect = QRect(margin, 4, self.W - 2 * margin, self.H - self.size_px - 12)
        p.setBrush(QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor("#888888"), 1))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(QColor("#222222"))
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        flags = int(Qt.AlignLeft) | int(Qt.AlignVCenter) | int(Qt.TextWordWrap)
        p.drawText(rect.adjusted(8, 6, -8, -6), flags, self._bubble_text)

    # --------------------------------------------------------- tương tác chuột
    def say(self, text, secs=6):
        self._bubble_text = text
        self._bubble_until = time.time() + secs
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._paused = True
            self.vx = 0.0

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        self._paused = False

    def mouseDoubleClickEvent(self, e):
        self._ask_command()

    def contextMenuEvent(self, e):
        menu = QMenu()
        a_cmd = menu.addAction("💬 Ra lệnh (gõ)")
        a_hide = menu.addAction("🙈 Ẩn 10 giây")
        menu.addSeparator()
        a_quit = menu.addAction("❌ Thoát")
        chosen = menu.exec(e.globalPos())
        if chosen == a_cmd:
            self._ask_command()
        elif chosen == a_hide:
            self.hide()
            QTimer.singleShot(10000, self.show)
        elif chosen == a_quit:
            QApplication.quit()

    def _ask_command(self):
        self._paused = True
        text, ok = QInputDialog.getText(self, "Ra lệnh cho trợ lý",
                                        "Bạn muốn mình làm gì?")
        self._paused = False
        if ok and text.strip():
            self._handle_command(text.strip())

    def _handle_command(self, text):
        """Chạy câu lệnh qua bộ não -> xác nhận -> thực thi (giống CLI, nhưng GUI)."""
        from .. import memory
        from ..config import Config
        from ..executor import execute
        from ..intents import CHAT, UNKNOWN
        from ..llm import parse_intent

        cfg = self.cfg or Config.load()
        self.state = THINKING
        self.say("Để mình nghĩ chút...", 30)
        QApplication.processEvents()

        context = memory.build_context(text, cfg)
        intent = parse_intent(text, cfg, context)

        # Chỉ trò chuyện / không cần thao tác
        if intent.action in (CHAT, UNKNOWN) or not intent.needs_confirmation:
            self.state = TALKING
            self.say(intent.reply or "...", 6)
            memory.add_interaction(text, intent.action, intent.target, cfg)
            QTimer.singleShot(3500, self._back_to_idle)
            return

        # Cần xác nhận -> hộp thoại Có/Không
        self.state = IDLE
        self.update()
        confirm = QMessageBox.question(self, "Xác nhận", intent.reply,
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            self.state = TALKING
            self.say("Đang làm...", 30)
            QApplication.processEvents()
            self.say(execute(intent, cfg), 8)
            memory.add_interaction(text, intent.action, intent.target, cfg)
        else:
            self.say("Ok, mình không làm nữa.", 4)
        QTimer.singleShot(3500, self._back_to_idle)

    def _back_to_idle(self):
        if self.state in (THINKING, TALKING, LISTENING):
            self.state = IDLE
            self.update()
