from __future__ import annotations

from typing import Any

from .artifact_lifecycle import normalize_artifact_entry, normalize_artifact_manifest
from .observability import build_trace_context, normalize_reason_code
from .memory_graph import build_runtime_run_provenance
from .memory import get_memory_record
from .store import get_runtime_run, get_task, list_runtime_run_events
from .runtime_events import group_runtime_events, normalize_runtime_events


def _step_artifacts(step: dict[str, Any]) -> list[dict[str, Any]]:
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    normalized: list[dict[str, Any]] = []
    if not isinstance(artifacts, dict):
        return normalized

    if "artifacts" in artifacts and isinstance(artifacts.get("artifacts"), list):
        manifest = normalize_artifact_manifest(
            {
                "artifacts": artifacts.get("artifacts"),
                "artifact_paths": artifacts.get("artifact_paths") if isinstance(artifacts.get("artifact_paths"), list) else [],
                "scope_type": "task",
                "scope_id": str(step.get("task_id") or step.get("index") or "step"),
                "task_id": step.get("task_id"),
                "runtime_run_id": step.get("runtime_run_id"),
                "correlation_id": step.get("correlation_id"),
            },
            source="runtime_trace",
        )
        if manifest is not None:
            normalized.extend(manifest.get("artifacts") or [])

    for key, value in artifacts.items():
        if key == "artifacts":
            continue
        if key == "artifact_paths" and isinstance(value, list):
            for ref in value:
                if isinstance(ref, str):
                    artifact = normalize_artifact_entry({"artifact_type": "file", "artifact_ref": ref, "label": ref.split("/")[-1]})
                    if artifact is not None:
                        normalized.append(artifact)
            continue
        if not isinstance(value, str):
            continue
        artifact = normalize_artifact_entry({"artifact_type": "file", "artifact_ref": value, "label": key})
        if artifact is not None:
            normalized.append(artifact)
    return normalized


def _step_reason(step: dict[str, Any]) -> dict[str, Any] | None:
    detail = str(step.get("detail") or "").strip()
    stderr = str(step.get("stderr") or "").strip()
    status = str(step.get("status") or "").strip().lower()
    if not detail and not stderr and status not in {"blocked", "failed", "pending_approval", "pending_input"}:
        return None
    message = detail or stderr or status or "step failed"
    return {
        "reason_code": normalize_reason_code(detail or stderr or status or "unknown_error"),
        "message": message,
    }


def build_runtime_run_trace(settings, *, runtime_run_id: str, limit: int = 100, depth: int = 2, step_index: int | None = None) -> dict[str, Any] | None:
    runtime_run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if runtime_run is None:
        return None

    raw_events = list_runtime_run_events(settings, runtime_run_id=runtime_run_id, limit=limit)
    events = normalize_runtime_events(raw_events)
    if step_index is not None:
        events = [event for event in events if event.get("step_index") == step_index]
    grouped_events = group_runtime_events(events)

    provenance = build_runtime_run_provenance(settings, runtime_run_id=runtime_run_id, limit=limit, depth=depth)
    runtime_snapshot = provenance.get("memory_snapshot") if isinstance(provenance, dict) else None
    trace_context = build_trace_context(
        correlation_id=str((runtime_run.get("context") or {}).get("correlation_id") or runtime_run.get("correlation_id") or ""),
        runtime_run_id=runtime_run_id,
    )

    steps_payload = runtime_run.get("steps") if isinstance(runtime_run.get("steps"), list) else []
    if step_index is not None:
        steps_payload = [step for step in steps_payload if isinstance(step, dict) and int(step.get("index") or 0) == step_index]
    steps: list[dict[str, Any]] = []
    artifact_map: dict[str, dict[str, Any]] = {}
    task_ids: list[str] = []
    for raw_step in steps_payload:
        if not isinstance(raw_step, dict):
            continue
        artifacts = _step_artifacts(raw_step)
        for artifact in artifacts:
            artifact_ref = str(artifact.get("artifact_ref") or "").strip()
            if artifact_ref and artifact_ref not in artifact_map:
                artifact_map[artifact_ref] = artifact
        task_id = raw_step.get("task_id")
        if isinstance(task_id, str) and task_id and task_id not in task_ids:
            task_ids.append(task_id)
        task = get_task(settings, task_id=task_id) if isinstance(task_id, str) and task_id else None
        step_trace = build_trace_context(
            correlation_id=trace_context["correlation_id"],
            runtime_run_id=runtime_run_id,
            task_id=task_id if isinstance(task_id, str) else None,
            step_index=int(raw_step.get("index") or 0) or None,
        )
        reason = _step_reason(raw_step)
        if reason is None and isinstance(raw_step.get("status"), str) and raw_step["status"] not in {"completed", "observed", "skipped"}:
            reason = {
                "reason_code": normalize_reason_code(raw_step.get("status"), fallback="unknown_error"),
                "message": str(raw_step.get("detail") or raw_step.get("status") or "step status changed"),
            }
        step_entry = {
            **raw_step,
            "trace": step_trace,
            "reason": reason,
            "task": task,
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
        }
        steps.append(step_entry)

    provenance_root = provenance.get("provenance", {}) if isinstance(provenance, dict) else {}
    memory_record_id = None
    if isinstance(runtime_snapshot, dict):
        memory_record_id = str(runtime_snapshot.get("id") or "") or None
    if memory_record_id is None and isinstance(provenance_root, dict):
        memory_record_id = str((provenance_root.get("root") or {}).get("id") or "") or None
    memory_record = get_memory_record(settings, memory_record_id=memory_record_id) if memory_record_id else None

    if memory_record is not None and isinstance(provenance_root, dict):
        provenance_root.setdefault("root_memory_record", memory_record)

    artifacts = list(artifact_map.values())
    if isinstance(runtime_snapshot, dict):
        snapshot_artifacts = runtime_snapshot.get("artifacts") if isinstance(runtime_snapshot.get("artifacts"), list) else []
        for artifact in snapshot_artifacts:
            if not isinstance(artifact, dict):
                continue
            normalized = normalize_artifact_entry(artifact)
            if normalized is None:
                continue
            artifact_ref = str(normalized.get("artifact_ref") or "").strip()
            if artifact_ref and artifact_ref not in artifact_map:
                artifact_map[artifact_ref] = normalized
        artifacts = list(artifact_map.values())

    navigation = {
        "correlation_id": trace_context["correlation_id"],
        "runtime_run_id": runtime_run_id,
        "task_ids": task_ids,
        "step_count": len(steps),
        "artifact_refs": [artifact["artifact_ref"] for artifact in artifacts],
        "memory_record_id": memory_record_id,
    }

    return {
        "trace_context": trace_context,
        "runtime_run": {
            **runtime_run,
            "correlation_id": trace_context["correlation_id"],
        },
        "events": events,
        "grouped_events": grouped_events,
        "provenance": provenance,
        "memory_snapshot": runtime_snapshot,
        "memory_record": memory_record,
        "steps": steps,
        "artifacts": artifacts,
        "navigation": navigation,
        "event_count": len(events),
        "step_count": len(steps),
    }
