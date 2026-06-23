from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .settings import get_settings
from .store import get_runtime_run
from .workflow_schedules import register_workflow_schedule
from .workflow_template_registry import delete_custom_workflow_template, list_custom_workflow_templates, upsert_custom_workflow_template
from .workflow_templates import (
    build_workflow_template_context,
    default_workflow_templates,
    normalize_workflow_template,
    resolve_workflow_template,
    workflow_template_to_dict,
)

router = APIRouter()
settings = get_settings()


class WorkflowTemplateStepPayload(BaseModel):
    title: str
    kind: str
    description: str
    tool_name: str | None = None
    requires_approval: bool = False


class WorkflowTemplateUpsertRequest(BaseModel):
    name: str
    kind: str = "workflow"
    summary: str | None = None
    steps: list[WorkflowTemplateStepPayload] = Field(default_factory=list)
    recommended_tool: str | None = None
    requires_approval: bool = False
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateRunRequest(BaseModel):
    goal: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = 5
    resume_from_step_index: int | None = None
    runtime_run_id: str | None = None


def _registered_workflow_templates() -> dict[str, dict[str, Any]]:
    templates = {name: workflow_template_to_dict(template) for name, template in default_workflow_templates().items()}
    for template in list_custom_workflow_templates(settings):
        normalized = normalize_workflow_template(template)
        if normalized is not None:
            templates[normalized.name] = workflow_template_to_dict(normalized)
    return templates


def _workflow_template_context(template_name: str, base_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = dict(base_context or {})
    registry: dict[str, Any] = {}
    raw_registry = context.get("workflow_templates")
    if isinstance(raw_registry, dict):
        registry.update(raw_registry)
    elif isinstance(raw_registry, list):
        for item in raw_registry:
            if isinstance(item, dict) and str(item.get("name") or ""):
                registry[str(item["name"])] = item

    for name, template in _registered_workflow_templates().items():
        registry.setdefault(name, template)

    context["workflow_template_name"] = template_name
    context["workflow_templates"] = registry
    return context


@router.get("/workflow-templates")
def list_workflow_templates() -> list[dict[str, object]]:
    return list(_registered_workflow_templates().values())


@router.get("/workflow-templates/{template_name}")
def get_workflow_template(template_name: str) -> dict[str, object]:
    template = resolve_workflow_template(_workflow_template_context(template_name))
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")
    return workflow_template_to_dict(template)


@router.post("/workflow-templates")
def upsert_workflow_template(request: WorkflowTemplateUpsertRequest) -> dict[str, object]:
    template = normalize_workflow_template(request.model_dump())
    if template is None:
        raise HTTPException(status_code=422, detail="invalid workflow template payload")
    saved = upsert_custom_workflow_template(settings, workflow_template_to_dict(template))
    normalized = normalize_workflow_template(saved)
    if normalized is None:
        raise HTTPException(status_code=500, detail="workflow template could not be saved")
    return workflow_template_to_dict(normalized)


@router.delete("/workflow-templates/{template_name}")
def delete_workflow_template(template_name: str) -> dict[str, object]:
    deleted = delete_custom_workflow_template(settings, name=template_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="workflow template not found")
    return {"deleted": True, "template_name": template_name}


def summarize_workflow_template_run(run: dict[str, Any] | None) -> dict[str, Any]:
    normalized_run = dict(run or {})
    context = normalized_run.get("context") if isinstance(normalized_run.get("context"), dict) else {}
    steps = normalized_run.get("steps") if isinstance(normalized_run.get("steps"), list) else []
    workflow_template_name = context.get("workflow_template_name")
    if not isinstance(workflow_template_name, str) or not workflow_template_name.strip():
        workflow_template_data = context.get("workflow_template") if isinstance(context.get("workflow_template"), dict) else {}
        workflow_template_name = str(workflow_template_data.get("name") or "")
    workflow_inputs = context.get("workflow_inputs") if isinstance(context.get("workflow_inputs"), dict) else {}

    artifact_paths: list[str] = []
    step_statuses: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_statuses.append(str(step.get("status") or ""))
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
        if isinstance(artifacts, dict):
            for key in ("workdir", "script_path", "html_path", "text_path", "json_path", "md_path", "report_path", "ranking_path", "scan_path", "compare_path", "schedule_path", "schedule_manifest_path", "artifact_manifest_path"):
                path = artifacts.get(key)
                if isinstance(path, str) and path not in artifact_paths:
                    artifact_paths.append(path)
            extra_artifact_paths = artifacts.get("artifact_paths")
            if isinstance(extra_artifact_paths, list):
                for path in extra_artifact_paths:
                    if isinstance(path, str) and path not in artifact_paths:
                        artifact_paths.append(path)

    return {
        "runtime_run_id": str(normalized_run.get("id") or ""),
        "workflow_template_name": workflow_template_name,
        "goal": normalized_run.get("goal"),
        "status": normalized_run.get("status"),
        "summary": normalized_run.get("summary"),
        "attempts": int(normalized_run.get("attempts") or 0),
        "checkpoint": normalized_run.get("checkpoint") if isinstance(normalized_run.get("checkpoint"), dict) else {},
        "workflow_inputs": workflow_inputs,
        "step_count": len(steps),
        "step_statuses": step_statuses,
        "artifact_paths": artifact_paths,
    }


def compare_workflow_template_runs(left_run: dict[str, Any] | None, right_run: dict[str, Any] | None) -> dict[str, Any]:
    left_snapshot = summarize_workflow_template_run(left_run)
    right_snapshot = summarize_workflow_template_run(right_run)

    differences: dict[str, dict[str, Any]] = {}
    for key in ("goal", "status", "summary", "attempts", "checkpoint", "workflow_inputs", "step_count", "step_statuses", "artifact_paths"):
        if left_snapshot.get(key) != right_snapshot.get(key):
            differences[key] = {"left": left_snapshot.get(key), "right": right_snapshot.get(key)}

    return {
        "left": left_snapshot,
        "right": right_snapshot,
        "differences": differences,
    }


@router.post("/workflow-templates/{template_name}/run")
def run_workflow_template(template_name: str, request: WorkflowTemplateRunRequest) -> dict[str, object]:
    template = resolve_workflow_template(_workflow_template_context(template_name, request.context))
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")

    workflow_context = build_workflow_template_context(
        template,
        workflow_inputs=request.inputs,
        context=request.context,
    )
    execution = run_agent_runtime(
        settings,
        goal=request.goal or template.summary,
        context=workflow_context,
        max_steps=request.max_steps,
        resume_from_step_index=request.resume_from_step_index,
        runtime_run_id=request.runtime_run_id,
    )

    schedule = None
    schedule_registration_error = None
    if template.kind == "schedule" and execution.status == "completed":
        try:
            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id=execution.runtime_run_id,
                source_template_name=template.name,
                source_goal=request.goal or template.summary,
                workflow_inputs=workflow_context.get("workflow_inputs", {}),
            )
        except ValueError as exc:
            schedule_registration_error = str(exc)

    return {
        "workflow_template": workflow_template_to_dict(template),
        "workflow_inputs": workflow_context.get("workflow_inputs", {}),
        "execution": runtime_execution_to_dict(execution),
        "schedule": schedule,
        "schedule_registration_error": schedule_registration_error,
    }
