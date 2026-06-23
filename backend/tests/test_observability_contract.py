from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability import build_structured_error, normalize_reason_code, normalize_runtime_event_name


class ObservabilityContractTests(TestCase):
    def test_runtime_event_name_aliases_are_normalized(self) -> None:
        self.assertEqual(normalize_runtime_event_name("running"), "started")
        self.assertEqual(normalize_runtime_event_name("pending_approval"), "blocked")
        self.assertEqual(normalize_runtime_event_name("completed"), "completed")

    def test_reason_codes_are_normalized_for_storage(self) -> None:
        self.assertEqual(normalize_reason_code("Blocked shell operator: &&"), "blocked_shell_operator")
        self.assertEqual(normalize_reason_code(""), "unknown_error")
        self.assertEqual(normalize_reason_code(None), "unknown_error")

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
