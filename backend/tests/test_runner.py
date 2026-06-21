from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_python_script
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
