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
    resume_hint: str | None = None
    checkpoint: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


def _resolve_timeout(context: dict[str, Any]) -> int | None:
    timeout = context.get("timeout_seconds")
    if isinstance(timeout, int) and timeout > 0:
        return timeout
    return None


def _resolve_start_step_index(
    context: dict[str, Any],
    resume_from_step_index: int | None = None,
) -> int:
    candidates: list[Any] = [resume_from_step_index, context.get("resume_from_step_index")]
    checkpoint = context.get("checkpoint")
    if isinstance(checkpoint, dict):
        candidates.append(checkpoint.get("next_step_index"))

    for candidate in candidates:
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    return 1


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


def _build_checkpoint(
    *,
    plan: AgentPlan,
    completed_step_indices: list[int],
    next_step_index: int,
    blocked_step_index: int | None = None,
    resume_from_step_index: int | None = None,
) -> dict[str, Any]:
    checkpoint: dict[str, Any] = {
        "total_steps": len(plan.steps),
        "completed_step_indices": completed_step_indices,
        "completed_step_count": len(completed_step_indices),
        "next_step_index": next_step_index,
    }
    if blocked_step_index is not None:
        checkpoint["blocked_step_index"] = blocked_step_index
    if resume_from_step_index is not None:
        checkpoint["resume_from_step_index"] = resume_from_step_index
    if plan.recommended_tool is not None:
        checkpoint["recommended_tool"] = plan.recommended_tool
    return checkpoint


def _resume_hint(status: str, checkpoint: dict[str, Any], blocked_reason: str | None = None) -> str | None:
    next_step_index = checkpoint.get("next_step_index")
    if status == "completed":
        return None
    if status == "partial":
        return f"Resume from step {next_step_index} after increasing max_steps or continuing with the same checkpoint."
    if status == "pending_approval":
        base = f"Resume from step {next_step_index} after approval is granted."
        return f"{base} {blocked_reason}".strip() if blocked_reason else base
    if status == "pending_input":
        base = f"Resume from step {next_step_index} after the missing input is supplied."
        return f"{base} {blocked_reason}".strip() if blocked_reason else base
    if status == "blocked":
        return blocked_reason or f"Resume from step {next_step_index} after resolving the blocking issue."
    if status == "failed":
        return blocked_reason or f"Resume from step {next_step_index} after fixing the failing step."
    return f"Resume from step {next_step_index}."


