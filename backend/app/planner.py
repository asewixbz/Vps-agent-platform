from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .model_adapter import ModelAdapterError
from .model_runtime import chat_model
from .settings import Settings
from .store import list_tools

RISKY_GOAL_SNIPPETS = (
    "delete",
    "remove",
    "wipe",
    "destroy",
    "shutdown",
    "restart",
    "deploy",
    "production",
    "prod",
    "secret",
    "credential",
    "password",
    "token",
)

KEYWORD_TOOL_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("browser", "web", "website", "page", "url", "link", "http", "https", "search the web"), "browser"),
    (("python", "script", "code", "function", "algorithm", "compute", "calculate", "parse"), "python"),
    (("shell", "terminal", "command", "bash", "cli", "console"), "shell"),
    (("model", "llm", "chat", "summarize", "summarise", "classify", "plan"), "model"),
)


@dataclass(frozen=True)
class PlanStep:
    title: str
    kind: str
    description: str
    tool_name: str | None = None
    requires_approval: bool = False


@dataclass(frozen=True)
class AgentPlan:
    goal: str
    summary: str
    source: str
    recommended_tool: str | None
    requires_approval: bool
    steps: list[PlanStep]
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _tool_rank(tool: dict[str, Any]) -> tuple[int, int, str]:
    status_score = {"trusted": 3, "tested": 2, "draft": 1, "blocked": 0}.get(str(tool.get("status") or ""), 0)
    trust_level = int(tool.get("trust_level") or 0)
    return status_score, trust_level, str(tool.get("name") or "")


