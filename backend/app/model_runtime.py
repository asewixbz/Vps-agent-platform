from __future__ import annotations

from typing import Any

from .kieai_adapter import register_kie_ai_adapter
from .model_adapter import ModelAdapterError, ModelMessage, ModelRequest, ModelResponse, build_model_adapter

register_kie_ai_adapter()


def _normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("text") is not None:
                    parts.append(str(item.get("text")))
                elif item.get("content") is not None:
                    parts.append(_normalize_content(item.get("content")))
            else:
                text = _normalize_content(item)
                if text:
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if content.get("text") is not None:
            return str(content.get("text"))
        if content.get("content") is not None:
            return _normalize_content(content.get("content"))
        return str(content)
    return str(content)


def _normalize_messages(raw_messages: Any, prompt: str | None = None) -> list[ModelMessage]:
    messages: list[dict[str, Any]] = []
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if isinstance(item, dict):
                messages.append(item)
    if not messages and prompt is not None:
        messages = [{"role": "user", "content": prompt}]

    normalized: list[ModelMessage] = []
    for item in messages:
        role = str(item.get("role") or "user")
        content = _normalize_content(item.get("content"))
        normalized.append(
            ModelMessage(
                role=role,  # type: ignore[arg-type]
                content=content,
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return normalized


def build_model_request(payload: dict[str, Any]) -> ModelRequest:
    metadata = dict(payload.get("metadata") or {})
    for key in ("stream", "reasoning", "tools", "tool_choice", "kie_input", "provider_input"):
        if key in payload and payload[key] is not None and key not in metadata:
            metadata[key] = payload[key]

    return ModelRequest(
        messages=_normalize_messages(payload.get("messages"), prompt=payload.get("prompt")),
        model=payload.get("model"),
        temperature=payload.get("temperature"),
        top_p=payload.get("top_p"),
        max_output_tokens=payload.get("max_output_tokens") or payload.get("max_tokens"),
        stop=list(payload.get("stop") or []),
        response_mode=str(payload.get("response_mode") or "text"),
        json_schema=payload.get("json_schema"),
        metadata=metadata,
    )


def chat_model(settings: Any, payload: dict[str, Any]) -> ModelResponse:
    adapter = build_model_adapter(settings)
    request = build_model_request(payload)
    return adapter.chat(request)


def model_health(settings: Any) -> dict[str, Any]:
    adapter = build_model_adapter(settings)
    health = adapter.health()
    return {"status": health.status, "message": health.message, "details": health.details, "adapter": adapter.name}
