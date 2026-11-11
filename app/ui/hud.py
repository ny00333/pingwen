"""悬浮窗主界面：实时预览选区画面 + 快速 AI 作答。"""
from __future__ import annotations

import copy
import random
import time
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QTextBrowser,
)

from app.config import ROOT, api_ready, save_config
from app.core.billing import (
    DEFAULT_BILLING,
    compute_cost,
    ensure_today,
    money,
    record_usage,
)
from app.core.capture import encode_png, grab_region, rect_from_dict, region_screen
from app.core.live import LiveCapture
from app.core.models import find_any_model, models_for_api, price_text, ratio_text, resolve_price
from app.core.sound import play_sound
from app.core.worker import AnswerWorker
from app.ui.mascot import WhaleMascot
from app.ui.model_menu import ModelPicker, ask_model_name
from app.ui.pet import CostBubble, PetWindow
from app.ui.region_picker import RegionPicker
from app.ui.settings_dialog import SettingsDialog
from app.ui.skin import load_skin
from app.ui.widgets import RoundedWindow, TitleBar

WHALE_IMAGE = Path(ROOT) / "assets" / "whale" / "dsniang.png"
WHALE_REACT_IMAGE = Path(ROOT) / "assets" / "whale" / "react_money.png"
# 按压 / 松开音效，直接使用 dsh-whale-widget-plus 的「小黄鸭」原文件，不做改动
PRESS_SOUND = Path(ROOT) / "assets" / "whale" / "Ya1.mp3"
RELEASE_SOUND = Path(ROOT) / "assets" / "whale" / "Ya2.mp3"

# 大肥鱼点击的最后一句随机台词；可在 skin.json 的 mascot.lines 里替换
DEFAULT_WHALE_LINES = [
    "大肥鱼在盯着钱包呢～",
    "点一下，鱼就少一口饭",
    "问答由我，省钱靠你",
    "又要问一道题了吗？",
    "今日份的 token 已记好账",
]

PLACEHOLDER = (
    "先点「区域」框选题目所在的位置，画面会在这里实时显示。\n\n"
    "点「识别并作答」即可直接使用最新画面作答，无需等待截图。"
)
PREVIEW_PLACEHOLDER = "选择区域后，这里会实时显示画面"


