from __future__ import annotations

from collections import defaultdict
from typing import Any

from .observability import normalize_reason_code, normalize_runtime_event_name


def normalize_runtime_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(event)
    payload = normalized.get("payload")
    if not isinstance(payload, dict):
        payload_json = normalized.pop("payload_json", None)
        if isinstance(payload_json, dict):
            payload = payload_json
        else:
            payload = {}
    normalized["payload"] = payload

    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    if not trace:
        trace = {}
        correlation_id = str(payload.get("correlation_id") or normalized.get("correlation_id") or "").strip()
        if correlation_id:
            trace["correlation_id"] = correlation_id
        runtime_run_id = str(payload.get("runtime_run_id") or normalized.get("runtime_run_id") or "").strip()
        if runtime_run_id:
            trace["runtime_run_id"] = runtime_run_id
        task_id = str(payload.get("task_id") or normalized.get("task_id") or "").strip()
        if task_id:
            trace["task_id"] = task_id
        step_index = normalized.get("step_index") if isinstance(normalized.get("step_index"), int) else payload.get("step_index") if isinstance(payload.get("step_index"), int) else None
        if step_index is not None:
            trace["step_index"] = step_index
        step_id = str(payload.get("step_id") or normalized.get("step_id") or "").strip()
        if step_id:
            trace["step_id"] = step_id
    normalized["trace"] = trace
    if trace.get("correlation_id") is not None:
        normalized["correlation_id"] = trace.get("correlation_id")
    if trace.get("runtime_run_id") is not None:
        normalized["runtime_run_id"] = trace.get("runtime_run_id")
    if trace.get("task_id") is not None:
        normalized["task_id"] = trace.get("task_id")
    if trace.get("step_index") is not None:
        normalized["step_index"] = trace.get("step_index")

    event_name = normalized.get("event_name") or normalized.get("event_type")
    normalized["event_name"] = normalize_runtime_event_name(str(event_name) if event_name is not None else None)
    normalized["reason_code"] = normalize_reason_code(
        str(normalized.get("reason_code") or payload.get("reason_code") or payload.get("blocked_reason") or payload.get("reason") or normalized.get("message") or "")
    )
    if "message" not in normalized:
        normalized["message"] = str(payload.get("summary") or payload.get("blocked_reason") or payload.get("reason") or normalized["event_name"])
    return normalized


def normalize_runtime_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_runtime_event(event) for event in events]


def runtime_events_for_step(events: list[dict[str, Any]], step_index: int | None) -> list[dict[str, Any]]:
    normalized_events = normalize_runtime_events(events)
    if step_index is None:
        return normalized_events
    return [event for event in normalized_events if event.get("step_index") == step_index]


def group_runtime_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_events = normalize_runtime_events(events)
    for event in normalized_events:
        key = str(event.get("step_index") if event.get("step_index") is not None else "run")
        grouped[key].append(event)
    return {
        "events": normalized_events,
        "by_step": dict(grouped),
        "event_count": len(normalized_events),
    }