def run_agent_runtime(
    settings: Settings,
    *,
    goal: str,
    context: dict[str, Any] | None = None,
    max_steps: int = 5,
    resume_from_step_index: int | None = None,
) -> RuntimeExecutionResult:
    normalized_context = dict(context or {})
    plan = build_execution_plan(settings, goal=goal, context=normalized_context)
    results: list[RuntimeStepResult] = []
    completed_step_indices: list[int] = []
    total_steps = len(plan.steps)

    if max_steps <= 0:
        checkpoint = _build_checkpoint(plan=plan, completed_step_indices=[], next_step_index=1)
        return RuntimeExecutionResult(
            goal=goal,
            status="blocked",
            summary="runtime loop was asked to run zero steps",
            plan=plan,
            steps=[],
            iterations=0,
            blocked_reason="max_steps must be greater than zero",
            resume_hint=_resume_hint("blocked", checkpoint, "max_steps must be greater than zero"),
            checkpoint=checkpoint,
            context=normalized_context,
        )

    start_step_index = _resolve_start_step_index(normalized_context, resume_from_step_index)
    if start_step_index > total_steps:
        checkpoint = _build_checkpoint(
            plan=plan,
            completed_step_indices=list(range(1, total_steps + 1)),
            next_step_index=total_steps + 1,
            resume_from_step_index=start_step_index,
        )
        return RuntimeExecutionResult(
            goal=goal,
            status="completed",
            summary=plan.summary,
            plan=plan,
            steps=[],
            iterations=0,
            resume_hint=_resume_hint("completed", checkpoint),
            checkpoint=checkpoint,
            context={**normalized_context, "checkpoint": checkpoint},
        )

    steps_to_process = plan.steps[start_step_index - 1 :]
    sliced_steps = steps_to_process[:max_steps]
    stopped_early = len(steps_to_process) > len(sliced_steps)
    next_step_index = start_step_index

    for index, step in enumerate(sliced_steps, start=start_step_index):
        if step.kind in {"clarify", "inspect", "verify"}:
            results.append(
                _step_to_result(
                    index,
                    step,
                    status="observed",
                    detail=step.description or "no execution required for this step",
                )
            )
            completed_step_indices.append(index)
            next_step_index = index + 1
            continue

        if step.kind == "approve":
            detail = step.description or "human approval is required before continuing"
            results.append(_step_to_result(index, step, status="pending_approval", detail=detail))
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_approval",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=detail,
                resume_hint=_resume_hint("pending_approval", checkpoint, detail),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
            )

        if step.kind != "execute":
            detail = f"step kind '{step.kind}' is not yet executed by the runtime loop"
            results.append(_step_to_result(index, step, status="skipped", detail=detail))
            completed_step_indices.append(index)
            next_step_index = index + 1
            continue

        tool_name = step.tool_name or plan.recommended_tool
        if tool_name is None:
            detail = "runtime loop could not select a tool for execution"
            results.append(_step_to_result(index, step, status="blocked", detail=detail))
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="blocked",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=detail,
                resume_hint=_resume_hint("blocked", checkpoint, detail),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
            )

        tool = get_tool(settings, name=tool_name)
        if tool is None:
            detail = f'tool "{tool_name}" was not found in the registry'
            results.append(_step_to_result(index, step, status="blocked", detail=detail, tool_name=tool_name))
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="blocked",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=detail,
                resume_hint=_resume_hint("blocked", checkpoint, detail),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
            )

        if (step.requires_approval or plan.requires_approval) and not normalized_context.get("approved") and not normalized_context.get(
            "allow_risky_execution"
        ):
            detail = "runtime loop paused for approval before executing a risky step"
            results.append(_step_to_result(index, step, status="pending_approval", detail=detail, tool_name=tool_name))
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_approval",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=detail,
                resume_hint=_resume_hint("pending_approval", checkpoint, detail),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
            )

        payload = _resolve_execute_payload(normalized_context, tool_name, step)
        if payload is None:
            detail = f'no payload was provided for tool "{tool_name}"'
            results.append(_step_to_result(index, step, status="pending_input", detail=detail, tool_name=tool_name))
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status="pending_input",
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=detail,
                resume_hint=_resume_hint("pending_input", checkpoint, detail),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
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
            checkpoint = _build_checkpoint(
                plan=plan,
                completed_step_indices=completed_step_indices,
                next_step_index=index,
                blocked_step_index=index,
                resume_from_step_index=start_step_index,
            )
            return RuntimeExecutionResult(
                goal=goal,
                status=task_status,
                summary=plan.summary,
                plan=plan,
                steps=results,
                iterations=len(results),
                blocked_reason=str(executed.get("reason") or executed.get("stderr") or f"step ended with status {task_status}"),
                resume_hint=_resume_hint(task_status, checkpoint, str(executed.get("stderr") or executed.get("reason") or "")),
                checkpoint=checkpoint,
                context={**normalized_context, "checkpoint": checkpoint},
            )

        completed_step_indices.append(index)
        next_step_index = index + 1
        normalized_context["last_result"] = executed.get("result")
        normalized_context["last_stdout"] = executed.get("stdout")
        normalized_context["last_stderr"] = executed.get("stderr")
        normalized_context["last_task_id"] = executed.get("id")
        normalized_context["last_tool_name"] = tool_name

    if stopped_early:
        checkpoint = _build_checkpoint(
            plan=plan,
            completed_step_indices=completed_step_indices,
            next_step_index=next_step_index,
            resume_from_step_index=start_step_index,
        )
        return RuntimeExecutionResult(
            goal=goal,
            status="partial",
            summary=plan.summary,
            plan=plan,
            steps=results,
            iterations=len(results),
            blocked_reason="runtime loop stopped after reaching max_steps",
            resume_hint=_resume_hint("partial", checkpoint, "runtime loop stopped after reaching max_steps"),
            checkpoint=checkpoint,
            context={**normalized_context, "checkpoint": checkpoint},
        )

    checkpoint = _build_checkpoint(
        plan=plan,
        completed_step_indices=completed_step_indices,
        next_step_index=next_step_index,
        resume_from_step_index=start_step_index,
    )
    return RuntimeExecutionResult(
        goal=goal,
        status="completed",
        summary=plan.summary,
        plan=plan,
        steps=results,
        iterations=len(results),
        checkpoint=checkpoint,
        context={**normalized_context, "checkpoint": checkpoint},
    )


def runtime_execution_to_dict(result: RuntimeExecutionResult) -> dict[str, Any]:
    return asdict(result)
