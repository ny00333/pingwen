"""设置对话框：AI 接口、模型选择、识别模式、答题风格与外观。"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from app.core.models import (
    PROVIDERS,
    models_for_provider,
    provider_by_id,
    provider_by_url,
)
from app.ui.model_menu import ModelPicker, ask_model_name
from app.ui.skin import list_skins, load_skin
from app.ui.widgets import TitleBar

MODES = [
    ("OCR 文字识别（省流量，推荐）", "ocr"),
    ("视觉模式（截图直传多模态模型）", "vision"),
]

STYLES = [
    ("简洁：答案 + 关键步骤", "concise"),
    ("详细：完整解析 + 易错点", "detailed"),
]


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = copy.deepcopy(config)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setStyleSheet(load_skin(self._config.get("skin", "default")).qss)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("Root")
        outer.addWidget(root)

        content = QVBoxLayout(root)
        content.setContentsMargins(12, 8, 12, 10)
        content.setSpacing(10)

        bar = TitleBar("设置", "⚙")
        bar.add_tool_button("×", "关闭", self.reject)
        content.addWidget(bar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        content.addLayout(grid)

        api = self._config.get("api", {})
        row = 0

        self.preset = QComboBox()
        for provider in PROVIDERS:
            self.preset.addItem(provider["name"], provider["id"])
        grid.addWidget(QLabel("AI 预设"), row, 0)
        grid.addWidget(self.preset, row, 1)
        row += 1

        self.base_url = QLineEdit(str(api.get("base_url", "")))
        self.base_url.setPlaceholderText("https://api.deepseek.com/v1")
        grid.addWidget(QLabel("接口地址"), row, 0)
        grid.addWidget(self.base_url, row, 1)
        row += 1

        self.api_key = QLineEdit(str(api.get("api_key", "")))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-…（本地模型可留空）")
        grid.addWidget(QLabel("API Key"), row, 0)
        grid.addWidget(self.api_key, row, 1)
        row += 1

        self.model_picker = ModelPicker()
        grid.addWidget(QLabel("模型"), row, 0)
        grid.addWidget(self.model_picker, row, 1)
        row += 1

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(float(api.get("temperature", 0.2)))
        grid.addWidget(QLabel("采样温度"), row, 0)
        grid.addWidget(self.temperature, row, 1)
        row += 1

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 8192)
        self.max_tokens.setSingleStep(256)
        self.max_tokens.setValue(int(api.get("max_tokens", 2048)))
        grid.addWidget(QLabel("最大输出 token"), row, 0)
        grid.addWidget(self.max_tokens, row, 1)
        row += 1

        self.mode = QComboBox()
        for text, value in MODES:
            self.mode.addItem(text, value)
        self._select_data(self.mode, self._config.get("mode", "ocr"))
        grid.addWidget(QLabel("识别方式"), row, 0)
        grid.addWidget(self.mode, row, 1)
        row += 1

        self.style = QComboBox()
        for text, value in STYLES:
            self.style.addItem(text, value)
        self._select_data(self.style, self._config.get("prompt_style", "concise"))
        grid.addWidget(QLabel("答题风格"), row, 0)
        grid.addWidget(self.style, row, 1)
        row += 1

        self.skin = QComboBox()
        for skin_id, display in list_skins():
            self.skin.addItem(display, skin_id)
        self._select_data(self.skin, self._config.get("skin", "default"))
        self.skin.currentIndexChanged.connect(
            lambda _: self.setStyleSheet(
                load_skin(self.skin.currentData() or "default").qss
            )
        )
        grid.addWidget(QLabel("悬浮窗皮肤"), row, 0)
        grid.addWidget(self.skin, row, 1)
        row += 1

        opacity_row = QHBoxLayout()
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(60, 100)
        self.opacity.setValue(int(float(self._config.get("opacity", 1.0)) * 100))
        self.opacity_value = QLabel(f"{self.opacity.value()}%")
        self.opacity.valueChanged.connect(
            lambda value: self.opacity_value.setText(f"{value}%")
        )
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_value)
        grid.addWidget(QLabel("窗口不透明度"), row, 0)
        grid.addLayout(opacity_row, row, 1)
        row += 1

        window = self._config.get("window") or {}
        self.window_width = QSpinBox()
        self.window_width.setRange(380, 900)
        self.window_width.setSingleStep(20)
        self.window_width.setSuffix(" px")
        self.window_width.setValue(int(window.get("w") or 465))
        self.window_height = QSpinBox()
        self.window_height.setRange(500, 1000)
        self.window_height.setSingleStep(20)
        self.window_height.setSuffix(" px")
        self.window_height.setValue(int(window.get("h") or 660))
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        size_row.addWidget(self.window_width, 1)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.window_height, 1)
        grid.addWidget(QLabel("窗口大小"), row, 0)
        grid.addLayout(size_row, row, 1)
        row += 1

        hint = QLabel(
            "模型列表里标注的是固定收费比例（1.00x = ¥10 / 百万 tokens 的参考基准），"
            "由程序内置、不能修改；视觉模式需选择标注「视觉」的模型。"
            "窗口大小保存后立即生效，超出屏幕时会自动收进屏幕范围。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        content.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setProperty("kind", "primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        content.addLayout(buttons)

        self.base_url.setMinimumWidth(300)
        self.api_key.setMinimumWidth(300)

        self.resize(600, 680)
        self._center_on_screen()
        self._load_from_config(api)
        self.preset.currentIndexChanged.connect(self._on_preset_changed)
        self.model_picker.model_selected.connect(self._on_model_selected)
        self.model_picker.add_requested.connect(self._add_model)

    @staticmethod
    def _select_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _center_on_screen(self) -> None:
        screen = None
        if self.parent() is not None:
            screen = self.parent().screen()
        screen = screen or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.center().y() - self.height() // 2,
        )

    # ---------------- 模型列表（固定收费比例） ----------------
    def _load_from_config(self, api: dict) -> None:
        provider = provider_by_url(str(api.get("base_url", "")))
        if provider is None:
            provider = provider_by_id("qianwen")
        self._model_id = str(api.get("model", ""))
        preset_index = self.preset.findData(provider["id"])
        self.preset.setCurrentIndex(preset_index if preset_index >= 0 else 0)
        self._refresh_models(provider)

    def _refresh_models(self, provider: dict | None = None, preferred: str | None = None) -> None:
        provider = provider or provider_by_id(str(self.preset.currentData() or "qianwen"))
        extra = (self._config.get("api") or {}).get("extra_models") or []
        models = models_for_provider(provider, extra)
        ids = [model["id"] for model in models]
        if preferred and preferred in ids:
            self._model_id = preferred
        elif self._model_id not in ids and models:
            self._model_id = models[0]["id"]
        self.model_picker.set_models(models, self._model_id)

    def _selected_model(self) -> str:
        return self.model_picker.current_model() or self._model_id

    def _on_preset_changed(self, index: int) -> None:
        provider = provider_by_id(str(self.preset.currentData() or "qianwen"))
        if not provider:
            return
        if provider.get("base_url"):
            self.base_url.setText(provider["base_url"])
        models = provider.get("models") or []
        self._model_id = models[0]["id"] if models else ""
        self._refresh_models(provider)

    def _on_model_selected(self, model_id: str) -> None:
        self._model_id = model_id

    def _add_model(self) -> None:
        name = ask_model_name(self)
        if not name:
            return
        extra = self._config.setdefault("api", {}).setdefault("extra_models", [])
        known = [
            str(item.get("id") if isinstance(item, dict) else item) for item in extra
        ]
        if name not in known:
            extra.append({"id": name})
        self._refresh_models(preferred=name)
        self._model_id = name
        self.model_picker.set_current(name)

    def _save(self) -> None:
        api = self._config.setdefault("api", {})
        api["base_url"] = self.base_url.text().strip()
        api["api_key"] = self.api_key.text().strip()
        api["model"] = self._selected_model()
        api.pop("price_in", None)
        api.pop("price_out", None)
        api["temperature"] = float(self.temperature.value())
        api["max_tokens"] = int(self.max_tokens.value())
        self._config["mode"] = self.mode.currentData()
        self._config["prompt_style"] = self.style.currentData()
        self._config["skin"] = self.skin.currentData() or "default"
        self._config["opacity"] = self.opacity.value() / 100.0
        window = self._config.setdefault("window", {})
        window["w"] = int(self.window_width.value())
        window["h"] = int(self.window_height.value())
        self.accept()

    def result_config(self) -> dict:
        return self._config
