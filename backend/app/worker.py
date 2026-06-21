from __future__ import annotations

from .executor import execute_task
from .job_queue import get_queue
from .settings import get_settings
from .store import init_db, seed_builtin_tools
from .workflow_schedules import dispatch_due_workflow_schedules


def main() -> None:
    settings = get_settings()
    init_db(settings)
    seed_builtin_tools(settings)
    queue = get_queue()

    print(f"[worker] started queue={settings.task_queue_name} redis={settings.redis_url}")
    while True:
        task_id = queue.dequeue()
        if task_id is None:
            dispatched = dispatch_due_workflow_schedules(settings)
            if dispatched:
                print(f"[worker] dispatched {len(dispatched)} due workflow schedule(s)")
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
