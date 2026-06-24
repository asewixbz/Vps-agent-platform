from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability import build_policy_audit_payload, build_structured_error, normalize_reason_code, normalize_runtime_event_name


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
