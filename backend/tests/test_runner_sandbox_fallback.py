from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_python_script
from app.settings import Settings


class RunnerSandboxFallbackReleaseGateTests(TestCase):
    def test_python_runner_reports_fallback_when_bubblewrap_build_fails(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                task_sandbox_mode="auto",
                task_sandbox_allow_network=False,
                default_timeout_seconds=5,
            )

            with patch("app.sandbox._bubblewrap_available", return_value=True), patch(
                "app.sandbox._build_bubblewrap_argv", side_effect=RuntimeError("boom")
            ):
                result = run_python_script(
                    settings,
                    task_id="task-fallback",
                    script='print("fallback")\n',
                    timeout_seconds=5,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["sandbox_backend"], "rlimit")
            self.assertEqual(result.artifacts["sandbox_mode"], "auto")
            self.assertTrue(result.artifacts["sandbox_fallback_used"])
            self.assertIn("fallback to rlimit", result.artifacts["sandbox_selection_reason"])
