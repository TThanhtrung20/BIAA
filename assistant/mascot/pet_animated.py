"""Mascot 3D CÓ animation, nổi trên desktop.

Nạp mô hình do balsam chuyển đổi (mỗi động tác là một Timeline). Điều khiển bằng
cách bật đúng MỘT Timeline tại một thời điểm:
- đứng yên (Idle) khi rảnh, đi bộ (Walking) khi di chuyển quanh màn hình,
- menu chuột phải: vẫy tay / nhảy múa / nhảy / chạy... (động tác một lần rồi
  quay lại trạng thái nền).

Kéo chuột trái để di chuyển. Cần GPU/OpenGL (màn hình thật).
"""
from __future__ import annotations

import os
import random
import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCursor, QSurfaceFormat
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import QApplication, QMenu

_QML = os.path.join(os.path.dirname(__file__), "mascot_anim.qml")

# Tên các động tác của RobotExpressive (và tên chuẩn Mixamo tương tự)
_ANIM_NAMES = {
    "Dance", "Death", "Idle", "Jump", "No", "Punch", "Running",
    "Sitting", "Standing", "ThumbsUp", "Walking", "WalkJump", "Wave", "Yes",
}

# Mỗi hành động của Bia -> một động tác biểu cảm tương ứng của mascot.
# Khi Bia thực hiện yêu cầu, mascot sẽ diễn động tác này (một lần rồi về Idle).
_ACTION_ANIM = {
    "play_music":       "Dance",     # phát nhạc -> nhảy múa
    "scroll":           "Jump",      # cuộn màn hình -> nhún nhảy
    "open_url":         "ThumbsUp",  # mở web -> giơ ngón cái
    "open_app":         "ThumbsUp",  # mở app -> giơ ngón cái
    "search_web":       "ThumbsUp",  # tìm kiếm -> giơ ngón cái
    "show_location":    "Running",   # dẫn đường -> chạy
    "get_datetime":     "Yes",       # xem giờ -> gật đầu
    "web_answer":       "Yes",       # tra tin -> gật đầu
    "create_word":      "ThumbsUp",
    "create_excel":     "ThumbsUp",
    "create_powerpoint": "ThumbsUp",
}

# Từ khoá chào hỏi -> mascot vẫy tay (Wave) khi chỉ trò chuyện.
_GREETING_WORDS = (
    "chào", "chao", "hello", "hi", "alo", "a lô", "a lo", "hey", "ê ",
    "xin chào", "xin chao",
)
# Động tác lặp vô hạn (trạng thái nền); còn lại là "một lần"
_LOOP = {"Idle", "Walking", "Running"}

# Menu động tác (nhãn hiển thị -> tên animation). Chỉ hiện cái nào mô hình có.
_MENU_ACTIONS = [
    ("👋 Vẫy tay", "Wave"),
    ("💃 Nhảy múa", "Dance"),
    ("🤸 Nhảy", "Jump"),
    ("👍 Đồng ý", "ThumbsUp"),
    ("🏃 Chạy vòng", "Running"),
]


class _AnimController:
    """Bật/tắt Timeline để phát đúng một động tác."""

    def __init__(self):
        self.timelines: dict[str, QObject] = {}
        self.durations: dict[str, float] = {}   # mili-giây (framesPerSecond=1000)
        self.base = "Idle"
        self._oneshot_until = 0.0

    def bind(self, root: QObject) -> int:
        found = [c for c in root.findChildren(QObject) if c.objectName() in _ANIM_NAMES]
        for tl in found:
            name = tl.objectName()
            self.timelines[name] = tl
            end_frame = tl.property("endFrame")
            self.durations[name] = float(end_frame) if end_frame else 1500.0
        if self.timelines:
            base = "Idle" if "Idle" in self.timelines else next(iter(self.timelines))
            self.base = base
            self._enable_only(base)
        return len(self.timelines)

    def _enable_only(self, name: str):
        for other, tl in self.timelines.items():
            tl.setProperty("enabled", other == name)

    def play_base(self, name: str):
        """Đặt trạng thái nền (Idle/Walking); chỉ áp dụng nếu không có động tác một-lần đang chạy."""
        if name not in self.timelines:
            return
        self.base = name
        if time.time() >= self._oneshot_until:
            self._enable_only(name)

    def play_action(self, name: str):
        """Phát một động tác một lần rồi quay lại trạng thái nền."""
        if name not in self.timelines:
            return
        self._enable_only(name)
        dur = self.durations.get(name, 1500.0)
        if name in _LOOP:
            self._oneshot_until = time.time() + 4.0   # chạy vòng ~4s rồi về nền
            QTimer.singleShot(4000, self._resume)
        else:
            self._oneshot_until = time.time() + dur / 1000.0
            QTimer.singleShot(int(dur) + 50, self._resume)

    def _resume(self):
        self._oneshot_until = 0.0
        self._enable_only(self.base)


