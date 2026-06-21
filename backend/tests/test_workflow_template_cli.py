from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import build_parser


class WorkflowTemplateCliTests(TestCase):
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
