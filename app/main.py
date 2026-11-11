"""程序入口。"""
from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.config import load_config
from app.ui.hud import HudWindow

_warmup_thread = None


class OcrWarmup(QThread):
    """启动后提前加载 OCR 模型，减少第一次作答的等待。"""

    def run(self) -> None:  # noqa: D102
        try:
            from app.core.ocr import warmup

            warmup()
        except Exception:  # noqa: BLE001
            pass


def build_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#6e9bff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    painter.setPen(QColor("#0e1118"))
    painter.setFont(QFont("Microsoft YaHei UI", 30, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "问")
    painter.end()
    return QIcon(pixmap)


def main() -> int:
    global _warmup_thread
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("屏问")
    app.setQuitOnLastWindowClosed(False)

    config = load_config()
    hud = HudWindow(config)
    hud.show()

    _warmup_thread = OcrWarmup()
    _warmup_thread.start()

    tray = QSystemTrayIcon(build_icon(), app)
    menu = QMenu()
    show_action = menu.addAction("显示悬浮窗")
    show_action.triggered.connect(hud.restore_from_pet)
    hide_action = menu.addAction("收起到桌面形象")
    hide_action.triggered.connect(hud.minimize_to_pet)
    pick_action = menu.addAction("重新框选区域")
    pick_action.triggered.connect(hud.pick_region)
    answer_action = menu.addAction("识别并作答")
    answer_action.triggered.connect(hud.start_answer)
    menu.addSeparator()
    quit_action = menu.addAction("退出")
    quit_action.triggered.connect(hud.request_quit)
    tray.setContextMenu(menu)
    tray.setToolTip("屏问 · 屏幕答题助手")
    tray.activated.connect(
        lambda reason: hud.restore_from_pet()
        if reason == QSystemTrayIcon.Trigger
        else None
    )
    tray.show()

    code = app.exec()
    if _warmup_thread is not None and _warmup_thread.isRunning():
        _warmup_thread.wait(1000)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
