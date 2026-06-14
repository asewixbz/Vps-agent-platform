from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .job_queue import enqueue_task, queue_size
from .settings import get_settings
from .store import (
    approve_task,
    create_task,
    get_task,
    get_tool,
    init_db,
    list_tasks,
    list_tools,
    register_tool,
    seed_builtin_tools,
)

settings = get_settings()
app = FastAPI(title=settings.app_name)


class ToolRegisterRequest(BaseModel):
    name: str
    kind: Literal["python", "shell", "browser", "model", "messaging"]
    description: str = ""
    entrypoint: str | None = None
    status: Literal["draft", "tested", "trusted", "blocked"] = "draft"
    trust_level: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreateRequest(BaseModel):
    tool_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    auto_run: bool = True
    timeout_seconds: int | None = None


class TaskApprovalRequest(BaseModel):
    note: str | None = None


@app.on_event("startup")
def startup() -> None:
    init_db(settings)
    seed_builtin_tools(settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/phases")
def phases() -> dict[str, Any]:
    return {
        "phase_1": [
            "FastAPI control plane",
            "SQLite persistence",
            "tool registry",
            "approval gate",
            "python runner",
            "shell runner",
        ],
        "phase_2": [
            "Redis queue",
            "worker processes",
            "browser runner",
            "artifact store",
        ],
        "phase_3": [
            "Postgres",
            "stronger policy engine",
            "trust scoring",
        ],
        "phase_4": [
            "automatic tool synthesis",
            "sandbox-first execution",
            "human approval for risky actions",
        ],
    }


@app.get("/tools")
def tools() -> list[dict[str, Any]]:
    return list_tools(settings)


@app.post("/tools/register")
def tools_register(request: ToolRegisterRequest) -> dict[str, Any]:
    existing = get_tool(settings, name=request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f'tool "{request.name}" already exists')
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


@app.get("/tasks")
def tasks() -> list[dict[str, Any]]:
    return list_tasks(settings)


@app.post("/tasks")
def tasks_create(request: TaskCreateRequest) -> dict[str, Any]:
    tool = get_tool(settings, name=request.tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f'tool "{request.tool_name}" not found')

    task = create_task(settings, tool_name=request.tool_name, payload=request.payload, auto_run=request.auto_run)
    if request.auto_run:
        enqueue_task(task["id"], settings)
    return get_task(settings, task_id=task["id"]) or task


@app.get("/tasks/{task_id}")
def tasks_get(task_id: str) -> dict[str, Any]:
    task = get_task(settings, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/queue")
def queue_status() -> dict[str, Any]:
    return {"name": settings.task_queue_name, "size": queue_size(settings)}


@app.post("/tasks/{task_id}/approve")
def tasks_approve(task_id: str, request: TaskApprovalRequest) -> dict[str, Any]:
    task = approve_task(settings, task_id=task_id, note=request.note)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    enqueue_task(task_id, settings)
    return get_task(settings, task_id=task_id) or task