class _Bridge(QObject):
    """Cầu nối QML -> Python: kéo cửa sổ, menu động tác."""

    def __init__(self, view: QQuickView, controller: _AnimController):
        super().__init__()
        self._view = view
        self._ctrl = controller
        self.dragging = False
        self.voice = None            # gán sau khi tạo _Voice

    @Slot(int, int)
    def move_by(self, dx: int, dy: int):
        self._view.setPosition(self._view.x() + dx, self._view.y() + dy)

    @Slot(bool)
    def set_dragging(self, value: bool):
        self.dragging = bool(value)

    @Slot()
    def listen(self):
        if self.voice is not None:
            self.voice.start()

    @Slot()
    def menu(self):
        menu = QMenu()
        listen_action = menu.addAction("🎤 Nói chuyện")
        wake_on = bool(getattr(self.voice, "cfg", None) and
                       getattr(self.voice.cfg, "wake_enabled", False)) if self.voice else False
        toggle_action = menu.addAction(
            "🔕 Tắt nghe gọi tên" if wake_on else "🔔 Bật nghe gọi tên")
        menu.addSeparator()
        mapping = {}
        for label, anim in _MENU_ACTIONS:
            if anim in self._ctrl.timelines:
                action = menu.addAction(label)
                mapping[action] = anim
        menu.addSeparator()
        quit_action = menu.addAction("❌ Thoát")
        chosen = menu.exec(QCursor.pos())
        if chosen == quit_action:
            QApplication.quit()
        elif chosen == listen_action:
            self.listen()
        elif chosen == toggle_action:
            if self.voice is not None:
                self.voice.set_wake_enabled(not wake_on)
        elif chosen in mapping:
            self._ctrl.play_action(mapping[chosen])


