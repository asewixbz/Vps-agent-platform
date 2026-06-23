from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .job_queue import get_queue
from .settings import get_settings
from .store import approve_task, connect, create_task, get_task, list_tasks, list_tools, register_tool, update_task, utc_now

router = APIRouter()
settings = get_settings()


class ToolRegisterRequest(BaseModel):
    name: str
    kind: str
    description: str = ""
    entrypoint: str | None = None
    status: str = "draft"
    trust_level: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreateRequest(BaseModel):
    tool_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    auto_run: bool = True
    timeout_seconds: int | None = None


class TaskApproveRequest(BaseModel):
    note: str | None = None


def _queue_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "name": settings.task_queue_name,
        "healthy": False,
        "size": None,
    }
    try:
        queue = get_queue()
        snapshot["healthy"] = queue.ping()
        snapshot["size"] = queue.size()
    except Exception as exc:  # pragma: no cover - defensive safety net
        snapshot["error"] = str(exc)
    return snapshot


def _enqueue_task(task_id: str) -> None:
    get_queue().enqueue(task_id)


def _queue_or_block(task_id: str) -> dict[str, Any]:
    try:
        _enqueue_task(task_id)
    except Exception as exc:
        updated = update_task(
            settings,
            task_id=task_id,
            status="blocked",
            reason=f"queue unavailable: {exc}",
            finished_at=utc_now(),
            result_json={"ok": False, "duration_ms": 0, "artifacts": {}, "queue_error": str(exc)},
        )
        if updated is not None:
            return updated
    task = get_task(settings, task_id=task_id)
    return task or {}


@router.get("/health")
def health() -> dict[str, object]:
    status = "ok"
    database = {"healthy": True}
    try:
        conn = connect(settings.db_path)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive safety net
        status = "degraded"
        database = {"healthy": False, "error": str(exc)}

    queue = _queue_snapshot()
    if not queue.get("healthy", False):
        status = "degraded"

    return {
        "status": status,
        "app": settings.app_name,
        "database": database,
        "queue": queue,
        "features": {
            "browser_runner_enabled": settings.browser_runner_enabled,
            "model_runner_enabled": settings.model_runner_enabled,
        },
    }


@router.get("/phases")
def phases() -> dict[str, list[str]]:
    return {
        "phase_1": [
            "CLI-first operational layer",
            "health, queue, tools, and task management",
            "approval flow and local execution entrypoints",
        ],
        "phase_2": [
            "provider-agnostic model adapter",
            "model health and chat endpoints",
            "execution planner bridge",
        ],
        "phase_3": [
            "agent runtime loop",
            "checkpoint and resume markers",
            "persistent runtime history and event logs",
        ],
        "phase_4": [
            "durable memory records",
            "project/contact dossiers",
            "memory links and provenance views",
        ],
        "phase_5": [
            "workflow templates",
            "custom workflow template persistence",
            "recurring schedule dispatch and compare helpers",
        ],
        "phase_6": [
            "runtime hardening",
            "sandboxing and isolation",
            "security polish and operational controls",
        ],
    }


@router.get("/queue")
def queue_info() -> dict[str, object]:
    queue = _queue_snapshot()
    if not queue.get("healthy", False):
        queue.setdefault("size", 0)
    return queue


@router.get("/tools")
def tools() -> list[dict[str, object]]:
    return list_tools(settings)


@router.post("/tools/register")
def register_tool_route(request: ToolRegisterRequest) -> dict[str, object]:
    return register_tool(
        settings,
        name=request.name,
        kind=request.kind,
        description=request.description,
        entrypoint=request.entrypoint,
        status=request.status,
        trust_level=request.trust_level,
        metadata=request.metadata,
    )


@router.get("/tasks")
def tasks() -> list[dict[str, object]]:
    return list_tasks(settings)


@router.post("/tasks")
def create_task_route(request: TaskCreateRequest) -> dict[str, object]:
    payload = dict(request.payload)
    if request.timeout_seconds is not None:
        payload["timeout_seconds"] = request.timeout_seconds
    task = create_task(
        settings,
        tool_name=request.tool_name,
        payload=payload,
        auto_run=request.auto_run,
    )
    if request.auto_run and task.get("status") == "queued" and task.get("id"):
        task = _queue_or_block(str(task["id"]))
    return task


@router.get("/tasks/{task_id}")
def get_task_route(task_id: str) -> dict[str, object]:
    task = get_task(settings, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/tasks/{task_id}/approve")
def approve_task_route(task_id: str, request: TaskApproveRequest) -> dict[str, object]:
    task = approve_task(settings, task_id=task_id, note=request.note)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.get("status") == "queued" and task.get("id"):
        task = _queue_or_block(str(task["id"]))
    return task