def _select_tool_by_kind(tools: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    matches = [tool for tool in tools if str(tool.get("kind") or "") == kind]
    if not matches:
        return None
    return sorted(matches, key=_tool_rank, reverse=True)[0]


def _select_tool_by_name_fragment(tools: list[dict[str, Any]], fragments: tuple[str, ...]) -> dict[str, Any] | None:
    for fragment in fragments:
        matches = [tool for tool in tools if fragment in str(tool.get("name") or "").lower()]
        if matches:
            return sorted(matches, key=_tool_rank, reverse=True)[0]
    return None


def _guess_recommended_tool(goal: str, tools: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = goal.lower()
    for keywords, kind in KEYWORD_TOOL_HINTS:
        if any(keyword in lowered for keyword in keywords):
            by_kind = _select_tool_by_kind(tools, kind)
            if by_kind is not None:
                return by_kind

    name_fragment_match = _select_tool_by_name_fragment(tools, ("python", "shell", "browser", "model"))
    if name_fragment_match is not None:
        return name_fragment_match

    trusted_tools = sorted([tool for tool in tools if str(tool.get("status") or "") == "trusted"], key=_tool_rank, reverse=True)
    return trusted_tools[0] if trusted_tools else (sorted(tools, key=_tool_rank, reverse=True)[0] if tools else None)


def _requires_approval(goal: str, tool: dict[str, Any] | None) -> tuple[bool, list[str]]:
    notes: list[str] = []
    lowered = goal.lower()
    risky_goal = any(snippet in lowered for snippet in RISKY_GOAL_SNIPPETS)
    if risky_goal:
        notes.append("goal contains risky language that should be reviewed before execution")

    if tool is None:
        return risky_goal, notes

    tool_status = str(tool.get("status") or "")
    trust_level = int(tool.get("trust_level") or 0)
    kind = str(tool.get("kind") or "")

    if tool_status != "trusted":
        notes.append(f'tool "{tool.get("name")}" is not trusted yet ({tool_status or "unknown"})')
    if trust_level < 2:
        notes.append(f'tool "{tool.get("name")}" has trust level {trust_level}')
    if kind == "shell":
        notes.append("shell execution should stay behind approval gates")

    requires_approval = risky_goal or tool_status != "trusted" or trust_level < 2 or kind == "shell"
    return requires_approval, notes


def _build_heuristic_plan(goal: str, context: dict[str, Any], tools: list[dict[str, Any]]) -> AgentPlan:
    recommended_tool = _guess_recommended_tool(goal, tools)
    requires_approval, notes = _requires_approval(goal, recommended_tool)
    tool_name = recommended_tool.get("name") if recommended_tool else None
    summary = f"Plan for: {goal.strip()}" if goal.strip() else "Plan for the requested task"

    if tool_name is None:
        steps = [
            PlanStep(
                title="Clarify the objective",
                kind="clarify",
                description="Identify missing inputs, success criteria, and any constraints before execution.",
            ),
            PlanStep(
                title="Choose the safest available tool",
                kind="inspect",
                description="Review the tool registry and select the least risky fit for the task.",
            ),
            PlanStep(
                title="Execute a first pass",
                kind="execute",
                description="Run the task once the inputs are clear and the tool choice is confirmed.",
            ),
            PlanStep(
                title="Verify the output",
                kind="verify",
                description="Check the result against the original goal and capture any gaps for the next iteration.",
            ),
        ]
    else:
        steps = [
            PlanStep(
                title="Prepare the task payload",
                kind="inspect",
                description=f"Collect the inputs needed for {tool_name} and shape them for execution.",
                tool_name=tool_name,
            ),
            PlanStep(
                title="Run the task",
                kind="execute",
                description=f"Execute the goal using {tool_name}.",
                tool_name=tool_name,
                requires_approval=requires_approval,
            ),
            PlanStep(
                title="Review the result",
                kind="verify",
                description="Inspect stdout, errors, and artifacts for correctness before moving on.",
                tool_name=tool_name,
            ),
        ]

    return AgentPlan(
        goal=goal,
        summary=summary,
        source="heuristic",
        recommended_tool=tool_name,
        requires_approval=requires_approval,
        steps=steps,
        notes=notes,
        metadata={"context": context, "available_tools": len(tools)},
    )


def _model_prompt(goal: str, context: dict[str, Any], tools: list[dict[str, Any]], heuristic_plan: AgentPlan) -> list[dict[str, Any]]:
    compact_tools = [
        {
            "name": tool.get("name"),
            "kind": tool.get("kind"),
            "status": tool.get("status"),
            "trust_level": tool.get("trust_level"),
            "description": tool.get("description"),
        }
        for tool in tools
    ]
    request_payload = {
        "goal": goal,
        "context": context,
        "available_tools": compact_tools,
        "heuristic_plan": asdict(heuristic_plan),
        "output_schema": {
            "source": "model",
            "summary": "string",
            "recommended_tool": "string|null",
            "requires_approval": "boolean",
            "notes": ["string"],
            "steps": [
                {
                    "title": "string",
                    "kind": "clarify|inspect|execute|verify|approve",
                    "description": "string",
                    "tool_name": "string|null",
                    "requires_approval": "boolean",
                }
            ],
        },
    }
    system_message = (
        "You are a conservative execution planner for a CLI-first control plane. "
        "Return only valid JSON that matches the requested schema. "
        "Do not wrap the JSON in markdown fences. "
        "Prefer the safest practical tool. If the task is underspecified, make that explicit in the steps."
    )
    user_message = json.dumps(request_payload, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def _plan_from_payload(goal: str, payload: dict[str, Any], context: dict[str, Any], source: str) -> AgentPlan:
    steps_payload = payload.get("steps")
    steps: list[PlanStep] = []
    if isinstance(steps_payload, list):
        for item in steps_payload:
            if not isinstance(item, dict):
                continue
            steps.append(
                PlanStep(
                    title=str(item.get("title") or "Untitled step"),
                    kind=str(item.get("kind") or "inspect"),
                    description=str(item.get("description") or ""),
                    tool_name=item.get("tool_name") if item.get("tool_name") is not None else None,
                    requires_approval=bool(item.get("requires_approval") or False),
                )
            )

    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    normalized_notes = [str(item) for item in notes if item is not None]
    summary = str(payload.get("summary") or f"Plan for: {goal.strip()}")
    recommended_tool = payload.get("recommended_tool")
    return AgentPlan(
        goal=goal,
        summary=summary,
        source=source,
        recommended_tool=str(recommended_tool) if recommended_tool not in {None, ""} else None,
        requires_approval=bool(payload.get("requires_approval") or False),
        steps=steps,
        notes=normalized_notes,
        metadata={"context": context, "raw": payload},
    )


def _model_plan(settings: Settings, goal: str, context: dict[str, Any], tools: list[dict[str, Any]], heuristic_plan: AgentPlan) -> AgentPlan | None:
    payload = {
        "messages": _model_prompt(goal, context, tools, heuristic_plan),
        "response_mode": "json",
        "metadata": {"planner": True},
    }
    response = chat_model(settings, payload)
    structured = response.structured_data
    if isinstance(structured, dict):
        return _plan_from_payload(goal, structured, context, source="model")
    if response.text:
        try:
            parsed = json.loads(response.text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return _plan_from_payload(goal, parsed, context, source="model")
    return None


def build_execution_plan(settings: Settings, *, goal: str, context: dict[str, Any] | None = None) -> AgentPlan:
    normalized_context = dict(context or {})
    tools = list_tools(settings)
    heuristic_plan = _build_heuristic_plan(goal, normalized_context, tools)

    if not settings.model_runner_enabled:
        return heuristic_plan

    try:
        model_plan = _model_plan(settings, goal, normalized_context, tools, heuristic_plan)
    except ModelAdapterError as exc:
        fallback_notes = list(heuristic_plan.notes)
        fallback_notes.append(f"Model planner unavailable; used heuristic fallback: {exc}")
        return AgentPlan(
            goal=heuristic_plan.goal,
            summary=heuristic_plan.summary,
            source=heuristic_plan.source,
            recommended_tool=heuristic_plan.recommended_tool,
            requires_approval=heuristic_plan.requires_approval,
            steps=heuristic_plan.steps,
            notes=fallback_notes,
            metadata={**heuristic_plan.metadata, "model_error": str(exc)},
        )

    if model_plan is None:
        fallback_notes = list(heuristic_plan.notes)
        fallback_notes.append("Model planner returned an unparseable response; used heuristic fallback.")
        return AgentPlan(
            goal=heuristic_plan.goal,
            summary=heuristic_plan.summary,
            source=heuristic_plan.source,
            recommended_tool=heuristic_plan.recommended_tool,
            requires_approval=heuristic_plan.requires_approval,
            steps=heuristic_plan.steps,
            notes=fallback_notes,
            metadata={**heuristic_plan.metadata, "model_response": "unparseable"},
        )

    return model_plan
