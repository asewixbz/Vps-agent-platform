from __future__ import annotations

from typing import Any

from .agent_runtime import run_agent_runtime
from .settings import Settings

INLINE_RUNTIME_EXECUTION_MODE = "inline"


def run_inline_runtime(
    settings: Settings,
    *,
    goal: str,
    context: dict[str, Any] | None = None,
    max_steps: int = 5,
    resume_from_step_index: int | None = None,
    runtime_run_id: str | None = None,
):
    execution_context = dict(context or {})
    execution_context.setdefault("execution_mode", INLINE_RUNTIME_EXECUTION_MODE)
    return run_agent_runtime(
        settings,
        goal=goal,
        context=execution_context,
        max_steps=max_steps,
        resume_from_step_index=resume_from_step_index,
        runtime_run_id=runtime_run_id,
    )
