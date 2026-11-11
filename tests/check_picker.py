"""验证区域选择遮罩：框选、确认后关闭并回传坐标。"""
import os
import sys

sys.path.insert(0, r"c:\Users\陈灿旭\Desktop\学习区\screen-answer")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.region_picker import RegionPicker

app = QApplication(sys.argv)
screen = QGuiApplication.primaryScreen()
picker = RegionPicker(screen, accent="#6e9bff")
picker.show()
QTest.qWait(300)

QTest.mousePress(picker, Qt.LeftButton, pos=QPoint(200, 200))
QTest.mouseMove(picker, QPoint(600, 420))
QTest.mouseRelease(picker, Qt.LeftButton, pos=QPoint(600, 420))
QTest.qWait(200)

print("SELECTION:", picker._selection, flush=True)
print("BAR VISIBLE:", picker._bar.isVisible(), flush=True)

captured = {}
picker.selected.connect(lambda rect: captured.update({"rect": rect}))

QTest.qWait(100)
picker._confirm()
QTest.qWait(200)
print("EMITTED:", captured.get("rect"), flush=True)
print("PICKER VISIBLE AFTER CONFIRM:", picker.isVisible(), flush=True)
os._exit(0)
