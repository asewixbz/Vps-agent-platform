from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.policy import evaluate
from app.security_controls import get_tool_policy_profile
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
            self.assertEqual(decision.details["policy_source"], "default")

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
            self.assertEqual(decision.details["scheme"], "file")

    def test_policy_override_precedence_uses_default_kind_tool_then_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                require_approval_for_draft=False,
                tool_policy_overrides_json=json.dumps(
                    {
                        "__default__": {
                            "allow_reason": "default allow",
                            "trust_level": 1,
                            "requires_approval": True,
                            "approval_triggers": ["default-trigger"],
                        },
                        "shell": {
                            "allow_reason": "kind allow",
                            "trust_level": 2,
                            "requires_approval": False,
                            "approval_triggers": ["kind-trigger"],
                            "deny_triggers": ["kind-deny"],
                        },
                        "local_shell": {
                            "allow_reason": "tool allow",
                            "trust_level": 3,
                            "requires_approval": False,
                            "deny_triggers": ["tool-deny"],
                        },
                    }
                ),
            )

            profile = get_tool_policy_profile(
                settings,
                {
                    "name": "local_shell",
                    "kind": "shell",
                    "status": "trusted",
                    "trust_level": 0,
                    "metadata": {
                        "policy_overrides": {
                            "allow_reason": "metadata allow",
                            "trust_level": 4,
                            "requires_approval": True,
                            "approval_triggers": ["metadata-trigger"],
                        }
                    },
                },
            )

            self.assertEqual(profile["allow_reason"], "metadata allow")
            self.assertEqual(profile["trust_level"], 4)
            self.assertTrue(profile["requires_approval"])
            self.assertEqual(
                profile["policy_sources"],
                ["default", "default_override", "kind_override", "tool_override", "metadata_override"],
            )
            self.assertEqual(profile["policy_source"], "metadata_override")
            self.assertIn("default-trigger", profile["approval_triggers"])
            self.assertIn("kind-trigger", profile["approval_triggers"])
            self.assertIn("metadata-trigger", profile["approval_triggers"])
            self.assertIn("kind-deny", profile["deny_triggers"])
            self.assertIn("tool-deny", profile["deny_triggers"])
            self.assertEqual(profile["deny_triggers"].count("kind-deny"), 1)
