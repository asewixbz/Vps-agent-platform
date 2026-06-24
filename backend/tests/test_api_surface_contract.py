from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.control_plane_api import TaskApproveRequest, TaskCreateRequest, approve_task_route, create_task_route, get_task_route, health, queue_info, tools
from app.main import app
from app.model_api import model_chat_route, model_health_route
from app.settings import Settings
from app.store import init_db, seed_builtin_tools
from app.workflow_templates_api import compare_workflow_template_runs_route

import app.control_plane_api as control_plane_api
import app.model_api as model_api
import app.runtime_api as runtime_api
import app.workflow_templates_api as workflow_templates_api


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def ping(self) -> bool:
        return True

    def size(self) -> int:
        return len(self.enqueued)

    def enqueue(self, task_id: str) -> None:
        self.enqueued.append(task_id)


class ApiSurfaceContractTests(TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(
            db_path=str(Path(tmpdir) / "app.db"),
            work_dir=str(Path(tmpdir) / "work"),
            default_timeout_seconds=5,
            task_timeout_hard_limit_seconds=5,
            runtime_max_steps_hard_limit=2,
            model_runner_enabled=True,
            browser_runner_enabled=False,
            require_approval_for_draft=False,
        )

    def test_public_routes_are_registered(self) -> None:
        paths = {route.path for route in app.routes if hasattr(route, "path")}
        expected_paths = {
            "/health",
            "/phases",
            "/queue",
            "/tools",
            "/tasks",
            "/tasks/{task_id}",
            "/tasks/{task_id}/approve",
            "/model/health",
            "/model/chat",
            "/persistence/layers",
            "/persistence/schema",
            "/workflow-templates/{template_name}/compare",
        }
        self.assertTrue(expected_paths.issubset(paths), f"missing routes: {sorted(expected_paths - paths)}")

    def test_public_surface_smoke_contracts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            init_db(settings)
            seed_builtin_tools(settings)
            fake_queue = FakeQueue()

            left_run = {
                "id": "left-run",
                "goal": "first goal",
                "status": "completed",
                "summary": "left summary",
                "attempts": 1,
                "checkpoint": {"next_step_index": 2},
                "context": {
                    "workflow_template_name": "compare_workflow",
                    "workflow_inputs": {"mode": "left"},
                },
                "steps": [
                    {
                        "status": "completed",
                        "result": {
                            "artifacts": {
                                "workdir": "/tmp/left",
                            }
                        },
                    }
                ],
            }
            right_run = {
                "id": "right-run",
                "goal": "second goal",
                "status": "partial",
                "summary": "right summary",
                "attempts": 2,
                "checkpoint": {"next_step_index": 3},
                "context": {
                    "workflow_template_name": "compare_workflow",
                    "workflow_inputs": {"mode": "right"},
                },
                "steps": [
                    {
                        "status": "completed",
                        "result": {
                            "artifacts": {
                                "workdir": "/tmp/right",
                            }
                        },
                    }
                ],
            }
            fake_model_response = SimpleNamespace(
                text="hello from model",
                structured_data={"ok": True},
                tool_calls=[],
                finish_reason="stop",
                model="fake-model",
                provider="fake-provider",
                usage=None,
                raw={"raw": True},
                metadata={"status": "completed"},
            )

            with (
                patch.object(control_plane_api, "settings", settings),
                patch.object(control_plane_api, "get_queue", return_value=fake_queue),
                patch.object(model_api, "settings", settings),
                patch.object(model_api, "chat_model", return_value=fake_model_response),
                patch.object(workflow_templates_api, "settings", settings),
                patch.object(workflow_templates_api, "resolve_workflow_template", return_value={"name": "compare_workflow", "kind": "workflow", "summary": "Compare"}),
                patch.object(workflow_templates_api, "workflow_template_to_dict", side_effect=lambda template: template),
                patch.object(workflow_templates_api, "compare_workflow_template_runs", wraps=workflow_templates_api.compare_workflow_template_runs),
                patch.object(workflow_templates_api, "get_runtime_run", side_effect=lambda _settings, runtime_run_id: left_run if runtime_run_id == "left-run" else right_run),
            ):
                health_snapshot = health()
                self.assertEqual(health_snapshot["status"], "ok")
                self.assertEqual(health_snapshot["queue"]["size"], 0)
                self.assertTrue(health_snapshot["database"]["healthy"])

                queue_snapshot = queue_info()
                self.assertEqual(queue_snapshot["name"], settings.task_queue_name)
                self.assertEqual(queue_snapshot["size"], 0)

                tool_rows = tools()
                tool_names = {tool["name"] for tool in tool_rows}
                self.assertTrue({"python_local", "shell_safe", "browser_runner", "model_eval_runner"}.issubset(tool_names))

                created = create_task_route(
                    TaskCreateRequest(
                        tool_name="python_local",
                        payload={"script": 'print("hello")'},
                        auto_run=False,
                    )
                )
                self.assertEqual(created["status"], "draft")
                self.assertFalse(created["approved"])

                approved = approve_task_route(created["id"], TaskApproveRequest(note="approved for smoke"))
                self.assertEqual(approved["status"], "queued")
                self.assertTrue(approved["approved"])
                self.assertEqual(fake_queue.enqueued, [created["id"]])
                self.assertEqual(queue_info()["size"], 1)

                fetched = get_task_route(created["id"])
                self.assertEqual(fetched["id"], created["id"])
                self.assertEqual(fetched["status"], "queued")

                model_health_snapshot = model_health_route()
                self.assertIn("status", model_health_snapshot)
                self.assertIn("adapter", model_health_snapshot)

                model_chat_snapshot = model_chat_route({"payload": {"messages": [{"role": "user", "content": "hi"}]}})
                self.assertEqual(model_chat_snapshot["text"], "hello from model")
                self.assertEqual(model_chat_snapshot["provider"], "fake-provider")
                self.assertEqual(model_chat_snapshot["structured_data"], {"ok": True})

                comparison = compare_workflow_template_runs_route("compare_workflow", "left-run", "right-run")
                self.assertEqual(comparison["workflow_template"]["name"], "compare_workflow")
                self.assertEqual(comparison["left_runtime_run_id"], "left-run")
                self.assertEqual(comparison["right_runtime_run_id"], "right-run")
                self.assertIn("comparison", comparison)
                self.assertIn("differences", comparison["comparison"])
                self.assertIn("goal", comparison["comparison"]["differences"])

    def test_agent_run_injects_inline_execution_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            init_db(settings)
            seed_builtin_tools(settings)

            fake_execution = SimpleNamespace(
                runtime_run_id="runtime-run-1",
                status="completed",
                summary="completed",
                context={"execution_mode": "inline"},
            )

            with (
                patch.object(runtime_api, "settings", settings),
                patch.object(runtime_api, "run_inline_runtime", return_value=fake_execution) as run_inline_runtime_mock,
                patch.object(
                    runtime_api,
                    "runtime_execution_to_dict",
                    side_effect=lambda execution: {
                        "runtime_run_id": execution.runtime_run_id,
                        "status": execution.status,
                        "context": execution.context,
                    },
                ),
            ):
                response = runtime_api.agent_run(
                    runtime_api.AgentRunRequest(
                        goal="Inspect route execution",
                        context={},
                        max_steps=1,
                    )
                )

            self.assertEqual(run_inline_runtime_mock.call_count, 1)
            self.assertEqual(run_inline_runtime_mock.call_args.kwargs["context"]["execution_mode"], "inline")
            self.assertEqual(response["context"]["execution_mode"], "inline")
            self.assertEqual(response["runtime_run_id"], "runtime-run-1")
