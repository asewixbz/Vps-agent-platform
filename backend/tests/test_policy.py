from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.policy import evaluate
from app.settings import Settings


class PolicyTests(TestCase):
    def test_shell_policy_rejects_malformed_command_without_raising(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                require_approval_for_draft=False,
            )

            decision = evaluate(
                {"name": "local_shell", "kind": "shell", "status": "trusted"},
                {"command": "echo 'unterminated"},
                settings,
            )

            self.assertFalse(decision.allowed)
            self.assertFalse(decision.requires_approval)
            self.assertEqual(decision.reason, "shell command could not be parsed safely")

    def test_shell_policy_blocks_control_operators_before_runner(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                require_approval_for_draft=False,
            )

            decision = evaluate(
                {"name": "local_shell", "kind": "shell", "status": "trusted"},
                {"command": "echo hello && whoami"},
                settings,
            )

            self.assertFalse(decision.allowed)
            self.assertFalse(decision.requires_approval)
            self.assertEqual(decision.reason, "blocked shell operator: &&")

    def test_browser_policy_requires_approval_for_external_http_urls(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                require_approval_for_draft=False,
            )

            decision = evaluate(
                {"name": "browser_runner", "kind": "browser", "status": "tested", "trust_level": 1},
                {"url": "https://example.com"},
                settings,
            )

            self.assertFalse(decision.allowed)
            self.assertTrue(decision.requires_approval)
            self.assertEqual(decision.reason_code, "approval.browser.external_url")

    def test_browser_policy_rejects_unsupported_url_schemes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                require_approval_for_draft=False,
            )

            decision = evaluate(
                {"name": "browser_runner", "kind": "browser", "status": "tested", "trust_level": 1},
                {"url": "file:///tmp/index.html"},
                settings,
            )

            self.assertFalse(decision.allowed)
            self.assertFalse(decision.requires_approval)
            self.assertEqual(decision.reason_code, "deny.browser_unsupported_scheme")
