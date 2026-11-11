"""皮肤系统：悬浮窗的全部外观由 skins/<皮肤名>/skin.json 驱动。

修改外观时只需要：
1. 复制 skins/default 为 skins/你的皮肤名；
2. 编辑 skin.json 里的颜色、圆角、字体、头像等字段；
3. 如需更细的控制，可填写 extra_qss（会追加到自动生成的样式表后面）。
也可把 avatar_text 换成 avatar_image（放在同一皮肤目录下的图片文件名）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import SKINS_DIR


@dataclass
class Skin:
    name: str
    display_name: str
    title: str
    avatar_text: str
    avatar_image: str
    opacity: float
    qss: str
    directory: Path
    mascot: dict = field(default_factory=dict)  # 大肥鱼形象/音效/气泡的可选配置


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "#000000").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except (ValueError, IndexError):
        return 0, 0, 0


def list_skins() -> list[tuple[str, str]]:
    """返回 [(皮肤目录名, 显示名称)]，按目录名排序。"""
    if not SKINS_DIR.exists():
        return []
    result = []
    for folder in sorted(SKINS_DIR.iterdir()):
        data_file = folder / "skin.json"
        if not folder.is_dir() or not data_file.exists():
            continue
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        result.append((folder.name, str(data.get("name") or folder.name)))
    return result


def load_skin(name: str) -> Skin:
    folder = SKINS_DIR / name
    data_file = folder / "skin.json"
    if not data_file.exists():
        folder = SKINS_DIR / "default"
        data_file = folder / "skin.json"
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}

    colors = data.get("colors") or {}
    bg_r, bg_g, bg_b = _hex_to_rgb(colors.get("bg", "#1b1d24"))
    radius = int(data.get("radius", 14))
    font = str(data.get("font_family", "Microsoft YaHei UI"))
    font_size = int(data.get("font_size", 13))
    avatar_text = str(data.get("avatar_text", "◈"))
    avatar_image = str(data.get("avatar_image", ""))

    palette = {
        "font": font,
        "font_size": font_size,
        "radius": radius,
        "small_radius": max(6, radius - 6),
        "bg_r": bg_r,
        "bg_g": bg_g,
        "bg_b": bg_b,
        "bg_a": int(data.get("bg_alpha", 240)),
        "panel": colors.get("panel", "#23262f"),
        "accent": colors.get("accent", "#6e9bff"),
        "accent_hover": colors.get("accent_hover", "#8ab0ff"),
        "accent_text": colors.get("accent_text", "#0e1118"),
        "text": colors.get("text", "#e9ecf4"),
        "muted": colors.get("muted", "#939cae"),
        "border": colors.get("border", "#323745"),
        "danger": colors.get("danger", "#ff6b6b"),
        "disabled": colors.get("disabled", "#2a2d38"),
    }
    qss = _TEMPLATE % palette + "\n" + str(data.get("extra_qss", ""))
    return Skin(
        name=name if (SKINS_DIR / name / "skin.json").exists() else "default",
        display_name=str(data.get("name") or name),
        title=str(data.get("title") or "屏问"),
        avatar_text=avatar_text,
        avatar_image=avatar_image,
        opacity=float(data.get("opacity", 1.0)),
        qss=qss,
        directory=folder,
        mascot=data.get("mascot") or {},
    )


_TEMPLATE = """
QWidget {
    font-family: "%(font)s";
    font-size: %(font_size)spx;
    color: %(text)s;
}
QFrame#Root {
    background-color: rgba(%(bg_r)s, %(bg_g)s, %(bg_b)s, %(bg_a)s);
    border: 1px solid %(border)s;
    border-radius: %(radius)spx;
}
QFrame#ActionBar {
    background-color: rgba(%(bg_r)s, %(bg_g)s, %(bg_b)s, %(bg_a)s);
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
}
QWidget#TitleBar { background: transparent; }
QLabel { background: transparent; }
QLabel#Avatar {
    color: %(accent)s;
    font-size: 20px;
    font-weight: 700;
    background-color: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    padding: 1px 7px;
}
QLabel#Title { font-size: 15px; font-weight: 600; }
QLabel#Hint { color: %(muted)s; font-size: 12px; }
QLabel#Cost { color: %(muted)s; font-size: 11px; }
QPushButton#ModelButton {
    background-color: transparent;
    color: %(muted)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    padding: 3px 8px;
    font-size: 11px;
    text-align: left;
}
QPushButton#ModelButton:hover {
    color: %(text)s;
    border-color: %(accent)s;
}
#Mascot {
    background: transparent;
    border: none;
    padding: 0;
}
QFrame#MenuPanel {
    background-color: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
}
QFrame#MenuDivider {
    background-color: %(border)s;
    border: none;
}
QWidget#ModelRow {
    background: transparent;
    border-radius: 8px;
}
QWidget#ModelRow[hover="true"] {
    background-color: rgba(255, 255, 255, 22);
}
QWidget#ModelRow[selected="true"] {
    background-color: rgba(110, 155, 255, 46);
}
QLabel#ModelIcon { color: %(accent)s; font-size: 13px; }
QLabel#ModelName { color: %(text)s; font-size: 13px; }
QLabel#ModelRatio { color: %(muted)s; font-size: 12px; }
QPushButton#AddModel {
    background: transparent;
    border: none;
    color: %(text)s;
    text-align: left;
    padding: 0 12px;
    font-size: 13px;
    border-radius: 8px;
}
QPushButton#AddModel:hover {
    background-color: rgba(255, 255, 255, 22);
}
QScrollArea { background: transparent; border: none; }
QLabel#Error { color: %(danger)s; font-size: 12px; }
QLabel#Preview {
    background-color: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    color: %(muted)s;
    font-size: 12px;
    padding: 4px;
}
QPushButton {
    background-color: %(panel)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    padding: 6px 12px;
}
QPushButton:hover { border-color: %(accent)s; }
QPushButton:pressed { background-color: %(disabled)s; }
QPushButton[kind="primary"] {
    background-color: %(accent)s;
    color: %(accent_text)s;
    border: none;
    font-weight: 600;
    padding: 10px 14px;
    border-radius: %(small_radius)spx;
}
QPushButton[kind="primary"]:hover { background-color: %(accent_hover)s; }
QPushButton[kind="primary"]:disabled {
    background-color: %(disabled)s;
    color: %(muted)s;
}
QPushButton[kind="tool"] {
    background: transparent;
    border: none;
    color: %(muted)s;
    padding: 3px 8px;
    border-radius: %(small_radius)spx;
}
QPushButton[kind="tool"]:hover {
    background-color: %(panel)s;
    color: %(text)s;
}
QPushButton[kind="tool"]:checked {
    color: %(accent)s;
    background-color: %(panel)s;
    border: 1px solid %(accent)s;
}
QTextBrowser#Answer {
    background-color: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    padding: 10px;
    color: %(text)s;
    selection-background-color: %(accent)s;
    selection-color: %(accent_text)s;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 8px; background: transparent; }
QScrollBar::handle:horizontal { background: %(border)s; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: %(panel)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    padding: 6px 8px;
    selection-background-color: %(accent)s;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: %(accent)s;
}
QComboBox QAbstractItemView {
    background-color: %(panel)s;
    border: 1px solid %(border)s;
    selection-background-color: %(accent)s;
    selection-color: %(accent_text)s;
}
QComboBox::drop-down { border: none; width: 18px; }
QGroupBox {
    border: 1px solid %(border)s;
    border-radius: %(small_radius)spx;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: %(muted)s;
}
QSlider::groove:horizontal {
    height: 4px;
    background: %(border)s;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: %(accent)s;
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QSizeGrip { background: transparent; width: 16px; height: 16px; }
QToolTip {
    background-color: %(panel)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
"""
