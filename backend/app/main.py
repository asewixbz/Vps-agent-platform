from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .dossiers import (
    get_contact_dossier,
    get_project_dossier,
    list_contact_dossiers,
    list_dossiers,
    list_project_dossiers,
    upsert_contact_dossier,
    upsert_project_dossier,
)
from .job_queue import enqueue_task, queue_size
from .memory import (
    add_memory_record_artifact,
    get_memory_record,
    init_memory_schema,
    list_memory_record_artifacts,
    list_memory_records,
    touch_memory_record,
    upsert_memory_record,
)
from .memory_links import (
    add_memory_link,
    init_memory_links_schema,
    list_memory_links,
    list_memory_links_for_entity,
)
from .model_adapter import ModelAdapterError
from .model_runtime import chat_model, model_health as runtime_model_health
from .planner import build_execution_plan
from .runtime_events import group_runtime_events, runtime_events_for_step
from .settings import get_settings
from .store import (
    approve_task,
    create_task,
    get_runtime_run,
    get_task,
    get_tool,
    init_db,
    list_runtime_run_events,
    list_runtime_runs,
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


class ModelChatRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)


class RuntimeRunRequest(BaseModel):
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=5, gt=0, le=50)
    resume_from_step_index: int | None = Field(default=None, gt=0)
    runtime_run_id: str | None = None


class MemoryRecordRequest(BaseModel):
    memory_key: str
    kind: str
    scope_type: str = "global"
    scope_id: str = "global"
    title: str
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None
    source_ref: str | None = None
    importance: int = 0
    pinned: bool = False
    last_accessed_at: str | None = None


class MemoryArtifactRequest(BaseModel):
    artifact_type: str
    artifact_ref: str
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryLinkRequest(BaseModel):
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation_type: str
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContactDossierRequest(BaseModel):
    contact_id: str
    title: str
    summary: str = ""
    content: str = ""
    stage: str | None = None
    next_step: str | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    source_ref: str | None = None
    importance: int = 0
    pinned: bool = False
    last_accessed_at: str | None = None


class ProjectDossierRequest(BaseModel):
    project_id: str
    title: str
    summary: str = ""
    content: str = ""
    stage: str | None = None
    next_step: str | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    source_ref: str | None = None
    importance: int = 0
    pinned: bool = False
    last_accessed_at: str | None = None


