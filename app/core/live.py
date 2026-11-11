"""实时区域捕获：后台线程以约 8 fps 抓取选区画面，用于悬浮窗预览与快速作答。

相比每次点击都重新截图，实时捕获会缓存最新画面，点击作答时可以直接使用
缓存帧（通常只落后几十到一百多毫秒），省去「隐藏窗口 + 等待 + 截图」的耗时。
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class LiveCapture(QThread):
    preview = Signal(QImage)
    scene_changed = Signal()
    failed = Signal(str)

    def __init__(self, interval_ms: int = 120, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._region = None  # (left, top, width, height) 物理像素
        self._latest = None  # PIL.Image
        self._latest_ts = 0.0
        self._last_small = None
        self._last_change_ts = 0.0
        self._active = threading.Event()
        self._running = False
        self._interval = max(interval_ms, 60) / 1000.0
        self._error_reported = False

    # ---------- 外部调用（主线程） ----------
    def set_region(self, rect, dpr: float) -> None:
        """rect 为全局逻辑坐标，dpr 为该屏幕的缩放比例。"""
        if rect is None:
            with self._lock:
                self._region = None
                self._latest = None
                self._last_small = None
            return
        left = round(rect.x() * dpr)
        top = round(rect.y() * dpr)
        width = max(1, round(rect.width() * dpr))
        height = max(1, round(rect.height() * dpr))
        with self._lock:
            self._region = (left, top, width, height)
            self._latest = None
            self._last_small = None

    def set_active(self, active: bool) -> None:
        if active:
            self._active.set()
        else:
            self._active.clear()

    def latest_frame(self):
        """返回 (PIL.Image 副本, 时间戳)；没有可用帧时返回 (None, 0)。"""
        with self._lock:
            if self._latest is None:
                return None, 0.0
            return self._latest.copy(), self._latest_ts

    def stop(self) -> None:
        self._running = False
        self._active.set()

    # ---------- 线程主体 ----------
    def run(self) -> None:  # noqa: D102
        try:
            import mss
            from PIL import Image, ImageChops, ImageStat
        except ImportError:
            self.failed.emit("缺少实时捕获依赖（mss / Pillow），预览不可用")
            return

        self._running = True
        try:
            factory = getattr(mss, "MSS", None) or mss.mss
            with factory() as sct:
                while self._running:
                    if not self._active.wait(0.2):
                        continue
                    if not self._running:
                        break
                    with self._lock:
                        region = self._region
                    if region is None:
                        time.sleep(0.2)
                        continue

                    started = time.perf_counter()
                    left, top, width, height = region
                    try:
                        shot = sct.grab(
                            {
                                "left": left,
                                "top": top,
                                "width": width,
                                "height": height,
                            }
                        )
                        image = Image.frombytes(
                            "RGB", shot.size, shot.bgra, "raw", "BGRX"
                        )
                    except Exception as exc:  # noqa: BLE001
                        if not self._error_reported:
                            self._error_reported = True
                            self.failed.emit(f"实时预览抓取失败：{exc}")
                        time.sleep(0.6)
                        continue

                    with self._lock:
                        self._latest = image
                        self._latest_ts = time.time()

                    self._emit_preview(image, Image)
                    self._detect_change(image, Image, ImageChops, ImageStat)

                    elapsed = time.perf_counter() - started
                    time.sleep(max(0.0, self._interval - elapsed))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"实时预览线程异常：{exc}")

    def _emit_preview(self, image, Image) -> None:
        preview = image.copy()
        preview.thumbnail((420, 150), Image.BILINEAR)
        data = preview.tobytes()
        qimage = QImage(
            data, preview.width, preview.height, preview.width * 3, QImage.Format_RGB888
        ).copy()
        self.preview.emit(qimage)

    def _detect_change(self, image, pil, ImageChops, ImageStat) -> None:
        # 用小尺寸灰度图做差异检测，避免逐像素比较的开销
        small = image.convert("L").resize((64, 40), pil.BILINEAR)
        if self._last_small is None:
            self._last_small = small
            return
        diff = ImageChops.difference(small, self._last_small)
        mean = ImageStat.Stat(diff).mean[0]
        self._last_small = small
        now = time.time()
        if mean >= 6.0 and now - self._last_change_ts >= 0.8:
            self._last_change_ts = now
            self.scene_changed.emit()
