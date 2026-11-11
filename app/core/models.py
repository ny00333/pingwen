"""模型目录：阿里云百炼（DashScope 兼容接口）可用模型与固定收费比例。

收费比例 = 参考输出单价 ÷ ¥10/百万 tokens，由程序内置、界面不可修改。
清单按当前接口的 /v1/models 返回结果筛选：只保留确认存在、可直接调用的模型；
不在清单里的模型名请用「添加模型」，按固定 1.00x 参考计费。
"""
from __future__ import annotations

BASE_PRICE = 10.0  # 1.00x 对应 ¥10 / 百万 tokens
EXTRA_RATIO = 1.00  # 「添加模型」未收录时的固定参考比例


def _model(model_id: str, label: str, input_price: float, output_price: float, vision: bool = False) -> dict:
    return {
        "id": model_id,
        "label": label,
        "input": float(input_price),
        "output": float(output_price),
        "ratio": round(float(output_price) / BASE_PRICE, 2),
        "vision": bool(vision),
    }


PROVIDERS: list[dict] = [
    {
        "id": "qianwen",
        "name": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # 均已实测：可用且首字延迟 < 1 秒；按收费从低到高排列
        "models": [
            _model("qwen-flash", "Qwen Flash", 0.5, 0.5),
            _model("qwen3.5-flash", "Qwen3.5 Flash", 0.8, 0.8),
            _model("qwen3.6-flash", "Qwen3.6 Flash", 0.8, 0.8),
            _model("qwen3.7-flash", "Qwen3.7 Flash", 0.8, 0.8),
            _model("qwen3.8-flash", "Qwen3.8 Flash", 0.8, 0.8),
            _model("qwen-plus", "Qwen Plus", 0.8, 2.0),
            _model("qwen3-vl-plus", "Qwen3-VL Plus", 1.5, 4.5, vision=True),
            _model("qwen3.8-max", "Qwen3.8 Max", 15.0, 15.0),
        ],
    },
    {
        "id": "custom",
        "name": "自定义 / 中转",
        "base_url": None,
        "models": [],
    },
]


def provider_by_url(base_url: str) -> dict | None:
    base = (base_url or "").strip().rstrip("/")
    for provider in PROVIDERS:
        url = (provider.get("base_url") or "").rstrip("/")
        if url and base == url:
            return provider
    return None


def provider_by_id(provider_id: str) -> dict | None:
    for provider in PROVIDERS:
        if provider["id"] == provider_id:
            return provider
    return None


def find_model(model_id: str) -> dict | None:
    for provider in PROVIDERS:
        for model in provider.get("models", []):
            if model["id"] == model_id:
                return model
    return None


def _extra_model_id(value) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    return str(value or "").strip()


def _extra_model(model_id: str) -> dict:
    return {
        "id": model_id,
        "label": model_id,
        "input": BASE_PRICE * EXTRA_RATIO,
        "output": BASE_PRICE * EXTRA_RATIO,
        "ratio": EXTRA_RATIO,
        "vision": False,
        "custom": True,
    }


def models_for_provider(provider: dict | None, extra_models=None) -> list[dict]:
    models = list((provider or {}).get("models") or [])
    seen = {model["id"] for model in models}
    for item in extra_models or []:
        model_id = _extra_model_id(item)
        if not model_id or model_id in seen:
            continue
        models.append(_extra_model(model_id))
        seen.add(model_id)
    return models


def models_for_api(api_cfg: dict) -> list[dict]:
    """当前接口地址对应的模型清单。

    地址不匹配时回落到百炼清单（保证列表永远有选项），
    不在清单里的模型可通过「添加模型」补上。
    """
    provider = provider_by_url(str((api_cfg or {}).get("base_url") or ""))
    provider = provider or provider_by_id("qianwen")
    return models_for_provider(provider, (api_cfg or {}).get("extra_models"))


def find_any_model(api_cfg: dict, model_id: str) -> dict | None:
    model = find_model(model_id)
    if model is not None:
        return model
    for item in (api_cfg or {}).get("extra_models") or []:
        if _extra_model_id(item) == model_id:
            return _extra_model(model_id)
    return None


def ratio_text(model: dict) -> str:
    ratio = float(model.get("ratio", 0.0))
    if ratio <= 0:
        return "免费"
    return f"{ratio:.2f}x"


def price_text(value: float) -> str:
    if value <= 0:
        return "免费"
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"¥{text}"


def resolve_price(api_cfg: dict) -> tuple[float, float, bool]:
    """返回 (输入价, 输出价, 是否内置)，元 / 百万 tokens。价格来自固定目录。"""
    model_id = str((api_cfg or {}).get("model") or "")
    model = find_any_model(api_cfg, model_id)
    if model is not None:
        return float(model["input"]), float(model["output"]), True
    # 未收录的模型名按固定 1.00x 参考计费，仍不提供改价入口
    return BASE_PRICE * EXTRA_RATIO, BASE_PRICE * EXTRA_RATIO, False
