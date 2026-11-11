"""端到端冒烟测试：题目窗口 + 实时捕获 + OCR + 本地模拟 AI 流式响应。"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, r"c:\Users\陈灿旭\Desktop\学习区\screen-answer")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from app.config import load_config
from app.ui.hud import HudWindow


class FakeAI(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in ["答案：", "C. 15", "\n\n", "解析：f(3)=9+6=15。"]:
            chunk = {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "fake",
                "choices": [
                    {"index": 0, "delta": {"content": piece}, "finish_reason": None}
                ],
            }
            self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n")
            self.wfile.flush()
        usage_chunk = {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "fake",
            "choices": [],
            "usage": {
                "prompt_tokens": 812,
                "completion_tokens": 456,
                "total_tokens": 1268,
            },
        }
        self.wfile.write(
            b"data: " + json.dumps(usage_chunk, ensure_ascii=False).encode("utf-8") + b"\n\n"
        )
        self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args):
        pass


def make_question():
    image = Image.new("RGB", (720, 250), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
    draw.text((30, 26), "1. 已知函数 f(x)=x^2+2x，求 f(3) 的值。", font=font, fill="black")
    draw.text((30, 100), "A. 9    B. 12    C. 15    D. 18", font=font, fill="black")
    return image


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    server = HTTPServer(("127.0.0.1", 8899), FakeAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = QApplication(sys.argv)

    image = make_question()
    data = image.tobytes()
    qimg = QImage(data, image.width, image.height, image.width * 3, QImage.Format_RGB888)
    label = QLabel()
    label.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    label.setPixmap(QPixmap.fromImage(qimg))
    label.adjustSize()
    label.move(90, 120)
    label.show()
    app.processEvents()

    config = load_config()
    config["api"] = {
        "base_url": "http://127.0.0.1:8899/v1",
        "api_key": "test-key",
        "model": "qwen-plus",
        "temperature": 0.2,
        "max_tokens": 512,
        "timeout": 20,
    }
    config["region"] = {
        "x": label.x(),
        "y": label.y(),
        "w": label.width(),
        "h": label.height(),
    }
    config["mode"] = "ocr"
    config["auto_answer"] = False

    hud = HudWindow(config)
    hud.move(1250, 700)
    hud.show()
    app.processEvents()

    QTimer.singleShot(1600, hud.start_answer)

    def check():
        worker = hud._worker
        if worker is not None and not worker.isRunning():
            print("ANSWER:", repr(hud._answer_text), flush=True)
            print("RECOGNIZED:", repr(hud._recognized_text), flush=True)
            print("STATUS:", hud.status_label.text(), flush=True)
            print("COST:", hud.cost_label.text(), flush=True)
            print("BILLING:", hud.config.get("billing"), flush=True)
            hud._shutdown_threads()
            server.shutdown()
            os._exit(0 if hud._answer_text else 1)
        else:
            QTimer.singleShot(300, check)

    QTimer.singleShot(2000, check)
    app.exec()


if __name__ == "__main__":
    main()
