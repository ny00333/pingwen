"""桌面像素形象：主窗口收起后的小悬浮窗。

素材与帧表来自 floating-pet-kit（精灵表 1536×3120，8 列 × 15 行，单元 192×208）。
按原 kit 的手法：180ms 逐帧、0.5 倍呈现（96×104）、像素化绘制、悬停挥手、
待机随机小动作，以及作答中的 analyzing / 完成 celebrating / 出错 failed 状态。
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QWidget

FRAMES: dict[str, list[tuple[int, int]]] = {
    "idle": [(0, i) for i in range(6)],
    "running-right": [(1, i) for i in range(8)],
    "running-left": [(2, i) for i in range(8)],
    "waving": [(3, i) for i in range(4)],
    "jumping": [(4, i) for i in range(5)],
    "failed": [(5, i) for i in range(8)],
    "waiting": [(6, i) for i in range(6)],
    "running": [(7, i) for i in range(6)],
    "review": [(8, i) for i in range(6)],
    "chatting": [(9, i) for i in range(8)],
    "fetching": [(10, i) for i in range(8)],
    "searching": [(11, i) for i in range(8)],
    "analyzing": [(12, i) for i in range(8)],
    "building": [(13, i) for i in range(8)],
    "celebrating": [(14, i) for i in range(8)],
}

CELL_W, CELL_H = 192, 208  # 精灵表单元尺寸
DRAW_W, DRAW_H = 96, 104  # 0.5 倍呈现尺寸
PAD = 8

SHEET_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "aemeath" / "spritesheet.webp"


class PetWindow(QWidget):
    """无边框透明小窗口，只画一只会动的像素精灵。"""

    clicked = Signal()  # 左键单击：展开主窗口
    moved = Signal()  # 拖动后位置变化
    request_region = Signal()
    request_answer = Signal()
    request_quit = Signal()

    def __init__(self) -> None:
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(DRAW_W + PAD * 2, DRAW_H + PAD * 2)
        self.setToolTip("点击展开主窗口 · 拖动移动")

        self._sheet = QPixmap(str(SHEET_PATH))
        self._state = "idle"
        self._frame = 0
        self._hold_until = 0.0
        self._press_global = None
        self._press_pos = None
        self._dragged = False

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(180)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        self._antics_timer = QTimer(self)
        self._antics_timer.setSingleShot(True)
        self._antics_timer.timeout.connect(self._play_antics)
        self._schedule_antics()

    # ---------------- 动画状态 ----------------
    def set_state(self, name: str, hold_ms: int = 0) -> None:
        """切换动作；hold_ms > 0 时到点自动回到 idle。"""
        if name not in FRAMES:
            return
        if name == self._state and not hold_ms:
            return
        self._state = name
        self._frame = 0
        self._hold_until = (
            time.monotonic() + hold_ms / 1000.0 if hold_ms else 0.0
        )
        self._schedule_antics()
        self.update()

    def _on_tick(self) -> None:
        self._frame += 1
        if self._hold_until and time.monotonic() >= self._hold_until:
            self._hold_until = 0.0
            self._state = "idle"
            self._frame = 0
            self._schedule_antics()
        self.update()

    def _schedule_antics(self) -> None:
        if not self._antics_timer.isActive():
            self._antics_timer.start(random.randint(12000, 38000))

    def _play_antics(self) -> None:
        if self._state == "idle" and not self._hold_until:
            self.set_state(random.choice(("waving", "jumping", "chatting")), 2200)
        self._schedule_antics()

    # ---------------- 绘制 ----------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        target = QRect(PAD, PAD, DRAW_W, DRAW_H)
        if self._sheet.isNull():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#23262f"))
            painter.drawRoundedRect(target, 10, 10)
            painter.setPen(QColor("#6e9bff"))
            painter.setFont(QFont("Microsoft YaHei UI", 22, QFont.Bold))
            painter.drawText(target, Qt.AlignCenter, "问")
            return
        frames = FRAMES.get(self._state, FRAMES["idle"])
        row, col = frames[self._frame % len(frames)]
        source = QRect(col * CELL_W, row * CELL_H, CELL_W, CELL_H)
        painter.drawPixmap(target, self._sheet, source)

    # ---------------- 交互 ----------------
    def enterEvent(self, event) -> None:  # noqa: N802
        if self._state == "idle" and not self._hold_until:
            self.set_state("waving", 1600)
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = self.pos()
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_global is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragged and delta.manhattanLength() > 4:
                self._dragged = True
            self.move(self._press_pos + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._press_global is not None:
            was_drag = self._dragged
            self._press_global = None
            self._press_pos = None
            self._dragged = False
            if not was_drag:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        open_action = menu.addAction("展开主窗口")
        answer_action = menu.addAction("识别并作答")
        region_action = menu.addAction("重新框选区域")
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        open_action.triggered.connect(lambda: self.clicked.emit())
        answer_action.triggered.connect(lambda: self.request_answer.emit())
        region_action.triggered.connect(lambda: self.request_region.emit())
        quit_action.triggered.connect(lambda: self.request_quit.emit())
        menu.exec(event.globalPosition().toPoint())

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self.moved.emit()


class CostBubble(QWidget):
    """形象头顶的费用气泡：参考小鲸鱼挂件的「每轮消耗提示」。

    深色圆角气泡 + 尖角指向形象，显示本次和今日花费，6 秒后自动关闭，点击可立即关闭。
    """

    ARROW = 8
    PAD_X = 11
    PAD_Y = 8
    MAX_TEXT_WIDTH = 230

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._anchor: QWidget | None = None
        self._text = ""
        self._font = QFont("Microsoft YaHei UI", 10)
        self._font.setBold(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        # 「啵」地一下淡入，避免气泡生硬地突然出现
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(150)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(
            lambda value: self.setWindowOpacity(float(value))
        )

    def show_for(self, pet: PetWindow, text: str, close_ms: int = 6000) -> None:
        self.show_near(pet, text, close_ms)

    def show_near(self, anchor: QWidget, text: str, close_ms: int = 6000) -> None:
        """在任意控件正上方弹出气泡（主窗口里的形象、收起后的形象都适用）。"""
        self._anchor = anchor
        self._set_text(text)
        self.reposition()
        self._fade.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(close_ms)

    def _set_text(self, text: str) -> None:
        self._text = text
        metrics = QFontMetrics(self._font)
        bounds = metrics.boundingRect(
            QRect(0, 0, self.MAX_TEXT_WIDTH, 1000),
            Qt.TextWordWrap | Qt.AlignCenter,
            text,
        )
        width = min(self.MAX_TEXT_WIDTH, bounds.width()) + self.PAD_X * 2
        height = bounds.height() + self.PAD_Y * 2 + self.ARROW
        self.setFixedSize(int(width), int(height))

    def reposition(self) -> None:
        anchor = self._anchor
        if anchor is None:
            return
        origin = anchor.mapToGlobal(QPoint(0, 0))
        x = origin.x() + anchor.width() // 2 - self.width() // 2
        y = origin.y() - self.height() - 2
        screen = anchor.screen()
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
            y = max(area.top() + 4, y)
        self.move(x, y)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(1, 1, self.width() - 2, self.height() - self.ARROW - 2)
        path = QPainterPath()
        path.addRoundedRect(body, 10, 10)
        cx = self.width() / 2
        arrow = QPainterPath()
        arrow.moveTo(cx - 6, body.bottom() - 1)
        arrow.lineTo(cx, self.height() - 1)
        arrow.lineTo(cx + 6, body.bottom() - 1)
        arrow.closeSubpath()
        path = path.united(arrow)
        painter.setPen(QPen(QColor(244, 114, 182, 160), 1))
        painter.setBrush(QColor(18, 21, 28, 244))
        painter.drawPath(path)
        painter.setPen(QColor("#f6f8ff"))
        painter.setFont(self._font)
        painter.drawText(
            body.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y),
            Qt.AlignCenter,
            self._text,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.hide()
        event.accept()

