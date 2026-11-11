"""token 计费：从接口 usage 换算费用，并累计今日 / 总耗费。"""
from __future__ import annotations

from datetime import date

DEFAULT_BILLING = {
    "total": 0.0,
    "today": 0.0,
    "date": "",
    "requests": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
}


def today_str() -> str:
    return date.today().isoformat()


def ensure_today(billing: dict) -> dict:
    """跨天后把「今日」归零。"""
    billing.setdefault("date", "")
    if billing.get("date") != today_str():
        billing["date"] = today_str()
        billing["today"] = 0.0
    return billing


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文按 1 字 1 token，其他按 4 字符 1 token。"""
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    others = len(text) - cjk
    return int(cjk + others / 4) + 1


def compute_cost(prompt_tokens: int, completion_tokens: int, api_cfg: dict) -> float:
    from app.core.models import resolve_price

    price_in, price_out, _ = resolve_price(api_cfg)
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


def record_usage(
    billing: dict,
    cost: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict:
    ensure_today(billing)
    billing["total"] = round(float(billing.get("total", 0.0)) + cost, 6)
    billing["today"] = round(float(billing.get("today", 0.0)) + cost, 6)
    billing["requests"] = int(billing.get("requests", 0)) + 1
    billing["prompt_tokens"] = int(billing.get("prompt_tokens", 0)) + prompt_tokens
    billing["completion_tokens"] = int(billing.get("completion_tokens", 0)) + completion_tokens
    return billing


def money(value: float) -> str:
    value = float(value or 0.0)
    if value >= 1:
        return f"¥{value:,.2f}"
    return f"¥{value:.4f}"
