from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_browser_task, run_python_script, run_shell_command
from app.settings import Settings


class RunnerArtifactManifestTests(TestCase):
    def test_python_runner_materializes_schedule_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
            )

            result = run_python_script(
                settings,
                task_id="task-123",
                script=(
                    "from pathlib import Path\n"
                    'Path("schedule.json").write_text("{}", encoding="utf-8")\n'
                    'Path("schedule.md").write_text("# schedule\n", encoding="utf-8")\n'
                    'print("done")\n'
                ),
                timeout_seconds=5,
            )

            workdir = Path(result.artifacts["workdir"])
            manifest_path = workdir / "schedule_manifest.json"
            artifacts_path = workdir / "artifacts.json"

            self.assertTrue(result.ok)
            self.assertIn("workdir", result.artifacts)
            self.assertIn("script_path", result.artifacts)
            self.assertIn("schedule_manifest_path", result.artifacts)
            self.assertIn("schedule_json_path", result.artifacts)
            self.assertIn("schedule_md_path", result.artifacts)
            self.assertEqual(result.artifacts["sandbox_mode"], "auto")
            self.assertIn("sandbox_selection_reason", result.artifacts)
            self.assertTrue(str(result.artifacts["schedule_manifest_path"]).endswith("schedule_manifest.json"))
            self.assertTrue(manifest_path.exists())
            self.assertTrue(artifacts_path.exists())

    def test_python_runner_materializes_workflow_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
            )

            result = run_python_script(
                settings,
                task_id="task-456",
                script=(
                    "from pathlib import Path\n"
                    'Path("report.json").write_text("{}", encoding="utf-8")\n'
                    'Path("report.md").write_text("# report\n", encoding="utf-8")\n'
                    'print("done")\n'
                ),
                timeout_seconds=5,
            )

            workdir = Path(result.artifacts["workdir"])
            artifacts_path = workdir / "artifacts.json"

            self.assertTrue(result.ok)
            self.assertIn("report_path", result.artifacts)
            self.assertIn("report_md_path", result.artifacts)
            self.assertIn("artifact_paths", result.artifacts)
            self.assertEqual(result.artifacts["report_path"], str(workdir / "report.json"))
            self.assertEqual(result.artifacts["report_md_path"], str(workdir / "report.md"))
            self.assertIn(str(workdir / "report.json"), result.artifacts["artifact_paths"])
            self.assertIn(str(workdir / "report.md"), result.artifacts["artifact_paths"])
            self.assertTrue(artifacts_path.exists())

    @patch("app.runner.subprocess.run")
    def test_python_runner_uses_isolated_interpreter_and_task_workdir(self, run_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                task_sandbox_mode="rlimit",
            )
            run_mock.return_value = CompletedProcess(
                args=[sys.executable, "-I", "-s", "-B", "main.py"],
                returncode=0,
                stdout="done\n",
                stderr="",
            )

            result = run_python_script(
                settings,
                task_id="task-789",
                script='print("done")\n',
                timeout_seconds=5,
            )

            call = run_mock.call_args
            self.assertIsNotNone(call)
            self.assertEqual(call.args[0][0], sys.executable)
            self.assertIn("-I", call.args[0])
            self.assertIn("-s", call.args[0])
            self.assertIn("-B", call.args[0])
            self.assertEqual(call.kwargs["cwd"], str(Path(tmpdir) / "work" / "task-789"))
            self.assertEqual(call.kwargs["env"]["HOME"], str(Path(tmpdir) / "work" / "task-789"))
            self.assertEqual(call.kwargs["env"]["TMPDIR"], str(Path(tmpdir) / "work" / "task-789" / "tmp"))
            self.assertIsNotNone(call.kwargs["preexec_fn"])
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(call.kwargs["close_fds"])
            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["sandbox_backend"], "rlimit")
            self.assertEqual(result.artifacts["sandbox_mode"], "rlimit")
            self.assertEqual(result.artifacts["sandbox_file_policy"], "cwd-and-rlimit")

    @patch("app.runner.subprocess.run")
    def test_shell_runner_executes_parsed_command_without_bash(self, run_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                task_sandbox_mode="rlimit",
            )
            run_mock.return_value = CompletedProcess(
                args=["echo", "hello world"],
                returncode=0,
                stdout="hello world\n",
                stderr="",
            )

            result = run_shell_command(
                settings,
                task_id="task-999",
                command='echo "hello world"',
                timeout_seconds=5,
            )

            call = run_mock.call_args
            self.assertIsNotNone(call)
            self.assertEqual(call.args[0], ["echo", "hello world"])
            self.assertNotEqual(call.args[0][0], "bash")
            self.assertEqual(call.kwargs["cwd"], str(Path(tmpdir) / "work" / "task-999"))
            self.assertEqual(call.kwargs["env"]["HOME"], str(Path(tmpdir) / "work" / "task-999"))
            self.assertEqual(call.kwargs["env"]["TMPDIR"], str(Path(tmpdir) / "work" / "task-999" / "tmp"))
            self.assertIsNotNone(call.kwargs["preexec_fn"])
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(call.kwargs["close_fds"])
            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["sandbox_backend"], "rlimit")
            self.assertEqual(result.artifacts["sandbox_mode"], "rlimit")
            self.assertEqual(result.artifacts["command_argv"], ["echo", "hello world"])

    def test_browser_runner_is_disabled_by_default(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                browser_runner_enabled=False,
            )

            result = run_browser_task(
                settings,
                task_id="task-browser",
                url="https://example.com",
                timeout_seconds=5,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.exit_code, 126)
            self.assertIn("browser runner is not enabled", result.stderr)
            self.assertEqual(result.artifacts["browser_runner_enabled"], False)

    def test_browser_runner_rejects_unsupported_url_scheme(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(
                work_dir=str(Path(tmpdir) / "work"),
                default_timeout_seconds=5,
                browser_runner_enabled=True,
            )

            result = run_browser_task(
                settings,
                task_id="task-browser-scheme",
                url="file:///tmp/index.html",
                timeout_seconds=5,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.exit_code, 2)
            self.assertIn("browser url scheme 'file' is not supported", result.stderr)
            self.assertEqual(result.artifacts["browser_url"], "file:///tmp/index.html")
