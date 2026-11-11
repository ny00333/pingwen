"""AI 作答：任意 OpenAI 兼容接口（DeepSeek / 通义千问 / 智谱 / OpenAI / Kimi…）。"""
from __future__ import annotations

import base64

SYSTEM_PROMPT = """你是一名严谨、耐心的解题助手。用户会给你一道从屏幕截图中识别出来的题目。

请遵守：
1. 先在心里纠正常见的 OCR 错误（错别字、断行、公式符号缺失），再理解题意；
2. 直接给出最终答案，选择题请写明选项字母和内容；
3. 若要求「简洁」：给出答案 + 3~6 条关键推导；若要求「详细」：给出完整解析与易错点；
   若要求「只给答案」：只输出最终答案，不写解析、步骤或解释；
4. 数学公式用 LaTeX 表示，例如 $x^2$；代码用 Markdown 代码块；
5. 若题目信息确实缺失、无法唯一作答，请指出缺少什么条件，不要编造题目；
6. 全部使用中文回答。"""

STYLE_HINTS = {
    "concise": "请用简洁风格：先给答案，再给关键步骤。",
    "detailed": "请用详细风格：逐步推导，并补充易错点或相关知识点。",
    "answer_only": "只给最终答案：选择题只写选项字母和内容，填空/计算只写结果；不要写任何解析、推导、步骤或解释。",
}


class AIError(Exception):
    """对用户可读的 AI 调用错误。"""


def _describe_error(exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if "401" in lowered or "invalid api key" in lowered or "unauthorized" in lowered:
        return "API Key 无效或未授权，请在设置中检查 Key。"
    if "404" in lowered or "not found" in lowered:
        return "接口地址或模型名称不存在，请检查 Base URL 与模型名。"
    if "429" in lowered or "rate limit" in lowered:
        return "请求过于频繁或额度不足，请稍后再试。"
    if "timeout" in lowered or "timed out" in lowered:
        return "请求超时，请检查网络或调大超时时间。"
    if "connect" in lowered or "network" in lowered or "ssl" in lowered:
        return f"网络连接失败：{text[:180]}"
    return text[:300] or "未知错误"


def _client(api_cfg: dict):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIError("缺少 openai 依赖，请先执行 pip install -r requirements.txt") from exc
    return OpenAI(
        api_key=api_cfg.get("api_key") or "missing",
        base_url=api_cfg.get("base_url") or None,
        timeout=float(api_cfg.get("timeout") or 90),
    )


def _build_messages(question: str | None, image_png: bytes | None, style: str):
    hint = STYLE_HINTS.get(style, STYLE_HINTS["concise"])
    if image_png is not None:
        encoded = base64.b64encode(image_png).decode("ascii")
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            },
            {
                "type": "text",
                "text": f"请识别图片中的题目并解答。{hint}",
            },
        ]
    else:
        user_content = f"题目如下（来自屏幕识别，可能有错字）：\n\n{question}\n\n{hint}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _create_stream(client, api_cfg: dict, messages):
    """请求流式补全。

    - Qwen3 系列默认会先「思考」，首字延迟可到 10~20 秒；这里关闭 thinking，
      实测首字延迟降到 1 秒以内。
    - 同时尽量申请 usage；部分兼容服务不支持这些参数时逐级退回。
    """
    model = str(api_cfg.get("model") or "")
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": float(api_cfg.get("temperature", 0.2)),
        "max_tokens": int(api_cfg.get("max_tokens", 2048)),
        "stream": True,
    }
    fast = dict(kwargs)
    if model.startswith("qwen3"):
        fast["extra_body"] = {"enable_thinking": False}
    variants = [
        (fast, {"stream_options": {"include_usage": True}}),
        (fast, {}),
        (kwargs, {"stream_options": {"include_usage": True}}),
        (kwargs, {}),
    ]
    last_error: Exception | None = None
    for params, extra in variants:
        try:
            return client.chat.completions.create(**params, **extra)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            lowered = str(exc).lower()
            if not any(
                key in lowered
                for key in ("stream_options", "enable_thinking", "unknown", "400")
            ):
                raise
    raise last_error if last_error else AIError("请求失败")


def stream_answer(
    api_cfg: dict,
    style: str = "concise",
    question: str | None = None,
    image_png: bytes | None = None,
    usage_sink: dict | None = None,
):
    """流式返回模型输出的文本片段。

    usage_sink 会被填入接口返回的 prompt_tokens / completion_tokens / total_tokens，
    供上层换算费用；接口不返回 usage 时保持为空，由调用方估算。
    """
    try:
        client = _client(api_cfg)
        stream = _create_stream(
            client, api_cfg, _build_messages(question, image_png, style)
        )
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None and usage_sink is not None:
                usage_sink["prompt_tokens"] = int(getattr(usage, "prompt_tokens", 0) or 0)
                usage_sink["completion_tokens"] = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
                usage_sink["total_tokens"] = int(
                    getattr(usage, "total_tokens", 0)
                    or usage_sink["prompt_tokens"] + usage_sink["completion_tokens"]
                )
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                yield content
    except AIError:
        raise
    except Exception as exc:
        raise AIError(_describe_error(exc)) from exc
