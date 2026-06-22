from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import runtime_trace


class RuntimeTraceTests(TestCase):
    def setUp(self) -> None:
        self.settings = object()
        self.runtime_run = {
            "id": "run-1",
            "goal": "Inspect the chain",
            "status": "completed",
            "summary": "done",
            "context": {"correlation_id": "corr-1"},
            "steps": [
                {
                    "index": 1,
                    "title": "Execute work",
                    "kind": "execute",
                    "status": "completed",
                    "tool_name": "python_local",
                    "task_id": "task-1",
                    "detail": "step executed",
                    "result": {"artifacts": {"report_path": "/tmp/report.json", "artifact_paths": ["/tmp/report.json"]}},
                }
            ],
        }
        self.events = [
            {
                "id": 1,
                "runtime_run_id": "run-1",
                "event_type": "running",
                "step_index": None,
                "message": "runtime started",
                "payload_json": {"status": "running", "trace": {"correlation_id": "corr-1", "runtime_run_id": "run-1"}},
            },
            {
                "id": 2,
                "runtime_run_id": "run-1",
                "event_type": "completed",
                "step_index": 1,
                "message": "runtime completed",
                "payload_json": {"status": "completed", "trace": {"correlation_id": "corr-1", "runtime_run_id": "run-1"}},
            },
        ]
        self.tasks = {
            "task-1": {
                "id": "task-1",
                "tool_name": "python_local",
                "status": "completed",
                "payload": {"script": "print('hi')"},
            }
        }
        self.snapshot = {
            "id": "memory-1",
            "kind": "runtime_summary",
            "scope_type": "runtime_run",
            "scope_id": "run-1",
            "title": "Run snapshot",
            "summary": "snapshot",
            "artifacts": [
                {"artifact_type": "file", "artifact_ref": "/tmp/report.json", "label": "report"},
            ],
        }

    def _get_run(self, settings: object, runtime_run_id: str) -> dict[str, object] | None:
        return self.runtime_run if runtime_run_id == "run-1" else None

    def _list_events(self, settings: object, runtime_run_id: str, *, limit: int | None = None) -> list[dict[str, object]]:
        return list(self.events) if runtime_run_id == "run-1" else []

    def _get_task(self, settings: object, task_id: str) -> dict[str, object] | None:
        return self.tasks.get(task_id)

    def _build_provenance(self, settings: object, runtime_run_id: str, *, limit: int = 100, depth: int = 2) -> dict[str, object]:
        return {
            "runtime_run_id": runtime_run_id,
            "memory_snapshot": self.snapshot,
            "provenance": {
                "root": {**self.snapshot, "section": "root", "depth": 0, "artifact_count": 1, "artifacts": self.snapshot["artifacts"]},
                "one_hop": [],
                "transitive": [],
                "artifact_only": {"artifacts": [], "links": [], "refs": ["/tmp/report.json"], "artifact_count": 0, "artifact_link_count": 0, "artifact_ref_count": 1},
                "links": [],
                "traversal": {"visited_record_count": 0},
            },
        }

    @patch("app.runtime_trace.get_memory_record")
    @patch("app.runtime_trace.build_runtime_run_provenance")
    @patch("app.runtime_trace.get_task")
    @patch("app.runtime_trace.list_runtime_run_events")
    @patch("app.runtime_trace.get_runtime_run")
    def test_build_runtime_run_trace_includes_events_steps_and_artifacts(
        self,
        mock_get_run,
        mock_list_events,
        mock_get_task,
        mock_build_provenance,
        mock_get_memory_record,
    ) -> None:
        mock_get_run.side_effect = self._get_run
        mock_list_events.side_effect = self._list_events
        mock_get_task.side_effect = self._get_task
        mock_build_provenance.side_effect = self._build_provenance
        mock_get_memory_record.return_value = self.snapshot

        trace = runtime_trace.build_runtime_run_trace(self.settings, runtime_run_id="run-1", limit=10, depth=2)

        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertEqual(trace["navigation"]["runtime_run_id"], "run-1")
        self.assertEqual(trace["navigation"]["task_ids"], ["task-1"])
        self.assertEqual(trace["navigation"]["artifact_refs"], ["/tmp/report.json"])
        self.assertEqual(trace["event_count"], 2)
        self.assertEqual(trace["step_count"], 1)
        self.assertEqual(trace["events"][0]["event_name"], "started")
        self.assertEqual(trace["events"][1]["event_name"], "completed")
        self.assertEqual(trace["steps"][0]["task"]["id"], "task-1")
        self.assertEqual(trace["steps"][0]["artifact_count"], 1)
        self.assertEqual(trace["memory_snapshot"]["id"], "memory-1")
