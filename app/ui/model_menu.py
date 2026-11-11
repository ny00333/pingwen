"""模型选择列表：仿参考截图的弹出菜单（模型名 + 固定收费比例 + 添加模型）。

收费比例来自 app.core.models 的固定目录，界面只展示、不允许修改。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ratio_text

ROW_HEIGHT = 44
MENU_WIDTH = 320
SCROLL_MAX = 330


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class ModelRow(QWidget):
    clicked = Signal(str)

    def __init__(self, model: dict, selected: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelRow")
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("selected", selected)
        self.setProperty("hover", False)
        self._model_id = str(model["id"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(10)

        icon = QLabel("◈")
        icon.setObjectName("ModelIcon")
        icon.setFixedWidth(18)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        name = QLabel(str(model.get("label") or model["id"]))
        name.setObjectName("ModelName")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(name, 1)

        ratio = QLabel(ratio_text(model))
        ratio.setObjectName("ModelRatio")
        ratio.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(ratio)

        detail = f"模型 {model['id']}\n输入 ¥{model['input']}/百万 · 输出 ¥{model['output']}/百万"
        if model.get("custom"):
            detail += "\n自定义添加：按固定 1.00x 参考计费"
        self.setToolTip(detail)

    def enterEvent(self, event):  # noqa: N802
        self.setProperty("hover", True)
        _repolish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self.setProperty("hover", False)
        _repolish(self)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._model_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ModelMenu(QWidget):
    """弹出式模型列表；点选条目或「添加模型」。"""

    model_selected = Signal(str)
    add_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(MENU_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("MenuPanel")
        outer.addWidget(panel)

        self._layout = QVBoxLayout(panel)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.viewport().setAutoFillBackground(False)
        self._layout.addWidget(self._scroll)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        self._scroll.setWidget(body)

        divider = QFrame()
        divider.setObjectName("MenuDivider")
        divider.setFixedHeight(1)
        self._layout.addWidget(divider)

        self._add_button = QPushButton("⚙   添加模型")
        self._add_button.setObjectName("AddModel")
        self._add_button.setFixedHeight(ROW_HEIGHT)
        self._add_button.setCursor(Qt.PointingHandCursor)
        self._add_button.setToolTip("输入 API 中的模型名；收费比例按固定 1.00x 参考值")
        self._add_button.clicked.connect(self._on_add)
        self._layout.addWidget(self._add_button)

    def set_models(self, models: list[dict], current: str = "") -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for model in models or []:
            row = ModelRow(model, selected=str(model["id"]) == str(current))
            row.clicked.connect(self._on_select)
            self._body_layout.addWidget(row)
        self._body_layout.addStretch(1)
        count = len(models or [])
        content = ROW_HEIGHT * count + 2 * max(0, count - 1) + 2
        self._scroll.setFixedHeight(min(max(content, ROW_HEIGHT), SCROLL_MAX))

    def _on_select(self, model_id: str) -> None:
        self.hide()
        self.model_selected.emit(model_id)

    def _on_add(self) -> None:
        self.hide()
        self.add_requested.emit()

    def popup_at(self, anchor: QWidget) -> None:
        self.adjustSize()
        screen = anchor.screen()
        area = screen.availableGeometry() if screen is not None else None
        below = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        above = anchor.mapToGlobal(QPoint(0, -self.height() - 6))
        x, y = below.x(), below.y()
        if area is not None:
            x = max(area.left() + 6, min(x, area.right() - self.width() - 6))
            if area.bottom() - 6 < y + self.height():
                y = max(area.top() + 6, above.y())
        self.move(x, y)
        self.show()
        self.raise_()


class ModelPicker(QPushButton):
    """显示当前模型与比例的按钮，点击弹出 ModelMenu。"""

    model_selected = Signal(str)
    add_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self.setToolTip("点击选择模型；比例由程序内置，不可修改")
        self._models: list[dict] = []
        self._current = ""
        self._menu: ModelMenu | None = None
        self.clicked.connect(lambda: self.show_menu())

    def set_models(self, models: list[dict], current: str | None = None) -> None:
        self._models = list(models or [])
        if current is not None:
            self._current = str(current or "")
        self._refresh_text()

    def set_current(self, model_id: str) -> None:
        self._current = str(model_id or "")
        self._refresh_text()

    def current_model(self) -> str:
        return self._current

    def _refresh_text(self) -> None:
        text = ""
        for model in self._models:
            if str(model["id"]) == self._current:
                text = f"{model.get('label') or model['id']}   {ratio_text(model)}  ▾"
                break
        if not text:
            text = f"{self._current or '选择模型'}   ▾"
        self.setText(text)

    def show_menu(self, anchor: QWidget | None = None) -> None:
        self._menu = ModelMenu(self)
        self._menu.set_models(self._models, self._current)
        self._menu.model_selected.connect(self._choose)
        self._menu.add_requested.connect(self.add_requested.emit)
        self._menu.popup_at(anchor or self)

    def _choose(self, model_id: str) -> None:
        self.set_current(model_id)
        self.model_selected.emit(model_id)


def ask_model_name(parent=None) -> str | None:
    """「添加模型」只要求填模型名，收费比例固定，避免用户自行改价。"""
    name, ok = QInputDialog.getText(
        parent,
        "添加模型",
        "输入 API 中的模型名（model id）：\n收费比例按固定 1.00x 参考值，不可修改。",
    )
    name = str(name or "").strip()
    if ok and name:
        return name
    return None
