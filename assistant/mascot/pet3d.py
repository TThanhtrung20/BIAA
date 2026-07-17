"""Mascot 3D: hiển thị mô hình .glb trong cửa sổ trong suốt, nổi trên desktop.

Dùng QtQuick3D + RuntimeLoader (nạp .glb lúc chạy). Nhân vật:
- tự đi lại quanh màn hình và thỉnh thoảng nhảy (chuyển động cả thân),
- nhún nhảy + xoay nhẹ cho sinh động (làm ở QML),
- được tô màu bằng ánh sáng màu (mô hình không có texture).

Kéo bằng chuột trái để di chuyển, chuột phải để thoát.

Lưu ý: cần GPU/OpenGL (chạy trên màn hình thật). Mô hình này không có xương/
animation nên không thể cử động tay/chân riêng lẻ - đó là chuyển động cả thân.
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import sys

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QColor, QGuiApplication, QSurfaceFormat, QVector3D
from PySide6.QtQuick import QQuickView

_QML = os.path.join(os.path.dirname(__file__), "mascot3d.qml")


def read_glb_bounds(path: str) -> tuple[QVector3D, float]:
    """Đọc tâm và kích thước lớn nhất của mô hình từ accessor POSITION trong .glb.

    Trả về (center, max_dim). Nếu không đọc được -> (gốc toạ độ, 1.0).
    Dùng để căn camera chắc chắn thay vì chờ RuntimeLoader.bounds (nạp trễ).
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        off = 12
        clen, _ = struct.unpack_from("<II", data, off)
        off += 8
        gltf = json.loads(data[off:off + clen].decode("utf-8"))
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        for mesh in gltf.get("meshes", []):
            for prim in mesh.get("primitives", []):
                pos = prim.get("attributes", {}).get("POSITION")
                if pos is None:
                    continue
                acc = gltf["accessors"][pos]
                amn, amx = acc.get("min"), acc.get("max")
                if amn and amx:
                    for i in range(3):
                        lo[i] = min(lo[i], amn[i])
                        hi[i] = max(hi[i], amx[i])
        if hi[0] < lo[0]:
            return QVector3D(0, 0, 0), 1.0
        center = QVector3D((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        size = max(hi[i] - lo[i] for i in range(3)) or 1.0
        return center, float(size)
    except (OSError, ValueError, KeyError, struct.error):
        return QVector3D(0, 0, 0), 1.0


class _Bridge(QObject):
    """Cầu nối cho QML gọi ngược về Python (kéo cửa sổ / thoát)."""

    def __init__(self, view: QQuickView):
        super().__init__()
        self._view = view
        self.dragging = False

    @Slot(int, int)
    def move_by(self, dx: int, dy: int):
        self._view.setPosition(self._view.x() + dx, self._view.y() + dy)

    @Slot(bool)
    def set_dragging(self, value: bool):
        self.dragging = bool(value)

    @Slot()
    def quit(self):
        QGuiApplication.quit()


class _Motion(QObject):
    """Điều khiển nhân vật tự đi lại và nhảy quanh màn hình (di chuyển cửa sổ)."""

    def __init__(self, view: QQuickView, bridge: _Bridge):
        super().__init__()
        self.view = view
        self.bridge = bridge
        screen = view.screen().availableGeometry()
        self.min_x = screen.left() + 10
        self.max_x = screen.right() - view.width() - 10
        self.base_y = screen.bottom() - view.height() - 10
        self.vx = 2.5
        self.facing = 1
        self.walking = True
        self.jump_total = 18
        self.jump_left = 0

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(30)                 # ~33 khung/giây

        self._decide_timer = QTimer(self)
        self._decide_timer.timeout.connect(self._decide)
        self._decide_timer.start(2800)             # đổi hành vi mỗi 2.8s

    def _decide(self):
        if self.bridge.dragging:
            return
        r = random.random()
        if r < 0.42:                               # đi
            self.walking = True
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * random.uniform(2.0, 4.5)
        elif r < 0.6:                              # đứng nghỉ
            self.walking = False
        elif r < 0.85 and self.jump_left == 0:     # nhảy
            self.jump_left = self.jump_total

    def _tick(self):
        if self.bridge.dragging:
            return
        x = self.view.x()
        if self.walking:
            x += self.vx
            if x <= self.min_x:
                x, self.vx = self.min_x, abs(self.vx)
            elif x >= self.max_x:
                x, self.vx = self.max_x, -abs(self.vx)
        y = self.base_y
        if self.jump_left > 0:
            t = (self.jump_total - self.jump_left) / self.jump_total
            y = self.base_y - int(math.sin(t * math.pi) * (self.view.height() * 0.4))
            self.jump_left -= 1
        self.view.setPosition(int(x), int(y))


def run(cfg) -> None:
    model = os.path.expanduser(getattr(cfg, "mascot_model", "") or "")

    # Bật kênh alpha để nền trong suốt
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QGuiApplication(sys.argv)

    view = QQuickView()
    view.setColor(Qt.transparent)
    view.setFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    side = int(getattr(cfg, "mascot_size", 120) or 120) * 2
    view.resize(side, side)

    center, size = read_glb_bounds(model)
    color = QColor(getattr(cfg, "mascot_color", "") or "#4aa3ff")

    bridge = _Bridge(view)
    ctx = view.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("modelSource", QUrl.fromLocalFile(model))
    ctx.setContextProperty("modelCenter", center)
    ctx.setContextProperty("modelSize", size)
    ctx.setContextProperty("mascotColor", color)
    view.setSource(QUrl.fromLocalFile(_QML))

    if view.status() == QQuickView.Error:
        for err in view.errors():
            print("QML error:", err.toString())
        sys.exit(2)

    screen = app.primaryScreen().availableGeometry()
    view.setPosition(screen.right() - view.width() - 60,
                     screen.bottom() - view.height() - 60)
    view.show()

    # Bắt đầu cho nhân vật tự đi lại / nhảy (giữ tham chiếu để không bị dọn rác)
    view._motion = _Motion(view, bridge)

    sys.exit(app.exec())