class _Motion(QObject):
    """Cho nhân vật tự đi/chạy/nhảy quanh màn hình, xoay người theo hướng đi."""

    def __init__(self, view: QQuickView, bridge: _Bridge,
                 controller: _AnimController, pivot: QObject | None):
        super().__init__()
        self.view = view
        self.bridge = bridge
        self.ctrl = controller
        self.pivot = pivot
        # Toàn bộ desktop ảo (gộp tất cả màn hình) -> đi được qua nhiều màn hình
        virtual = QApplication.primaryScreen().virtualGeometry()
        avail = QApplication.primaryScreen().availableGeometry()
        self.min_x = virtual.left() + 10
        self.max_x = virtual.right() - view.width() - 10
        self.base_y = avail.bottom() - view.height() - 6
        self.vx = 0.0
        self.state = "idle"          # idle | walk | run
        self.jump_total = 26
        self.jump_frames = 0
        self.paused = False          # dừng đi lại khi đang trò chuyện

        self.view.setPosition((self.min_x + self.max_x) // 2, self.base_y)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(30)

        self._decide_timer = QTimer(self)
        self._decide_timer.timeout.connect(self._decide)
        self._decide_timer.start(2800)

    def set_paused(self, value: bool):
        self.paused = bool(value)
        if self.paused:
            self.state = "idle"
            self.vx = 0.0
            self._face(0)

    def _face(self, direction: int):
        """direction: +1 quay phải, -1 quay trái, 0 quay mặt ra camera."""
        if self.pivot is None:
            return
        yaw = 90 if direction > 0 else (-90 if direction < 0 else 0)
        self.pivot.setProperty("yaw", yaw)

    def _decide(self):
        if self.paused or self.bridge.dragging or self.jump_frames > 0:
            return
        if time.time() < self.ctrl._oneshot_until:   # đang phát động tác một-lần
            return
        r = random.random()
        if r < 0.28:                      # đứng yên
            self.state = "idle"; self.vx = 0.0
            self._face(0); self.ctrl.play_base("Idle")
        elif r < 0.56:                    # đi bộ từng bước
            self.state = "walk"; d = random.choice((-1, 1))
            self.vx = d * random.uniform(2.5, 3.5)
            self._face(d); self.ctrl.play_base("Walking")
        elif r < 0.80:                    # chạy
            self.state = "run"; d = random.choice((-1, 1))
            self.vx = d * random.uniform(6.0, 8.0)
            self._face(d); self.ctrl.play_base("Running")
        else:                             # nhảy tại chỗ
            self.state = "idle"; self.vx = 0.0
            self._face(0)
            self.ctrl.play_action("Jump")
            self.jump_frames = self.jump_total

    def _tick(self):
        if self.paused or self.bridge.dragging:
            return
        x = self.view.x()
        if self.state in ("walk", "run") and self.jump_frames == 0:
            x += self.vx
            if x <= self.min_x:
                x, self.vx = self.min_x, abs(self.vx); self._face(1)
            elif x >= self.max_x:
                x, self.vx = self.max_x, -abs(self.vx); self._face(-1)
        y = self.base_y
        if self.jump_frames > 0:
            import math
            t = (self.jump_total - self.jump_frames) / self.jump_total
            y = self.base_y - int(math.sin(t * math.pi) * (self.view.height() * 0.30))
            self.jump_frames -= 1
        self.view.setPosition(int(x), int(y))


class _Voice(QObject):
    """Trò chuyện bằng giọng, RẢNH TAY.

    Luôn lắng nghe nền; khi nghe thấy tên gọi ("a lô Bia ...") thì thức dậy và
    thực thi. Vẫn giữ double-click/menu làm cách kích hoạt thủ công.

    Toàn bộ chạy trong thread nền; cập nhật GUI (bong bóng, trạng thái) qua
    signal (Qt tự đưa về luồng chính).
    """

    sig_bubble = Signal(str)
    sig_state = Signal(str)      # 'listen' | 'think' | 'talk' | 'idle'

    def __init__(self, cfg, controller: _AnimController, view: QQuickView, motion_getter):
        super().__init__()
        self.cfg = cfg
        self.ctrl = controller
        self.view = view
        self.motion_getter = motion_getter
        self.busy = False
        self._stt = None
        self._tts = None
        self._wake_stop = threading.Event()
        self.manual_event = threading.Event()
        self.wake_running = False
        self.sig_bubble.connect(self._on_bubble)
        self.sig_state.connect(self._on_state)

    # --- slot chạy ở luồng GUI ---
    def _on_bubble(self, text: str):
        root = self.view.rootObject()
        if root is not None:
            root.setProperty("bubbleText", text)

    def _on_state(self, state: str):
        motion = self.motion_getter()
        if state == "idle":
            if motion is not None:
                motion.set_paused(False)
        else:
            if motion is not None:
                motion.set_paused(True)
            self.ctrl.play_base("Idle")

    def _models_ready(self) -> bool:
        return self._stt is not None and self._tts is not None

    # --- nạp model (nặng) ở thread nền, xong thì bật nghe tên gọi ---
    def warmup(self):
        threading.Thread(target=self._warmup_job, daemon=True).start()

    def _warmup_job(self):
        try:
            self._ensure_models()
        except Exception as exc:   # noqa: BLE001
            self.sig_bubble.emit(f"Không tải được giọng nói: {exc}")
            return
        if getattr(self.cfg, "wake_enabled", True):
            self._start_wake_loop()

    def _ensure_models(self):
        if self._stt is None:
            from ..voice.stt import Stt
            self._stt = Stt(model_size=getattr(self.cfg, "whisper_model", "small"))
        if self._tts is None:
            from ..voice.tts import Tts
            self._tts = Tts(getattr(self.cfg, "piper_voice", ""))

    # --- vòng lặp nghe tên gọi (rảnh tay) ---
    def _start_wake_loop(self):
        if self.wake_running or not self._models_ready():
            return
        self._wake_stop.clear()
        self.manual_event.clear()
        self.wake_running = True
        threading.Thread(target=self._wake_loop, daemon=True).start()

    def stop_wake(self):
        self._wake_stop.set()

    def stop(self):
        self._wake_stop.set()

    def set_wake_enabled(self, value: bool):
        self.cfg.wake_enabled = bool(value)
        try:
            self.cfg.save()
        except Exception:   # noqa: BLE001
            pass
        if value:
            self._start_wake_loop()
        else:
            self.stop_wake()

    def _wake_loop(self):
        from ..voice.wake import detect_wake
        names = tuple(getattr(self.cfg, "wake_words", ["bia"]) or ["bia"])
        thr = float(getattr(self.cfg, "wake_threshold", 0.02))
        try:
            while not self._wake_stop.is_set():
                try:
                    status, audio = self._stt.wait_for_utterance(
                        self._wake_stop, self.manual_event, threshold=thr)
                except Exception as exc:   # noqa: BLE001
                    self.sig_bubble.emit(f"Lỗi mic: {exc}")
                    break
                if status == "stop":
                    break
                if status == "manual":
                    self.manual_event.clear()
                    self._handle("", manual=True)
                    continue
                transcript = self._stt.transcribe(audio)
                if not transcript:
                    continue
                woke, command = detect_wake(transcript, names)
                if not woke:
                    continue
                self._handle(command)
        finally:
            self.wake_running = False

    # --- kích hoạt thủ công (double-click / menu) ---
    def start(self):
        if not self._models_ready():
            self.sig_bubble.emit("Đợi mình chút, đang tải giọng nói...")
            return
        if self.wake_running:
            self.manual_event.set()          # để vòng lặp nghe xử lý
        elif not self.busy:
            threading.Thread(target=lambda: self._handle("", manual=True),
                             daemon=True).start()

    # --- một lượt hội thoại ---
    def _handle(self, command: str, manual: bool = False):
        if self.busy:
            return
        self.busy = True
        try:
            self._converse(command, manual)
        except Exception as exc:   # noqa: BLE001
            self.sig_bubble.emit(f"Lỗi giọng nói: {exc}")
        finally:
            self.sig_state.emit("idle")
            time.sleep(1.5)                  # giữ kết quả để đọc, tránh nghe lại đuôi câu
            self.sig_bubble.emit("")
            self.busy = False

    def _play_anim(self, name: str):
        """Cho mascot diễn một động tác (gọi an toàn từ thread nền qua QTimer)."""
        if not name:
            return
        QTimer.singleShot(0, lambda: self.ctrl.play_action(name))

    def _converse(self, command: str, manual: bool):
        from .. import memory
        from ..confirm import is_affirmative
        from ..executor import execute
        from ..intents import CHAT, UNKNOWN
        from ..llm import parse_intent

        self._ensure_models()
        text = (command or "").strip()

        # Gọi tên nhưng chưa kèm lệnh (hoặc bấm thủ công) -> hỏi rồi nghe lệnh
        if not text:
            self.sig_state.emit("talk")
            self.sig_bubble.emit("Dạ, bạn cần gì?")
            self._tts.speak("Dạ, bạn cần gì?")
            time.sleep(0.25)
            self.sig_state.emit("listen")
            self.sig_bubble.emit("🎤 Đang nghe...")
            text = self._stt.listen(max_seconds=8.0)

        if not text:
            self.sig_state.emit("talk")
            self.sig_bubble.emit("Mình không nghe rõ 😅")
            self._tts.speak("Mình không nghe rõ, bạn nói lại nhé")
            return

        self.sig_bubble.emit("Bạn: " + text)
        self.sig_state.emit("think")
        context = memory.build_context(text, self.cfg)
        intent = parse_intent(text, self.cfg, context)

        # 1) Chỉ trò chuyện -> nói câu trả lời (vẫy tay nếu là lời chào)
        if intent.action in (CHAT, UNKNOWN):
            answer = intent.reply or "..."
            low = text.lower()
            if any(w in low for w in _GREETING_WORDS):
                self._play_anim("Wave")
            self.sig_state.emit("talk")
            self.sig_bubble.emit(answer)
            self._tts.speak(answer)
            memory.add_interaction(text, intent.action, intent.target, self.cfg)
            memory.learn_async(text, self.cfg, intent.action, intent.target, answer)
            return

        # 2) Chỉ đọc thông tin (giờ/ngày, tin tức...) -> làm ngay rồi đọc kết quả
        if not intent.needs_confirmation:
            if intent.reply:
                self.sig_state.emit("talk")
                self.sig_bubble.emit(intent.reply)
                self._tts.speak(intent.reply)
            self.sig_state.emit("think")
            self.sig_bubble.emit("⏳ Để mình xem nhé...")
            self._play_anim(_ACTION_ANIM.get(intent.action))   # diễn động tác
            result = execute(intent, self.cfg)
            self.sig_state.emit("talk")
            self.sig_bubble.emit(result)
            self._tts.speak(result)
            memory.add_interaction(text, intent.action, intent.target, self.cfg)
            memory.learn_async(text, self.cfg, intent.action, intent.target, result)
            return

        # 3) Hành động thay đổi máy -> xác nhận trước
        self.sig_state.emit("talk")
        self.sig_bubble.emit(intent.reply or "...")
        self._tts.speak(intent.reply or "")
        time.sleep(0.25)
        self.sig_state.emit("listen")
        self.sig_bubble.emit("🎤 (nói 'có' hoặc 'không')")
        answer = self._stt.listen(max_seconds=5.0)
        if is_affirmative(answer):
            self._play_anim("Yes")                             # gật đầu đồng ý
            self.sig_state.emit("think")
            self._play_anim(_ACTION_ANIM.get(intent.action))   # rồi diễn động tác
            result = execute(intent, self.cfg)
            self.sig_state.emit("talk")
            self.sig_bubble.emit(result)
            self._tts.speak(result)
            memory.add_interaction(text, intent.action, intent.target, self.cfg)
            memory.record_feedback(intent.action, intent.target, True)
            memory.learn_async(text, self.cfg, intent.action, intent.target, result)
        else:
            self._play_anim("No")                              # lắc đầu
            self.sig_state.emit("talk")
            self.sig_bubble.emit("Ok, mình không làm nữa.")
            self._tts.speak("Được, mình không làm nữa")
            memory.record_feedback(intent.action, intent.target, False)


def run(cfg) -> None:
    model_qml = os.path.expanduser(getattr(cfg, "mascot_qml", "") or "")

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    view = QQuickView()
    view.setColor(Qt.transparent)
    view.setFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    side = int(getattr(cfg, "mascot_size", 120) or 120)
    view.resize(side * 2, int(side * 2.6))

    controller = _AnimController()
    bridge = _Bridge(view, controller)
    ctx = view.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("modelQmlUrl", QUrl.fromLocalFile(model_qml))
    ctx.setContextProperty("camY", float(getattr(cfg, "mascot_cam_y", 1.8)))
    ctx.setContextProperty("camZ", float(getattr(cfg, "mascot_cam_z", 11.0)))
    view.setSource(QUrl.fromLocalFile(_QML))

    if view.status() == QQuickView.Error:
        for err in view.errors():
            print("QML error:", err.toString())
        sys.exit(2)

    view.show()

    # Loader3D nạp bất đồng bộ -> thử tìm Timeline vài lần cho tới khi có
    holder = {"motion": None, "tries": 0}

    # Giọng nói: double-click hoặc menu -> nghe/nói
    voice = _Voice(cfg, controller, view, lambda: holder.get("motion"))
    bridge.voice = voice
    if os.path.exists(os.path.expanduser(getattr(cfg, "piper_voice", "") or "")):
        voice.warmup()               # nạp STT/TTS ở nền để lần đầu bớt trễ

    def try_bind():
        root = view.rootObject()
        count = controller.bind(root)
        holder["tries"] += 1
        if count == 0 and holder["tries"] < 25:
            QTimer.singleShot(200, try_bind)
            return
        print(f"[mascot] tìm thấy {count} động tác")
        pivot = root.findChild(QObject, "modelPivot")
        controller.play_action("Wave")     # vẫy tay chào khi mới mở
        holder["motion"] = _Motion(view, bridge, controller, pivot)

        # Bong bóng chào + hướng dẫn gọi tên
        name = getattr(cfg, "assistant_name", "Bia")
        has_voice = os.path.exists(os.path.expanduser(getattr(cfg, "piper_voice", "") or ""))
        if has_voice and getattr(cfg, "wake_enabled", True):
            greet = f"Chào, mình là {name}! Gọi \"a lô {name}\" để nhờ mình nhé 👋"
        else:
            greet = f"Chào, mình là {name}! Double-click để nói chuyện 👋"
        root.setProperty("bubbleText", greet)
        QTimer.singleShot(
            6000,
            lambda: root.setProperty("bubbleText", "") if not voice.busy else None)

    QTimer.singleShot(300, try_bind)

    app.aboutToQuit.connect(voice.stop)   # dừng vòng lặp nghe khi thoát

    # giữ tham chiếu tránh bị dọn rác
    view._bridge = bridge
    view._controller = controller
    view._holder = holder
    view._voice = voice

    sys.exit(app.exec())
