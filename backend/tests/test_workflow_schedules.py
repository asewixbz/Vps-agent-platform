from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings
from app.store import init_db, seed_builtin_tools
from app.workflow_template_registry import upsert_custom_workflow_template
from app.workflow_schedules import dispatch_due_workflow_schedules, register_workflow_schedule


class WorkflowScheduleTests(TestCase):
    def test_register_and_dispatch_recurring_workflow_schedule(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
            )
            init_db(settings)
            seed_builtin_tools(settings)

            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id="schedule-run-1",
                source_template_name="schedule_workflow",
                source_goal="Plan a recurring report",
                workflow_inputs={
                    "cadence": "daily",
                    "timezone": "UTC",
                    "target_workflow": "report_workflow",
                    "target_goal": "Daily report",
                    "target_inputs": {
                        "report_title": "Daily report",
                        "audience": "ops",
                        "source_data": ["alpha", "beta"],
                        "output_constraints": ["concise"],
                    },
                },
            )

            self.assertEqual(schedule["source_runtime_run_id"], "schedule-run-1")
            self.assertEqual(schedule["target_workflow_name"], "report_workflow")
            self.assertEqual(schedule["status"], "active")
            self.assertIsNotNone(schedule["next_run_at"])
            original_next_run_at = schedule["next_run_at"]

            dispatched = dispatch_due_workflow_schedules(
                settings,
                now=datetime.now(timezone.utc) + timedelta(days=2),
            )

            self.assertEqual(len(dispatched), 1)
            dispatched_item = dispatched[0]
            self.assertIn("execution", dispatched_item)
            self.assertIn("schedule", dispatched_item)
            self.assertEqual(dispatched_item["execution"]["status"], "completed")
            self.assertEqual(dispatched_item["schedule"]["status"], "active")
            self.assertEqual(dispatched_item["schedule"]["last_run_status"], "completed")
            self.assertGreater(dispatched_item["schedule"]["next_run_at"], original_next_run_at)
            self.assertEqual(dispatched_item["schedule"]["target_workflow_name"], "report_workflow")
            self.assertEqual(dispatched_item["schedule"]["target_goal"], "Daily report")
            self.assertEqual(dispatched_item["workflow_inputs"]["report_title"], "Daily report")

    def test_dispatch_due_workflow_schedules_resolves_custom_templates(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
            )
            init_db(settings)
            seed_builtin_tools(settings)
            upsert_custom_workflow_template(
                settings,
                {
                    "name": "custom_report_workflow",
                    "kind": "report",
                    "summary": "Custom report workflow",
                    "recommended_tool": "python_local",
                    "steps": [
                        {
                            "title": "Collect reporting inputs",
                            "kind": "inspect",
                            "description": "Collect the reporting inputs.",
                        },
                        {
                            "title": "Generate the report",
                            "kind": "execute",
                            "description": "Generate the report with Python.",
                            "tool_name": "python_local",
                        },
                        {
                            "title": "Verify the report",
                            "kind": "verify",
                            "description": "Check the generated report.",
                        },
                    ],
                },
            )

            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id="schedule-run-2",
                source_template_name="schedule_workflow",
                source_goal="Plan a custom recurring report",
                workflow_inputs={
                    "cadence": "every 12 hours",
                    "timezone": "UTC",
                    "target_workflow": "custom_report_workflow",
                    "target_goal": "Custom recurring report",
                    "target_inputs": {
                        "report_title": "Custom recurring report",
                        "audience": "finance",
                        "source_data": ["gamma", "delta"],
                        "output_constraints": ["cited"],
                    },
                },
            )

            dispatched = dispatch_due_workflow_schedules(
                settings,
                now=datetime.now(timezone.utc) + timedelta(days=1),
            )

            self.assertEqual(len(dispatched), 1)
            self.assertEqual(dispatched[0]["schedule"]["target_workflow_name"], "custom_report_workflow")
            self.assertEqual(dispatched[0]["execution"]["status"], "completed")
            self.assertEqual(dispatched[0]["schedule"]["last_run_status"], "completed")
            self.assertEqual(schedule["target_workflow_name"], "custom_report_workflow")

    def test_register_and_dispatch_one_shot_workflow_schedule_completes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
            )
            init_db(settings)
            seed_builtin_tools(settings)

            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id="schedule-run-3",
                source_template_name="schedule_workflow",
                source_goal="Plan a one-shot report",
                workflow_inputs={
                    "cadence": "once",
                    "timezone": "UTC",
                    "target_workflow": "report_workflow",
                    "target_goal": "One-shot report",
                    "target_inputs": {
                        "report_title": "One-shot report",
                        "audience": "ops",
                    },
                },
            )

            self.assertEqual(schedule["status"], "active")
            self.assertIsNotNone(schedule["next_run_at"])

            dispatched = dispatch_due_workflow_schedules(
                settings,
                now=datetime.now(timezone.utc) + timedelta(days=1),
            )

            self.assertEqual(len(dispatched), 1)
            self.assertEqual(dispatched[0]["execution"]["status"], "completed")
            self.assertEqual(dispatched[0]["schedule"]["status"], "completed")
            self.assertIsNone(dispatched[0]["schedule"]["next_run_at"])
            self.assertEqual(dispatched[0]["schedule"]["last_run_status"], "completed")
