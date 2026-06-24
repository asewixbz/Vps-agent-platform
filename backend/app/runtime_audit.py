from __future__ import annotations

from typing import Any

from .observability import normalize_reason_code, normalize_runtime_event_name


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _unique_values(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        token = str(value)
        if token in seen:
            continue
        seen.add(token)
        unique.append(value)
    return unique


def build_runtime_event_audit_payload(
    event: Any,
    *,
    source: str | None = None,
    context: dict[str, Any] | None = None,
    extra_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(event, dict):
        raw = dict(event)
    else:
        raw = {
            "event_name": getattr(event, "event_name", None),
            "event_type": getattr(event, "event_type", None),
            "status": getattr(event, "status", None),
            "message": getattr(event, "message", None),
            "reason_code": getattr(event, "reason_code", None),
            "summary": getattr(event, "summary", None),
            "blocked_reason": getattr(event, "blocked_reason", None),
            "resume_hint": getattr(event, "resume_hint", None),
            "tool_name": getattr(event, "tool_name", None),
            "kind": getattr(event, "kind", None),
            "task_id": getattr(event, "task_id", None),
            "runtime_run_id": getattr(event, "runtime_run_id", None),
            "step_index": getattr(event, "step_index", None),
            "step_id": getattr(event, "step_id", None),
            "correlation_id": getattr(event, "correlation_id", None),
            "artifact_refs": getattr(event, "artifact_refs", None),
            "details": getattr(event, "details", None),
            "trace": getattr(event, "trace", None),
        }

    details = _coerce_dict(raw.get("details"))
    if extra_details:
        details = {**details, **extra_details}

    trace = _coerce_dict(raw.get("trace"))
    if not trace:
        trace = {}
        correlation_id = str(raw.get("correlation_id") or (context or {}).get("correlation_id") or "").strip()
        if correlation_id:
            trace["correlation_id"] = correlation_id
        runtime_run_id = str(raw.get("runtime_run_id") or (context or {}).get("runtime_run_id") or "").strip()
        if runtime_run_id:
            trace["runtime_run_id"] = runtime_run_id
        task_id = str(raw.get("task_id") or (context or {}).get("task_id") or "").strip()
        if task_id:
            trace["task_id"] = task_id
        step_index = raw.get("step_index") if isinstance(raw.get("step_index"), int) else (context or {}).get("step_index")
        if isinstance(step_index, int):
            trace["step_index"] = step_index
        step_id = str(raw.get("step_id") or (context or {}).get("step_id") or "").strip()
        if step_id:
            trace["step_id"] = step_id

    event_name = str(raw.get("event_name") or raw.get("event_type") or raw.get("status") or "")
    normalized_event_name = normalize_runtime_event_name(event_name)
    reason_code = normalize_reason_code(
        raw.get("reason_code") or raw.get("blocked_reason") or raw.get("resume_hint") or raw.get("message") or raw.get("summary") or normalized_event_name
    )
    message = str(raw.get("message") or raw.get("summary") or raw.get("blocked_reason") or raw.get("resume_hint") or normalized_event_name)
    payload: dict[str, Any] = {
        "event_name": normalized_event_name,
        "event_type": str(raw.get("event_type") or normalized_event_name),
        "status": str(raw.get("status") or normalized_event_name),
        "reason_code": reason_code,
        "message": message,
        "summary": str(raw.get("summary") or message),
        "blocked_reason": str(raw.get("blocked_reason") or "").strip() or None,
        "resume_hint": str(raw.get("resume_hint") or "").strip() or None,
        "tool_name": str(raw.get("tool_name") or details.get("tool_name") or "").strip() or None,
        "kind": str(raw.get("kind") or details.get("kind") or "").strip() or None,
        "task_id": str(raw.get("task_id") or trace.get("task_id") or "").strip() or None,
        "runtime_run_id": str(raw.get("runtime_run_id") or trace.get("runtime_run_id") or "").strip() or None,
        "step_index": raw.get("step_index") if isinstance(raw.get("step_index"), int) else trace.get("step_index"),
        "step_id": str(raw.get("step_id") or trace.get("step_id") or "").strip() or None,
        "policy_source": str(source or raw.get("source") or "runtime"),
        "details": details,
        "trace": trace,
    }
    if payload["tool_name"] is None and isinstance(details.get("tool_name"), str):
        payload["tool_name"] = details["tool_name"]
    if payload["kind"] is None and isinstance(details.get("kind"), str):
        payload["kind"] = details["kind"]
    artifact_refs = raw.get("artifact_refs") if raw.get("artifact_refs") is not None else details.get("artifact_refs")
    normalized_artifact_refs = [str(item).strip() for item in _coerce_list(artifact_refs) if str(item).strip()]
    if normalized_artifact_refs:
        payload["artifact_refs"] = normalized_artifact_refs
    if context:
        payload["context"] = context
    return payload


def summarize_runtime_audit(
    events: list[dict[str, Any]],
    *,
    runtime_run: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    trace_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_events = [build_runtime_event_audit_payload(event, context=trace_context) for event in events]
    normalized_steps = [build_runtime_event_audit_payload(step, context=trace_context) for step in (steps or []) if isinstance(step, dict)]

    event_names = _unique_values([event.get("event_name") for event in normalized_events])
    reason_codes = _unique_values([event.get("reason_code") for event in normalized_events])
    tool_names = _unique_values([event.get("tool_name") for event in [*normalized_events, *normalized_steps]])
    task_ids = _unique_values([event.get("task_id") for event in [*normalized_events, *normalized_steps]])
    step_indices = sorted({event.get("step_index") for event in [*normalized_events, *normalized_steps] if isinstance(event.get("step_index"), int)})
    blocked_count = sum(1 for event in normalized_events if event.get("event_name") == "blocked" or event.get("blocked_reason"))
    approval_count = sum(1 for event in normalized_events if event.get("event_name") == "approved")
    artifact_refs: list[str] = []
    for event in [*normalized_events, *normalized_steps]:
        for ref in event.get("artifact_refs") or []:
            text = str(ref).strip()
            if text and text not in artifact_refs:
                artifact_refs.append(text)

    summary: dict[str, Any] = {
        "event_count": len(normalized_events),
        "step_count": len(normalized_steps),
        "event_names": event_names,
        "reason_codes": reason_codes,
        "tool_names": tool_names,
        "task_ids": task_ids,
        "step_indices": step_indices,
        "blocked_event_count": blocked_count,
        "approval_event_count": approval_count,
        "artifact_refs": artifact_refs,
    }
    if runtime_run is not None:
        summary["runtime_run_id"] = runtime_run.get("id") or runtime_run.get("runtime_run_id")
        summary["status"] = runtime_run.get("status")
        summary["blocked_reason"] = runtime_run.get("blocked_reason")
        summary["resume_hint"] = runtime_run.get("resume_hint")
        summary["summary"] = runtime_run.get("summary")
        summary["attempts"] = runtime_run.get("attempts")
    if trace_context:
        summary["trace_context"] = trace_context
    return summary
