from __future__ import annotations

from collections import defaultdict
from typing import Any


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
