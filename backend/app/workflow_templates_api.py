from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .workflow_templates import default_workflow_templates, resolve_workflow_template, workflow_template_to_dict

router = APIRouter()


@router.get("/workflow-templates")
def list_workflow_templates() -> list[dict[str, object]]:
    return [workflow_template_to_dict(template) for template in default_workflow_templates().values()]


@router.get("/workflow-templates/{template_name}")
def get_workflow_template(template_name: str) -> dict[str, object]:
    template = resolve_workflow_template({"workflow_template_name": template_name})
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")
    return workflow_template_to_dict(template)
