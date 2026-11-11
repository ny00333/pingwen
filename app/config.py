"""配置读写：全部保存在项目根目录的 config.json，方便备份与迁移。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SKINS_DIR = ROOT / "skins"

DEFAULT_CONFIG = {
    # 截图区域（全局逻辑坐标，由区域选择器写入）
    "region": None,
    # 悬浮窗位置与大小
    "window": {"x": None, "y": None, "w": 430, "h": 660},
    # 收起后桌面形象的位置
    "pet": {"x": None, "y": None},
    # 外观
    "skin": "default",
    "opacity": 1.0,
    # 识别方式：ocr = 先文字识别再交给模型；vision = 直接把截图交给多模态模型
    "mode": "ocr",
    # 答题风格：concise = 答案 + 关键步骤；detailed = 完整解析
    "prompt_style": "concise",
    # 只给答案（不写解析）：开启后覆盖 prompt_style，速度更快、token 更省
    "answer_only": False,
    # 画面变化时自动作答（默认关闭，避免误触发消耗额度）
    "auto_answer": False,
    # OpenAI 兼容接口配置
    "api": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "model": "qwen-flash",
        # 用户自行添加的模型名（收费比例固定为 1.00x 参考值，不可修改）
        "extra_models": [],
        "temperature": 0.2,
        "max_tokens": 2048,
        "timeout": 90,
    },
    # token 计费统计（total = 累计，today = 今日；跨天自动归零）
    "billing": {
        "total": 0.0,
        "today": 0.0,
        "date": "",
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}
    return _deep_merge(DEFAULT_CONFIG, data)


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def api_ready(config: dict) -> bool:
    """校验接口配置：云端服务需要 Key，本地服务（如 Ollama）可以留空。"""
    api = config.get("api") or {}
    base_url = str(api.get("base_url") or "")
    if not base_url or not api.get("model"):
        return False
    if api.get("api_key"):
        return True
    return any(
        host in base_url.lower()
        for host in ("127.0.0.1", "localhost", "0.0.0.0")
    )