@app.on_event("startup")
def startup() -> None:
    init_db(settings)
    init_memory_schema(settings)
    init_memory_links_schema(settings)
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
            "execution planning bridge",
        ],
        "phase_3": [
            "multi-step runtime loop",
            "checkpoint and resume markers",
            "persistent runtime history",
            "runtime event logs",
            "Postgres",
            "stronger policy engine",
            "trust scoring",
        ],
        "phase_4": [
            "durable memory records",
            "project/contact dossiers",
            "memory links",
            "artifact indexing",
            "long-lived workflow context",
        ],
        "phase_5": [
            "workflow templates",
            "ranking workflows",
            "report generation workflows",
            "repeatable monitoring jobs",
        ],
        "phase_6": [
            "automatic tool synthesis",
            "sandbox-first execution",
            "human approval for risky actions",
            "stronger observability and audit logs",
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


@app.get("/model/health")
def model_health() -> dict[str, Any]:
    return runtime_model_health(settings)


@app.post("/model/chat")
def model_chat(request: ModelChatRequest) -> dict[str, Any]:
    if not settings.model_runner_enabled:
        raise HTTPException(status_code=503, detail="model runner is not enabled")
    try:
        response = chat_model(settings, request.payload)
    except ModelAdapterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return asdict(response)


@app.post("/agent/plan")
def agent_plan(request: PlanRequest) -> dict[str, Any]:
    plan = build_execution_plan(settings, goal=request.goal, context=request.context)
    return asdict(plan)


@app.get("/agent/runs")
def agent_runs() -> list[dict[str, Any]]:
    return list_runtime_runs(settings)


@app.get("/agent/runs/{runtime_run_id}")
def agent_run_get(runtime_run_id: str) -> dict[str, Any]:
    run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    return run


@app.get("/agent/runs/{runtime_run_id}/events")
def agent_run_events(
    runtime_run_id: str,
    step_index: int | None = None,
    grouped: bool = False,
) -> dict[str, Any] | list[dict[str, Any]]:
    run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    events = list_runtime_run_events(settings, runtime_run_id=runtime_run_id)
    events = runtime_events_for_step(events, step_index)
    if grouped:
        return group_runtime_events(events)
    return events


@app.post("/agent/run")
def agent_run(request: RuntimeRunRequest) -> dict[str, Any]:
    result = run_agent_runtime(
        settings,
        goal=request.goal,
        context=request.context,
        max_steps=request.max_steps,
        resume_from_step_index=request.resume_from_step_index,
        runtime_run_id=request.runtime_run_id,
    )
    runtime_snapshot = upsert_memory_record(
        settings,
        memory_key=f"runtime_run:{result.runtime_run_id}",
        kind="runtime_summary",
        scope_type="runtime_run",
        scope_id=result.runtime_run_id,
        title=result.goal,
        summary=result.summary,
        content="\n".join(
            [
                f"Goal: {result.goal}",
                f"Status: {result.status}",
                f"Summary: {result.summary}",
                f"Attempts: {result.attempts}",
                f"Iterations: {result.iterations}",
                f"Blocked reason: {result.blocked_reason or ''}",
                f"Resume hint: {result.resume_hint or ''}",
                f"Checkpoint: {json.dumps(result.checkpoint, ensure_ascii=False)}",
            ]
        ).strip(),
        tags=["runtime", "summary", result.status],
        metadata={
            "runtime_run_id": result.runtime_run_id,
            "status": result.status,
            "attempts": result.attempts,
            "iterations": result.iterations,
            "checkpoint": result.checkpoint,
            "blocked_reason": result.blocked_reason,
            "resume_hint": result.resume_hint,
            "plan": asdict(result.plan),
        },
        source="agent_runtime",
        source_ref=result.runtime_run_id,
        importance=1 if result.status == "completed" else 0,
        pinned=False,
    )
    add_memory_link(
        settings,
        source_type="memory_record",
        source_id=runtime_snapshot["id"],
        target_type="artifact",
        target_id=f"runtime_run:{result.runtime_run_id}",
        relation_type="references",
        note="runtime event log",
        metadata={"runtime_run_id": result.runtime_run_id, "status": result.status},
    )

    context = dict(request.context)
    contact_id = context.get("contact_id")
    if isinstance(contact_id, str) and contact_id.strip():
        contact_title = str(context.get("contact_name") or context.get("contact_title") or contact_id)
        contact_dossier = upsert_contact_dossier(
            settings,
            contact_id=contact_id,
            title=contact_title,
            summary=result.summary,
            content="\n".join(
                [
                    f"Goal: {result.goal}",
                    f"Status: {result.status}",
                    f"Attempts: {result.attempts}",
                    f"Iterations: {result.iterations}",
                    f"Resume hint: {result.resume_hint or ''}",
                    f"Checkpoint: {json.dumps(result.checkpoint, ensure_ascii=False)}",
                ]
            ).strip(),
            stage=result.status,
            next_step=result.resume_hint,
            status=result.status,
            tags=["runtime", "contact", "dossier"],
            metadata={
                "runtime_run_id": result.runtime_run_id,
                "goal": result.goal,
                "checkpoint": result.checkpoint,
                "blocked_reason": result.blocked_reason,
            },
            source="agent_runtime",
            source_ref=result.runtime_run_id,
            importance=1 if result.status == "completed" else 0,
        )
        add_memory_link(
            settings,
            source_type="memory_record",
            source_id=runtime_snapshot["id"],
            target_type="memory_record",
            target_id=contact_dossier["id"],
            relation_type="updates",
            note="contact dossier updated from runtime snapshot",
            metadata={"runtime_run_id": result.runtime_run_id, "contact_id": contact_id},
        )
        add_memory_link(
            settings,
            source_type="memory_record",
            source_id=contact_dossier["id"],
            target_type="memory_record",
            target_id=runtime_snapshot["id"],
            relation_type="derived_from",
            note="contact dossier derived from runtime snapshot",
            metadata={"runtime_run_id": result.runtime_run_id, "contact_id": contact_id},
        )

    project_id = context.get("project_id")
    if isinstance(project_id, str) and project_id.strip():
        project_title = str(context.get("project_name") or context.get("project_title") or result.goal)
        project_dossier = upsert_project_dossier(
            settings,
            project_id=project_id,
            title=project_title,
            summary=result.summary,
            content="\n".join(
                [
                    f"Goal: {result.goal}",
                    f"Status: {result.status}",
                    f"Attempts: {result.attempts}",
                    f"Iterations: {result.iterations}",
                    f"Resume hint: {result.resume_hint or ''}",
                    f"Checkpoint: {json.dumps(result.checkpoint, ensure_ascii=False)}",
                ]
            ).strip(),
            stage=result.status,
            next_step=result.resume_hint,
            status=result.status,
            tags=["runtime", "project", "dossier"],
            metadata={
                "runtime_run_id": result.runtime_run_id,
                "goal": result.goal,
                "checkpoint": result.checkpoint,
                "blocked_reason": result.blocked_reason,
            },
            source="agent_runtime",
            source_ref=result.runtime_run_id,
            importance=1 if result.status == "completed" else 0,
        )
        add_memory_link(
            settings,
            source_type="memory_record",
            source_id=runtime_snapshot["id"],
            target_type="memory_record",
            target_id=project_dossier["id"],
            relation_type="updates",
            note="project dossier updated from runtime snapshot",
            metadata={"runtime_run_id": result.runtime_run_id, "project_id": project_id},
        )
        add_memory_link(
            settings,
            source_type="memory_record",
            source_id=project_dossier["id"],
            target_type="memory_record",
            target_id=runtime_snapshot["id"],
            relation_type="derived_from",
            note="project dossier derived from runtime snapshot",
            metadata={"runtime_run_id": result.runtime_run_id, "project_id": project_id},
        )

    return runtime_execution_to_dict(result)


@app.get("/memory/records")
def memory_records(
    kind: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return list_memory_records(
        settings,
        kind=kind,
        scope_type=scope_type,
        scope_id=scope_id,
        query=query,
        limit=limit,
    )


@app.post("/memory/records")
def memory_records_upsert(request: MemoryRecordRequest) -> dict[str, Any]:
    return upsert_memory_record(
        settings,
        memory_key=request.memory_key,
        kind=request.kind,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        title=request.title,
        summary=request.summary,
        content=request.content,
        tags=request.tags,
        metadata=request.metadata,
        artifacts=request.artifacts,
        source=request.source,
        source_ref=request.source_ref,
        importance=request.importance,
        pinned=request.pinned,
        last_accessed_at=request.last_accessed_at,
    )


@app.get("/memory/records/{memory_record_id}")
def memory_record_get(memory_record_id: str) -> dict[str, Any]:
    record = get_memory_record(settings, memory_record_id=memory_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="memory record not found")
    return record


@app.post("/memory/records/{memory_record_id}/touch")
def memory_record_touch(memory_record_id: str) -> dict[str, Any]:
    record = touch_memory_record(settings, memory_record_id=memory_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="memory record not found")
    return record


@app.get("/memory/records/{memory_record_id}/artifacts")
def memory_record_artifacts(memory_record_id: str) -> list[dict[str, Any]]:
    record = get_memory_record(settings, memory_record_id=memory_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="memory record not found")
    return list_memory_record_artifacts(settings, memory_record_id=memory_record_id)


@app.post("/memory/records/{memory_record_id}/artifacts")
def memory_record_artifact_add(memory_record_id: str, request: MemoryArtifactRequest) -> dict[str, Any]:
    record = add_memory_record_artifact(
        settings,
        memory_record_id=memory_record_id,
        artifact_type=request.artifact_type,
        artifact_ref=request.artifact_ref,
        label=request.label,
        metadata=request.metadata,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="memory record not found")
    return record


@app.get("/memory/links")
def memory_links(
    source_type: str | None = None,
    source_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    relation_type: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return list_memory_links(
        settings,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
        relation_type=relation_type,
        query=query,
        limit=limit,
    )


@app.post("/memory/links")
def memory_link_create(request: MemoryLinkRequest) -> dict[str, Any]:
    return add_memory_link(
        settings,
        source_type=request.source_type,
        source_id=request.source_id,
        target_type=request.target_type,
        target_id=request.target_id,
        relation_type=request.relation_type,
        note=request.note,
        metadata=request.metadata,
    )


@app.get("/memory/records/{memory_record_id}/links")
def memory_record_links(
    memory_record_id: str,
    direction: Literal["outbound", "inbound", "both"] = "outbound",
    relation_type: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    outbound = list_memory_links_for_entity(
        settings,
        entity_type="memory_record",
        entity_id=memory_record_id,
        relation_type=relation_type,
        query=query,
        limit=limit,
    )
    if direction == "outbound":
        return outbound
    inbound = list_memory_links(
        settings,
        target_type="memory_record",
        target_id=memory_record_id,
        relation_type=relation_type,
        query=query,
        limit=limit,
    )
    if direction == "inbound":
        return inbound
    combined = {link["id"]: link for link in outbound + inbound}
    return list(combined.values())


@app.get("/dossiers")
def dossiers(
    kind: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if kind == "contact":
        return list_contact_dossiers(settings, query=query, limit=limit)
    if kind == "project":
        return list_project_dossiers(settings, query=query, limit=limit)
    return list_dossiers(settings, query=query, limit=limit)


@app.get("/dossiers/contact")
def contact_dossiers(query: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return list_contact_dossiers(settings, query=query, limit=limit)


@app.post("/dossiers/contact")
def contact_dossier_upsert(request: ContactDossierRequest) -> dict[str, Any]:
    return upsert_contact_dossier(
        settings,
        contact_id=request.contact_id,
        title=request.title,
        summary=request.summary,
        content=request.content,
        stage=request.stage,
        next_step=request.next_step,
        status=request.status,
        tags=request.tags,
        metadata=request.metadata,
        source=request.source,
        source_ref=request.source_ref,
        importance=request.importance,
        pinned=request.pinned,
        last_accessed_at=request.last_accessed_at,
    )


@app.get("/dossiers/contact/{contact_id}")
def contact_dossier_get(contact_id: str) -> dict[str, Any]:
    dossier = get_contact_dossier(settings, contact_id=contact_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="contact dossier not found")
    return dossier


@app.get("/dossiers/project")
def project_dossiers(query: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return list_project_dossiers(settings, query=query, limit=limit)


@app.post("/dossiers/project")
def project_dossier_upsert(request: ProjectDossierRequest) -> dict[str, Any]:
    return upsert_project_dossier(
        settings,
        project_id=request.project_id,
        title=request.title,
        summary=request.summary,
        content=request.content,
        stage=request.stage,
        next_step=request.next_step,
        status=request.status,
        tags=request.tags,
        metadata=request.metadata,
        source=request.source,
        source_ref=request.source_ref,
        importance=request.importance,
        pinned=request.pinned,
        last_accessed_at=request.last_accessed_at,
    )


@app.get("/dossiers/project/{project_id}")
def project_dossier_get(project_id: str) -> dict[str, Any]:
    dossier = get_project_dossier(settings, project_id=project_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="project dossier not found")
    return dossier
