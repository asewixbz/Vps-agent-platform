from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_WORKFLOW_TEMPLATE_NAMES = ("scan_workflow", "rank_workflow", "report_workflow")
DEFAULT_WORKFLOW_TEMPLATE_KINDS = ("scan", "rank", "report")


@dataclass(frozen=True)
class WorkflowTemplateStep:
    title: str
    kind: str
    description: str
    tool_name: str | None = None
    requires_approval: bool = False


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    kind: str
    summary: str
    steps: list[WorkflowTemplateStep]
    recommended_tool: str | None = None
    requires_approval: bool = False
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_notes(raw_notes: Any) -> list[str]:
    if not isinstance(raw_notes, list):
        return []
    return [str(item) for item in raw_notes if item is not None]


def _normalize_metadata(raw_metadata: Any) -> dict[str, Any]:
    return dict(raw_metadata) if isinstance(raw_metadata, dict) else {}


def _normalize_steps(raw_steps: Any) -> list[WorkflowTemplateStep] | None:
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    steps: list[WorkflowTemplateStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            return None

        title = str(item.get("title") or "").strip()
        kind = str(item.get("kind") or "inspect").strip() or "inspect"
        description = str(item.get("description") or "").strip()
        tool_name = item.get("tool_name")
        if tool_name in {"", None}:
            tool_name = None
        if not title or not description:
            return None
        if kind == "execute" and tool_name is None:
            return None

        steps.append(
            WorkflowTemplateStep(
                title=title,
                kind=kind,
                description=description,
                tool_name=str(tool_name) if tool_name is not None else None,
                requires_approval=bool(item.get("requires_approval") or False),
            )
        )
    return steps


def normalize_workflow_template(raw_template: Any) -> WorkflowTemplate | None:
    if not isinstance(raw_template, dict):
        return None

    name = str(raw_template.get("name") or raw_template.get("template_name") or "").strip()
    kind = str(raw_template.get("kind") or raw_template.get("template_kind") or "workflow").strip() or "workflow"
    steps = _normalize_steps(raw_template.get("steps"))
    if not name or steps is None:
        return None

    summary = str(raw_template.get("summary") or "").strip()
    if not summary:
        summary = f"Workflow template: {name}"

    recommended_tool = raw_template.get("recommended_tool")
    if recommended_tool in {None, ""}:
        recommended_tool = None

    return WorkflowTemplate(
        name=name,
        kind=kind,
        summary=summary,
        steps=steps,
        recommended_tool=str(recommended_tool) if recommended_tool is not None else None,
        requires_approval=bool(raw_template.get("requires_approval") or False),
        notes=_normalize_notes(raw_template.get("notes")),
        metadata=_normalize_metadata(raw_template.get("metadata")),
    )


def workflow_template_to_dict(template: WorkflowTemplate) -> dict[str, Any]:
    data = asdict(template)
    return data


def default_workflow_templates() -> dict[str, WorkflowTemplate]:
    templates = [
        WorkflowTemplate(
            name="scan_workflow",
            kind="scan",
            summary="Scan a source set and normalize the items for downstream workflows.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect scan inputs",
                    kind="inspect",
                    description="Collect the source set, inclusion rules, and any required filters before scanning.",
                ),
                WorkflowTemplateStep(
                    title="Run the scan",
                    kind="execute",
                    description="Scan the inputs and normalize them into structured results.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify scan output",
                    kind="verify",
                    description="Check the scan output for missing items, duplicates, and obvious mismatches.",
                ),
            ],
            notes=["Phase 5 template for repeatable scanning workflows."],
            metadata={"phase": 5, "category": "scan"},
        ),
        WorkflowTemplate(
            name="rank_workflow",
            kind="rank",
            summary="Rank items against the supplied criteria using a fixed workflow template.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect ranking criteria",
                    kind="inspect",
                    description="Collect the ranking criteria, weighting rules, and the candidate items to score.",
                ),
                WorkflowTemplateStep(
                    title="Score the candidates",
                    kind="execute",
                    description="Apply the ranking criteria and produce an ordered result set.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the ranking",
                    kind="verify",
                    description="Check the ranking for ties, outliers, and missing rationale.",
                ),
            ],
            notes=["Phase 5 template for repeatable ranking workflows."],
            metadata={"phase": 5, "category": "rank"},
        ),
        WorkflowTemplate(
            name="report_workflow",
            kind="report",
            summary="Generate a concise report from workflow inputs with a fixed template.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect reporting inputs",
                    kind="inspect",
                    description="Collect the data source, audience, and report constraints before generation.",
                ),
                WorkflowTemplateStep(
                    title="Build the report",
                    kind="execute",
                    description="Assemble the report and supporting summary from the supplied inputs.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the report",
                    kind="verify",
                    description="Check the report for omissions, unsupported claims, and formatting issues.",
                ),
            ],
            notes=["Phase 5 template for repeatable report generation workflows."],
            metadata={"phase": 5, "category": "report"},
        ),
    ]
    return {template.name: template for template in templates}


def _lookup_template_from_registry(registry: Any, template_name: str) -> Any:
    if isinstance(registry, dict):
        return registry.get(template_name)
    if isinstance(registry, list):
        for item in registry:
            if isinstance(item, dict) and str(item.get("name") or "") == template_name:
                return item
    return None


def resolve_workflow_template(context: dict[str, Any] | None) -> WorkflowTemplate | None:
    normalized_context = dict(context or {})

    direct_template = normalized_context.get("workflow_template")
    if isinstance(direct_template, str):
        direct_template = _lookup_template_from_registry(default_workflow_templates(), direct_template)
    template = normalize_workflow_template(direct_template)
    if template is not None:
        return template

    template_name = normalized_context.get("workflow_template_name")
    if not isinstance(template_name, str) or not template_name.strip():
        return None
    template_name = template_name.strip()

    registry = normalized_context.get("workflow_templates")
    registry_template = _lookup_template_from_registry(registry, template_name)
    if registry_template is None:
        registry_template = default_workflow_templates().get(template_name)

    return normalize_workflow_template(registry_template)
