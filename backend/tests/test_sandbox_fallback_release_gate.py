from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_python_script
from app.settings import Settings


class SandboxFallbackReleaseGateTests(TestCase):
    @patch("app.sandbox.shutil.which", return_value=None)
    def test_release_gate_smoke_covers_sandbox_fallback(self, which_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                task_sandbox_mode="auto",
                task_sandbox_allow_network=False,
            )

            result = run_python_script(
                settings,
                task_id="release-gate-sandbox-fallback",
                script='print("hello from the fallback sandbox")\n',
                timeout_seconds=5,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["sandbox_mode"], "auto")
            self.assertEqual(result.artifacts["sandbox_backend"], "rlimit")
            self.assertTrue(result.artifacts["sandbox_fallback_used"])
            self.assertIn("falling back to rlimit", result.artifacts["sandbox_selection_reason"])
            which_mock.assert_called_once_with("bwrap")
