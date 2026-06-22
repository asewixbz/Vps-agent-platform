from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.artifact_lifecycle import (
    artifact_manifest_issues,
    build_artifact_manifest,
    cleanup_artifact_roots,
    normalize_artifact_manifest,
    write_artifact_manifest,
)
from app.settings import Settings


class ArtifactLifecycleTests(TestCase):
    def test_build_and_normalize_artifact_manifest(self) -> None:
        manifest = build_artifact_manifest(
            scope_type="task",
            scope_id="task-1",
            artifacts=[
                {"artifact_type": "file", "artifact_ref": "/tmp/report.json", "label": "report"},
                {"artifact_type": "file", "artifact_ref": "/tmp/report.json", "label": "report"},
                {"artifact_type": "markdown", "artifact_ref": "/tmp/report.md", "label": "report-md"},
            ],
            runtime_run_id="run-1",
            task_id="task-1",
            source="test",
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["scope_type"], "task")
        self.assertEqual(manifest["scope_id"], "task-1")
        self.assertEqual(manifest["artifact_paths"], ["/tmp/report.json", "/tmp/report.md"])
        self.assertEqual(len(manifest["artifacts"]), 3)

        normalized = normalize_artifact_manifest(
            {
                "report_path": "/tmp/report.json",
                "report_md_path": "/tmp/report.md",
                "artifact_paths": ["/tmp/report.json", "/tmp/report.md"],
                "scope_type": "task",
                "scope_id": "task-1",
            },
            source="legacy",
        )

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["artifact_paths"], ["/tmp/report.json", "/tmp/report.md"])
        self.assertGreaterEqual(len(normalized["artifacts"]), 2)
        self.assertEqual(artifact_manifest_issues(normalized), [])

    def test_cleanup_artifact_roots_deletes_expired_workdirs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir) / "work"
            artifact_dir = Path(tmpdir) / "artifacts"
            work_dir.mkdir()
            artifact_dir.mkdir()

            expired_dir = work_dir / "task-1"
            expired_dir.mkdir()
            write_artifact_manifest(
                expired_dir / "artifacts.json",
                {
                    "schema_version": 1,
                    "scope_type": "task",
                    "scope_id": "task-1",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                    "retention_class": "transient",
                    "artifacts": [
                        {"artifact_type": "file", "artifact_ref": str(expired_dir / "stdout.txt"), "label": "stdout"}
                    ],
                    "artifact_paths": [str(expired_dir / "stdout.txt")],
                },
            )
            (expired_dir / "stdout.txt").write_text("hello\n", encoding="utf-8")

            settings = Settings(
                db_path=str(Path(tmpdir) / "app.db"),
                work_dir=str(work_dir),
                artifact_dir=str(artifact_dir),
            )

            summary = cleanup_artifact_roots(settings, now=Path("2026-01-01").resolve().stat() if False else None)  # type: ignore[arg-type]

            self.assertGreaterEqual(summary["scanned"], 1)
            self.assertEqual(summary["deleted"], 1)
            self.assertFalse(expired_dir.exists())
