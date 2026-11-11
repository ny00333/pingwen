"""屏幕区域选择遮罩。

确认后遮罩立即销毁，不在桌面上留下任何常驻窗口，因此不会遮挡屏幕内容；
再次点击悬浮窗的「区域」按钮才会重新出现。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

MIN_SIZE = 10


class RegionPicker(QWidget):
    selected = Signal(object)  # QRect，全局逻辑坐标
    canceled = Signal()

    def __init__(self, screen, initial: QRect | None = None, skin_qss: str = "", accent: str = "#6e9bff"):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setStyleSheet(skin_qss)
        self.setGeometry(screen.geometry())

        self._screen = screen
        self._geo = screen.geometry()
        self._accent = QColor(accent)
        self._background = screen.grabWindow(0)
        self._origin: QPoint | None = None
        self._selection = QRect()
        self._confirmed = False

        self._bar = QFrame(self)
        self._bar.setObjectName("ActionBar")
        bar_layout = QHBoxLayout(self._bar)
        bar_layout.setContentsMargins(10, 6, 10, 6)
        bar_layout.setSpacing(8)
        self._size_label = QLabel("")
        self._size_label.setObjectName("Hint")
        bar_layout.addWidget(self._size_label)
        confirm = QPushButton("确定")
        confirm.setProperty("kind", "primary")
        confirm.setCursor(Qt.PointingHandCursor)
        confirm.clicked.connect(self._confirm)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self._cancel)
        bar_layout.addWidget(confirm)
        bar_layout.addWidget(cancel)
        self._bar.hide()

        if initial is not None and initial.width() >= MIN_SIZE:
            self._selection = QRect(
                initial.x() - self._geo.x(),
                initial.y() - self._geo.y(),
                initial.width(),
                initial.height(),
            ).intersected(self.rect())
            self._refresh_bar()

        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- 绘制 ----------
    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._background.isNull():
            painter.drawPixmap(self.rect(), self._background)

        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        if not self._selection.isNull():
            path.addRect(QRectF(self._selection))
        painter.fillPath(path, QColor(0, 0, 0, 118))

        if not self._selection.isNull():
            pen = QPen(self._accent, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._selection.adjusted(0, 0, -1, -1))

            # 四角控制点（视觉提示）
            painter.setBrush(self._accent)
            painter.setPen(Qt.NoPen)
            for point in (
                self._selection.topLeft(),
                self._selection.topRight(),
                self._selection.bottomLeft(),
                self._selection.bottomRight(),
            ):
                painter.drawRect(QRect(point.x() - 3, point.y() - 3, 6, 6))

        if self._selection.isNull():
            hint = "拖动鼠标框选题目区域  ·  Enter 确认  ·  Esc 取消"
            painter.setFont(QFont("Microsoft YaHei UI", 13))
            metrics = painter.fontMetrics()
            width = metrics.horizontalAdvance(hint) + 28
            rect = QRectF(
                (self.width() - width) / 2, 36, width, metrics.height() + 16
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(20, 22, 28, 220))
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QColor(233, 236, 244))
            painter.drawText(rect, Qt.AlignCenter, hint)

        painter.end()

    # ---------- 鼠标 ----------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, self._origin)
            self._bar.hide()
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._origin is not None:
            current = event.position().toPoint()
            self._selection = QRect(self._origin, current).normalized()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._origin is not None:
            self._origin = None
            if self._selection.width() >= MIN_SIZE and self._selection.height() >= MIN_SIZE:
                self._refresh_bar()
            else:
                self._selection = QRect()
                self._bar.hide()
            self.update()
            event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if not self._selection.isNull():
            self._confirm()

    # ---------- 键盘 ----------
    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()
        elif event.key() == Qt.Key_Escape:
            self._cancel()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.setFocus()

    # ---------- 操作 ----------
    def _refresh_bar(self):
        if self._selection.isNull():
            self._bar.hide()
            return
        self._size_label.setText(
            f"{self._selection.width()} × {self._selection.height()}"
        )
        self._bar.adjustSize()
        width, height = self._bar.width(), self._bar.height()
        x = self._selection.center().x() - width // 2
        y = self._selection.bottom() + 12
        if y + height > self.height() - 8:
            y = self._selection.top() - height - 12
        if y < 8:
            y = 8
        x = max(8, min(x, self.width() - width - 8))
        self._bar.move(x, y)
        self._bar.show()

    def _confirm(self):
        if self._selection.width() < MIN_SIZE or self._selection.height() < MIN_SIZE:
            return
        self._confirmed = True
        rect = QRect(
            self._selection.x() + self._geo.x(),
            self._selection.y() + self._geo.y(),
            self._selection.width(),
            self._selection.height(),
        )
        self.selected.emit(rect)
        self.close()

    def _cancel(self):
        self._confirmed = True
        self.canceled.emit()
        self.close()

    def closeEvent(self, event):  # noqa: N802
        if not self._confirmed:
            self._confirmed = True
            self.canceled.emit()
        super().closeEvent(event)
