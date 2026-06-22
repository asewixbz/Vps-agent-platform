from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .artifact_lifecycle import cleanup_artifact_roots
from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .observability import build_trace_context
from .planner import build_execution_plan
from .runtime_events import group_runtime_events, normalize_runtime_events, runtime_events_for_step
from .runtime_trace import build_runtime_run_trace
from .settings import get_settings
from .store import get_runtime_run, list_runtime_run_events, list_runtime_runs

router = APIRouter()
settings = get_settings()


class AgentPlanRequest(BaseModel):
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = 5
    resume_from_step_index: int | None = None
    runtime_run_id: str | None = None


@router.post("/agent/plan")
def agent_plan(request: AgentPlanRequest) -> dict[str, object]:
    plan = build_execution_plan(settings, goal=request.goal, context=request.context)
    return asdict(plan)


@router.post("/agent/run")
def agent_run(request: AgentRunRequest) -> dict[str, object]:
    trace_context = build_trace_context(
        correlation_id=str(request.context.get("correlation_id") or request.runtime_run_id or "").strip() or None,
        runtime_run_id=request.runtime_run_id,
    )
    execution_context = dict(request.context)
    execution_context.setdefault("correlation_id", trace_context["correlation_id"])
    execution_context.setdefault("runtime_run_id", request.runtime_run_id or trace_context.get("runtime_run_id"))
    execution = run_agent_runtime(
        settings,
        goal=request.goal,
        context=execution_context,
        max_steps=request.max_steps,
        resume_from_step_index=request.resume_from_step_index,
        runtime_run_id=request.runtime_run_id,
    )
    return runtime_execution_to_dict(execution)


@router.get("/agent/runs")
def agent_runs(limit: int = 100) -> list[dict[str, object]]:
    return list_runtime_runs(settings, limit=limit)


@router.get("/agent/runs/{runtime_run_id}")
def agent_run_show(runtime_run_id: str) -> dict[str, object]:
    runtime_run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if runtime_run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    events = normalize_runtime_events(list_runtime_run_events(settings, runtime_run_id=runtime_run_id, limit=1))
    return {
        **runtime_run,
        "correlation_id": str((runtime_run.get("context") or {}).get("correlation_id") or runtime_run.get("correlation_id") or runtime_run_id),
        "event_count": runtime_run.get("event_count") or len(events),
    }


@router.get("/agent/runs/{runtime_run_id}/events")
def agent_run_events(runtime_run_id: str, step_index: int | None = None, grouped: bool = False, limit: int = 100) -> dict[str, object] | list[dict[str, object]]:
    runtime_run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if runtime_run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    events = list_runtime_run_events(settings, runtime_run_id=runtime_run_id, limit=limit)
    if step_index is not None:
        events = runtime_events_for_step(events, step_index)
    normalized = normalize_runtime_events(events)
    if grouped:
        return group_runtime_events(normalized)
    return normalized


@router.get("/agent/runs/{runtime_run_id}/trace")
def agent_run_trace(runtime_run_id: str, step_index: int | None = None, limit: int = 100, depth: int = 2) -> dict[str, object]:
    trace = build_runtime_run_trace(settings, runtime_run_id=runtime_run_id, limit=limit, depth=depth, step_index=step_index)
    if trace is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    return trace


@router.post("/artifacts/cleanup")
def cleanup_artifacts(dry_run: bool = False, compress_logs: bool = False) -> dict[str, object]:
    return cleanup_artifact_roots(settings, dry_run=dry_run, compress_logs=compress_logs)
