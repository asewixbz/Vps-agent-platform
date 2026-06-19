from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .executor import execute_task
from .planner import AgentPlan, PlanStep, build_execution_plan
from .settings import Settings
from .store import create_task, get_tool


@dataclass(frozen=True)
class RuntimeStepResult:
    index: int
    title: str
    kind: str
    tool_name: str | None
    status: str
    detail: str
    task_id: str | None = None
    task_status: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeExecutionResult:
    goal: str
    status: str
    summary: str
    plan: AgentPlan
    steps: list[RuntimeStepResult]
    iterations: int
    blocked_reason: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


def _resolve_timeout(context: dict[str, Any]) -> int | None:
    timeout = context.get("timeout_seconds")
    if isinstance(timeout, int) and timeout > 0:
        return timeout
    return None


def _resolve_execute_payload(context: dict[str, Any], tool_name: str | None, step: PlanStep) -> dict[str, Any] | None:
    if tool_name is None:
        return None

    for key in ("payload_by_tool", "tool_payloads"):
        mapping = context.get(key)
        if isinstance(mapping, dict):
            payload = mapping.get(tool_name)
            if isinstance(payload, dict):
                return dict(payload)

    for key in ("payload", "task_payload", "input"):
        payload = context.get(key)
        if isinstance(payload, dict):
            return dict(payload)

    step_payloads = context.get("step_payloads")
    if isinstance(step_payloads, dict):
        payload = step_payloads.get(step.title) or step_payloads.get(tool_name)
        if isinstance(payload, dict):
            return dict(payload)

    return None


def _step_to_result(index: int, step: PlanStep, *, status: str, detail: str, **fields: Any) -> RuntimeStepResult:
    return RuntimeStepResult(
        index=index,
        title=step.title,
        kind=step.kind,
        tool_name=step.tool_name,
        status=status,
        detail=detail,
        **fields,
    )


def run_agent_runtime(
    settings: Settings,
    *,
    goal: str,
    context: dict[str, Any] | None = None,
    max_steps: int = 5,
) -> RuntimeExecutionResult:
    normalized_context = dict(context or {})
    plan = build_execution_plan(settings, goal=goal, context=normalized_context)
    results: list[RuntimeStepResult] = []
    steps = plan.steps[: max_steps if max_steps > 0 else len(plan.steps)]
    stopped_early = len(plan.steps) > len(steps)

    if max_steps <= 0:
        return RuntimeExecutionResult(
            goal=goal,
            status="blocked",
            summary="runtime loop was asked to run zero steps",
            plan=plan,
            steps=[],
            iterations=0,
            blocked_reason="max_steps must be greater than zero",
            context=normalized_context,
        )

    for index, step in enumerate(steps, start=1):
        if step.kind in {"clarify", "inspect", "verify"}:
            results.append(
                _step_to_result(
                    index,
                    step,
                    status="observed",
                    detail=step.description or "no execution required for this step",
                )
            )
            continue

        if step.kind == "approve":
            results.append(
                _step_to_result(
                    index,
                    step,
                    status="pending_approval",
                    detail=step.description or "human approval is required before continuing",
                )
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_approval",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=step.description or "human approval is required before continuing",
                context=normalized_context,
            )

        if step.kind != "execute":
            results.append(
                _step_to_result(
                    index,
                    step,
                    status="skipped",
                    detail=f"step kind '{step.kind}' is not yet executed by the runtime loop",
                )
            )
            continue

        tool_name = step.tool_name or plan.recommended_tool
        if tool_name is None:
            detail = "runtime loop could not select a tool for execution"
            results.append(_step_to_result(index, step, status="blocked", detail=detail))
            return RuntimeExecutionResult(
                goal=goal,
                status="blocked",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=detail,
                context=normalized_context,
            )

        tool = get_tool(settings, name=tool_name)
        if tool is None:
            detail = f'tool "{tool_name}" was not found in the registry'
            results.append(_step_to_result(index, step, status="blocked", detail=detail, tool_name=tool_name))
            return RuntimeExecutionResult(
                goal=goal,
                status="blocked",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=detail,
                context=normalized_context,
            )

        if (step.requires_approval or plan.requires_approval) and not normalized_context.get("approved") and not normalized_context.get(
            "allow_risky_execution"
        ):
            detail = "runtime loop paused for approval before executing a risky step"
            results.append(_step_to_result(index, step, status="pending_approval", detail=detail, tool_name=tool_name))
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_approval",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=detail,
                context=normalized_context,
            )

        payload = _resolve_execute_payload(normalized_context, tool_name, step)
        if payload is None:
            detail = f'no payload was provided for tool "{tool_name}"'
            results.append(_step_to_result(index, step, status="pending_input", detail=detail, tool_name=tool_name))
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_input",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=detail,
                context=normalized_context,
            )

        task = create_task(settings, tool_name=tool_name, payload=payload, auto_run=False)
        executed = execute_task(settings, task_id=task["id"], timeout_seconds=_resolve_timeout(normalized_context))
        task_status = str(executed.get("status") or "failed")
        result_payload = executed.get("result") if isinstance(executed.get("result"), dict) else {}
        results.append(
            _step_to_result(
                index,
                step,
                status=task_status,
                detail=str(executed.get("reason") or executed.get("stderr") or "step executed"),
                tool_name=tool_name,
                task_id=str(executed.get("id") or task["id"]),
                task_status=task_status,
                stdout=executed.get("stdout"),
                stderr=executed.get("stderr"),
                result=result_payload,
            )
        )

        if task_status != "completed":
            return RuntimeExecutionResult(
                goal=goal,
                status=task_status,
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=index,
                blocked_reason=str(executed.get("reason") or executed.get("stderr") or f"step ended with status {task_status}"),
                context=normalized_context,
            )

        normalized_context["last_result"] = executed.get("result")
        normalized_context["last_stdout"] = executed.get("stdout")
        normalized_context["last_stderr"] = executed.get("stderr")
        normalized_context["last_task_id"] = executed.get("id")
        normalized_context["last_tool_name"] = tool_name

    if stopped_early:
        return RuntimeExecutionResult(
            goal=goal,
            status="partial",
            summary=plan.summary,
            plan=plan,
            steps=results,
            iterations=len(results),
            blocked_reason="runtime loop stopped after reaching max_steps",
            context=normalized_context,
        )

    return RuntimeExecutionResult(
        goal=goal,
        status="completed",
        summary=plan.summary,
        plan=plan,
        steps=results,
        iterations=len(results),
        context=normalized_context,
    )


def runtime_execution_to_dict(result: RuntimeExecutionResult) -> dict[str, Any]:
    return asdict(result)
