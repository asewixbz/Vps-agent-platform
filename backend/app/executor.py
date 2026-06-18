from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .policy import evaluate
from .runner import run_browser_task, run_model_task, run_python_script, run_shell_command, run_unimplemented
from .settings import Settings
from .store import get_task, get_tool, update_task, utc_now


def execute_task(settings: Settings, task_id: str, timeout_seconds: int | None = None) -> dict[str, Any]:
    task = get_task(settings, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    tool = get_tool(settings, name=task["tool_name"])
    if tool is None:
        return update_task(
            settings,
            task_id=task_id,
            status="blocked",
            reason=f'tool "{task["tool_name"]}" no longer exists',
            finished_at=utc_now(),
        ) or task

    decision = evaluate(tool, task["payload"], settings, approved=bool(task.get("approved")))
    if not decision.allowed:
        new_status = "pending_approval" if decision.requires_approval else "blocked"
        return update_task(
            settings,
            task_id=task_id,
            status=new_status,
            reason=decision.reason,
            finished_at=utc_now(),
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
    try:
        if kind == "python":
            result = run_python_script(
                settings,
                task_id=task_id,
                script=payload.get("script", ""),
                timeout_seconds=timeout_seconds,
            )
        elif kind == "shell":
            result = run_shell_command(
                settings,
                task_id=task_id,
                command=payload.get("command", ""),
                timeout_seconds=timeout_seconds,
            )
        elif kind == "browser":
            result = run_browser_task(
                settings,
                task_id=task_id,
                url=payload.get("url", ""),
                timeout_seconds=timeout_seconds,
                wait_until=payload.get("wait_until", "domcontentloaded"),
            )
        elif kind == "model":
            result = run_model_task(
                settings,
                task_id=task_id,
                payload=payload,
                timeout_seconds=timeout_seconds,
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
            result_json={"ok": False, "duration_ms": 0, "artifacts": {}},
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
        },
    )
    return updated or task
