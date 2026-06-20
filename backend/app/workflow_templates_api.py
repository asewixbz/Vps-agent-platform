from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .settings import get_settings
from .store import get_runtime_run
from .workflow_templates import (
    build_workflow_template_context,
    default_workflow_templates,
    resolve_workflow_template,
    workflow_template_to_dict,
)

router = APIRouter()
settings = get_settings()


class WorkflowTemplateRunRequest(BaseModel):
    goal: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = 5
    resume_from_step_index: int | None = None
    runtime_run_id: str | None = None


@router.get("/workflow-templates")
def list_workflow_templates() -> list[dict[str, object]]:
    return [workflow_template_to_dict(template) for template in default_workflow_templates().values()]


@router.get("/workflow-templates/{template_name}")
def get_workflow_template(template_name: str) -> dict[str, object]:
    template = resolve_workflow_template({"workflow_template_name": template_name})
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")
    return workflow_template_to_dict(template)


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
            for key in ("workdir", "script_path", "html_path", "text_path"):
                path = artifacts.get(key)
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
    template = resolve_workflow_template({"workflow_template_name": template_name})
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
    return {
        "workflow_template": workflow_template_to_dict(template),
        "workflow_inputs": workflow_context.get("workflow_inputs", {}),
        "execution": runtime_execution_to_dict(execution),
    }


@router.get("/workflow-templates/{template_name}/compare")
def compare_workflow_template_runs_route(
    template_name: str,
    left_runtime_run_id: str,
    right_runtime_run_id: str,
) -> dict[str, object]:
    template = resolve_workflow_template({"workflow_template_name": template_name})
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")

    left_run = get_runtime_run(settings, runtime_run_id=left_runtime_run_id)
    right_run = get_runtime_run(settings, runtime_run_id=right_runtime_run_id)
    if left_run is None or right_run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")

    comparison = compare_workflow_template_runs(left_run, right_run)
    if comparison["left"]["workflow_template_name"] != template_name or comparison["right"]["workflow_template_name"] != template_name:
        raise HTTPException(status_code=409, detail="runtime runs do not match the requested workflow template")

    return {
        "workflow_template": workflow_template_to_dict(template),
        "left_runtime_run_id": left_runtime_run_id,
        "right_runtime_run_id": right_runtime_run_id,
        "comparison": comparison,
    }
