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
