"""本地 OCR：使用 RapidOCR（ONNX Runtime，离线、免安装服务）。

输出会按行重组，尽量减少 OCR 把同一行拆成多段造成的语义断裂。
"""
from __future__ import annotations

import io

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "缺少 OCR 依赖 rapidocr-onnxruntime，请先执行 pip install -r requirements.txt"
            ) from exc
        _engine = RapidOCR()
    return _engine


def warmup() -> None:
    """提前加载 OCR 模型，让第一次作答不必等待初始化。"""
    try:
        _get_engine()
    except Exception:  # noqa: BLE001
        pass


def recognize(png_bytes: bytes) -> str:
    """识别 PNG 图片中的文字，返回按行合并后的纯文本。"""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 numpy / Pillow 依赖") from exc

    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    # 区域较小时放大，提升小字号题目的识别率
    if image.width < 700:
        scale = min(2.0, 700 / max(image.width, 1))
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
        )
    array = np.array(image)[:, :, ::-1].copy()  # RGB -> BGR，符合 OpenCV 习惯

    engine = _get_engine()
    result = engine(array)
    if isinstance(result, tuple):  # 兼容 (result, elapsed) 返回形式
        result = result[0]
    return _merge_lines(result or [])


def _merge_lines(result) -> str:
    items = []
    for entry in result:
        try:
            box, text = entry[0], str(entry[1])
        except (IndexError, TypeError):
            continue
        text = text.strip()
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        items.append(
            {
                "x": min(xs),
                "y": min(ys),
                "height": max(max(ys) - min(ys), 1.0),
                "text": text,
            }
        )

    if not items:
        return ""

    items.sort(key=lambda item: (item["y"], item["x"]))
    lines: list[dict] = []
    for item in items:
        center = item["y"] + item["height"] / 2
        target = None
        for line in lines:
            if abs(line["center"] - center) <= max(line["height"], item["height"]) * 0.55:
                target = line
                break
        if target is None:
            lines.append(
                {
                    "center": center,
                    "height": item["height"],
                    "items": [item],
                }
            )
        else:
            target["items"].append(item)
            target["center"] = sum(
                entry["y"] + entry["height"] / 2 for entry in target["items"]
            ) / len(target["items"])
            target["height"] = max(target["height"], item["height"])

    lines.sort(key=lambda line: line["center"])
    output: list[str] = []
    previous_center = None
    previous_height = None
    for line in lines:
        if previous_center is not None and previous_height is not None:
            gap = line["center"] - previous_center
            if gap > previous_height * 1.9:
                output.append("")  # 行距明显变大，视为段落间隔
        line["items"].sort(key=lambda item: item["x"])
        pieces = [item["text"] for item in line["items"]]
        merged = pieces[0]
        for previous, current in zip(pieces, pieces[1:]):
            if previous and current and previous[-1].isascii() and current[0].isascii():
                merged += " "
            merged += current
        output.append(merged)
        previous_center = line["center"]
        previous_height = line["height"]
    return "\n".join(output).strip()
