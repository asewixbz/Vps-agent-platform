from __future__ import annotations

import re
import traceback
import uuid
from typing import Any

STANDARD_RUNTIME_EVENT_NAMES = {
    "started",
    "planned",
    "approved",
    "blocked",
    "executed",
    "failed",
    "resumed",
    "completed",
}

_EVENT_NAME_ALIASES = {
    "running": "started",
    "pending_approval": "blocked",
    "pending_input": "blocked",
    "partial": "blocked",
    "blocked": "blocked",
    "failed": "failed",
    "completed": "completed",
    "started": "started",
    "planned": "planned",
    "approved": "approved",
    "executed": "executed",
    "resumed": "resumed",
}

_REASON_CODE_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_runtime_event_name(event_name: str | None, *, fallback: str = "blocked") -> str:
    normalized = str(event_name or "").strip().lower()
    if not normalized:
        return fallback
    return _EVENT_NAME_ALIASES.get(normalized, normalized if normalized in STANDARD_RUNTIME_EVENT_NAMES else fallback)


def normalize_reason_code(reason: str | None, *, fallback: str = "unknown_error") -> str:
    normalized = str(reason or "").strip().lower()
    if not normalized:
        return fallback
    normalized = normalized.replace("/", "_")
    normalized = _REASON_CODE_PATTERN.sub("_", normalized)
    normalized = normalized.strip("_")
    return normalized or fallback


def normalize_policy_reason_code(reason: str | None, *, fallback: str = "unknown_error") -> str:
    return normalize_reason_code(reason, fallback=fallback)


def _coerce_details(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def build_policy_audit_payload(
    decision: Any,
    *,
    source: str | None = None,
    context: dict[str, Any] | None = None,
    extra_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(decision, dict):
        raw = dict(decision)
    else:
        raw = {
            "decision": getattr(decision, "decision", None),
            "allowed": getattr(decision, "allowed", None),
            "requires_approval": getattr(decision, "requires_approval", None),
            "reason": getattr(decision, "reason", None),
            "reason_code": getattr(decision, "reason_code", None),
            "trust_level": getattr(decision, "trust_level", None),
            "details": getattr(decision, "details", None),
        }

    details = _coerce_details(raw.get("details"))
    if extra_details:
        details = {**details, **extra_details}

    policy_sources = details.get("policy_sources")
    normalized_policy_sources = [str(item) for item in policy_sources if item is not None] if isinstance(policy_sources, list) else []
    policy_source = str(source or raw.get("policy_source") or details.get("policy_source") or (normalized_policy_sources[-1] if normalized_policy_sources else "policy"))
    if raw.get("decision"):
        decision_name = str(raw.get("decision"))
    elif raw.get("requires_approval") and not raw.get("allowed"):
        decision_name = "approval_required"
    elif raw.get("allowed"):
        decision_name = "allow"
    else:
        decision_name = "deny"
    reason = str(raw.get("reason") or "")
    reason_code = normalize_policy_reason_code(raw.get("reason_code") or reason or decision_name)
    trust_level = int(raw.get("trust_level") or 0)
    summary_parts = [decision_name, reason_code]
    if reason:
        summary_parts.append(reason)
    payload: dict[str, Any] = {
        "decision": decision_name,
        "allowed": bool(raw.get("allowed")),
        "requires_approval": bool(raw.get("requires_approval")),
        "reason": reason,
        "reason_code": reason_code,
        "trust_level": trust_level,
        "policy_source": policy_source,
        "decision_summary": " | ".join(part for part in summary_parts if part),
        "details": details,
    }
    if normalized_policy_sources:
        payload["policy_sources"] = normalized_policy_sources
    matched_trigger = details.get("matched_trigger")
    if matched_trigger is not None:
        payload["matched_trigger"] = matched_trigger
    if context:
        payload["context"] = context
    return payload


def build_trace_context(
    *,
    correlation_id: str | None = None,
    runtime_run_id: str | None = None,
    task_id: str | None = None,
    step_index: int | None = None,
    step_id: str | None = None,
    memory_record_id: str | None = None,
    artifact_ref: str | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "correlation_id": correlation_id or str(uuid.uuid4()),
    }
    if runtime_run_id is not None:
        trace["runtime_run_id"] = runtime_run_id
    if task_id is not None:
        trace["task_id"] = task_id
    if step_index is not None:
        trace["step_index"] = step_index
    if step_id is not None:
        trace["step_id"] = step_id
    if memory_record_id is not None:
        trace["memory_record_id"] = memory_record_id
    if artifact_ref is not None:
        trace["artifact_ref"] = artifact_ref
    return trace


def attach_trace(payload: dict[str, Any] | None, trace: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload or {})
    merged["trace"] = trace
    merged.setdefault("correlation_id", trace.get("correlation_id"))
    if trace.get("runtime_run_id") is not None:
        merged.setdefault("runtime_run_id", trace.get("runtime_run_id"))
    if trace.get("task_id") is not None:
        merged.setdefault("task_id", trace.get("task_id"))
    if trace.get("step_index") is not None:
        merged.setdefault("step_index", trace.get("step_index"))
    if trace.get("step_id") is not None:
        merged.setdefault("step_id", trace.get("step_id"))
    return merged


def safe_stack_details(exc: BaseException, *, max_frames: int = 12) -> list[str]:
    formatted = traceback.format_exception(type(exc), exc, exc.__traceback__)
    if len(formatted) <= max_frames:
        return [line.rstrip("\n") for line in formatted]
    tail = formatted[-max_frames:]
    return [line.rstrip("\n") for line in tail]


def build_structured_error(
    reason_code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    stack: list[str] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason_code": normalize_reason_code(reason_code),
        "message": message,
        "severity": severity,
    }
    if details:
        payload["details"] = details
    if trace:
        payload["trace"] = trace
    if stack:
        payload["stack"] = stack
    return payload


def structured_error_from_exception(
    reason_code: str,
    exc: BaseException,
    *,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    return build_structured_error(
        reason_code,
        message or str(exc),
        details=details,
        trace=trace,
        stack=safe_stack_details(exc),
        severity=severity,
    )


def reason_code_from_text(reason: str | None, *, fallback: str = "unknown_error") -> str:
    return normalize_reason_code(reason, fallback=fallback)
