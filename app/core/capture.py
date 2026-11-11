"""屏幕区域截图。

坐标体系：配置中的区域使用 Qt 的「全局逻辑坐标」，截图时按所在屏幕换算为
相对坐标，由 Qt 自行处理高 DPI 缩放，避免多屏缩放不一致导致的偏移。
"""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap


def region_screen(rect: QRect):
    """返回区域中心所在的屏幕。"""
    return QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()


def grab_region(rect: QRect, max_edge: int | None = None) -> bytes | None:
    """截取指定区域并返回 PNG 字节；区域无效时返回 None。"""
    if rect is None or rect.width() < 6 or rect.height() < 6:
        return None
    screen = region_screen(rect)
    if screen is None:
        return None
    geo = screen.geometry()
    local = QRect(
        rect.x() - geo.x(), rect.y() - geo.y(), rect.width(), rect.height()
    )
    pixmap = screen.grabWindow(0, local.x(), local.y(), local.width(), local.height())
    if pixmap.isNull():
        return None

    image = pixmap.toImage()
    if max_edge and max(image.width(), image.height()) > max_edge:
        image = image.scaled(
            max_edge,
            max_edge,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
    return _to_png(image)


def _to_png(image: QImage) -> bytes | None:
    buffer = QBuffer()
    buffer.open(QBuffer.ReadWrite)
    if not image.save(buffer, "PNG"):
        return None
    data = buffer.data()
    buffer.close()
    return bytes(data)


def encode_png(image, max_edge: int | None = None) -> bytes | None:
    """把 PIL.Image 编码为 PNG 字节，可选限制最长边。"""
    try:
        import io

        if max_edge and max(image.width, image.height) > max_edge:
            image = image.copy()
            image.thumbnail((max_edge, max_edge))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


def rect_from_dict(data: dict | None) -> QRect | None:
    if not data:
        return None
    try:
        rect = QRect(int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))
    except (KeyError, TypeError, ValueError):
        return None
    if rect.width() < 6 or rect.height() < 6:
        return None
    return rect
