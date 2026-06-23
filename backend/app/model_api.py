from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .model_runtime import chat_model, model_health
from .settings import get_settings

router = APIRouter()
settings = get_settings()


class ModelChatRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/model/health")
def model_health_route() -> dict[str, Any]:
    return model_health(settings)


@router.post("/model/chat")
def model_chat_route(request: ModelChatRequest) -> dict[str, Any]:
    if not settings.model_runner_enabled:
        raise HTTPException(status_code=400, detail="model runner is not enabled")

    response = chat_model(settings, request.payload)
    return {
        "text": response.text,
        "structured_data": response.structured_data,
        "tool_calls": response.tool_calls,
        "finish_reason": response.finish_reason,
        "model": response.model,
        "provider": response.provider,
        "usage": asdict(response.usage) if response.usage else None,
        "raw": response.raw,
        "metadata": response.metadata,
    }
