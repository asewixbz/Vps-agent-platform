from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.planner import build_execution_plan
from app.settings import Settings
from app.store import init_db, seed_builtin_tools
from app.workflow_templates import (
    build_workflow_template_context,
    default_workflow_templates,
    normalize_workflow_template,
    resolve_workflow_template,
    workflow_template_to_dict,
)


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

    def test_build_workflow_template_context_materializes_report_payloads(self) -> None:
        template = resolve_workflow_template({"workflow_template_name": "report_workflow"})
        self.assertIsNotNone(template)
        assert template is not None

        context = build_workflow_template_context(
            template,
            workflow_inputs={
                "report_title": "Weekly update",
                "audience": "ops",
                "output_constraints": ["concise", "cited"],
                "source_data": {"items": ["alpha", "beta"]},
            },
        )

        self.assertEqual(context["workflow_template_name"], "report_workflow")
        self.assertEqual(context["workflow_inputs"]["audience"], "ops")
        self.assertIn("payload_by_tool", context)
        self.assertIn("tool_payloads", context)
        self.assertEqual(context["payload_by_tool"]["python_local"], context["tool_payloads"]["python_local"])

        script = context["payload_by_tool"]["python_local"]["script"]
        self.assertIn("report.json", script)
        self.assertIn("report.md", script)
        self.assertIn("_report_result", script)
        self.assertIn("Workflow template", script)

    def test_build_workflow_template_context_materializes_rank_payloads(self) -> None:
        template = resolve_workflow_template({"workflow_template_name": "rank_workflow"})
        self.assertIsNotNone(template)
        assert template is not None

        context = build_workflow_template_context(
            template,
            workflow_inputs={
                "criteria": {
                    "weights": {"priority": 3, "fit": 2},
                    "preferred_values": {"status": "ready"},
                    "required_fields": ["title"],
                },
                "candidates": [
                    {"title": "A", "priority": 2, "fit": 1, "status": "ready"},
                    {"title": "B", "priority": 1, "fit": 2, "status": "pending"},
                ],
            },
        )

        self.assertEqual(context["workflow_template_name"], "rank_workflow")
        script = context["payload_by_tool"]["python_local"]["script"]
        self.assertIn("ranking.json", script)
        self.assertIn("_score_candidate", script)
        self.assertIn("required_fields", script)

    def test_build_execution_plan_prefers_workflow_template_context(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(db_path=str(Path(tmpdir) / "app.db"))
            init_db(settings)
            seed_builtin_tools(settings)

            plan = build_execution_plan(
                settings,
                goal="Scan vendor listings",
                context={"workflow_template_name": "scan_workflow"},
            )

        self.assertEqual(plan.source, "workflow_template")
        self.assertEqual(plan.summary, "Scan a source set and normalize the items for downstream workflows.")
        self.assertEqual(plan.steps[1].tool_name, "python_local")
        self.assertIn("Resolved workflow template 'scan_workflow'", plan.notes)
        self.assertEqual(plan.metadata["workflow_template"]["name"], "scan_workflow")
