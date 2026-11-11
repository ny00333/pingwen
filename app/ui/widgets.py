"""通用小控件：可拖动标题栏、圆角无边框窗口基类。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TitleBar(QWidget):
    """标题栏：左边头像 + 标题，右边可追加工具按钮；按住空白处可拖动窗口。"""

    def __init__(self, title: str, avatar_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 4)
        layout.setSpacing(8)

        self.avatar = QLabel(avatar_text)
        self.avatar.setObjectName("Avatar")
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setVisible(bool(avatar_text))
        self.avatar.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.avatar)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("Title")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(2)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.button_layout)

    def add_tool_button(self, text: str, tooltip: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("kind", "tool")
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        self.button_layout.addWidget(button)
        return button

    # 拖动窗口
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        event.accept()


class RoundedWindow(QWidget):
    """无边框、透明背景、圆角内容区的窗口基类。"""

    def __init__(self, flags=None, parent=None):
        super().__init__(parent)
        base_flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if flags is not None:
            base_flags |= flags
        self.setWindowFlags(base_flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(0)

        self.root = QFrame()
        self.root.setObjectName("Root")
        self.outer.addWidget(self.root)

    def content_layout(self) -> QVBoxLayout:
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(8)
        return layout
