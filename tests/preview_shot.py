"""验证实时预览：显示题目窗口 + 悬浮窗，等待后截取悬浮窗画面。"""
import os
import sys

sys.path.insert(0, r"c:\Users\陈灿旭\Desktop\学习区\screen-answer")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from app.config import load_config
from app.ui.hud import HudWindow

app = QApplication(sys.argv)

image = Image.new("RGB", (720, 250), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
draw.text((30, 26), "1. 已知函数 f(x)=x^2+2x，求 f(3) 的值。", font=font, fill="black")
draw.text((30, 100), "A. 9    B. 12    C. 15    D. 18", font=font, fill="black")
qimg = QImage(
    image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888
)

label = QLabel()
label.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
label.setPixmap(QPixmap.fromImage(qimg))
label.adjustSize()
label.move(90, 120)
label.show()

config = load_config()
config["region"] = {
    "x": label.x(),
    "y": label.y(),
    "w": label.width(),
    "h": label.height(),
}

hud = HudWindow(config)
hud.move(820, 60)
hud.show()


def shoot():
    import mss

    screen = hud.screen()
    dpr = screen.devicePixelRatio()
    rect = hud.frameGeometry()
    region = {
        "left": round(rect.x() * dpr),
        "top": round(rect.y() * dpr),
        "width": round(rect.width() * dpr),
        "height": round(rect.height() * dpr),
    }
    with mss.MSS() as sct:
        shot = sct.grab(region)
    path = r"c:\Users\陈灿旭\Desktop\学习区\screen-answer\tests\preview_shot.png"
    Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(path)
    print("PREVIEW SHOT:", path, shot.size, flush=True)
    hud._shutdown_threads()
    os._exit(0)


QTimer.singleShot(2600, shoot)
app.exec()