class HudWindow(RoundedWindow):
    def __init__(self, config: dict):
        super().__init__(Qt.Tool)
        self.config = config
        self._skin = load_skin(config.get("skin", "default"))
        self._worker: AnswerWorker | None = None
        self._picker: RegionPicker | None = None
        self._answer_text = ""
        self._recognized_text = ""
        self._auto = bool(config.get("auto_answer"))
        self._answer_only = bool(config.get("answer_only"))
        self._last_auto = 0.0
        self._preview_image: QImage | None = None
        self._last_cost: float | None = None
        self._last_usage: dict | None = None
        self._bubble_page = 0
        self._press_sound = PRESS_SOUND
        self._release_sound = RELEASE_SOUND
        self._bubble_close_ms = 6500
        self._bubble_lines = list(DEFAULT_WHALE_LINES)
        self._ready = False
        self._size_applied = False

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_answer)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._persist_window)

        self._build_ui()
        self._apply_skin(self._skin)
        self._restore_geometry()
        self._update_region_label()
        self._setup_pet()
        self._setup_live_capture()
        self._refresh_model_picker()
        self._update_cost_label()
        self._ready = True
        # 布局搭建完成后再次应用保存的尺寸：Qt 首次布局会把窗口撑到默认宽度，
        # 这里重新设回用户保存的宽高，避免「打开后突然变大」。
        QTimer.singleShot(0, self._apply_window_size)

    # ---------------- 界面搭建 ----------------
    def _build_ui(self) -> None:
        layout = self.content_layout()
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(8)

        self.title_bar = TitleBar("屏问", self._skin.avatar_text)
        self.title_bar.add_tool_button("区域", "框选/修改屏幕区域", self.pick_region)
        self.title_bar.add_tool_button("设置", "配置 AI 接口与外观", self.open_settings)
        self.title_bar.add_tool_button("—", "收起为桌面形象", self.minimize_to_pet)
        self.title_bar.add_tool_button("×", "退出程序", self.request_quit)
        layout.addWidget(self.title_bar)

        self.preview_label = QLabel(PREVIEW_PLACEHOLDER)
        self.preview_label.setObjectName("Preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedHeight(150)
        self.preview_label.setToolTip("实时显示选区画面（约 8 帧/秒）")
        layout.addWidget(self.preview_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.answer_button = QPushButton("识别并作答")
        self.answer_button.setProperty("kind", "primary")
        self.answer_button.setCursor(Qt.PointingHandCursor)
        self.answer_button.setMinimumHeight(40)
        self.answer_button.setToolTip("直接使用最新画面作答")
        self.answer_button.clicked.connect(lambda: self.start_answer())
        action_row.addWidget(self.answer_button, 1)

        self.answer_only_button = QPushButton()
        self.answer_only_button.setProperty("kind", "tool")
        self.answer_only_button.setCursor(Qt.PointingHandCursor)
        self.answer_only_button.setCheckable(True)
        self.answer_only_button.setChecked(self._answer_only)
        self.answer_only_button.setToolTip("开启后只输出最终答案，不写解析；作答更快、更省 token")
        self.answer_only_button.toggled.connect(self._on_answer_only_toggled)
        self._update_answer_only_text()
        action_row.addWidget(self.answer_only_button)

        self.auto_button = QPushButton()
        self.auto_button.setProperty("kind", "tool")
        self.auto_button.setCursor(Qt.PointingHandCursor)
        self.auto_button.setCheckable(True)
        self.auto_button.setChecked(self._auto)
        self.auto_button.setToolTip("画面变化时自动作答（间隔不少于 3 秒）")
        self.auto_button.toggled.connect(self._on_auto_toggled)
        self._update_auto_text()
        action_row.addWidget(self.auto_button)
        layout.addLayout(action_row)

        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        self.region_label = QLabel("")
        self.region_label.setObjectName("Hint")
        info_row.addWidget(self.region_label, 1)
        self.model_picker = ModelPicker()
        self.model_picker.setMinimumWidth(160)
        self.model_picker.model_selected.connect(self._on_model_selected)
        self.model_picker.add_requested.connect(self._add_model)
        info_row.addWidget(self.model_picker)
        self.copy_button = QPushButton("复制答案")
        self.copy_button.setProperty("kind", "tool")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(self.copy_answer)
        info_row.addWidget(self.copy_button)
        layout.addLayout(info_row)

        self.answer_view = QTextBrowser()
        self.answer_view.setObjectName("Answer")
        self.answer_view.setOpenExternalLinks(True)
        self.answer_view.setPlainText(PLACEHOLDER)
        layout.addWidget(self.answer_view, 1)

        self.cost_label = QLabel()
        self.cost_label.setObjectName("Cost")
        layout.addWidget(self.cost_label)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(4)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("Hint")
        bottom_row.addWidget(self.status_label, 1)

        self.mascot = WhaleMascot(WHALE_IMAGE, WHALE_REACT_IMAGE, size=78)
        self.mascot.setToolTip("大肥鱼 · 点一下看消耗，再点继续翻页")
        self.mascot.pressed.connect(lambda: play_sound(self._press_sound))
        self.mascot.released.connect(lambda: play_sound(self._release_sound))
        self.mascot.clicked.connect(self._on_mascot_clicked)
        bottom_row.addWidget(self.mascot, 0, Qt.AlignRight | Qt.AlignBottom)

        bottom_row.addWidget(QSizeGrip(self.root), 0, Qt.AlignRight | Qt.AlignBottom)
        layout.addLayout(bottom_row)

    def _skin_asset(self, value) -> Path | None:
        """解析皮肤里的素材路径：相对路径以皮肤目录为基准，找不到时回落到默认素材。"""
        text = str(value or "").strip()
        if not text:
            return None
        path = Path(text)
        if not path.is_absolute():
            path = (self._skin.directory / path).resolve()
        return path if path.exists() else None

    def _apply_mascot_skin(self, skin) -> None:
        """把 skin.json 的 mascot 段应用到右下角形象；缺省时使用内置素材。"""
        cfg = getattr(skin, "mascot", None) or {}
        self._press_sound = (
            self._skin_asset(cfg.get("press_sound"))
            or self._skin_asset(cfg.get("click_sound"))
            or PRESS_SOUND
        )
        self._release_sound = self._skin_asset(cfg.get("release_sound")) or RELEASE_SOUND
        self._bubble_close_ms = int(cfg.get("bubble_close_ms") or 6500)
        self._bubble_lines = [
            str(line) for line in (cfg.get("lines") or []) if str(line).strip()
        ] or DEFAULT_WHALE_LINES
        size = max(48, int(cfg.get("size") or 78))
        self.mascot.set_images(
            self._skin_asset(cfg.get("idle_image")) or WHALE_IMAGE,
            self._skin_asset(cfg.get("react_image")) or WHALE_REACT_IMAGE,
            size,
        )

    def _apply_skin(self, skin) -> None:
        self._skin = skin
        self.setStyleSheet(skin.qss)
        if getattr(self, "mascot", None) is not None:
            self._apply_mascot_skin(skin)
        self.title_bar.title_label.setText(getattr(skin, "title", "屏问") or "屏问")
        avatar = self.title_bar.avatar
        if skin.avatar_image and (skin.directory / skin.avatar_image).exists():
            pixmap = QPixmap(str(skin.directory / skin.avatar_image))
            if not pixmap.isNull():
                avatar.setPixmap(
                    pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                avatar.setText("")
                return
        avatar.clear()
        avatar.setText(skin.avatar_text)
        avatar.setVisible(bool(skin.avatar_text))
        self.setWindowOpacity(float(self.config.get("opacity", 1.0)))

    # ---------------- 模型选择（固定收费比例） ----------------
    def _refresh_model_picker(self) -> None:
        api = self.config.get("api") or {}
        self.model_picker.set_models(
            models_for_api(api), str(api.get("model") or "")
        )

    def _on_model_selected(self, model_id: str) -> None:
        api = self.config.setdefault("api", {})
        api["model"] = model_id
        save_config(self.config)
        self._update_cost_label()
        self._set_status(f"模型已切换：{model_id}")

    def _add_model(self) -> None:
        name = ask_model_name(self)
        if not name:
            return
        api = self.config.setdefault("api", {})
        extra = api.setdefault("extra_models", [])
        known = [
            str(item.get("id") if isinstance(item, dict) else item) for item in extra
        ]
        if name not in known:
            extra.append({"id": name})
        api["model"] = name
        save_config(self.config)
        self._refresh_model_picker()
        self._update_cost_label()
        self._set_status(f"已添加模型：{name}")

    # ---------------- 收起后的桌面形象 ----------------
    def _setup_pet(self) -> None:
        self._pet = PetWindow()
        self._pet.clicked.connect(self.restore_from_pet)
        self._pet.request_region.connect(self.pick_region)
        self._pet.request_answer.connect(lambda: self.start_answer())
        self._pet.request_quit.connect(self.request_quit)
        self._pet.moved.connect(self._on_pet_moved)

        self._pet_save_timer = QTimer(self)
        self._pet_save_timer.setSingleShot(True)
        self._pet_save_timer.timeout.connect(self._persist_pet)

        self._cost_bubble = CostBubble()
        self._restore_pet_geometry()

    def _restore_pet_geometry(self) -> None:
        pet_cfg = self.config.get("pet") or {}
        width, height = self._pet.width(), self._pet.height()
        x, y = pet_cfg.get("x"), pet_cfg.get("y")
        area = QGuiApplication.primaryScreen().availableGeometry()
        if x is None or y is None:
            x = area.right() - width - 24
            y = area.bottom() - height - 24
        screen = QGuiApplication.screenAt(QRect(x, y, width, height).center())
        if screen is not None:
            area = screen.availableGeometry()
        x = max(area.left(), min(int(x), area.right() - width))
        y = max(area.top(), min(int(y), area.bottom() - height))
        self._pet.move(x, y)

    def minimize_to_pet(self) -> None:
        """收起主窗口，只留桌面上的小形象，避免「隐藏后找不到」。"""
        self._cost_bubble.hide()
        self._pet.show()
        self._pet.raise_()
        self.hide()
        self._set_status("已收起到桌面形象，点击形象可展开")

    def restore_from_pet(self) -> None:
        self._cost_bubble.hide()
        self._pet.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_pet_moved(self) -> None:
        if self._cost_bubble.isVisible():
            self._cost_bubble.reposition()
        if self._ready:
            self._pet_save_timer.start(800)

    def _persist_pet(self) -> None:
        self.config["pet"] = {"x": self._pet.x(), "y": self._pet.y()}
        save_config(self.config)

    # ---------------- token 计费 ----------------
    def _billing(self) -> dict:
        billing = self.config.setdefault("billing", copy.deepcopy(DEFAULT_BILLING))
        for key, value in DEFAULT_BILLING.items():
            billing.setdefault(key, value)
        ensure_today(billing)
        return billing

    def _update_cost_label(
        self, last_cost: float | None = None, usage: dict | None = None
    ) -> None:
        if last_cost is not None:
            self._last_cost = last_cost
        if usage:
            self._last_usage = usage
        billing = self._billing()
        last = money(last_cost) if last_cost is not None else "--"
        text = f"本次 {last} · 今日 {money(billing['today'])} · 累计 {money(billing['total'])}"
        if usage:
            text += (
                f" · 输入 {int(usage.get('prompt_tokens', 0)):,}"
                f" / 输出 {int(usage.get('completion_tokens', 0)):,} tokens"
            )
            if usage.get("estimated"):
                text += "（估算）"
        self.cost_label.setText(text)

        api = self.config.get("api") or {}
        price_in, price_out, known = resolve_price(api)
        model = find_any_model(api, str(api.get("model") or ""))
        ratio = ratio_text(model) if model is not None else "1.00x"
        if known:
            self.cost_label.setToolTip(
                f"模型 {api.get('model', '')} · {ratio}\n"
                f"输入 {price_text(price_in)} / 百万 tokens\n"
                f"输出 {price_text(price_out)} / 百万 tokens\n"
                "收费比例为内置固定值，不可修改"
            )
        else:
            self.cost_label.setToolTip(
                f"模型 {api.get('model', '')} 未收录，按固定 1.00x 参考比例计费。"
            )

    def _cost_pages(self) -> list[str]:
        """点击序列：每点一次往后翻一页，翻完再点收起（参考小鲸鱼挂件的泡泡队列）。"""
        billing = self._billing()
        api = self.config.get("api") or {}
        model = find_any_model(api, str(api.get("model") or ""))
        price_in, price_out, known = resolve_price(api)

        wallet = []
        if self._last_cost is not None:
            wallet.append(f"本次 {money(self._last_cost)}")
        wallet.append(f"今日 {money(billing['today'])}")
        wallet.append(f"累计 {money(billing['total'])}")

        ledger = (
            f"今日记账 · {int(billing.get('requests', 0))} 次请求\n"
            f"输入 {int(billing.get('prompt_tokens', 0)):,}"
            f" · 输出 {int(billing.get('completion_tokens', 0)):,} tokens"
        )

        if model is not None:
            rate = (
                f"{model.get('label') or model['id']} · {ratio_text(model)}\n"
                f"输入 {price_text(price_in)} / 百万\n"
                f"输出 {price_text(price_out)} / 百万"
            )
            if not known:
                rate += "\n未收录模型按固定参考价计费"
            else:
                rate += "\n费率内置固定，不可修改"
        else:
            rate = f"当前模型 {api.get('model') or '未选择'}\n按固定 1.00x 参考比例计费"

        return ["\n".join(wallet), ledger, rate, random.choice(self._bubble_lines)]

    def _on_mascot_clicked(self) -> None:
        """点大肥鱼：数钱表情 + 依次翻页显示消耗费用，不触发模型切换。"""
        self.mascot.flash_reaction()
        pages = self._cost_pages()
        if self._cost_bubble.isVisible():
            page = self._bubble_page + 1
        else:
            page = 0
        if page >= len(pages):
            self._bubble_page = 0
            self._cost_bubble.hide()
            return
        self._bubble_page = page
        self._cost_bubble.show_near(
            self.mascot, pages[page], close_ms=self._bubble_close_ms
        )

    def _on_usage(self, usage: dict) -> None:
        billing = self._billing()
        self._bubble_page = 0
        api = self.config.get("api") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        cost = compute_cost(prompt_tokens, completion_tokens, api)
        record_usage(billing, cost, prompt_tokens, completion_tokens)
        self.config["billing"] = billing
        save_config(self.config)
        self._update_cost_label(last_cost=cost, usage=usage)
        if self._pet.isVisible():
            note = "（估算）" if usage.get("estimated") else ""
            self._cost_bubble.show_for(
                self._pet,
                f"本次 {money(cost)}{note}\n"
                f"今日 {money(billing['today'])} · 累计 {money(billing['total'])}",
            )

    # ---------------- 实时预览 ----------------
    def _setup_live_capture(self) -> None:
        self._live = LiveCapture(120, self)
        self._live.preview.connect(self._on_preview)
        self._live.scene_changed.connect(self._on_scene_changed)
        self._live.failed.connect(lambda message: self._set_status(message, error=True))
        self._live.start()
        self._sync_live_region()

    def _sync_live_region(self) -> None:
        rect = rect_from_dict(self.config.get("region"))
        if rect is None:
            self._live.set_region(None, 1.0)
            self._preview_image = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(PREVIEW_PLACEHOLDER)
            return
        screen = region_screen(rect)
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        self._live.set_region(rect, dpr)
        self._preview_image = None

    def _on_preview(self, image: QImage) -> None:
        self._preview_image = image
        self._render_preview()

    def _render_preview(self) -> None:
        if self._preview_image is None:
            if self.preview_label.pixmap().isNull():
                self.preview_label.setText(PREVIEW_PLACEHOLDER)
            return
        self.preview_label.setText("")
        pixmap = QPixmap.fromImage(self._preview_image)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _on_scene_changed(self) -> None:
        if not self._auto or not api_ready(self.config):
            return
        if self._worker is not None and self._worker.isRunning():
            return
        rect = rect_from_dict(self.config.get("region"))
        if rect is None:
            return
        hud_overlap = self.isVisible() and self.frameGeometry().intersects(rect)
        pet_overlap = self._pet.isVisible() and self._pet.frameGeometry().intersects(rect)
        if hud_overlap or pet_overlap:
            return
        now = time.monotonic()
        if now - self._last_auto < 3.0:
            return
        self._last_auto = now
        self.start_answer(auto=True)

    def _on_auto_toggled(self, checked: bool) -> None:
        self._auto = checked
        self.config["auto_answer"] = checked
        save_config(self.config)
        self._update_auto_text()
        self._set_status("自动作答已开启" if checked else "自动作答已关闭")

    def _update_auto_text(self) -> None:
        self.auto_button.setText("自动作答：开" if self._auto else "自动作答：关")

    def _on_answer_only_toggled(self, checked: bool) -> None:
        self._answer_only = checked
        self.config["answer_only"] = checked
        save_config(self.config)
        self._update_answer_only_text()
        self._set_status("只给答案：开（不写解析）" if checked else "只给答案：关（附解析）")

    def _update_answer_only_text(self) -> None:
        self.answer_only_button.setText("只给答案：开" if self._answer_only else "只给答案：关")

    # ---------------- 窗口位置与大小 ----------------
    def _apply_window_size(self) -> None:
        """按 config 的 window.w/h 设置窗口大小，并夹在当前屏幕可用范围内。"""
        win = self.config.setdefault("window", {})
        screen = QGuiApplication.screenAt(self.frameGeometry().center())
        area = (screen or QGuiApplication.primaryScreen()).availableGeometry()
        width = max(380, min(int(win.get("w") or 430), area.width() - 24))
        height = max(500, min(int(win.get("h") or 660), area.height() - 48))
        self.resize(width, height)
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width())),
            max(area.top(), min(self.y(), area.bottom() - self.height())),
        )
        # 写回实际生效值，供下次启动与设置界面读取
        win["w"], win["h"] = width, height
        self._size_applied = True

    def _restore_geometry(self) -> None:
        win = self.config.get("window") or {}
        width = max(380, int(win.get("w") or 430))
        height = max(500, int(win.get("h") or 660))
        self.resize(width, height)

        x, y = win.get("x"), win.get("y")
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if x is None or y is None:
            x = area.right() - width - 24
            y = area.top() + 60
        target = QGuiApplication.screenAt(QRect(x, y, width, height).center())
        if target is not None:
            area = target.availableGeometry()
        x = max(area.left(), min(int(x), area.right() - width))
        y = max(area.top(), min(int(y), area.bottom() - height))
        self.move(x, y)

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        if self._cost_bubble.isVisible():
            self._cost_bubble.reposition()
        if self._ready:
            self._save_timer.start(700)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._cost_bubble.isVisible():
            self._cost_bubble.reposition()
        if self._ready:
            self._save_timer.start(700)
        self._render_preview()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._size_applied:
            QTimer.singleShot(0, self._apply_window_size)
        if hasattr(self, "_live"):
            self._live.set_active(True)

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        if hasattr(self, "_live"):
            # 收起成桌面形象时仍保持实时抓取，展开后可直接作答
            self._live.set_active(self._pet.isVisible())

    def _persist_window(self) -> None:
        # 首次布局会临时把窗口撑宽，未应用用户尺寸前不记录，避免把错误尺寸写进配置
        if not self._size_applied:
            return
        self.config["window"] = {
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height(),
        }
        save_config(self.config)

    # ---------------- 状态与显示 ----------------
    def _set_status(self, text: str, error: bool = False) -> None:
        text = str(text)
        if len(text) > 64:
            text = text[:64] + "…"
        self.status_label.setObjectName("Error" if error else "Hint")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(text)

    def _update_region_label(self) -> None:
        rect = rect_from_dict(self.config.get("region"))
        if rect is None:
            self.region_label.setText("尚未选择区域")
        else:
            self.region_label.setText(f"区域 {rect.width()} × {rect.height()}")

    def _set_busy(self, busy: bool) -> None:
        self.answer_button.setEnabled(not busy)
        self.answer_button.setText("作答中…" if busy else "识别并作答")
        if busy:
            self._pet.set_state("analyzing")

    # ---------------- 区域选择 ----------------
    def pick_region(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._set_status("正在作答，请稍候再修改区域", error=True)
            return
        rect = rect_from_dict(self.config.get("region"))
        screen = (
            QGuiApplication.screenAt(rect.center())
            if rect is not None
            else QGuiApplication.primaryScreen()
        )
        screen = screen or QGuiApplication.primaryScreen()
        self._pet.hide()
        self.hide()
        QTimer.singleShot(220, lambda: self._open_picker(screen, rect))

    def _open_picker(self, screen, rect) -> None:
        picker = RegionPicker(
            screen,
            initial=rect,
            skin_qss=self._skin.qss,
            accent=self._skin_accent(),
        )
        picker.selected.connect(self._on_region_selected)
        picker.canceled.connect(self._on_region_canceled)
        self._picker = picker
        picker.show()
        picker.raise_()
        picker.activateWindow()

    def _skin_accent(self) -> str:
        import json

        try:
            data = json.loads(
                (self._skin.directory / "skin.json").read_text(encoding="utf-8")
            )
            return data.get("colors", {}).get("accent", "#6e9bff")
        except (OSError, json.JSONDecodeError):
            return "#6e9bff"

    def _on_region_selected(self, rect: QRect) -> None:
        self.config["region"] = {
            "x": rect.x(),
            "y": rect.y(),
            "w": rect.width(),
            "h": rect.height(),
        }
        save_config(self.config)
        self._update_region_label()
        self._sync_live_region()
        self._set_status("区域已保存，画面已开始实时预览")
        self._show_after_picker()

    def _on_region_canceled(self) -> None:
        self._show_after_picker()

    def _show_after_picker(self) -> None:
        self._picker = None
        self.show()
        self.raise_()
        self.activateWindow()

    # ---------------- 作答流程 ----------------
    def start_answer(self, auto: bool = False) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        rect = rect_from_dict(self.config.get("region"))
        if rect is None:
            if auto:
                return
            self._set_status("请先框选屏幕区域", error=True)
            self.pick_region()
            return
        if not api_ready(self.config):
            if auto:
                return
            self._set_status("请先在设置中填写 API Key", error=True)
            self.open_settings()
            return

        # 主窗口与桌面形象都收起时，先把主窗口叫出来，便于看到作答过程
        if not self.isVisible() and not self._pet.isVisible():
            self.show()

        pet_visible = self._pet.isVisible()
        overlaps = self.frameGeometry().intersects(rect)
        if pet_visible and self._pet.frameGeometry().intersects(rect):
            overlaps = True
        if auto and overlaps:
            self._set_status("悬浮窗遮挡了选区，自动作答已跳过")
            return

        self._answer_text = ""
        self._recognized_text = ""
        self.answer_view.setPlainText("正在准备画面…")
        self._set_busy(True)
        self._set_status("正在读取实时画面…")

        frame, timestamp = self._live.latest_frame()
        fresh = frame is not None and (time.time() - timestamp) <= 2.0
        if fresh and not overlaps:
            max_edge = 1600 if self.config.get("mode") == "vision" else None
            png = encode_png(frame, max_edge)
            self._set_status("使用实时画面，正在识别…")
            self._run_worker(png)
            return

        # 窗口与选区重叠，或实时画面尚未就绪：收起窗口后截取一帧
        self._set_status("正在截图…")
        target = "hud" if self.isVisible() else ("pet" if pet_visible else "none")
        self._pet.hide()
        self.hide()
        QTimer.singleShot(260, lambda: self._capture_and_run(rect, target))

    def _capture_and_run(self, rect: QRect, restore: str) -> None:
        mode = self.config.get("mode", "ocr")
        png = None
        try:
            png = grab_region(rect, max_edge=1600 if mode == "vision" else None)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"截图异常：{exc}", error=True)
        finally:
            if restore == "hud":
                self.show()
            elif restore == "pet":
                self._pet.show()
        if not png:
            self._set_busy(False)
            self._set_status("截图失败，请重新框选区域", error=True)
            self.answer_view.setPlainText("截图失败：区域可能已超出屏幕或尺寸过小。")
            return
        self._run_worker(png)

    def _run_worker(self, png: bytes | None) -> None:
        if not png:
            self._set_busy(False)
            self._set_status("画面读取失败，请重新框选区域", error=True)
            return
        worker = AnswerWorker(png, copy.deepcopy(self.config))
        worker.stage_changed.connect(self._on_stage)
        worker.recognized.connect(self._on_recognized)
        worker.answer_chunk.connect(self._on_chunk)
        worker.usage_ready.connect(self._on_usage)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_stage(self, text: str) -> None:
        if self._recognized_text and text.startswith("AI"):
            text = f"{text} · 已识别 {len(self._recognized_text)} 字"
        self._set_status(text)

    def _on_recognized(self, text: str) -> None:
        self._recognized_text = text
        preview = text.replace("\n", " ")
        if len(preview) > 40:
            preview = preview[:40] + "…"
        self._set_status(f"已识别 {len(text)} 字：{preview}")

    def _on_chunk(self, chunk: str) -> None:
        self._answer_text += chunk
        if not self._render_timer.isActive():
            self._render_timer.start(70)

    def _render_answer(self) -> None:
        self.answer_view.setMarkdown(self._answer_text)
        scrollbar = self.answer_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_completed(self) -> None:
        self._render_timer.stop()
        self._render_answer()
        self._set_busy(False)
        self._set_status("完成")
        self._pet.set_state("celebrating", 2600)

    def _on_failed(self, message: str) -> None:
        self._render_timer.stop()
        self._set_busy(False)
        self._set_status(message, error=True)
        self._pet.set_state("failed", 2600)
        if not self._answer_text:
            self.answer_view.setPlainText(f"出错了：{message}")

    def copy_answer(self) -> None:
        if not self._answer_text:
            self._set_status("还没有答案可复制")
            return
        QApplication.clipboard().setText(self._answer_text)
        self._set_status("答案已复制到剪贴板")

    # ---------------- 设置 ----------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.result_config()
            save_config(self.config)
            self._apply_skin(load_skin(self.config.get("skin", "default")))
            self._apply_window_size()
            self._update_region_label()
            self._sync_live_region()
            self._refresh_model_picker()
            self._update_cost_label()
            self._set_status("设置已保存")

    # ---------------- 退出 ----------------
    def request_quit(self) -> None:
        self._shutdown_threads()
        self._persist_window()
        self._persist_pet()
        self._cost_bubble.close()
        self._pet.close()
        QApplication.quit()

    def _shutdown_threads(self) -> None:
        if hasattr(self, "_live"):
            self._live.stop()
            if not self._live.wait(1500):
                self._live.terminate()
                self._live.wait(500)
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            if not self._worker.wait(2000):
                self._worker.terminate()
                self._worker.wait(500)

    def closeEvent(self, event):  # noqa: N802
        self._shutdown_threads()
        self._persist_window()
        self._cost_bubble.close()
        self._pet.close()
        super().closeEvent(event)
        QApplication.quit()
