from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .settings import get_settings
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
