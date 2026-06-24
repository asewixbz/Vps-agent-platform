from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .observability import build_policy_audit_payload
from .policy import evaluate
from .runner import run_browser_task, run_model_task, run_python_script, run_shell_command, run_unimplemented
from .security_controls import resolve_task_timeout_budget
from .settings import Settings
from .store import get_task, get_tool, update_task, utc_now


def execute_task(settings: Settings, task_id: str, timeout_seconds: int | None = None) -> dict[str, Any]:
    task = get_task(settings, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    tool = get_tool(settings, name=task["tool_name"])
    if tool is None:
        policy_payload = build_policy_audit_payload(
            {
                "decision": "deny",
                "allowed": False,
                "requires_approval": False,
                "reason": f'tool "{task["tool_name"]}" no longer exists',
                "reason_code": "deny.tool_missing",
                "trust_level": 0,
                "details": {"tool_name": task["tool_name"], "kind": None},
            },
            source="executor.tool_missing",
            context={"task_id": task_id, "tool_name": task["tool_name"]},
        )
        return update_task(
            settings,
            task_id=task_id,
            status="blocked",
            reason=f'tool "{task["tool_name"]}" no longer exists',
            finished_at=utc_now(),
            result_json={"ok": False, "duration_ms": 0, "artifacts": {}, "policy": policy_payload},
        ) or task

    decision = evaluate(tool, task["payload"], settings, approved=bool(task.get("approved")))
    policy_payload = build_policy_audit_payload(
        decision,
        source="executor.policy",
        context={"task_id": task_id, "tool_name": tool.get("name"), "kind": tool.get("kind")},
    )
    if not decision.allowed:
        new_status = "pending_approval" if decision.requires_approval else "blocked"
        return update_task(
            settings,
            task_id=task_id,
            status=new_status,
            reason=decision.reason,
            finished_at=utc_now(),
            result_json={"ok": False, "duration_ms": 0, "artifacts": {}, "policy": policy_payload},
        ) or task

    timeout_budget = resolve_task_timeout_budget(
        settings,
        tool,
        task["payload"],
        requested_timeout_seconds=timeout_seconds,
    )
    timeout_policy_payload = build_policy_audit_payload(
        {
            "decision": "allow" if timeout_budget.allowed else "deny",
            "allowed": timeout_budget.allowed,
            "requires_approval": False,
            "reason": timeout_budget.reason,
            "reason_code": timeout_budget.reason_code,
            "trust_level": int(tool.get("trust_level") or 0),
            "details": timeout_budget.details,
        },
        source="executor.timeout_budget",
        context={"task_id": task_id, "tool_name": tool.get("name"), "kind": tool.get("kind")},
    )
    if not timeout_budget.allowed:
        return update_task(
            settings,
            task_id=task_id,
            status="blocked",
            reason=timeout_budget.reason,
            finished_at=utc_now(),
            result_json={
                "ok": False,
                "duration_ms": 0,
                "artifacts": {},
                "policy": timeout_policy_payload,
            },
        ) or task

    update_task(
        settings,
        task_id=task_id,
        status="running",
        reason=decision.reason,
        started_at=utc_now(),
        attempts=int(task.get("attempts") or 0) + 1,
    )

    payload = task["payload"]
    kind = tool["kind"]
    effective_timeout_seconds = timeout_budget.timeout_seconds
    try:
        if kind == "python":
            result = run_python_script(
                settings,
                task_id=task_id,
                script=payload.get("script", ""),
                timeout_seconds=effective_timeout_seconds,
            )
        elif kind == "shell":
            result = run_shell_command(
                settings,
                task_id=task_id,
                command=payload.get("command", ""),
                timeout_seconds=effective_timeout_seconds,
            )
        elif kind == "browser":
            if not settings.browser_runner_enabled:
                browser_policy_payload = build_policy_audit_payload(
                    {
                        "decision": "deny",
                        "allowed": False,
                        "requires_approval": False,
                        "reason": "browser runner is not enabled",
                        "reason_code": "deny.browser_runner_disabled",
                        "trust_level": int(tool.get("trust_level") or 0),
                        "details": {"tool_name": tool.get("name"), "kind": "browser"},
                    },
                    source="executor.browser_gate",
                    context={"task_id": task_id, "tool_name": tool.get("name"), "kind": "browser"},
                )
                return update_task(
                    settings,
                    task_id=task_id,
                    status="blocked",
                    reason="browser runner is not enabled",
                    finished_at=utc_now(),
                    result_json={
                        "ok": False,
                        "duration_ms": 0,
                        "artifacts": {},
                        "policy": browser_policy_payload,
                    },
                ) or task
            result = run_browser_task(
                settings,
                task_id=task_id,
                url=payload.get("url", ""),
                timeout_seconds=effective_timeout_seconds,
                wait_until=payload.get("wait_until", "domcontentloaded"),
            )
        elif kind == "model":
            result = run_model_task(
                settings,
                task_id=task_id,
                payload=payload,
                timeout_seconds=effective_timeout_seconds,
            )
        else:
            result = run_unimplemented(kind)
    except Exception as exc:  # pragma: no cover - defensive safety net
        return update_task(
            settings,
            task_id=task_id,
            status="failed",
            stderr=str(exc),
            exit_code=1,
            finished_at=utc_now(),
            result_json={"ok": False, "duration_ms": 0, "artifacts": {}, "policy": policy_payload},
        ) or task

    final_status = "completed" if result.ok else "failed"
    updated = update_task(
        settings,
        task_id=task_id,
        status=final_status,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=int(result.timed_out),
        finished_at=utc_now(),
        result_json={
            "ok": result.ok,
            "duration_ms": result.duration_ms,
            "artifacts": result.artifacts,
            "policy": policy_payload,
            "timeout_budget": {
                "allowed": timeout_budget.allowed,
                "timeout_seconds": timeout_budget.timeout_seconds,
                "requested_seconds": timeout_budget.requested_seconds,
                "limit_seconds": timeout_budget.limit_seconds,
                "reason_code": timeout_budget.reason_code,
            },
        },
    )
    return updated or task
