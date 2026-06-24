from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability import build_policy_audit_payload, build_structured_error, normalize_reason_code, normalize_runtime_event_name
from app.runtime_audit import build_runtime_event_audit_payload, summarize_runtime_audit


class ObservabilityContractTests(TestCase):
    def test_runtime_event_name_aliases_are_normalized(self) -> None:
        self.assertEqual(normalize_runtime_event_name("running"), "started")
        self.assertEqual(normalize_runtime_event_name("pending_approval"), "blocked")
        self.assertEqual(normalize_runtime_event_name("completed"), "completed")

    def test_reason_codes_are_normalized_for_storage(self) -> None:
        self.assertEqual(normalize_reason_code("Blocked shell operator: &&"), "blocked_shell_operator")
        self.assertEqual(normalize_reason_code(""), "unknown_error")
        self.assertEqual(normalize_reason_code(None), "unknown_error")

    def test_policy_audit_payload_is_normalized_and_audit_friendly(self) -> None:
        payload = build_policy_audit_payload(
            {
                "decision": "approval_required",
                "allowed": False,
                "requires_approval": True,
                "reason": "browser execution requires approval for external url: https://example.com",
                "reason_code": "approval.browser.external_url",
                "trust_level": 1,
                "details": {
                    "tool_name": "browser_runner",
                    "kind": "browser",
                    "matched_trigger": "external_url",
                    "policy_source": "metadata_override",
                    "policy_sources": ["default", "kind_override", "metadata_override"],
                },
            },
            source="executor.policy",
            context={"task_id": "task-1", "tool_name": "browser_runner"},
        )

        self.assertEqual(payload["decision"], "approval_required")
        self.assertFalse(payload["allowed"])
        self.assertTrue(payload["requires_approval"])
        self.assertEqual(payload["reason_code"], "approval_browser_external_url")
        self.assertEqual(payload["policy_source"], "executor.policy")
        self.assertEqual(payload["decision_summary"], "approval_required | approval_browser_external_url | browser execution requires approval for external url: https://example.com")
        self.assertEqual(payload["matched_trigger"], "external_url")
        self.assertEqual(payload["policy_sources"], ["default", "kind_override", "metadata_override"])
        self.assertEqual(payload["context"], {"task_id": "task-1", "tool_name": "browser_runner"})

    def test_runtime_event_audit_payload_and_summary_are_normalized(self) -> None:
        event = build_runtime_event_audit_payload(
            {
                "event_type": "running",
                "status": "running",
                "message": "runtime started",
                "reason_code": "runtime.start",
                "runtime_run_id": "run-1",
                "task_id": "task-1",
                "step_index": 1,
                "tool_name": "python_local",
                "kind": "python",
                "artifact_refs": ["/tmp/report.json"],
                "trace": {"correlation_id": "corr-1", "runtime_run_id": "run-1"},
            },
            source="runtime_runner",
        )
        self.assertEqual(event["event_name"], "started")
        self.assertEqual(event["reason_code"], "runtime_start")
        self.assertEqual(event["tool_name"], "python_local")
        self.assertEqual(event["artifact_refs"], ["/tmp/report.json"])
        self.assertEqual(event["trace"]["runtime_run_id"], "run-1")

        summary = summarize_runtime_audit(
            [
                event,
                build_runtime_event_audit_payload(
                    {
                        "event_type": "completed",
                        "status": "completed",
                        "message": "runtime finished",
                        "reason_code": "runtime.complete",
                        "runtime_run_id": "run-1",
                        "task_id": "task-1",
                        "step_index": 1,
                        "tool_name": "python_local",
                        "kind": "python",
                    },
                    source="runtime_runner",
                ),
            ],
            runtime_run={"id": "run-1", "status": "completed", "summary": "done"},
            steps=[
                {
                    "index": 1,
                    "status": "completed",
                    "detail": "step executed",
                    "task_id": "task-1",
                    "tool_name": "python_local",
                    "kind": "python",
                }
            ],
            trace_context={"correlation_id": "corr-1", "runtime_run_id": "run-1"},
        )

        self.assertEqual(summary["runtime_run_id"], "run-1")
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["step_count"], 1)
        self.assertEqual(summary["event_names"], ["started", "completed"])
        self.assertEqual(summary["reason_codes"], ["runtime_start", "runtime_complete"])
        self.assertIn("python_local", summary["tool_names"])
        self.assertEqual(summary["task_ids"], ["task-1"])
        self.assertEqual(summary["step_indices"], [1])
        self.assertEqual(summary["artifact_refs"], ["/tmp/report.json"])

    def test_structured_error_contains_reason_code_and_message(self) -> None:
        payload = build_structured_error(
            "shell.policy.blocked",
            "blocked shell operator: &&",
            details={"operator": "&&"},
            trace={"correlation_id": "trace-1", "runtime_run_id": "run-1"},
        )

        self.assertEqual(payload["reason_code"], "shell_policy_blocked")
        self.assertEqual(payload["message"], "blocked shell operator: &&")
        self.assertEqual(payload["details"], {"operator": "&&"})
        self.assertEqual(payload["trace"]["runtime_run_id"], "run-1")
