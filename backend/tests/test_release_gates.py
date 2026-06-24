from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.artifact_lifecycle import normalize_artifact_manifest
from app.memory import init_memory_schema
from app.memory_links import init_memory_links_schema
from app.policy import evaluate
from app.runner import run_python_script
from app.security_controls import resolve_runtime_step_budget, resolve_task_timeout_budget
from app.settings import Settings
from app.store import init_db, seed_builtin_tools
from app.runtime_trace import build_runtime_run_trace
from app.workflow_schedules import dispatch_due_workflow_schedules, register_workflow_schedule


class ReleaseGateTests(TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(
            db_path=str(Path(tmpdir) / "app.db"),
            work_dir=str(Path(tmpdir) / "work"),
            default_timeout_seconds=5,
            task_timeout_hard_limit_seconds=5,
            runtime_max_steps_hard_limit=2,
            require_approval_for_draft=False,
        )

    def test_policy_regression_and_guardrails(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            tool = {"name": "shell_safe", "kind": "shell", "status": "trusted", "trust_level": 2, "metadata": {"builtin": True}}

            safe = evaluate(tool, {"command": "echo hello"}, settings)
            self.assertTrue(safe.allowed)
            self.assertFalse(safe.requires_approval)
            self.assertEqual(safe.decision, "allow")
            self.assertEqual(safe.reason_code, "allow.shell_policy_passed")

            denied = evaluate(tool, {"command": "python -c \"print(1)\""}, settings)
            self.assertFalse(denied.allowed)
            self.assertFalse(denied.requires_approval)
            self.assertEqual(denied.decision, "deny")
            self.assertEqual(denied.reason_code, "deny.shell.not_allowlisted")

            denied_snippet = evaluate(tool, {"command": "rm -rf /"}, settings)
            self.assertFalse(denied_snippet.allowed)
            self.assertFalse(denied_snippet.requires_approval)
            self.assertEqual(denied_snippet.decision, "deny")
            self.assertEqual(denied_snippet.reason_code, "deny.shell.rm_rf")

            browser_external = evaluate(
                {"name": "browser_runner", "kind": "browser", "status": "tested", "trust_level": 1},
                {"url": "https://example.com"},
                settings,
            )
            self.assertFalse(browser_external.allowed)
            self.assertTrue(browser_external.requires_approval)
            self.assertEqual(browser_external.reason_code, "approval.browser.external_url")

            browser_denied = evaluate(
                {"name": "browser_runner", "kind": "browser", "status": "tested", "trust_level": 1},
                {"url": "file:///tmp/index.html"},
                settings,
            )
            self.assertFalse(browser_denied.allowed)
            self.assertFalse(browser_denied.requires_approval)
            self.assertEqual(browser_denied.reason_code, "deny.browser_unsupported_scheme")

            timeout_budget = resolve_task_timeout_budget(settings, tool, {"timeout_seconds": 10}, requested_timeout_seconds=10)
            self.assertFalse(timeout_budget.allowed)
            self.assertEqual(timeout_budget.reason_code, "deny.timeout_exceeds_limit")
            self.assertEqual(timeout_budget.limit_seconds, 5)

            step_budget = resolve_runtime_step_budget(settings, 5)
            self.assertFalse(step_budget.allowed)
            self.assertEqual(step_budget.reason_code, "deny.max_steps_exceeds_limit")
            self.assertEqual(step_budget.limit_max_steps, 2)

    def test_schedule_dispatch_smoke(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            init_db(settings)
            init_memory_schema(settings)
            init_memory_links_schema(settings)
            seed_builtin_tools(settings)

            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id="release-gate-schedule-run",
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

            self.assertEqual(schedule["status"], "active")
            self.assertIsNotNone(schedule["next_run_at"])

            dispatched = dispatch_due_workflow_schedules(
                settings,
                now=datetime.now(timezone.utc) + timedelta(days=1),
            )

            self.assertEqual(len(dispatched), 1)
            self.assertEqual(dispatched[0]["execution"]["status"], "completed")
            self.assertEqual(dispatched[0]["schedule"]["last_run_status"], "completed")
            self.assertEqual(dispatched[0]["schedule"]["target_workflow_name"], "report_workflow")

    def test_runtime_resume_artifact_manifest_and_provenance_fetch_smoke(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            init_db(settings)
            init_memory_schema(settings)
            init_memory_links_schema(settings)
            seed_builtin_tools(settings)

            context = {
                "workflow_template_name": "schedule_workflow",
                "workflow_inputs": {
                    "cadence": "daily",
                    "timezone": "UTC",
                    "target_workflow": "report_workflow",
                    "target_goal": "Daily report",
                    "target_inputs": {
                        "report_title": "Daily report",
                        "audience": "ops",
                    },
                },
            }

            first_run = run_python_script(
                settings,
                task_id="release-gate-runtime-run",
                script=(
                    "from pathlib import Path\n"
                    'Path("report.json").write_text("{}", encoding="utf-8")\n'
                    'Path("report.md").write_text("# report\n", encoding="utf-8")\n'
                    'print("done")\n'
                ),
                timeout_seconds=1,
            )
            self.assertTrue(first_run.ok)
            self.assertEqual(first_run.artifacts["sandbox_mode"], "auto")

            schedule = register_workflow_schedule(
                settings,
                source_runtime_run_id="release-gate-schedule-run-2",
                source_template_name="schedule_workflow",
                source_goal="Plan a recurring schedule",
                workflow_inputs={
                    "cadence": "daily",
                    "timezone": "UTC",
                    "target_workflow": "report_workflow",
                    "target_goal": "Daily report",
                    "target_inputs": {
                        "report_title": "Daily report",
                        "audience": "ops",
                    },
                },
            )
            self.assertEqual(schedule["status"], "active")

            dispatched = dispatch_due_workflow_schedules(
                settings,
                now=datetime.now(timezone.utc) + timedelta(days=1),
            )
            self.assertEqual(len(dispatched), 1)
            self.assertEqual(dispatched[0]["execution"]["status"], "completed")

            execute_steps = [step for step in dispatched[0]["execution"]["steps"] if step.get("kind") == "execute"]
            self.assertTrue(execute_steps)
            artifact_map = execute_steps[0].get("result", {}).get("artifacts", {}) if isinstance(execute_steps[0].get("result"), dict) else {}
            self.assertIn("artifact_manifest_path", artifact_map)
            manifest_path = Path(str(artifact_map["artifact_manifest_path"]))
            self.assertTrue(manifest_path.exists())

            manifest = normalize_artifact_manifest(json.loads(manifest_path.read_text(encoding="utf-8")), source="release_gates_smoke")
            self.assertIsNotNone(manifest)
            self.assertGreaterEqual(len(manifest.get("artifacts") or []), 1)

            trace = build_runtime_run_trace(settings, runtime_run_id=dispatched[0]["execution"]["runtime_run_id"], limit=50, depth=2)
            self.assertIsNotNone(trace)
            assert trace is not None
            self.assertEqual(trace["navigation"]["runtime_run_id"], dispatched[0]["execution"]["runtime_run_id"])
            self.assertGreaterEqual(trace["event_count"], 1)
            self.assertGreaterEqual(trace["step_count"], 2)
            self.assertIn("provenance", trace)
            self.assertIn("artifacts", trace)
