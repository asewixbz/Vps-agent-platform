from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow_templates import default_workflow_templates, normalize_workflow_template, resolve_workflow_template, workflow_template_to_dict


class WorkflowTemplateTests(TestCase):
    def test_normalize_workflow_template_requires_execute_tool(self) -> None:
        template = normalize_workflow_template(
            {
                "name": "broken_template",
                "kind": "scan",
                "steps": [
                    {
                        "title": "Run the scan",
                        "kind": "execute",
                        "description": "Execute the scan without a tool name.",
                    }
                ],
            }
        )

        self.assertIsNone(template)

    def test_resolve_workflow_template_prefers_direct_template(self) -> None:
        template = resolve_workflow_template(
            {
                "workflow_template": {
                    "name": "custom_report",
                    "kind": "report",
                    "summary": "Custom report workflow",
                    "notes": ["custom note"],
                    "metadata": {"owner": "team-a"},
                    "steps": [
                        {
                            "title": "Collect inputs",
                            "kind": "inspect",
                            "description": "Collect report inputs.",
                        },
                        {
                            "title": "Generate report",
                            "kind": "execute",
                            "description": "Generate the report.",
                            "tool_name": "python_local",
                        },
                    ],
                }
            }
        )

        self.assertIsNotNone(template)
        assert template is not None
        self.assertEqual(template.name, "custom_report")
        self.assertEqual(template.kind, "report")
        self.assertEqual(template.steps[1].tool_name, "python_local")
        self.assertEqual(template.notes, ["custom note"])
        self.assertEqual(template.metadata, {"owner": "team-a"})

    def test_resolve_workflow_template_falls_back_to_builtin_registry(self) -> None:
        template = resolve_workflow_template({"workflow_template_name": "rank_workflow"})

        self.assertIsNotNone(template)
        assert template is not None
        self.assertEqual(template.name, "rank_workflow")
        self.assertEqual(template.kind, "rank")
        self.assertEqual(template.recommended_tool, "python_local")
        self.assertEqual(len(template.steps), 3)

    def test_default_workflow_templates_cover_phase_five_workflows(self) -> None:
        templates = default_workflow_templates()

        self.assertEqual(set(templates.keys()), {"scan_workflow", "rank_workflow", "report_workflow"})
        self.assertEqual(templates["scan_workflow"].steps[1].tool_name, "python_local")
        self.assertEqual(templates["report_workflow"].metadata["phase"], 5)

    def test_workflow_template_to_dict_is_serializable(self) -> None:
        template = resolve_workflow_template({"workflow_template_name": "scan_workflow"})
        self.assertIsNotNone(template)
        assert template is not None

        data = workflow_template_to_dict(template)

        self.assertEqual(data["name"], "scan_workflow")
        self.assertEqual(data["steps"][1]["kind"], "execute")
        self.assertEqual(data["steps"][1]["tool_name"], "python_local")
