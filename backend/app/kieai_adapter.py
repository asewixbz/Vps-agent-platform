from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model_adapter import (
    ModelAdapter,
    ModelAdapterError,
    ModelCapabilities,
    ModelHealth,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ModelAdapterSpec,
    register_model_adapter,
)

PROVIDER_NAME = "kie_ai"
DEFAULT_BASE_URL = "https://api.kie.ai"
DEFAULT_ENDPOINT = "/codex/v1/responses"
DEFAULT_MODEL = "gpt-5-5"


def _coerce_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in {"input_text", "output_text"} and item.get("text") is not None:
                    parts.append(str(item.get("text")))
                elif item.get("text") is not None:
                    parts.append(str(item.get("text")))
                elif item.get("content") is not None:
                    parts.append(_coerce_text(item.get("content")))
            else:
                piece = _coerce_text(item)
                if piece:
                    parts.append(piece)
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if content.get("text") is not None:
            return str(content.get("text"))
        if content.get("content") is not None:
            return _coerce_text(content.get("content"))
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _json_response(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
    except HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        parsed_error: Any
        try:
            parsed_error = json.loads(raw_error) if raw_error.strip() else {}
        except json.JSONDecodeError:
            parsed_error = raw_error.strip() or {}

        message = _extract_error_message(parsed_error, exc.code)
        raise ModelAdapterError(f"Kie.ai request failed ({exc.code} {exc.reason}): {message}") from exc
    except URLError as exc:
        raise ModelAdapterError(f"Kie.ai request failed: {exc.reason}") from exc


def _extract_error_message(payload: Any, status_code: int | None = None) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or payload.get("msg") or json.dumps(error, ensure_ascii=False)
            error_type = error.get("type")
            if error_type:
                return f"{error_type}: {message}"
            return str(message)
        if payload.get("msg"):
            return str(payload["msg"])
        if payload.get("message"):
            return str(payload["message"])
        if status_code is not None:
            return f"HTTP {status_code}"
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if status_code is not None:
        return f"HTTP {status_code}"
    return "unknown provider error"


class KieAIModelAdapter(ModelAdapter):
    def __init__(self, spec: ModelAdapterSpec):
        self._spec = spec
        options = dict(spec.options or {})
        self._api_key = str(options.get("api_key") or options.get("token") or options.get("bearer_token") or "").strip()
        self._base_url = str(options.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self._endpoint = str(options.get("endpoint") or DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
        self._default_model = str(options.get("default_model") or spec.model_name or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self._request_timeout_seconds = int(options.get("request_timeout_seconds") or 120)

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_streaming=True,
            supports_json_mode=False,
            supports_structured_output=False,
            supports_tool_calls=True,
            supports_system_messages=True,
            provider="kie_ai",
            adapter=self.name,
            notes="Kie.ai responses-style adapter backed by /codex/v1/responses",
        )

    def health(self) -> ModelHealth:
        if not self._api_key:
            return ModelHealth(
                status="unconfigured",
                message="Kie.ai API key is not configured",
                details={
                    "provider": "kie_ai",
                    "base_url": self._base_url,
                    "endpoint": self._endpoint,
                    "model": self._default_model,
                },
            )

        return ModelHealth(
            status="ok",
            message="Kie.ai adapter is configured",
            details={
                "provider": "kie_ai",
                "base_url": self._base_url,
                "endpoint": self._endpoint,
                "model": self._default_model,
                "request_timeout_seconds": self._request_timeout_seconds,
                "api_key_present": True,
            },
        )

    def _build_input(self, request: ModelRequest) -> list[dict[str, Any]] | Any:
        provider_input = request.metadata.get("kie_input") or request.metadata.get("provider_input")
        if provider_input is not None:
            return provider_input

        input_messages: list[dict[str, Any]] = []
        for message in request.messages:
            input_messages.append(
                {
                    "role": message.role,
                    "content": [
                        {
                            "type": "input_text",
                            "text": _coerce_text(message.content),
                        }
                    ],
                }
            )
        return input_messages

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "stream": bool(request.metadata.get("stream", False)),
            "input": self._build_input(request),
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.stop:
            payload["stop"] = request.stop
        if request.metadata.get("reasoning") is not None:
            payload["reasoning"] = request.metadata["reasoning"]
        if request.metadata.get("tools") is not None:
            payload["tools"] = request.metadata["tools"]
        if request.metadata.get("tool_choice") is not None:
            payload["tool_choice"] = request.metadata["tool_choice"]

        return payload

    def _normalize_response(self, response: dict[str, Any], request: ModelRequest) -> ModelResponse:
        output = response.get("output") or []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        reasoning_blocks: list[dict[str, Any]] = []

        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "message":
                    content = item.get("content") or []
                    if isinstance(content, list):
                        for content_item in content:
                            if not isinstance(content_item, dict):
                                continue
                            content_type = content_item.get("type")
                            if content_type == "output_text":
                                text_parts.append(str(content_item.get("text") or ""))
                            elif content_type in {"tool_call", "function_call"}:
                                tool_calls.append(content_item)
                elif item_type in {"tool_call", "function_call"}:
                    tool_calls.append(item)
                elif item_type == "reasoning":
                    reasoning_blocks.append(item)

        text = "".join(text_parts)
        structured_data: Any = None
        if request.response_mode == "json":
            try:
                structured_data = json.loads(text)
            except Exception:
                structured_data = response

        usage_payload = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        usage = None
        if isinstance(usage_payload, dict) and usage_payload:
            usage = ModelUsage(
                prompt_tokens=usage_payload.get("input_tokens"),
                completion_tokens=usage_payload.get("output_tokens"),
                total_tokens=usage_payload.get("total_tokens"),
            )

        metadata: dict[str, Any] = {
            "status": response.get("status"),
            "credits_consumed": response.get("credits_consumed"),
            "reasoning": reasoning_blocks,
        }
        if isinstance(usage_payload, dict) and usage_payload.get("input_tokens_details") is not None:
            metadata["usage_details"] = usage_payload.get("input_tokens_details")

        return ModelResponse(
            text=text,
            structured_data=structured_data,
            tool_calls=tool_calls,
            finish_reason=response.get("status"),
            model=response.get("model") or request.model or self._default_model,
            provider="kie_ai",
            usage=usage,
            raw=response,
            metadata=metadata,
        )

    def chat(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key:
            raise ModelAdapterError("Kie.ai API key is not configured")

        payload = self._build_payload(request)
        response = _json_response(
            "POST",
            f"{self._base_url}{self._endpoint}",
            payload,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._request_timeout_seconds,
        )
        return self._normalize_response(response, request)


def register_kie_ai_adapter() -> None:
    register_model_adapter(PROVIDER_NAME, lambda spec: KieAIModelAdapter(spec), overwrite=True)
