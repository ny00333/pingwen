"""主窗口右下角的大肥鱼形象。

交互参考 dsh-whale-widget-plus：
- 按下时底部坐标不变、整体 Q 弹压扁，松开回弹；
- 按下即触发音效（pressed 信号），点击后换「数钱」表情；
- 悬停 / 按压有柔和高亮，形象与音效路径可由 skin.json 的 mascot 段替换。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class WhaleMascot(QWidget):
    clicked = Signal()  # 左键点击完成（松开且仍在形象内）
    pressed = Signal()  # 左键按下，用于播放 GitHub 原版按压音效
    released = Signal()  # 左键松开，用于播放 GitHub 原版松开音效

    PRESS_SCALE = 0.90  # 按下压扁比例
    HOVER_SCALE = 1.04  # 悬停轻微放大

    def __init__(
        self,
        idle_image: str | Path,
        react_image: str | Path | None = None,
        size: int = 78,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("Mascot")
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._size = size
        self._idle = QPixmap(str(idle_image))
        self._react = QPixmap(str(react_image)) if react_image else QPixmap()
        self._scale = 1.0
        self._reaction_until = 0.0
        self._pressed = False
        self._hovered = False

        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_scale)

        self._reaction_timer = QTimer(self)
        self._reaction_timer.setSingleShot(True)
        self._reaction_timer.timeout.connect(self.update)

    # ---------------- 缩放动画 ----------------
    def _on_scale(self, value) -> None:
        self._scale = float(value)
        self.update()

    def _animate(self, end: float, duration: int, easing: QEasingCurve.Type) -> None:
        self._anim.stop()
        self._anim.setEasingCurve(easing)
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._scale)
        self._anim.setEndValue(float(end))
        self._anim.start()

    def set_images(
        self,
        idle_image: str | Path,
        react_image: str | Path | None = None,
        size: int | None = None,
    ) -> None:
        """替换形象素材（由 skin.json 的 mascot 段驱动）。"""
        self._idle = QPixmap(str(idle_image))
        self._react = QPixmap(str(react_image)) if react_image else QPixmap()
        self._reaction_until = 0.0
        if size and int(size) != self._size:
            self._size = max(48, int(size))
            self.setFixedSize(self._size, self._size)
        self.update()

    def flash_reaction(self, ms: int = 2600) -> None:
        """点击后短暂换成「数钱」表情，再回到常态。"""
        if self._react.isNull():
            return
        self._reaction_until = time.monotonic() + ms / 1000.0
        self.update()
        self._reaction_timer.start(ms + 40)

    def _current(self) -> QPixmap:
        if self._react.isNull() or time.monotonic() >= self._reaction_until:
            return self._idle
        return self._react

    # ---------------- 绘制 ----------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._pressed or self._hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 40 if self._pressed else 22))
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

        pixmap = self._current()
        if pixmap.isNull():
            return
        side = max(1, int(self._size * self._scale))
        drawn = pixmap.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 底部锚定：缩放时脚底位置不变，避免整只鱼上下跳动
        target = QRectF(
            (self._size - drawn.width()) / 2,
            self._size - drawn.height(),
            drawn.width(),
            drawn.height(),
        )
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(target, drawn, QRectF(drawn.rect()))

    # ---------------- 交互 ----------------
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        if not self._pressed:
            self._animate(self.HOVER_SCALE, 140, QEasingCurve.OutQuad)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        if not self._pressed:
            self._animate(1.0, 160, QEasingCurve.OutQuad)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            self._animate(self.PRESS_SCALE, 90, QEasingCurve.OutQuad)
            self.pressed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            inside = self.rect().contains(event.position().toPoint())
            self._pressed = False
            self.update()
            self.released.emit()
            if inside:
                self._animate(
                    self.HOVER_SCALE if self._hovered else 1.0,
                    380,
                    QEasingCurve.OutElastic,
                )
                self.clicked.emit()
            else:
                self._animate(1.0, 160, QEasingCurve.OutQuad)
            event.accept()
            return
        super().mouseReleaseEvent(event)
