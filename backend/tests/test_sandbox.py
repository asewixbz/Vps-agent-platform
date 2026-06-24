from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sandbox import build_subprocess_sandbox
from app.settings import Settings


class SandboxTests(TestCase):
    @patch("app.sandbox.shutil.which", return_value="/usr/bin/bwrap")
    def test_auto_mode_prefers_bubblewrap_when_available(self, which_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                task_sandbox_mode="auto",
                task_sandbox_allow_network=False,
                default_timeout_seconds=5,
            )
            workdir = Path(tmpdir) / "work" / "task-1"
            workdir.mkdir(parents=True, exist_ok=True)

            sandbox = build_subprocess_sandbox(
                settings,
                workdir=workdir,
                argv=["echo", "hello"],
                timeout_seconds=5,
            )

            self.assertEqual(sandbox.requested_mode, "auto")
            self.assertEqual(sandbox.backend, "bubblewrap")
            self.assertEqual(sandbox.cwd, "/work")
            self.assertIsNone(sandbox.preexec_fn)
            self.assertEqual(sandbox.env["HOME"], "/work")
            self.assertEqual(sandbox.env["TMPDIR"], "/work/tmp")
            self.assertEqual(sandbox.file_policy, "workdir-bind-only")
            self.assertEqual(sandbox.network_policy, "unshared")
            self.assertFalse(sandbox.fallback_used)
            self.assertIn("bubblewrap", sandbox.selection_reason)
            self.assertEqual(sandbox.argv[0], "bwrap")
            self.assertIn("--unshare-all", sandbox.argv)
            self.assertIn("--bind", sandbox.argv)
            self.assertIn("/work", sandbox.argv)
            which_mock.assert_called_once_with("bwrap")

    @patch("app.sandbox.shutil.which", return_value=None)
    def test_auto_mode_falls_back_to_rlimit_when_bubblewrap_is_missing(self, which_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                task_sandbox_mode="auto",
                task_sandbox_allow_network=False,
                default_timeout_seconds=5,
            )
            workdir = Path(tmpdir) / "work" / "task-2"
            workdir.mkdir(parents=True, exist_ok=True)

            with patch("app.sandbox.logger.warning") as warning_mock:
                sandbox = build_subprocess_sandbox(
                    settings,
                    workdir=workdir,
                    argv=["echo", "hello"],
                    timeout_seconds=5,
                )

            self.assertEqual(sandbox.requested_mode, "auto")
            self.assertEqual(sandbox.backend, "rlimit")
            self.assertEqual(sandbox.cwd, str(workdir))
            self.assertIsNotNone(sandbox.preexec_fn)
            self.assertEqual(sandbox.env["HOME"], str(workdir))
            self.assertEqual(sandbox.env["TMPDIR"], str(workdir / "tmp"))
            self.assertEqual(sandbox.file_policy, "cwd-and-rlimit")
            self.assertEqual(sandbox.network_policy, "not-enforced")
            self.assertTrue(sandbox.fallback_used)
            self.assertIn("falling back to rlimit", sandbox.selection_reason)
            self.assertEqual(sandbox.argv, ["echo", "hello"])
            warning_mock.assert_called_once()
            which_mock.assert_called_once_with("bwrap")
