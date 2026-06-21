from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings
import app.worker as worker


class WorkerScheduleDispatchTests(TestCase):
    def test_worker_dispatches_due_schedules_before_dequeuing_tasks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                worker_poll_seconds=1,
                worker_once=True,
            )
            queue = Mock()
            queue.dequeue.return_value = "task-1"

            with patch.object(worker, "get_settings", return_value=settings) as get_settings_mock, \
                patch.object(worker, "init_db") as init_db_mock, \
                patch.object(worker, "seed_builtin_tools") as seed_builtin_tools_mock, \
                patch.object(worker, "get_queue", return_value=queue) as get_queue_mock, \
                patch.object(worker, "dispatch_due_workflow_schedules", return_value=[{"schedule": {"id": "schedule-1"}}]) as dispatch_mock, \
                patch.object(worker, "execute_task", return_value={"status": "completed"}) as execute_task_mock:
                worker.main()

            get_settings_mock.assert_called_once()
            init_db_mock.assert_called_once_with(settings)
            seed_builtin_tools_mock.assert_called_once_with(settings)
            get_queue_mock.assert_called_once()
            queue.dequeue.assert_called_once()
            dispatch_mock.assert_called_once()
            execute_task_mock.assert_called_once_with(settings, "task-1")
