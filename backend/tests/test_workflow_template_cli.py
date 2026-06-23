from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import build_parser


class WorkflowTemplateCliTests(TestCase):
    def test_public_cli_commands_are_registered(self) -> None:
        parser = build_parser()

        for command in ("health", "queue", "tools", "tasks", "model-health"):
            parsed = parser.parse_args([command])
            self.assertEqual(parsed.command, command)
            self.assertTrue(callable(parsed.func))

    def test_workflow_template_save_command_is_registered(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(["workflow-template-save"])
        self.assertEqual(parsed.command, "workflow-template-save")
        self.assertTrue(callable(parsed.func))

    def test_workflow_template_delete_command_is_registered(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(["workflow-template-delete", "custom_report"])
        self.assertEqual(parsed.command, "workflow-template-delete")
        self.assertTrue(callable(parsed.func))

    def test_workflow_template_compare_command_is_registered(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(["workflow-template-compare", "compare_workflow", "left-run", "right-run"])
        self.assertEqual(parsed.command, "workflow-template-compare")
        self.assertTrue(callable(parsed.func))

    def test_workflow_schedule_commands_are_registered(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(["workflow-schedules"])
        self.assertEqual(parsed.command, "workflow-schedules")
        self.assertTrue(callable(parsed.func))

        parsed = parser.parse_args(["workflow-schedule", "schedule-123"])
        self.assertEqual(parsed.command, "workflow-schedule")
        self.assertTrue(callable(parsed.func))

        parsed = parser.parse_args(["workflow-schedule-dispatch-due"])
        self.assertEqual(parsed.command, "workflow-schedule-dispatch-due")
        self.assertTrue(callable(parsed.func))
