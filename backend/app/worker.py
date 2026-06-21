from __future__ import annotations

from datetime import datetime, timezone

from .executor import execute_task
from .job_queue import get_queue
from .settings import get_settings
from .store import init_db, seed_builtin_tools
from .workflow_schedules import dispatch_due_workflow_schedules


def _dispatch_due_workflow_schedules_if_needed(settings, *, last_dispatch_at: datetime | None) -> datetime:
    now = datetime.now(timezone.utc)
    if last_dispatch_at is not None:
        elapsed_seconds = (now - last_dispatch_at).total_seconds()
        if elapsed_seconds < settings.worker_poll_seconds:
            return last_dispatch_at

    dispatched = dispatch_due_workflow_schedules(settings, now=now)
    if dispatched:
        print(f"[worker] dispatched {len(dispatched)} due workflow schedule(s)")
    return now


def main() -> None:
    settings = get_settings()
    init_db(settings)
    seed_builtin_tools(settings)
    queue = get_queue()

    print(f"[worker] started queue={settings.task_queue_name} redis={settings.redis_url}")
    last_schedule_dispatch_at: datetime | None = None
    while True:
        last_schedule_dispatch_at = _dispatch_due_workflow_schedules_if_needed(
            settings,
            last_dispatch_at=last_schedule_dispatch_at,
        )

        task_id = queue.dequeue()
        if task_id is None:
            if settings.worker_once:
                break
            continue

        print(f"[worker] executing task_id={task_id}")
        result = execute_task(settings, task_id)
        print(f"[worker] done task_id={task_id} status={result.get('status')}")

        if settings.worker_once:
            break


if __name__ == "__main__":
    main()
