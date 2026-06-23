from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_python_script, run_shell_command
from app.settings import Settings


class RunnerManifestContractTests(TestCase):
    def test_python_runner_writes_canonical_schedule_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(work_dir=str(Path(tmpdir) / "work"), default_timeout_seconds=5)

            result = run_python_script(
                settings,
                task_id="task-schedule",
                script=(
                    "from pathlib import Path\n"
                    'Path("schedule.json").write_text("{}", encoding="utf-8")\n'
                    'Path("schedule.md").write_text("# schedule\n", encoding="utf-8")\n'
                    'print("done")\n'
                ),
                timeout_seconds=5,
            )

            workdir = Path(result.artifacts["workdir"])
            artifacts_manifest = json.loads((workdir / "artifacts.json").read_text(encoding="utf-8"))
            schedule_manifest = json.loads((workdir / "schedule_manifest.json").read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["artifact_manifest_path"], str(workdir / "artifacts.json"))
            self.assertEqual(result.artifacts["schedule_manifest_path"], str(workdir / "schedule_manifest.json"))
            self.assertEqual(artifacts_manifest["schema_version"], 1)
            self.assertEqual(artifacts_manifest["scope_type"], "task")
            self.assertEqual(artifacts_manifest["scope_id"], "task-schedule")
            self.assertEqual(artifacts_manifest["source"], "schedule_runner")
            self.assertEqual(schedule_manifest["schema_version"], 1)
            self.assertEqual(schedule_manifest["scope_type"], "task")
            self.assertEqual(schedule_manifest["scope_id"], "task-schedule")
            self.assertEqual(schedule_manifest["source"], "schedule_runner")
            self.assertIn(str(workdir / "main.py"), artifacts_manifest["artifact_paths"])
            self.assertIn(str(workdir / "schedule.json"), artifacts_manifest["artifact_paths"])
            self.assertIn(str(workdir / "schedule.md"), artifacts_manifest["artifact_paths"])
            self.assertTrue(any(artifact["artifact_ref"] == str(workdir / "schedule.json") for artifact in artifacts_manifest["artifacts"]))
            self.assertTrue(any(artifact["artifact_ref"] == str(workdir / "schedule.md") for artifact in artifacts_manifest["artifacts"]))

    def test_python_runner_writes_canonical_workflow_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(work_dir=str(Path(tmpdir) / "work"), default_timeout_seconds=5)

            result = run_python_script(
                settings,
                task_id="task-report",
                script=(
                    "from pathlib import Path\n"
                    'Path("report.json").write_text("{}", encoding="utf-8")\n'
                    'Path("report.md").write_text("# report\n", encoding="utf-8")\n'
                    'print("done")\n'
                ),
                timeout_seconds=5,
            )

            workdir = Path(result.artifacts["workdir"])
            artifacts_manifest = json.loads((workdir / "artifacts.json").read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["artifact_manifest_path"], str(workdir / "artifacts.json"))
            self.assertEqual(artifacts_manifest["schema_version"], 1)
            self.assertEqual(artifacts_manifest["scope_type"], "task")
            self.assertEqual(artifacts_manifest["scope_id"], "task-report")
            self.assertEqual(artifacts_manifest["source"], "workflow_runner")
            self.assertIn(str(workdir / "main.py"), artifacts_manifest["artifact_paths"])
            self.assertIn(str(workdir / "report.json"), artifacts_manifest["artifact_paths"])
            self.assertIn(str(workdir / "report.md"), artifacts_manifest["artifact_paths"])
            self.assertTrue(any(artifact["artifact_ref"] == str(workdir / "report.json") for artifact in artifacts_manifest["artifacts"]))
            self.assertTrue(any(artifact["artifact_ref"] == str(workdir / "report.md") for artifact in artifacts_manifest["artifacts"]))

    @patch("app.runner.subprocess.run")
    def test_shell_runner_writes_canonical_manifest_for_output_files(self, run_mock) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings(work_dir=str(Path(tmpdir) / "work"), default_timeout_seconds=5, task_sandbox_mode="rlimit")

            def _side_effect(*args, **kwargs):
                Path(kwargs["cwd"]).joinpath("output.txt").write_text("hello\n", encoding="utf-8")
                return CompletedProcess(args=["echo", "hello world"], returncode=0, stdout="hello world\n", stderr="")

            run_mock.side_effect = _side_effect

            result = run_shell_command(settings, task_id="task-shell", command='echo "hello world"', timeout_seconds=5)

            workdir = Path(tmpdir) / "work" / "task-shell"
            artifacts_manifest = json.loads((workdir / "artifacts.json").read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(result.artifacts["artifact_manifest_path"], str(workdir / "artifacts.json"))
            self.assertEqual(artifacts_manifest["schema_version"], 1)
            self.assertEqual(artifacts_manifest["scope_type"], "task")
            self.assertEqual(artifacts_manifest["scope_id"], "task-shell")
            self.assertEqual(artifacts_manifest["source"], "shell_runner")
            self.assertIn(str(workdir / "output.txt"), artifacts_manifest["artifact_paths"])
            self.assertTrue(any(artifact["artifact_ref"] == str(workdir / "output.txt") for artifact in artifacts_manifest["artifacts"]))
