"""后台工作线程：OCR -> AI 流式作答，避免阻塞界面。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.core.ai import AIError, stream_answer
from app.core.billing import estimate_tokens


class AnswerWorker(QThread):
    stage_changed = Signal(str)
    recognized = Signal(str)
    answer_chunk = Signal(str)
    usage_ready = Signal(dict)
    completed = Signal()
    failed = Signal(str)

    def __init__(self, png_bytes: bytes, config: dict, parent=None):
        super().__init__(parent)
        self._png = png_bytes
        self._config = config
        self._canceled = False

    def cancel(self) -> None:
        self._canceled = True

    def run(self) -> None:  # noqa: D102
        try:
            mode = self._config.get("mode", "ocr")
            style = (
                "answer_only"
                if self._config.get("answer_only")
                else self._config.get("prompt_style", "concise")
            )
            api_cfg = self._config.get("api", {})

            question: str | None = None
            usage: dict = {}
            if mode == "vision":
                self.stage_changed.emit("视觉模型正在读图作答…")
                generator = stream_answer(
                    api_cfg,
                    style=style,
                    question=None,
                    image_png=self._png,
                    usage_sink=usage,
                )
            else:
                from app.core.ocr import recognize

                self.stage_changed.emit("正在识别题目…")
                text = recognize(self._png)
                if self._canceled:
                    return
                if not text.strip():
                    raise AIError(
                        "未识别到文字。请检查区域是否包含题目，或在设置中改用「视觉模式」。"
                    )
                question = text
                self.recognized.emit(text)
                self.stage_changed.emit("AI 正在作答…")
                generator = stream_answer(
                    api_cfg,
                    style=style,
                    question=text,
                    usage_sink=usage,
                )

            parts: list[str] = []
            for chunk in generator:
                if self._canceled:
                    return
                parts.append(chunk)
                self.answer_chunk.emit(chunk)

            if self._canceled:
                return
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            estimated = False
            if not prompt_tokens and not completion_tokens:
                # 接口没有返回 usage，用文本长度估算
                estimated = True
                prompt_tokens = 320 + estimate_tokens(question or "")
                if mode == "vision":
                    prompt_tokens += 900  # 图片占用的 token 粗估
                completion_tokens = estimate_tokens("".join(parts))
            self.usage_ready.emit(
                {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "estimated": estimated,
                }
            )
            self.completed.emit()
        except AIError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"处理失败：{exc}")
