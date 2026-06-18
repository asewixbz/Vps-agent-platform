from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Role = Literal["system", "user", "assistant", "tool", "developer"]
ResponseMode = Literal["text", "json"]
HealthStatus = Literal["ok", "unconfigured", "degraded", "error"]


@dataclass(frozen=True)
class ModelMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRequest:
    messages: list[ModelMessage]
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    stop: list[str] = field(default_factory=list)
    response_mode: ResponseMode = "text"
    json_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    text: str = ""
    structured_data: Any = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None
    provider: str | None = None
    usage: ModelUsage | None = None
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelCapabilities:
    supports_streaming: bool = False
    supports_json_mode: bool = False
    supports_structured_output: bool = False
    supports_tool_calls: bool = False
    supports_system_messages: bool = True
    max_context_tokens: int | None = None
    provider: str = "unknown"
    adapter: str = "unknown"
    notes: str = ""


@dataclass(frozen=True)
class ModelHealth:
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelAdapterSpec:
    adapter_name: str = "unconfigured"
    model_name: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


class ModelAdapterError(RuntimeError):
    pass


class ModelAdapter(ABC):
    """Provider-neutral contract for text and structured model calls."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> ModelCapabilities:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ModelHealth:
        raise NotImplementedError

    @abstractmethod
    def chat(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    def structured(self, request: ModelRequest) -> ModelResponse:
        if not self.capabilities.supports_structured_output:
            raise ModelAdapterError(f'model adapter "{self.name}" does not support structured output')
        return self.chat(request)


class UnconfiguredModelAdapter(ModelAdapter):
    def __init__(self, spec: ModelAdapterSpec):
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.adapter_name

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_streaming=False,
            supports_json_mode=False,
            supports_structured_output=False,
            supports_tool_calls=False,
            supports_system_messages=True,
            provider="unconfigured",
            adapter=self._spec.adapter_name,
            notes="No provider is configured yet",
        )

    def health(self) -> ModelHealth:
        return ModelHealth(
            status="unconfigured",
            message="No model adapter has been configured yet",
            details={"adapter": self._spec.adapter_name, "model": self._spec.model_name},
        )

    def chat(self, request: ModelRequest) -> ModelResponse:
        raise ModelAdapterError(
            f'model adapter "{self._spec.adapter_name}" is not configured; cannot run model request'
        )


ModelAdapterFactory = Callable[[ModelAdapterSpec], ModelAdapter]
_ADAPTER_FACTORIES: dict[str, ModelAdapterFactory] = {}


def register_model_adapter(name: str, factory: ModelAdapterFactory, *, overwrite: bool = False) -> None:
    if not overwrite and name in _ADAPTER_FACTORIES:
        raise ModelAdapterError(f'model adapter "{name}" is already registered')
    _ADAPTER_FACTORIES[name] = factory


def available_model_adapters() -> list[str]:
    return sorted({"unconfigured", *_ADAPTER_FACTORIES.keys()})


def resolve_model_adapter(spec: ModelAdapterSpec) -> ModelAdapter:
    if spec.adapter_name in {"", "unconfigured", None}:
        return UnconfiguredModelAdapter(spec)

    factory = _ADAPTER_FACTORIES.get(spec.adapter_name)
    if factory is None:
        raise ModelAdapterError(f'model adapter "{spec.adapter_name}" is not registered')
    return factory(spec)


def build_model_adapter_spec(settings: Any) -> ModelAdapterSpec:
    adapter_name = getattr(settings, "model_adapter_name", "unconfigured")
    model_name = getattr(settings, "model_default_alias", None)
    options = dict(getattr(settings, "model_adapter_options", {}) or {})
    request_timeout_seconds = getattr(settings, "model_request_timeout_seconds", None)
    if request_timeout_seconds is not None and "request_timeout_seconds" not in options:
        options["request_timeout_seconds"] = request_timeout_seconds
    return ModelAdapterSpec(adapter_name=adapter_name, model_name=model_name, options=options)


def build_model_adapter(settings: Any) -> ModelAdapter:
    return resolve_model_adapter(build_model_adapter_spec(settings))
